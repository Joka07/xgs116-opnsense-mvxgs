/* SPDX-License-Identifier: BSD-2-Clause
 * Stable per-appliance port identity and read-only open-firmware telemetry.
 * Copyright (c) 2026 XGS116 integration contributors.
 */
#include <sys/param.h>
#include <sys/systm.h>
#include <sys/kernel.h>
#include <sys/bus.h>
#include <sys/lock.h>
#include <sys/mutex.h>
#include <sys/sx.h>
#include <sys/callout.h>
#include <sys/endian.h>
#include <machine/bus.h>
#include "if_agnic.h"

int
agnic_mac_setup(struct agnic_softc *sc)
{
    char *text;
    unsigned b[6];
    char tail;
    unsigned i;

    text = kern_getenv("hw.agnic.mac_base");
    if (text != NULL) {
        int n = sscanf(text, "%x:%x:%x:%x:%x:%x%c", &b[0], &b[1], &b[2],
            &b[3], &b[4], &b[5], &tail);
        freeenv(text);
        if (n != 6) return (EINVAL);
        for (i = 0; i < 6; i++) {
            if (b[i] > 255) return (EINVAL);
            sc->port_mac_base[i] = b[i];
        }
        if (!agnic_mac_valid(sc->port_mac_base) || !(b[0] & 2) || b[5] != 0)
            return (EINVAL);
    } else {
        int valid = 0;
        text = kern_getenv("smbios.system.uuid");
        if (text != NULL) {
            valid = agnic_uuid_mac(text, sc->port_mac_base);
            freeenv(text);
        }
        if (!valid) return (ENOENT);
    }
    device_printf(sc->dev, "stable port MAC prefix %02x:%02x:%02x:%02x:%02x (ports 01..09)\n",
        sc->port_mac_base[0], sc->port_mac_base[1], sc->port_mac_base[2],
        sc->port_mac_base[3], sc->port_mac_base[4]);
    return (0);
}

int
agnic_swop_probe(struct agnic_softc *sc)
{
    const uint32_t slots[] = {AGNIC_SWOP_SLOT, 0};
    int bar = sc->fac_bar[AGNIC_FAC_NW_AGENT];
    uint32_t base = sc->fac_off[AGNIC_FAC_NW_AGENT];
    unsigned i;

    sc->swop_version = 0;
    if (bar < 0 || sc->fac_size[AGNIC_FAC_NW_AGENT] < NPU_NWA_WIN_SIZE)
        return (ENXIO);
    for (i = 0; i < nitems(slots); i++) {
        uint32_t off = base + slots[i], magic, version, features;
        if ((uint64_t)off + 12 > sc->bar_size[bar]) continue;
        magic = AGNIC_RD4(sc, bar, off);
        version = AGNIC_RD4(sc, bar, off + 4);
        features = version == 2 ? AGNIC_RD4(sc, bar, off + 8) : 0;
        if (!agnic_swop_cap_valid(magic, version, features) ||
            magic != AGNIC_RD4(sc, bar, off)) continue;
        sc->swop_version = version;
        sc->swop_slot = slots[i];
        sc->swop_features = features;
        device_printf(sc->dev, "SWOP capability v%u at NWA+0x%x (read-only telemetry)\n",
            version, slots[i]);
        return (0);
    }
    return (ENOENT);
}

int
agnic_swop_ports(struct agnic_softc *sc, uint16_t *status)
{
    uint8_t req[12] = {0}, resp[56] = {0};
    int bar = sc->fac_bar[AGNIC_FAC_NW_AGENT];
    uint32_t off = sc->fac_off[AGNIC_FAC_NW_AGENT] + sc->swop_slot;
    int error;
    unsigned i;

    if (!sc->swop_version || sc->swop_errors >= 3 || sc->recovery_required) return (ENXIO);
    /* Capability disappearance/version change suggests an NPU restart.
     * No automatic queue re-init: a stale mapping must not be reused. */
    if (AGNIC_RD4(sc, bar, off) != AGNIC_SWOP_MAGIC ||
        AGNIC_RD4(sc, bar, off + 4) != sc->swop_version) {
        sc->recovery_required = 1;
        sc->datapath_ready = 0;
        return (EIO);
    }
    le32enc(req, AGNIC_SWOP_MAGIC);
    req[4] = 1; /* wire version; independent from capability v1/v2 */
    req[5] = 3; /* PORTS: read-only status + VLAN map of devices 0..10 */
    error = agnic_mgmt_custom(sc, req, sizeof(req), resp, sizeof(resp));
    if (error != 0) goto fail;
    if (!agnic_swop_ports_valid(resp, sizeof(resp))) {
        error = EPROTO;
        goto fail;
    }
    for (i = 0; i < AGNIC_PORT_COUNT; i++)
        status[i] = le16dec(resp + 12 + (i + 1) * 4);
    return (0);
fail:
    sc->swop_errors++;
    return (error);
}
