# mvxgs Phase 8 — HOST_ALIVE experiment

Phase 7 proved that bus mastering (`0x0406`) plus five MSI-X vectors is not
sufficient by itself: the NPU remains at CTRL `0x03`.

Further disassembly of the real Sophos/Marvell driver found a heartbeat timer
that calls `mv_facility_host_is_alive()` every 250 jiffies. That function ORs
`0x08` into CTRL.

Phase 8 tests exactly one HOST_ALIVE pulse after HOST_READY. The driver still
does not acknowledge MVMGMT, configure SR-IOV, allocate packet DMA, ring
doorbells, initialize GIU/NWA, or create Ethernet interfaces.
