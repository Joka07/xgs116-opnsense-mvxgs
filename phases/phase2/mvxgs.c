/*-
 * SPDX-License-Identifier: BSD-2-Clause
 *
 * Experimental FreeBSD/OPNsense diagnostic driver for the Marvell PCIe
 * endpoint used by Sophos XGS Gen.1 appliances (observed: XGS 116 11ab:7080).
 *
 * Phase 2 goal:
 *   - bind the PF
 *   - map BAR0/BAR2/BAR4
 *   - passively decode the vendor BAR-map/facility table
 *   - passively inspect the known control cookie/flags
 *   - expose the decoded state through sysctl
 *
 * SAFETY BOUNDARY:
 *   This revision DOES NOT perform MMIO writes, enable SR-IOV, enable bus
 *   mastering, allocate DMA memory, allocate interrupts, ring doorbells,
 *   reset the NPU, or create an Ethernet interface.
 */

#include <sys/param.h>
#include <sys/systm.h>
#include <sys/bus.h>
#include <sys/kernel.h>
#include <sys/module.h>
#include <sys/rman.h>
#include <sys/sysctl.h>
#include <sys/types.h>

#include <machine/bus.h>
#include <machine/resource.h>

#include <dev/pci/pcireg.h>
#include <dev/pci/pcivar.h>

#include "mvxgs_hw.h"

struct mvxgs_bar {
        int                     rid;
        int                     barno;
        struct resource         *res;
        bus_space_tag_t         tag;
        bus_space_handle_t      handle;
        rman_res_t              start;
        rman_res_t              size;
};

struct mvxgs_fac_state {
        uint32_t                present;
        uint32_t                bar;
        uint32_t                offset;
        uint32_t                size;
};

struct mvxgs_softc {
        device_t                dev;
        struct mvxgs_bar        bars[MVXGS_NBARS];
        int                     msix_count;
        int                     msi_count;

        uint32_t                barmap_version;
        uint32_t                target_cookie;
        uint32_t                ctrl_cookie;
        uint32_t                ctrl_flags;
        uint32_t                barmap_valid;
        uint32_t                ctrl_valid;
        struct mvxgs_fac_state  fac[MVXGS_FACILITY_COUNT];
        char                    status[128];
};

static int mvxgs_probe(device_t dev);
static int mvxgs_attach(device_t dev);
static int mvxgs_detach(device_t dev);
static int mvxgs_shutdown(device_t dev);
static int mvxgs_suspend(device_t dev);
static int mvxgs_resume(device_t dev);
static int mvxgs_scan(struct mvxgs_softc *sc, bool noisy);
static int mvxgs_sysctl_rescan(SYSCTL_HANDLER_ARGS);

static const char *const mvxgs_fac_names[MVXGS_FACILITY_COUNT] = {
        "ctrl", "mvmgmt", "nwa", "rpc", "giu"
};

static struct mvxgs_bar *
mvxgs_bar_by_no(struct mvxgs_softc *sc, uint32_t barno)
{
        int i;

        for (i = 0; i < MVXGS_NBARS; i++) {
                if (sc->bars[i].res != NULL &&
                    sc->bars[i].barno == (int)barno)
                        return (&sc->bars[i]);
        }
        return (NULL);
}

static int
mvxgs_alloc_bar(struct mvxgs_softc *sc, int slot, int barno)
{
        struct mvxgs_bar *bar;

        bar = &sc->bars[slot];
        bar->barno = barno;
        bar->rid = PCIR_BAR(barno);
        bar->res = bus_alloc_resource_any(sc->dev, SYS_RES_MEMORY,
            &bar->rid, RF_ACTIVE);
        if (bar->res == NULL) {
                device_printf(sc->dev,
                    "unable to map BAR%d (rid 0x%x)\n", barno, bar->rid);
                return (ENXIO);
        }

        bar->tag = rman_get_bustag(bar->res);
        bar->handle = rman_get_bushandle(bar->res);
        bar->start = rman_get_start(bar->res);
        bar->size = rman_get_size(bar->res);

        device_printf(sc->dev,
            "BAR%d: start=%#jx size=%#jx (%ju bytes)\n",
            barno, (uintmax_t)bar->start, (uintmax_t)bar->size,
            (uintmax_t)bar->size);
        return (0);
}

static void
mvxgs_free_bars(struct mvxgs_softc *sc)
{
        int i;

        for (i = 0; i < MVXGS_NBARS; i++) {
                if (sc->bars[i].res != NULL) {
                        bus_release_resource(sc->dev, SYS_RES_MEMORY,
                            sc->bars[i].rid, sc->bars[i].res);
                        sc->bars[i].res = NULL;
                }
        }
}

static int
mvxgs_read32(struct mvxgs_bar *bar, rman_res_t off, uint32_t *value)
{
        if (bar == NULL || value == NULL)
                return (EINVAL);
        if (off > bar->size || bar->size - off < sizeof(uint32_t))
                return (ERANGE);

        bus_space_barrier(bar->tag, bar->handle, (bus_size_t)off,
            sizeof(uint32_t), BUS_SPACE_BARRIER_READ);
        *value = bus_space_read_4(bar->tag, bar->handle, (bus_size_t)off);
        return (0);
}

/*
 * Translate the target BAR-map logical window index as Sophos' armada_pci
 * driver does on the XGS 116 sample:
 *   logical 0 -> PF BAR0, base 0, size 0x14000
 *   logical 1 -> PF BAR2, base (BAR2 size - 0x104000), size 0x103000
 *   logical 2 -> PF BAR4, base 0, full BAR
 *
 * Note the deliberate 4 KiB gap at the end of PF BAR2.  The target BAR map
 * is at PF BAR2 end-0x2000 and a separate BOOTCMD page is at end-0x1000.
 */
static int
mvxgs_facility_host_offset(struct mvxgs_softc *sc, uint32_t logical_bar,
    uint32_t target_off, uint32_t length, struct mvxgs_bar **barp,
    rman_res_t *host_offp)
{
        struct mvxgs_bar *bar;
        rman_res_t win_base, win_size;
        int pci_bar;

        switch (logical_bar) {
        case 0:
                pci_bar = MVXGS_BAR0;
                break;
        case 1:
                pci_bar = MVXGS_BAR2;
                break;
        case 2:
                pci_bar = MVXGS_BAR4;
                break;
        default:
                return (EINVAL);
        }

        bar = mvxgs_bar_by_no(sc, (uint32_t)pci_bar);
        if (bar == NULL)
                return (ENOENT);

        switch (logical_bar) {
        case 0:
                win_base = 0;
                win_size = MIN(bar->size,
                    (rman_res_t)MVXGS_BAR0_WINDOW_SIZE);
                break;
        case 1:
                if (bar->size < MVXGS_BAR2_WINDOW_BASE_FROM_END)
                        return (ERANGE);
                win_base = bar->size - MVXGS_BAR2_WINDOW_BASE_FROM_END;
                win_size = MVXGS_BAR2_WINDOW_SIZE;
                break;
        case 2:
                win_base = 0;
                win_size = bar->size;
                break;
        default:
                return (EINVAL);
        }

        if ((rman_res_t)target_off > win_size ||
            (rman_res_t)length > win_size - (rman_res_t)target_off)
                return (ERANGE);

        *barp = bar;
        *host_offp = win_base + (rman_res_t)target_off;
        return (0);
}

static void
mvxgs_reset_scan_state(struct mvxgs_softc *sc)
{
        int i;

        sc->barmap_version = 0;
        sc->target_cookie = 0;
        sc->ctrl_cookie = 0;
        sc->ctrl_flags = 0;
        sc->barmap_valid = 0;
        sc->ctrl_valid = 0;
        for (i = 0; i < MVXGS_FACILITY_COUNT; i++) {
                sc->fac[i].present = 0;
                sc->fac[i].bar = 0;
                sc->fac[i].offset = 0;
                sc->fac[i].size = 0;
        }
}

static int
mvxgs_scan(struct mvxgs_softc *sc, bool noisy)
{
        struct mvxgs_bar *bar2, *fbar;
        rman_res_t bmoff, foff;
        uint32_t barno, id, off, size, v;
        int error, i;

        mvxgs_reset_scan_state(sc);
        strlcpy(sc->status, "not scanned", sizeof(sc->status));

        bar2 = mvxgs_bar_by_no(sc, MVXGS_BAR2);
        if (bar2 == NULL) {
                strlcpy(sc->status, "BAR2 unavailable", sizeof(sc->status));
                return (ENXIO);
        }
        if (bar2->size < MVXGS_BARMAP_FROM_BAR_END) {
                strlcpy(sc->status, "BAR2 too small", sizeof(sc->status));
                return (ERANGE);
        }

        /* Linux BAR2-window + 0x102000 == full PF BAR2 end - 0x2000. */
        bmoff = bar2->size - MVXGS_BARMAP_FROM_BAR_END;

        error = mvxgs_read32(bar2, bmoff + 0x00, &sc->barmap_version);
        if (error != 0)
                goto read_fail;
        error = mvxgs_read32(bar2, bmoff + 0x04, &sc->target_cookie);
        if (error != 0)
                goto read_fail;

        if (noisy) {
                device_printf(sc->dev,
                    "passive barmap scan: off=%#jx version=%#x target_cookie=%#x\n",
                    (uintmax_t)bmoff, sc->barmap_version,
                    sc->target_cookie);
        }

        if (sc->barmap_version != MVXGS_BARMAP_VERSION) {
                snprintf(sc->status, sizeof(sc->status),
                    "unexpected barmap version %#x (expected %#x)",
                    sc->barmap_version, MVXGS_BARMAP_VERSION);
                return (EPROTO);
        }
        if (sc->target_cookie != MVXGS_TARGET_COOKIE) {
                snprintf(sc->status, sizeof(sc->status),
                    "target cookie not ready: %#x", sc->target_cookie);
                return (EAGAIN);
        }

        sc->barmap_valid = 1;

        /* Header is 8 bytes; each target facility entry is 16 bytes. */
        for (i = 0; i < MVXGS_FACILITY_COUNT; i++) {
                rman_res_t eoff = bmoff + 0x08 + (rman_res_t)i * 0x10;

                error = mvxgs_read32(bar2, eoff + 0x00, &barno);
                if (error != 0)
                        goto read_fail;
                error = mvxgs_read32(bar2, eoff + 0x04, &id);
                if (error != 0)
                        goto read_fail;
                error = mvxgs_read32(bar2, eoff + 0x08, &off);
                if (error != 0)
                        goto read_fail;
                error = mvxgs_read32(bar2, eoff + 0x0c, &size);
                if (error != 0)
                        goto read_fail;

                if (id >= MVXGS_FACILITY_COUNT) {
                        if (noisy)
                                device_printf(sc->dev,
                                    "facility slot %d has unknown id=%u bar=%u off=%#x size=%#x\n",
                                    i, id, barno, off, size);
                        continue;
                }

                sc->fac[id].present = 1;
                sc->fac[id].bar = barno;
                sc->fac[id].offset = off;
                sc->fac[id].size = size;

                if (noisy)
                        device_printf(sc->dev,
                            "facility[%u] %-6s: BAR%u logical_off=%#x size=%#x\n",
                            id, mvxgs_fac_names[id], barno, off, size);
        }

        if (!sc->fac[MVXGS_FAC_CTRL].present) {
                strlcpy(sc->status, "barmap valid; ctrl facility missing",
                    sizeof(sc->status));
                return (ENOENT);
        }

        error = mvxgs_facility_host_offset(sc,
            sc->fac[MVXGS_FAC_CTRL].bar,
            sc->fac[MVXGS_FAC_CTRL].offset,
            MAX(sc->fac[MVXGS_FAC_CTRL].size, 8u), &fbar, &foff);
        if (error != 0) {
                strlcpy(sc->status, "ctrl facility mapping invalid",
                    sizeof(sc->status));
                return (error);
        }

        error = mvxgs_read32(fbar, foff + 0x00, &sc->ctrl_cookie);
        if (error != 0)
                goto read_fail;
        error = mvxgs_read32(fbar, foff + 0x04, &sc->ctrl_flags);
        if (error != 0)
                goto read_fail;

        if (sc->ctrl_cookie == MVXGS_CTRL_COOKIE)
                sc->ctrl_valid = 1;

        if (noisy) {
                device_printf(sc->dev,
                    "ctrl: cookie=%#x flags=%#x target_ready=%u host_ready=%u host_alive=%u\n",
                    sc->ctrl_cookie, sc->ctrl_flags,
                    !!(sc->ctrl_flags & MVXGS_CTRL_F_TARGET_READY),
                    !!(sc->ctrl_flags & MVXGS_CTRL_F_HOST_READY),
                    !!(sc->ctrl_flags & MVXGS_CTRL_F_HOST_ALIVE));
        }

        if (!sc->ctrl_valid) {
                snprintf(sc->status, sizeof(sc->status),
                    "barmap valid; unexpected ctrl cookie %#x",
                    sc->ctrl_cookie);
                return (EPROTO);
        }
        if ((sc->ctrl_flags & MVXGS_CTRL_F_TARGET_READY) == 0) {
                strlcpy(sc->status,
                    "barmap+ctrl valid; NPU target-ready bit is clear",
                    sizeof(sc->status));
                return (EAGAIN);
        }

        strlcpy(sc->status,
            "PASS: target barmap and ctrl handshake state are visible",
            sizeof(sc->status));
        return (0);

read_fail:
        v = error;
        snprintf(sc->status, sizeof(sc->status),
            "MMIO read failed: errno %u", v);
        return (error);
}

static void
mvxgs_add_sysctls(struct mvxgs_softc *sc)
{
        struct sysctl_ctx_list *ctx;
        struct sysctl_oid *tree, *facroot, *node;
        int i;

        ctx = device_get_sysctl_ctx(sc->dev);
        tree = device_get_sysctl_tree(sc->dev);

        SYSCTL_ADD_STRING(ctx, SYSCTL_CHILDREN(tree), OID_AUTO, "status",
            CTLFLAG_RD, sc->status, sizeof(sc->status),
            "Passive NPU handshake diagnostic status");
        SYSCTL_ADD_U32(ctx, SYSCTL_CHILDREN(tree), OID_AUTO, "barmap_valid",
            CTLFLAG_RD, &sc->barmap_valid, 0, "Vendor BAR map validated");
        SYSCTL_ADD_U32(ctx, SYSCTL_CHILDREN(tree), OID_AUTO, "barmap_version",
            CTLFLAG_RD, &sc->barmap_version, 0, "Target BAR map version");
        SYSCTL_ADD_U32(ctx, SYSCTL_CHILDREN(tree), OID_AUTO, "target_cookie",
            CTLFLAG_RD, &sc->target_cookie, 0, "Target BAR map cookie");
        SYSCTL_ADD_U32(ctx, SYSCTL_CHILDREN(tree), OID_AUTO, "ctrl_valid",
            CTLFLAG_RD, &sc->ctrl_valid, 0, "Control facility cookie validated");
        SYSCTL_ADD_U32(ctx, SYSCTL_CHILDREN(tree), OID_AUTO, "ctrl_cookie",
            CTLFLAG_RD, &sc->ctrl_cookie, 0, "Control facility cookie");
        SYSCTL_ADD_U32(ctx, SYSCTL_CHILDREN(tree), OID_AUTO, "ctrl_flags",
            CTLFLAG_RD, &sc->ctrl_flags, 0, "Control facility flags");
        SYSCTL_ADD_PROC(ctx, SYSCTL_CHILDREN(tree), OID_AUTO, "rescan",
            CTLTYPE_INT | CTLFLAG_RW | CTLFLAG_MPSAFE, sc, 0,
            mvxgs_sysctl_rescan, "I",
            "Write non-zero to repeat the passive MMIO scan");

        facroot = SYSCTL_ADD_NODE(ctx, SYSCTL_CHILDREN(tree), OID_AUTO,
            "facility", CTLFLAG_RD | CTLFLAG_MPSAFE, NULL,
            "Decoded target facilities");
        if (facroot == NULL)
                return;

        for (i = 0; i < MVXGS_FACILITY_COUNT; i++) {
                node = SYSCTL_ADD_NODE(ctx, SYSCTL_CHILDREN(facroot), OID_AUTO,
                    mvxgs_fac_names[i], CTLFLAG_RD | CTLFLAG_MPSAFE, NULL,
                    "Decoded facility mapping");
                if (node == NULL)
                        continue;
                SYSCTL_ADD_U32(ctx, SYSCTL_CHILDREN(node), OID_AUTO,
                    "present", CTLFLAG_RD, &sc->fac[i].present, 0, "Present");
                SYSCTL_ADD_U32(ctx, SYSCTL_CHILDREN(node), OID_AUTO,
                    "bar", CTLFLAG_RD, &sc->fac[i].bar, 0, "Logical BAR number");
                SYSCTL_ADD_U32(ctx, SYSCTL_CHILDREN(node), OID_AUTO,
                    "offset", CTLFLAG_RD, &sc->fac[i].offset, 0,
                    "Offset within Sophos logical BAR window");
                SYSCTL_ADD_U32(ctx, SYSCTL_CHILDREN(node), OID_AUTO,
                    "size", CTLFLAG_RD, &sc->fac[i].size, 0, "Facility size");
        }
}

static int
mvxgs_sysctl_rescan(SYSCTL_HANDLER_ARGS)
{
        struct mvxgs_softc *sc;
        int error, value;

        sc = arg1;
        value = 0;
        error = sysctl_handle_int(oidp, &value, 0, req);
        if (error != 0 || req->newptr == NULL)
                return (error);
        if (value != 0)
                (void)mvxgs_scan(sc, true);
        return (0);
}

static int
mvxgs_probe(device_t dev)
{
        if (pci_get_vendor(dev) != MVXGS_VENDOR_ID ||
            pci_get_device(dev) != MVXGS_DEVICE_ID_PF)
                return (ENXIO);

        device_set_desc(dev,
            "Marvell/Sophos XGS NPU PF diagnostic endpoint (experimental)");
        return (BUS_PROBE_DEFAULT);
}

static int
mvxgs_attach(device_t dev)
{
        struct mvxgs_softc *sc;
        int error;

        sc = device_get_softc(dev);
        sc->dev = dev;

        error = mvxgs_alloc_bar(sc, 0, MVXGS_BAR0);
        if (error != 0)
                goto fail;
        error = mvxgs_alloc_bar(sc, 1, MVXGS_BAR2);
        if (error != 0)
                goto fail;
        error = mvxgs_alloc_bar(sc, 2, MVXGS_BAR4);
        if (error != 0)
                goto fail;

        sc->msix_count = pci_msix_count(dev);
        sc->msi_count = pci_msi_count(dev);
        device_printf(dev,
            "PCI %04x:%04x; MSI-X=%d MSI=%d; phase2 passive mode\n",
            pci_get_vendor(dev), pci_get_device(dev),
            sc->msix_count, sc->msi_count);

        /* Create sysctls before scanning so even a failed scan is inspectable. */
        mvxgs_add_sysctls(sc);
        (void)mvxgs_scan(sc, true);

        device_printf(dev,
            "NO hardware writes: SR-IOV/DMA/interrupts/doorbells remain disabled\n");
        return (0);

fail:
        mvxgs_free_bars(sc);
        return (error);
}

static int
mvxgs_detach(device_t dev)
{
        struct mvxgs_softc *sc;

        sc = device_get_softc(dev);
        mvxgs_free_bars(sc);
        return (0);
}

static int mvxgs_shutdown(device_t dev) { (void)dev; return (0); }
static int mvxgs_suspend(device_t dev)  { (void)dev; return (0); }
static int mvxgs_resume(device_t dev)   { (void)dev; return (0); }

static device_method_t mvxgs_methods[] = {
        DEVMETHOD(device_probe,         mvxgs_probe),
        DEVMETHOD(device_attach,        mvxgs_attach),
        DEVMETHOD(device_detach,        mvxgs_detach),
        DEVMETHOD(device_shutdown,      mvxgs_shutdown),
        DEVMETHOD(device_suspend,       mvxgs_suspend),
        DEVMETHOD(device_resume,        mvxgs_resume),
        DEVMETHOD_END
};

static driver_t mvxgs_driver = {
        "mvxgs",
        mvxgs_methods,
        sizeof(struct mvxgs_softc)
};

DRIVER_MODULE(mvxgs, pci, mvxgs_driver, 0, 0);
MODULE_DEPEND(mvxgs, pci, 1, 1, 1);
MODULE_VERSION(mvxgs, 3);
