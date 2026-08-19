# mvxgs Phase 7 — Bus Mastering A/B test

Phase 6 proved that FreeBSD can map the Marvell endpoint, allocate five MSI-X
vectors, and write `HOST_READY`, but the NPU stopped at CTRL `0x03`.

Phase 7 adds one controlled pre-handshake PCI action:

`pci_enable_busmaster()`

The observed FreeBSD command register was `0x0402`; SFOS was `0x0406`.

The NPU protocol write remains exactly the same single
`CTRL.flags |= 0x02` operation as Phase 6. No MVMGMT acknowledgement, DMA
buffer setup, SR-IOV, doorbell ringing, GIU/NWA initialization, or Ethernet
interface is added.

See `PHASE7-TEST.md`.
