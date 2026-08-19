/*-
 * SPDX-License-Identifier: BSD-2-Clause
 *
 * Experimental FreeBSD/OPNsense probe driver for the Marvell PCIe endpoint
 * found in Sophos XGS Gen.1 appliances (observed on XGS 116 as 11ab:7080).
 *
 * Phase 1 goal:
 *   - bind to the otherwise-unclaimed PCI function
 *   - map the three observed MMIO BARs without touching device registers
 *   - report PCI/MSI/MSI-X/SR-IOV-visible properties
 *
 * This is NOT yet an Ethernet driver.  It deliberately performs no MMIO
 * reads/writes, DMA setup, reset, firmware upload, mailbox operations, or
 * interrupt allocation because the Sophos/Marvell host<->NPU protocol is not
 * public in the material currently available.
 */

#include <sys/param.h>
#include <sys/systm.h>
#include <sys/bus.h>
#include <sys/kernel.h>
#include <sys/module.h>
#include <sys/rman.h>
#include <sys/types.h>

#include <machine/bus.h>
#include <machine/resource.h>

#include <dev/pci/pcireg.h>
#include <dev/pci/pcivar.h>

#define MVXGS_VENDOR_ID          0x11ab
#define MVXGS_DEVICE_ID_PF       0x7080
#define MVXGS_DEVICE_ID_VF       0x7081

#define MVXGS_NBARS              3

struct mvxgs_bar {
        int             rid;
        int             barno;
        struct resource *res;
        bus_space_tag_t tag;
        bus_space_handle_t handle;
        rman_res_t      start;
        rman_res_t      size;
};

struct mvxgs_softc {
        device_t        dev;
        struct mvxgs_bar bars[MVXGS_NBARS];
        int             msix_count;
        int             msi_count;
};

static int mvxgs_probe(device_t dev);
static int mvxgs_attach(device_t dev);
static int mvxgs_detach(device_t dev);
static int mvxgs_shutdown(device_t dev);
static int mvxgs_suspend(device_t dev);
static int mvxgs_resume(device_t dev);

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
            "BAR%d mapped: start=%#jx size=%#jx (%ju bytes)\n",
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
mvxgs_probe(device_t dev)
{
        if (pci_get_vendor(dev) != MVXGS_VENDOR_ID)
                return (ENXIO);

        if (pci_get_device(dev) != MVXGS_DEVICE_ID_PF)
                return (ENXIO);

        device_set_desc(dev,
            "Marvell/Sophos XGS network-processing PCIe endpoint (experimental)");
        return (BUS_PROBE_DEFAULT);
}

static int
mvxgs_attach(device_t dev)
{
        struct mvxgs_softc *sc;
        int error;

        sc = device_get_softc(dev);
        sc->dev = dev;

        /*
         * The XGS 116 sample reports BARs at config offsets 0x10, 0x18,
         * and 0x20, i.e. BAR0 (64-bit), BAR2 (64-bit), BAR4 (32-bit).
         * We only reserve/map them here.  No register access is performed.
         */
        error = mvxgs_alloc_bar(sc, 0, 0);
        if (error != 0)
                goto fail;

        error = mvxgs_alloc_bar(sc, 1, 2);
        if (error != 0)
                goto fail;

        error = mvxgs_alloc_bar(sc, 2, 4);
        if (error != 0)
                goto fail;

        sc->msix_count = pci_msix_count(dev);
        sc->msi_count = pci_msi_count(dev);

        device_printf(dev,
            "PCI %04x:%04x attached; MSI-X vectors=%d, MSI vectors=%d\n",
            pci_get_vendor(dev), pci_get_device(dev),
            sc->msix_count, sc->msi_count);

        device_printf(dev,
            "safe probe mode: bus mastering, DMA, interrupts and MMIO access are intentionally disabled\n");
        device_printf(dev,
            "next milestone requires the Sophos/Marvell mailbox + NPU firmware protocol\n");

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

static int
mvxgs_shutdown(device_t dev)
{
        (void)dev;
        return (0);
}

static int
mvxgs_suspend(device_t dev)
{
        (void)dev;
        return (0);
}

static int
mvxgs_resume(device_t dev)
{
        (void)dev;
        return (0);
}

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
MODULE_VERSION(mvxgs, 1);
