# Sophos XGS 116 / Marvell 11ab:7080 reverse-engineering notes

Observed appliance: Sophos XGS 116, SFOS 19.5.4 MR-4, Linux 4.14.277.
Target OS: OPNsense 26.7 / FreeBSD 15.1.

## Confirmed PCI layout

- PF: `11ab:7080`
- VF: `11ab:7081`
- PF BAR0: 1 MiB
- PF BAR2: 16 MiB
- PF BAR4: 16 MiB
- SR-IOV: 6 VFs supported; SFOS enables 4.

## Confirmed target BAR map

The target publishes its BAR map at full PF BAR2 `end - 0x2000`.
On the observed XGS 116 this is physical `0xfdffe000`.

Header:

- version = `5`
- target cookie = `0xd0fac10d`

Five 16-byte records follow, each:

`{ logical_bar, facility_id, offset, size }`

Observed records:

| id | name   | logical bar | offset | size |
|---:|--------|------------:|-------:|-----:|
| 4 | giu     | 0 | 0x0000 | 0x4000 |
| 0 | ctrl    | 1 | 0x0000 | 0x1000 |
| 1 | mvmgmt  | 1 | 0x1000 | 0x1000 |
| 2 | nwa     | 0 | 0x4000 | 0x10000 |
| 3 | rpc     | 1 | 0x2000 | 0x100000 |

Logical BAR 0 maps to the BAR0 window. Logical BAR 1 maps to the special
BAR2 window beginning 0x104000 bytes before the end of the full BAR.

## CTRL handshake

`ctrl + 0x00 = 0xafacafac`

Observed under OPNsense before any host driver writes:

`ctrl + 0x04 = 0x00000001`

Recovered from `mv_armada_drv.ko`:

- bit 0 (`0x01`) = target ready
- bit 1 (`0x02`) = host ready; SFOS sets this only after configuring facilities,
  MSI-X and doorbells.
- bit 3 (`0x08`) participates in host-alive/heartbeat state.

Do **not** manually set HOST_READY before reproducing the preceding setup.

## Facility interrupt/doorbell plan recovered from mv_armada_drv.ko

The built-in facility configuration table implies:

- total target -> host doorbells: 5
- total host -> target doorbells: 5
- GIU contributes 4 in each direction
- RPC contributes one target -> host doorbell
- MVMGMT contributes one host -> target doorbell

This matches SFOS boot logs allocating five MSI-X vectors and later reporting
GIU doorbell IRQs.

## MVMGMT / pcinet handshake

`mv_pcinet_drv.ko` waits until:

`mvmgmt + 0x18 == 0xaa55aa55`

then writes:

`mvmgmt + 0x18 = 0xbb66bb66`

and proceeds with `pcinet_init()`.

Observed under OPNsense before host initialization:

- `mvmgmt + 0x10 = 0x80`
- `mvmgmt + 0x14 = 0x01`
- `mvmgmt + 0x18 = 0xaa55aa55`

The semantics of +0x10/+0x14 are intentionally left unnamed until confirmed.

## GIU / NWA state under OPNsense

Before host initialization, the first pages of both GIU and NWA facilities
read as zero. This is consistent with the SFOS module order: host-side
facility, interrupt, and queue setup precedes HOST_READY and the later GIU/NWA
modules populate/use those regions.

## Safety boundary of Phase 3 passive

The included FreeBSD module still performs no MMIO writes, DMA setup, SR-IOV,
interrupt allocation, doorbell writes, or network-interface registration.

## Phase 5: MSI-X allocation semantics

Static symbol/disassembly review of the captured `mv_armada_drv.ko` shows the PF init path calls `pci_alloc_irq_vectors_affinity()` with MSI-X mode and then calls `pci_irq_vector()` for the allocated vectors. The module does not import Linux helpers for extracting an MSI message address/data pair from an IRQ descriptor. This supports the working model that the Marvell endpoint triggers MSI-X table entries by index and the host PCI subsystem owns/programs the MSI-X table.

The FreeBSD port therefore uses `pci_alloc_msix(dev, &count)` and allocates the resulting `SYS_RES_IRQ` resources at RIDs 1..5. BAR0 is kept allocated because the endpoint's MSI-X table and PBA live there.

## First active vendor-protocol write

Phase 5 deliberately separates PCI/MSI-X preparation from the vendor handshake. `signal_host_ready=1` is the only path that writes vendor shared MMIO, and it only ORs `0x02` into CTRL flags after exact preconditions are revalidated. The driver does not acknowledge MVMGMT or set HOST_ALIVE in this phase.
