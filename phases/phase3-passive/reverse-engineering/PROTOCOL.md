# Sophos XGS 116 / Marvell 11ab:7080 — recovered host interface

This document records behaviour recovered from the user-supplied SFOS 19.5.4 MR-4 binaries and runtime logs.  The generated driver package does **not** contain the Sophos/Marvell binaries.

## Confirmed from the supplied system

- PF: PCI `11ab:7080`, handled by Sophos module `mv_armada_drv` / kernel driver name `armada_pci`.
- SR-IOV VF: PCI `11ab:7081`; the tested SFOS instance enables four VFs, while the PF advertises six total VFs.
- Sophos binds the active VFs to `vfio-pci`.
- Sophos ships a DPDK PMD whose metadata identifies `net_armada_ep`, `vfio-pci`, and PCI ID `11ab:7081`.
- Data-plane parent: `mv-pcimux0`; physical logical children: Port1..Port8 and PortF1.
- Management netdev: `mvmgmt0`.
- The Marvell module stack includes `mv_armada_drv`, `mv_pcinet_drv`, `mv_giu_drv`, `mv_nwa_host`, and `mv_pport`.

## PF mapping used by `mv_armada_drv`

Observed full PCI resources on the XGS 116:

- BAR0: 1 MiB
- BAR2: 16 MiB
- BAR4: 16 MiB

The vendor driver maps these logical windows:

- BAR0: offset `0`, length `0x14000`
- BAR2: last `0x103000` bytes of BAR2
- BAR4: the whole BAR4

The target BAR map lives at `BAR2-window + 0x102000`, which is equivalently the **last 4 KiB page of BAR2**.

## Target BAR map

Recovered layout:

```c
struct target_barmap {
    uint32_t version;        // expected 5
    uint32_t target_cookie;  // expected 0xd0fac10d
    struct {
        uint32_t bar;
        uint32_t facility_id;
        uint32_t offset;
        uint32_t size;
    } facility[5];
};
```

The facility records are matched by `facility_id`, not assumed to be in fixed order.

Known IDs/names:

| ID | Name |
|---:|---|
| 0 | ctrl |
| 1 | mvmgmt |
| 2 | nwa |
| 3 | rpc |
| 4 | giu |

## Control facility

The first two dwords are read by the vendor driver:

- `+0x00`: cookie, expected `0xafacafac`
- `+0x04`: state flags

Recovered flag use:

- bit `0x1`: target/NPU ready; vendor driver waits for it
- bit `0x2`: host ready; vendor driver ORs it after its host-side setup
- bit `0x8`: host alive; `mv_facility_host_is_alive()` ORs it

Phase 2 **only reads** these values.  It does not set bits.

## Doorbells

The runtime facility object has separate H2T and T2H doorbell counts.  From the static configuration in `mv_armada_drv`:

| Facility | H2T | T2H |
|---|---:|---:|
| ctrl | 0 | 0 |
| mvmgmt | 0 | 1 |
| nwa | 0 | 0 |
| rpc | 1 | 0 |
| giu | 4 | 4 |

`mv_send_dbell()` uses 16-byte H2T entries containing a mapped MMIO address and a 32-bit value; sending a doorbell is a 32-bit MMIO write.  Phase 2 deliberately does not reproduce that write yet.

The tested SFOS boot allocates five target-to-host IRQ vectors in total and logs four GIU doorbell IRQs plus the management path.

## `mvmgmt0` handshake

The `mv_pcinet_drv` module obtains the `mvmgmt` facility and waits on a 32-bit pattern at facility offset `+0x18`:

- target publishes `0xaa55aa55`
- host changes it to `0xbb66bb66`
- then `pcinet_init()` creates the Linux management netdev

This is a separate, later handshake from the global `ctrl` facility handshake.

## Data plane

`mv_giu_drv` reports:

- `Marvell GIU-NIC Network Adapter`
- four RX queues and four TX queues on this SFOS configuration
- a separate management command/notification mechanism

The supplied DPDK PMD (`net_armada_ep`) targets the SR-IOV VF (`11ab:7081`) and contains RX/TX burst functions plus management-command and notification-queue code.  This strongly supports the model:

1. PF `7080`: host/NPU control, shared facilities, SR-IOV provisioning, doorbells.
2. VF `7081`: accelerated packet/data-plane endpoint.
3. PPORT layer: tags/demultiplexes the aggregate packet path into physical Port1..Port8/PortF1.
4. NWA layer: physical-port/link control.

## Physical PPORT tags observed

- Port1: `0x8100`, lif_id 0
- Port2: `0x8200`, lif_id 1
- Port3: `0x8300`, lif_id 2
- Port4: `0x8400`, lif_id 3
- Port5: `0x8500`, lif_id 4
- Port6: `0x8600`, lif_id 5
- Port7: `0x8700`, lif_id 6
- Port8: `0x8800`, lif_id 7
- PortF1: `0x8900`, lif_id 8

## What Phase 2 proves

If OPNsense prints:

```text
barmap version=0x5 target_cookie=0xd0fac10d
ctrl cookie=0xafacafac flags=...
```

then the NPU is already sufficiently alive under FreeBSD for us to see the exact vendor shared-memory handshake without any SFOS host driver.  The next safe milestone is then to reproduce the host-ready handshake and MSI-X/doorbell discovery.

If those cookies are absent under OPNsense, the missing step is earlier: NPU boot/firmware/rootfs initialization must be understood before the packet driver can work.
