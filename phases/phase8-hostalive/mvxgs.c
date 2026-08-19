/*-
 * SPDX-License-Identifier: BSD-2-Clause
 *
 * Experimental FreeBSD/OPNsense diagnostic driver for the Marvell PCIe
 * endpoint used by Sophos XGS Gen.1 appliances (observed: XGS 116 11ab:7080).
 *
 * Phase 8 controlled HOST_READY + HOST_ALIVE experiment:
 *   - passive validation of BAR-map/CTRL/MVMGMT and PCI command state
 *   - explicitly enable PCI bus mastering before MSI-X/HOST_READY
 *   - allocate exactly five MSI-X vectors with inert counting handlers
 *   - require an explicit arm step, then set CTRL.HOST_READY exactly once
 *   - separately arm and send one CTRL.HOST_ALIVE pulse (0x08)
 *   - then poll for target H2T-ready (0x04) and capture descriptors
 *
 * SAFETY BOUNDARY:
 *   Attach remains read-only.  Phase 8 has one explicit PCI configuration
 *   action (pci_enable_busmaster()) before MSI-X setup.  There are exactly two
 *   gated NPU protocol state transitions: CTRL |= HOST_READY (0x02), then
 *   CTRL |= HOST_ALIVE (0x08).  This revision DOES NOT acknowledge MVMGMT,
 *   set HOST_ALIVE, enable SR-IOV, allocate DMA, ring doorbells, reset the NPU,
 *   or create an Ethernet interface.  Once HOST_READY is sent the module
 *   refuses detach; reboot is the supported reset path.
 */

#include <sys/param.h>
#include <machine/atomic.h>
#include <sys/systm.h>
#include <sys/bus.h>
#include <sys/kernel.h>
#include <sys/interrupt.h>
#include <sys/module.h>
#include <sys/rman.h>
#include <sys/sysctl.h>
#include <sys/sx.h>
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

struct mvxgs_softc;

struct mvxgs_irq_ctx {
        struct mvxgs_softc      *sc;
        int                     index;
        uint64_t                hits;
};

struct mvxgs_h2t_desc {
        uint64_t                target_offset;
        uint32_t                data;
        uint32_t                valid;
};

struct mvxgs_softc {
        device_t                dev;
        struct mvxgs_bar        bars[MVXGS_NBARS];
        int                     msix_count;
        int                     msi_count;
        int                     active_stage;
        int                     msix_allocated;
        int                     host_ready_sent;
        int                     host_ready_armed;
        int                     host_alive_sent;
        int                     host_alive_armed;
        int                     busmaster_enabled_by_driver;
        uint32_t                pci_command;
        uint32_t                pci_command_initial;
        struct resource         *irq[MVXGS_T2H_MSIX_COUNT];
        int                     irq_rid[MVXGS_T2H_MSIX_COUNT];
        void                    *irq_cookie[MVXGS_T2H_MSIX_COUNT];
        struct mvxgs_irq_ctx    irq_ctx[MVXGS_T2H_MSIX_COUNT];
        struct mvxgs_h2t_desc   h2t[MVXGS_H2T_DBELL_COUNT];
        struct sx               state_sx;

        uint32_t                barmap_version;
        uint32_t                target_cookie;
        uint32_t                ctrl_cookie;
        uint32_t                ctrl_flags;
        uint32_t                mvmgmt_word10;
        uint32_t                mvmgmt_word14;
        uint32_t                mvmgmt_pattern;
        uint32_t                mvmgmt_target_ready;
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
static int mvxgs_sysctl_enable_busmaster(SYSCTL_HANDLER_ARGS);
static int mvxgs_sysctl_prepare_msix(SYSCTL_HANDLER_ARGS);
static int mvxgs_sysctl_arm_host_ready(SYSCTL_HANDLER_ARGS);
static int mvxgs_sysctl_signal_host_ready(SYSCTL_HANDLER_ARGS);
static int mvxgs_sysctl_arm_host_alive(SYSCTL_HANDLER_ARGS);
static int mvxgs_sysctl_signal_host_alive(SYSCTL_HANDLER_ARGS);
static int mvxgs_enable_busmaster(struct mvxgs_softc *sc);
static int mvxgs_prepare_msix(struct mvxgs_softc *sc);
static void mvxgs_release_msix(struct mvxgs_softc *sc);
static int mvxgs_signal_host_ready(struct mvxgs_softc *sc);
static int mvxgs_signal_host_alive(struct mvxgs_softc *sc);
static void mvxgs_irq_handler(void *arg);

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

static int
mvxgs_read64(struct mvxgs_bar *bar, rman_res_t off, uint64_t *value)
{
        uint32_t lo, hi;
        int error;

        if (value == NULL)
                return (EINVAL);
        error = mvxgs_read32(bar, off, &lo);
        if (error != 0)
                return (error);
        error = mvxgs_read32(bar, off + 4, &hi);
        if (error != 0)
                return (error);
        *value = ((uint64_t)hi << 32) | lo;
        return (0);
}

static int
mvxgs_write32(struct mvxgs_bar *bar, rman_res_t off, uint32_t value)
{
        if (bar == NULL)
                return (EINVAL);
        if (off > bar->size || bar->size - off < sizeof(uint32_t))
                return (ERANGE);

        bus_space_write_4(bar->tag, bar->handle, (bus_size_t)off, value);
        bus_space_barrier(bar->tag, bar->handle, (bus_size_t)off,
            sizeof(uint32_t), BUS_SPACE_BARRIER_WRITE | BUS_SPACE_BARRIER_READ);
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
        sc->mvmgmt_word10 = 0;
        sc->mvmgmt_word14 = 0;
        sc->mvmgmt_pattern = 0;
        sc->mvmgmt_target_ready = 0;
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
        sc->pci_command = pci_read_config(sc->dev, PCIR_COMMAND, 2);

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

        /*
         * pcinet/mvmgmt target pattern.  The SFOS mv_pcinet_drv waits for
         * mvmgmt+0x18 == 0xaa55aa55 before replacing it with 0xbb66bb66.
         * This passive driver only reads it.
         */
        if (sc->fac[MVXGS_FAC_MVMGMT].present) {
                error = mvxgs_facility_host_offset(sc,
                    sc->fac[MVXGS_FAC_MVMGMT].bar,
                    sc->fac[MVXGS_FAC_MVMGMT].offset,
                    MAX(sc->fac[MVXGS_FAC_MVMGMT].size, 0x1cu),
                    &fbar, &foff);
                if (error == 0) {
                        (void)mvxgs_read32(fbar, foff + 0x10,
                            &sc->mvmgmt_word10);
                        (void)mvxgs_read32(fbar, foff + 0x14,
                            &sc->mvmgmt_word14);
                        (void)mvxgs_read32(fbar, foff + 0x18,
                            &sc->mvmgmt_pattern);
                        if (sc->mvmgmt_pattern ==
                            MVXGS_PCINET_TARGET_PATTERN)
                                sc->mvmgmt_target_ready = 1;
                        if (noisy)
                                device_printf(sc->dev,
                                    "mvmgmt: +0x10=%#x +0x14=%#x pattern=%#x target_pattern=%u\n",
                                    sc->mvmgmt_word10, sc->mvmgmt_word14,
                                    sc->mvmgmt_pattern,
                                    sc->mvmgmt_target_ready);
                }
        }

        if (sc->mvmgmt_target_ready)
                strlcpy(sc->status,
                    "PASS: barmap+ctrl+mvmgmt target handshakes visible",
                    sizeof(sc->status));
        else
                strlcpy(sc->status,
                    "PASS: barmap+ctrl visible; mvmgmt target pattern absent",
                    sizeof(sc->status));
        return (0);

read_fail:
        v = error;
        snprintf(sc->status, sizeof(sc->status),
            "MMIO read failed: errno %u", v);
        return (error);
}

static void
mvxgs_irq_handler(void *arg)
{
        struct mvxgs_irq_ctx *ctx;

        ctx = arg;
        atomic_add_64(&ctx->hits, 1);
        /* Intentionally no device access and no doorbell acknowledgement. */
}

static void
mvxgs_release_msix(struct mvxgs_softc *sc)
{
        int i;

        for (i = MVXGS_T2H_MSIX_COUNT - 1; i >= 0; i--) {
                if (sc->irq_cookie[i] != NULL && sc->irq[i] != NULL) {
                        bus_teardown_intr(sc->dev, sc->irq[i],
                            sc->irq_cookie[i]);
                        sc->irq_cookie[i] = NULL;
                }
                if (sc->irq[i] != NULL) {
                        bus_release_resource(sc->dev, SYS_RES_IRQ,
                            sc->irq_rid[i], sc->irq[i]);
                        sc->irq[i] = NULL;
                }
        }
        if (sc->msix_allocated != 0) {
                (void)pci_release_msi(sc->dev);
                sc->msix_allocated = 0;
        }
        if (!sc->host_ready_sent)
                sc->active_stage = 0;
}

static int
mvxgs_enable_busmaster(struct mvxgs_softc *sc)
{
        uint32_t before, after;
        int error;

        if (sc->active_stage != 0 || sc->msix_allocated != 0 ||
            sc->host_ready_sent)
                return (EBUSY);

        error = mvxgs_scan(sc, true);
        if (error != 0)
                return (error);

        if (!sc->barmap_valid || !sc->ctrl_valid ||
            sc->ctrl_flags != MVXGS_CTRL_F_TARGET_READY ||
            !sc->mvmgmt_target_ready) {
                strlcpy(sc->status,
                    "REFUSED: busmaster preconditions do not match XGS116 baseline",
                    sizeof(sc->status));
                return (EPROTO);
        }

        before = pci_read_config(sc->dev, PCIR_COMMAND, 2);
        sc->pci_command = before;

        if ((before & PCIM_CMD_BUSMASTEREN) != 0) {
                snprintf(sc->status, sizeof(sc->status),
                    "PCI busmaster already enabled; command=%#x", before);
                return (0);
        }

        error = pci_enable_busmaster(sc->dev);
        if (error != 0) {
                snprintf(sc->status, sizeof(sc->status),
                    "pci_enable_busmaster failed: errno %d", error);
                return (error);
        }

        after = pci_read_config(sc->dev, PCIR_COMMAND, 2);
        sc->pci_command = after;
        if ((after & PCIM_CMD_BUSMASTEREN) == 0) {
                strlcpy(sc->status,
                    "PCI busmaster enable did not read back",
                    sizeof(sc->status));
                return (EIO);
        }

        sc->busmaster_enabled_by_driver = 1;
        snprintf(sc->status, sizeof(sc->status),
            "PCI busmaster enabled: command %#x -> %#x; no NPU protocol write",
            before, after);
        device_printf(sc->dev,
            "PCI busmaster enabled: command %#x -> %#x\n", before, after);
        return (0);
}

static int
mvxgs_prepare_msix(struct mvxgs_softc *sc)
{
        int count, error, i;

        if (sc->active_stage != 0 || sc->msix_allocated != 0)
                return (EBUSY);

        if ((pci_read_config(sc->dev, PCIR_COMMAND, 2) &
            PCIM_CMD_BUSMASTEREN) == 0) {
                strlcpy(sc->status,
                    "REFUSED: enable PCI busmaster before MSI-X",
                    sizeof(sc->status));
                return (EPERM);
        }

        error = mvxgs_scan(sc, true);
        if (error != 0)
                return (error);

        /* Phase-5 hard gate: require the exact pre-host state we observed. */
        if (!sc->barmap_valid || !sc->ctrl_valid ||
            sc->ctrl_flags != MVXGS_CTRL_F_TARGET_READY ||
            !sc->mvmgmt_target_ready) {
                strlcpy(sc->status,
                    "REFUSED: pre-host handshake does not match XGS116 baseline",
                    sizeof(sc->status));
                return (EPROTO);
        }
        if (sc->msix_count < MVXGS_T2H_MSIX_COUNT) {
                snprintf(sc->status, sizeof(sc->status),
                    "REFUSED: only %d MSI-X vectors available; need %d",
                    sc->msix_count, MVXGS_T2H_MSIX_COUNT);
                return (ENOSPC);
        }

        /* BAR0 contains the endpoint MSI-X table/PBA and is already mapped. */
        if (mvxgs_bar_by_no(sc, MVXGS_BAR0) == NULL)
                return (ENXIO);

        count = MVXGS_T2H_MSIX_COUNT;
        error = pci_alloc_msix(sc->dev, &count);
        if (error != 0) {
                snprintf(sc->status, sizeof(sc->status),
                    "MSI-X allocation failed: errno %d", error);
                return (error);
        }
        sc->msix_allocated = count;
        if (count != MVXGS_T2H_MSIX_COUNT) {
                snprintf(sc->status, sizeof(sc->status),
                    "MSI-X partial allocation: got %d need %d", count,
                    MVXGS_T2H_MSIX_COUNT);
                mvxgs_release_msix(sc);
                return (ENOSPC);
        }

        for (i = 0; i < MVXGS_T2H_MSIX_COUNT; i++) {
                sc->irq_ctx[i].sc = sc;
                sc->irq_ctx[i].index = i;
                sc->irq_ctx[i].hits = 0;
                sc->irq_rid[i] = i + 1;
                sc->irq[i] = bus_alloc_resource_any(sc->dev, SYS_RES_IRQ,
                    &sc->irq_rid[i], RF_ACTIVE);
                if (sc->irq[i] == NULL) {
                        error = ENXIO;
                        device_printf(sc->dev,
                            "unable to allocate MSI-X IRQ resource %d\n", i);
                        goto fail;
                }
                error = bus_setup_intr(sc->dev, sc->irq[i],
                    INTR_TYPE_NET | INTR_MPSAFE, NULL, mvxgs_irq_handler,
                    &sc->irq_ctx[i], &sc->irq_cookie[i]);
                if (error != 0) {
                        device_printf(sc->dev,
                            "unable to install MSI-X handler %d: %d\n",
                            i, error);
                        goto fail;
                }
                device_printf(sc->dev,
                    "MSI-X[%d] ready: rid=%d irq=%#jx\n", i,
                    sc->irq_rid[i], (uintmax_t)rman_get_start(sc->irq[i]));
        }

        sc->active_stage = 1;
        sc->host_ready_armed = 0;
        strlcpy(sc->status,
            "STAGE1: five MSI-X vectors+inert handlers ready; HOST_READY not armed",
            sizeof(sc->status));
        return (0);

fail:
        mvxgs_release_msix(sc);
        strlcpy(sc->status,
            "MSI-X preparation failed; resources rolled back",
            sizeof(sc->status));
        return (error);
}

static int
mvxgs_signal_host_ready(struct mvxgs_softc *sc)
{
        struct mvxgs_bar *fbar;
        rman_res_t foff;
        uint32_t flags, readback;
        int error, i;

        if (sc->active_stage != 1 ||
            sc->msix_allocated != MVXGS_T2H_MSIX_COUNT ||
            sc->host_ready_armed != 1 ||
            (pci_read_config(sc->dev, PCIR_COMMAND, 2) &
            PCIM_CMD_BUSMASTEREN) == 0)
                return (EPERM);

        for (i = 0; i < MVXGS_T2H_MSIX_COUNT; i++) {
                if (sc->irq[i] == NULL || sc->irq_cookie[i] == NULL)
                        return (ENXIO);
        }

        error = mvxgs_scan(sc, true);
        if (error != 0)
                return (error);
        if (sc->ctrl_flags != MVXGS_CTRL_F_TARGET_READY ||
            !sc->mvmgmt_target_ready) {
                strlcpy(sc->status,
                    "REFUSED: target state changed before HOST_READY",
                    sizeof(sc->status));
                return (EPROTO);
        }

        error = mvxgs_facility_host_offset(sc,
            sc->fac[MVXGS_FAC_CTRL].bar, sc->fac[MVXGS_FAC_CTRL].offset,
            sc->fac[MVXGS_FAC_CTRL].size, &fbar, &foff);
        if (error != 0)
                return (error);

        error = mvxgs_read32(fbar, foff + 0x04, &flags);
        if (error != 0 || flags != MVXGS_CTRL_F_TARGET_READY)
                return (EPROTO);

        sc->host_ready_armed = 0;
        flags |= MVXGS_CTRL_F_HOST_READY;
        error = mvxgs_write32(fbar, foff + 0x04, flags);
        if (error != 0)
                return (error);

        sc->host_ready_sent = 1;
        sc->active_stage = 2;

        error = mvxgs_read32(fbar, foff + 0x04, &readback);
        if (error != 0)
                return (error);
        sc->ctrl_flags = readback;
        if ((readback & MVXGS_CTRL_F_HOST_READY) == 0) {
                strlcpy(sc->status,
                    "HOST_READY write did not read back; reboot recommended",
                    sizeof(sc->status));
                return (EIO);
        }

        strlcpy(sc->status,
            "STAGE2: HOST_READY sent; arm HOST_ALIVE next; no wait performed",
            sizeof(sc->status));
        return (0);
}

static int
mvxgs_signal_host_alive(struct mvxgs_softc *sc)
{
        struct mvxgs_bar *fbar;
        rman_res_t foff;
        uint32_t flags, readback;
        uint64_t target_offset;
        int error, i, ticks;

        if (sc->active_stage != 2 ||
            !sc->host_ready_sent ||
            sc->host_alive_armed != 1 ||
            sc->msix_allocated != MVXGS_T2H_MSIX_COUNT ||
            (pci_read_config(sc->dev, PCIR_COMMAND, 2) &
            PCIM_CMD_BUSMASTEREN) == 0)
                return (EPERM);

        error = mvxgs_scan(sc, true);
        if (error != 0)
                return (error);

        /*
         * The exact pre-HOST_ALIVE state observed in Phase 7 is CTRL=0x03.
         * Refuse if target state unexpectedly changed.
         */
        if (sc->ctrl_flags !=
            (MVXGS_CTRL_F_TARGET_READY | MVXGS_CTRL_F_HOST_READY)) {
                strlcpy(sc->status,
                    "REFUSED: expected CTRL=0x03 before HOST_ALIVE",
                    sizeof(sc->status));
                return (EPROTO);
        }

        error = mvxgs_facility_host_offset(sc,
            sc->fac[MVXGS_FAC_CTRL].bar, sc->fac[MVXGS_FAC_CTRL].offset,
            sc->fac[MVXGS_FAC_CTRL].size, &fbar, &foff);
        if (error != 0)
                return (error);

        error = mvxgs_read32(fbar, foff + 0x04, &flags);
        if (error != 0)
                return (error);

        sc->host_alive_armed = 0;
        flags |= MVXGS_CTRL_F_HOST_ALIVE;
        error = mvxgs_write32(fbar, foff + 0x04, flags);
        if (error != 0)
                return (error);

        sc->host_alive_sent = 1;
        sc->active_stage = 3;

        /*
         * One-shot experiment: wait up to ~3 seconds for target H2T-ready.
         * The real vendor driver reasserts HOST_ALIVE periodically; Phase 8
         * intentionally sends only one pulse to isolate this variable.
         */
        for (ticks = 0; ticks < 300; ticks++) {
                error = mvxgs_read32(fbar, foff + 0x04, &readback);
                if (error != 0)
                        break;
                sc->ctrl_flags = readback;
                if ((readback & MVXGS_CTRL_F_TARGET_H2T_READY) != 0)
                        break;
                pause("mvxalive", MAX(1, hz / 100));
        }

        if ((sc->ctrl_flags & MVXGS_CTRL_F_TARGET_H2T_READY) == 0) {
                strlcpy(sc->status,
                    "STAGE3: HOST_ALIVE sent; target H2T-ready not observed; REBOOT",
                    sizeof(sc->status));
                return (ETIMEDOUT);
        }

        for (i = 0; i < MVXGS_H2T_DBELL_COUNT; i++) {
                rman_res_t doff = foff + MVXGS_CTRL_H2T_DESC_BASE +
                    (rman_res_t)i * MVXGS_CTRL_H2T_DESC_STRIDE;
                uint32_t data;

                sc->h2t[i].target_offset = 0;
                sc->h2t[i].data = 0;
                sc->h2t[i].valid = 0;
                if (mvxgs_read64(fbar, doff, &target_offset) != 0 ||
                    mvxgs_read32(fbar, doff + 8, &data) != 0)
                        continue;
                sc->h2t[i].target_offset = target_offset;
                sc->h2t[i].data = data;
                sc->h2t[i].valid = target_offset != 0;
                device_printf(sc->dev,
                    "H2T descriptor[%d]: target_off=%#jx data=%#x valid=%u\n",
                    i, (uintmax_t)target_offset, data, sc->h2t[i].valid);
        }

        strlcpy(sc->status,
            "STAGE3: HOST_ALIVE accepted; target H2T-ready observed; descriptors captured",
            sizeof(sc->status));
        return (0);
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
            "NPU handshake diagnostic/active-stage status");
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
        SYSCTL_ADD_U32(ctx, SYSCTL_CHILDREN(tree), OID_AUTO,
            "mvmgmt_word10", CTLFLAG_RD, &sc->mvmgmt_word10, 0,
            "Observed mvmgmt dword at +0x10 (semantics not yet named)");
        SYSCTL_ADD_U32(ctx, SYSCTL_CHILDREN(tree), OID_AUTO,
            "mvmgmt_word14", CTLFLAG_RD, &sc->mvmgmt_word14, 0,
            "Observed mvmgmt dword at +0x14 (semantics not yet named)");
        SYSCTL_ADD_U32(ctx, SYSCTL_CHILDREN(tree), OID_AUTO,
            "mvmgmt_pattern", CTLFLAG_RD, &sc->mvmgmt_pattern, 0,
            "pcinet target handshake pattern at mvmgmt+0x18");
        SYSCTL_ADD_U32(ctx, SYSCTL_CHILDREN(tree), OID_AUTO,
            "mvmgmt_target_ready", CTLFLAG_RD, &sc->mvmgmt_target_ready, 0,
            "mvmgmt target pattern equals 0xaa55aa55");
        SYSCTL_ADD_PROC(ctx, SYSCTL_CHILDREN(tree), OID_AUTO, "rescan",
            CTLTYPE_INT | CTLFLAG_RW | CTLFLAG_MPSAFE, sc, 0,
            mvxgs_sysctl_rescan, "I",
            "Write non-zero to repeat the passive MMIO scan");
        SYSCTL_ADD_INT(ctx, SYSCTL_CHILDREN(tree), OID_AUTO, "active_stage",
            CTLFLAG_RD, &sc->active_stage, 0,
            "0=passive, 1=MSI-X ready, 2=HOST_READY sent, 3=HOST_ALIVE sent");
        SYSCTL_ADD_INT(ctx, SYSCTL_CHILDREN(tree), OID_AUTO, "msix_allocated",
            CTLFLAG_RD, &sc->msix_allocated, 0,
            "Number of MSI-X vectors allocated by this driver");
        SYSCTL_ADD_INT(ctx, SYSCTL_CHILDREN(tree), OID_AUTO, "host_ready_sent",
            CTLFLAG_RD, &sc->host_ready_sent, 0,
            "CTRL.HOST_READY has been written by this driver");
        SYSCTL_ADD_INT(ctx, SYSCTL_CHILDREN(tree), OID_AUTO, "host_ready_armed",
            CTLFLAG_RD, &sc->host_ready_armed, 0,
            "HOST_READY write is armed for one explicit signal operation");
        SYSCTL_ADD_INT(ctx, SYSCTL_CHILDREN(tree), OID_AUTO, "host_alive_sent",
            CTLFLAG_RD, &sc->host_alive_sent, 0,
            "CTRL.HOST_ALIVE has been written once by this driver");
        SYSCTL_ADD_INT(ctx, SYSCTL_CHILDREN(tree), OID_AUTO, "host_alive_armed",
            CTLFLAG_RD, &sc->host_alive_armed, 0,
            "HOST_ALIVE one-shot write is armed");
        SYSCTL_ADD_U32(ctx, SYSCTL_CHILDREN(tree), OID_AUTO, "pci_command",
            CTLFLAG_RD, &sc->pci_command, 0,
            "Observed PCI command register; refresh with rescan");
        SYSCTL_ADD_U32(ctx, SYSCTL_CHILDREN(tree), OID_AUTO, "pci_command_initial",
            CTLFLAG_RD, &sc->pci_command_initial, 0,
            "PCI command register observed at attach");
        SYSCTL_ADD_INT(ctx, SYSCTL_CHILDREN(tree), OID_AUTO,
            "busmaster_enabled_by_driver", CTLFLAG_RD,
            &sc->busmaster_enabled_by_driver, 0,
            "Driver explicitly enabled PCI bus mastering");
        SYSCTL_ADD_PROC(ctx, SYSCTL_CHILDREN(tree), OID_AUTO, "enable_busmaster",
            CTLTYPE_INT | CTLFLAG_RW | CTLFLAG_MPSAFE, sc, 0,
            mvxgs_sysctl_enable_busmaster, "I",
            "Write 1 before MSI-X to call pci_enable_busmaster()");
        SYSCTL_ADD_PROC(ctx, SYSCTL_CHILDREN(tree), OID_AUTO, "prepare_msix",
            CTLTYPE_INT | CTLFLAG_RW | CTLFLAG_MPSAFE, sc, 0,
            mvxgs_sysctl_prepare_msix, "I",
            "Write 1 to allocate five MSI-X vectors; does not write NPU protocol state");
        SYSCTL_ADD_PROC(ctx, SYSCTL_CHILDREN(tree), OID_AUTO, "arm_host_ready",
            CTLTYPE_INT | CTLFLAG_RW | CTLFLAG_MPSAFE, sc, 0,
            mvxgs_sysctl_arm_host_ready, "I",
            "Write 1 after Stage1 to arm exactly one HOST_READY attempt");
        SYSCTL_ADD_PROC(ctx, SYSCTL_CHILDREN(tree), OID_AUTO, "signal_host_ready",
            CTLTYPE_INT | CTLFLAG_RW | CTLFLAG_MPSAFE, sc, 0,
            mvxgs_sysctl_signal_host_ready, "I",
            "ACTIVE: write 1 only after arm_host_ready=1 to set CTRL.HOST_READY");
        SYSCTL_ADD_PROC(ctx, SYSCTL_CHILDREN(tree), OID_AUTO, "arm_host_alive",
            CTLTYPE_INT | CTLFLAG_RW | CTLFLAG_MPSAFE, sc, 0,
            mvxgs_sysctl_arm_host_alive, "I",
            "Write 1 after HOST_READY to arm one HOST_ALIVE pulse");
        SYSCTL_ADD_PROC(ctx, SYSCTL_CHILDREN(tree), OID_AUTO, "signal_host_alive",
            CTLTYPE_INT | CTLFLAG_RW | CTLFLAG_MPSAFE, sc, 0,
            mvxgs_sysctl_signal_host_alive, "I",
            "ACTIVE: write 1 only after arm_host_alive=1 to set CTRL.HOST_ALIVE once");

        for (i = 0; i < MVXGS_T2H_MSIX_COUNT; i++) {
                char name[24];
                snprintf(name, sizeof(name), "irq%d_hits", i);
                SYSCTL_ADD_U64(ctx, SYSCTL_CHILDREN(tree), OID_AUTO, name,
                    CTLFLAG_RD, &sc->irq_ctx[i].hits, 0,
                    "Observed calls to inert MSI-X interrupt handler");
        }
        for (i = 0; i < MVXGS_H2T_DBELL_COUNT; i++) {
                char name[32];
                snprintf(name, sizeof(name), "h2t%d_target_offset", i);
                SYSCTL_ADD_U64(ctx, SYSCTL_CHILDREN(tree), OID_AUTO, name,
                    CTLFLAG_RD, &sc->h2t[i].target_offset, 0,
                    "Target-provided H2T doorbell offset");
                snprintf(name, sizeof(name), "h2t%d_data", i);
                SYSCTL_ADD_U32(ctx, SYSCTL_CHILDREN(tree), OID_AUTO, name,
                    CTLFLAG_RD, &sc->h2t[i].data, 0,
                    "Target-provided H2T doorbell data");
                snprintf(name, sizeof(name), "h2t%d_valid", i);
                SYSCTL_ADD_U32(ctx, SYSCTL_CHILDREN(tree), OID_AUTO, name,
                    CTLFLAG_RD, &sc->h2t[i].valid, 0,
                    "Target-provided H2T descriptor is non-zero");
        }

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
        if (value != 0) {
                sx_xlock(&sc->state_sx);
                (void)mvxgs_scan(sc, true);
                sx_xunlock(&sc->state_sx);
        }
        return (0);
}

static int
mvxgs_sysctl_enable_busmaster(SYSCTL_HANDLER_ARGS)
{
        struct mvxgs_softc *sc;
        int error, value;

        sc = arg1;
        value = 0;
        error = sysctl_handle_int(oidp, &value, 0, req);
        if (error != 0 || req->newptr == NULL || value == 0)
                return (error);
        if (value != 1)
                return (EINVAL);

        sx_xlock(&sc->state_sx);
        error = mvxgs_enable_busmaster(sc);
        sx_xunlock(&sc->state_sx);
        return (error);
}

static int
mvxgs_sysctl_prepare_msix(SYSCTL_HANDLER_ARGS)
{
        struct mvxgs_softc *sc;
        int error, value;

        sc = arg1;
        value = 0;
        error = sysctl_handle_int(oidp, &value, 0, req);
        if (error != 0 || req->newptr == NULL || value == 0)
                return (error);
        if (value != 1)
                return (EINVAL);

        sx_xlock(&sc->state_sx);
        error = mvxgs_prepare_msix(sc);
        sx_xunlock(&sc->state_sx);
        return (error);
}

static int
mvxgs_sysctl_arm_host_ready(SYSCTL_HANDLER_ARGS)
{
        struct mvxgs_softc *sc;
        int error, value, i;

        sc = arg1;
        value = 0;
        error = sysctl_handle_int(oidp, &value, 0, req);
        if (error != 0 || req->newptr == NULL || value == 0)
                return (error);
        if (value != 1)
                return (EINVAL);

        sx_xlock(&sc->state_sx);

        if (sc->active_stage != 1 ||
            sc->msix_allocated != MVXGS_T2H_MSIX_COUNT ||
            sc->host_ready_sent ||
            (pci_read_config(sc->dev, PCIR_COMMAND, 2) &
            PCIM_CMD_BUSMASTEREN) == 0) {
                sx_xunlock(&sc->state_sx);
                return (EPERM);
        }

        for (i = 0; i < MVXGS_T2H_MSIX_COUNT; i++) {
                if (sc->irq[i] == NULL || sc->irq_cookie[i] == NULL) {
                        sx_xunlock(&sc->state_sx);
                        return (ENXIO);
                }
        }

        error = mvxgs_scan(sc, true);
        if (error == 0 &&
            sc->barmap_valid &&
            sc->ctrl_valid &&
            sc->ctrl_flags == MVXGS_CTRL_F_TARGET_READY &&
            sc->mvmgmt_target_ready) {
                sc->host_ready_armed = 1;
                strlcpy(sc->status,
                    "ARMED: Stage1 valid; next signal_host_ready=1 performs one CTRL HOST_READY write",
                    sizeof(sc->status));
        } else {
                sc->host_ready_armed = 0;
                if (error == 0)
                        error = EPROTO;
                strlcpy(sc->status,
                    "REFUSED: HOST_READY arm preconditions do not match baseline",
                    sizeof(sc->status));
        }

        sx_xunlock(&sc->state_sx);
        return (error);
}

static int
mvxgs_sysctl_signal_host_ready(SYSCTL_HANDLER_ARGS)
{
        struct mvxgs_softc *sc;
        int error, value;

        sc = arg1;
        value = 0;
        error = sysctl_handle_int(oidp, &value, 0, req);
        if (error != 0 || req->newptr == NULL || value == 0)
                return (error);
        if (value != 1)
                return (EINVAL);

        sx_xlock(&sc->state_sx);
        error = mvxgs_signal_host_ready(sc);
        sx_xunlock(&sc->state_sx);
        return (error);
}

static int
mvxgs_sysctl_arm_host_alive(SYSCTL_HANDLER_ARGS)
{
        struct mvxgs_softc *sc;
        int error, value;

        sc = arg1;
        value = 0;
        error = sysctl_handle_int(oidp, &value, 0, req);
        if (error != 0 || req->newptr == NULL || value == 0)
                return (error);
        if (value != 1)
                return (EINVAL);

        sx_xlock(&sc->state_sx);
        if (sc->active_stage != 2 || !sc->host_ready_sent ||
            sc->host_alive_sent) {
                sx_xunlock(&sc->state_sx);
                return (EPERM);
        }

        error = mvxgs_scan(sc, true);
        if (error == 0 &&
            sc->ctrl_flags ==
            (MVXGS_CTRL_F_TARGET_READY | MVXGS_CTRL_F_HOST_READY)) {
                sc->host_alive_armed = 1;
                strlcpy(sc->status,
                    "ARMED: next signal_host_alive=1 performs one CTRL HOST_ALIVE write",
                    sizeof(sc->status));
        } else {
                sc->host_alive_armed = 0;
                if (error == 0)
                        error = EPROTO;
                strlcpy(sc->status,
                    "REFUSED: HOST_ALIVE arm preconditions do not match CTRL=0x03",
                    sizeof(sc->status));
        }
        sx_xunlock(&sc->state_sx);
        return (error);
}

static int
mvxgs_sysctl_signal_host_alive(SYSCTL_HANDLER_ARGS)
{
        struct mvxgs_softc *sc;
        int error, value;

        sc = arg1;
        value = 0;
        error = sysctl_handle_int(oidp, &value, 0, req);
        if (error != 0 || req->newptr == NULL || value == 0)
                return (error);
        if (value != 1)
                return (EINVAL);

        sx_xlock(&sc->state_sx);
        error = mvxgs_signal_host_alive(sc);
        sx_xunlock(&sc->state_sx);
        return (error);
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
        sx_init(&sc->state_sx, "mvxgs-state");
        sc->active_stage = 0;
        sc->msix_allocated = 0;
        sc->host_ready_sent = 0;
        sc->host_ready_armed = 0;
        sc->host_alive_sent = 0;
        sc->host_alive_armed = 0;
        sc->busmaster_enabled_by_driver = 0;
        sc->pci_command_initial = pci_read_config(dev, PCIR_COMMAND, 2);
        sc->pci_command = sc->pci_command_initial;

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
            "PCI %04x:%04x; MSI-X=%d MSI=%d; phase8 attach is passive; command=%#x\n",
            pci_get_vendor(dev), pci_get_device(dev),
            sc->msix_count, sc->msi_count, sc->pci_command_initial);

        /* Create sysctls before scanning so even a failed scan is inspectable. */
        mvxgs_add_sysctls(sc);
        (void)mvxgs_scan(sc, true);

        device_printf(dev,
            "attach performed no protocol writes; Phase8 adds separately gated HOST_READY and HOST_ALIVE\n");
        return (0);

fail:
        mvxgs_free_bars(sc);
        sx_destroy(&sc->state_sx);
        return (error);
}

static int
mvxgs_detach(device_t dev)
{
        struct mvxgs_softc *sc;

        sc = device_get_softc(dev);
        sx_xlock(&sc->state_sx);
        if (sc->host_ready_sent) {
                sx_xunlock(&sc->state_sx);
                device_printf(dev,
                    "refusing detach after HOST_READY; reboot to reset NPU state\n");
                return (EBUSY);
        }
        mvxgs_release_msix(sc);
        if (sc->busmaster_enabled_by_driver) {
                (void)pci_disable_busmaster(sc->dev);
                sc->busmaster_enabled_by_driver = 0;
                sc->pci_command = pci_read_config(sc->dev, PCIR_COMMAND, 2);
                device_printf(dev,
                    "PCI busmaster disabled during safe detach; command=%#x\n",
                    sc->pci_command);
        }
        sx_xunlock(&sc->state_sx);
        mvxgs_free_bars(sc);
        sx_destroy(&sc->state_sx);
        return (0);
}

static int mvxgs_shutdown(device_t dev) { (void)dev; return (0); }
static int
mvxgs_suspend(device_t dev)
{
        struct mvxgs_softc *sc = device_get_softc(dev);
        return (sc->host_ready_sent ? EBUSY : 0);
}
static int mvxgs_resume(device_t dev) { (void)dev; return (0); }

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
MODULE_VERSION(mvxgs, 8);
