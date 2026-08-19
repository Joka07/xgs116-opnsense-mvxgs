# Project status — 2026-08-19

## Goal

Use the onboard ports of a Sophos XGS 116 under OPNsense instead of relying on Sophos SFOS or a permanent USB Ethernet adapter.

## Hardware discovery

The main PCI endpoint is Marvell `11ab:7080`. Under OPNsense it initially has no usable NIC driver. The device exposes:

- BAR0 `0xfe000000`, size `0x100000`
- BAR2 `0xfd000000`, size `0x1000000`
- BAR4 `0xfc000000`, size `0x1000000`
- MSI-X: 16 messages
- MSI: 32 messages
- SR-IOV: 6 VFs, VF ID `11ab:7081`

The Sophos SFOS stack uses a PF control driver plus Marvell GIU/management/network-agent/port components and VFIO/DPDK for the datapath.

## NPU BAR map

BARMAP at physical `0xfdffe000`:

- version = `5`
- target cookie = `0xd0fac10d`

Entries (16-byte records after the 8-byte header):

1. logical BAR 0, facility `giu` (id 4), offset `0x0000`, size `0x4000`
2. logical BAR 1, facility `ctrl` (id 0), offset `0x0000`, size `0x1000`
3. logical BAR 1, facility `mvmgmt` (id 1), offset `0x1000`, size `0x1000`
4. logical BAR 0, facility `nwa` (id 2), offset `0x4000`, size `0x10000`
5. logical BAR 1, facility `rpc` (id 3), offset `0x2000`, size `0x100000`

`BOOTCMD!` is in the following page at `0xfdfff000`.

## CTRL state machine observed so far

CTRL begins with:

- `+0x00 = 0xafacafac`
- `+0x04 = flags`
- initial flags = `0x01`

Current bit interpretation from vendor-driver analysis:

- `0x01` — TARGET_READY
- `0x02` — HOST_READY
- `0x04` — target H2T-ready / target-published doorbell state
- `0x08` — HOST_ALIVE heartbeat

Fully running SFOS was observed at `0x0f`.

## MVMGMT

Initial state under OPNsense:

- `+0x10 = 0x80`
- `+0x14 = 0x01`
- `+0x18 = 0xaa55aa55`

Vendor `mv_pcinet_drv` waits for `0xaa55aa55`, then writes `0xbb66bb66` before initializing the management netdev. We have **not** reproduced that acknowledgement yet.

## MSI-X

Phase 5 proved that FreeBSD can allocate five MSI-X vectors with inert handlers:

- RID 1 -> IRQ `0x3d`
- RID 2 -> IRQ `0x3e`
- RID 3 -> IRQ `0x3f`
- RID 4 -> IRQ `0x40`
- RID 5 -> IRQ `0x41`

The NPU CTRL and MVMGMT state remained unchanged after MSI-X setup.

FreeBSD's first five hardware MSI-X table entries were populated and unmasked. This ruled out a basic “MSI-X table never programmed” failure.

## Bus mastering

The vendor driver calls Linux `pci_set_master()` before facility initialization.

FreeBSD initially showed PCI command `0x0002`. Phase 7 explicitly called `pci_enable_busmaster()` and read back `0x0006`. After MSI-X setup the command became `0x0406`, matching the relevant SFOS state. CTRL/MVMGMT were still unchanged.

Bus mastering alone did **not** cause the target to progress past HOST_READY.

## HOST_READY tests

Phase 6 and Phase 7 both performed a single gated protocol write:

`CTRL.flags |= 0x02`

Observed result:

- before: `0x01`
- after: `0x03`
- target never added `0x04`
- H2T descriptors remained zero
- five IRQ counters remained zero

A later direct MMIO read confirmed the target still remained at `0x03`; this was not merely a cached-value or short-timeout issue.

## Newest finding: HOST_ALIVE heartbeat

Further vendor-driver analysis found a heartbeat timer:

- periodic callback every `0xfa` (250) jiffies
- callback calls `mv_facility_host_is_alive(ctrl_handle)`
- that function ORs `0x08` into CTRL flags

This explains why running SFOS reaches `0x0f` and suggests that the missing step after HOST_READY is a host heartbeat.

## Phase 8 hypothesis

Expected experimental sequence:

1. target starts at `0x01`
2. enable PCI bus mastering
3. allocate 5 MSI-X vectors
4. set HOST_READY -> `0x03`
5. send one HOST_ALIVE pulse -> expected host bits `0x0b`
6. observe whether target adds `0x04`, yielding a value containing all four bits (ideally `0x0f`)
7. if successful, capture H2T descriptors and IRQ activity

Phase 8 deliberately sends only one HOST_ALIVE pulse. A periodic heartbeat is a later phase.

## Not implemented yet

- periodic HOST_ALIVE heartbeat
- MVMGMT `0xbb66bb66` acknowledgement
- DMA queue allocation
- H2T doorbell ringing
- GIU/AGNIC initialization
- NWA mailbox initialization
- port enumeration / Port1..Port8
- SR-IOV VF datapath under FreeBSD
- Ethernet `ifnet` interfaces
