# Phase 8 finding: the vendor heartbeat

Static analysis of the supplied `mv_armada_drv.ko` revealed the missing host
action after `mv_facility_conf_init()`:

- `armada_pci_probe()` obtains the `ctrl` facility handle.
- It starts `armada_pci_heartbeat_timeout`.
- The timer fires every `0xfa` (250) jiffies.
- Each timer invocation calls `mv_facility_host_is_alive(ctrl_handle)`.
- `mv_facility_host_is_alive()` performs:

  `CTRL.flags |= 0x08`

This explains why the fully running SFOS snapshot had CTRL `0x0f`.

The real sequence is therefore:

1. Target starts with `0x01`.
2. Host allocates five MSI-X vectors.
3. Host sets `HOST_READY` (`0x02`) -> `0x03`.
4. The host heartbeat repeatedly sets `HOST_ALIVE` (`0x08`).
5. The target is expected to publish H2T-ready (`0x04`) and descriptors.

Phase 8 intentionally tests a **single** HOST_ALIVE pulse first. It does not
yet implement the periodic timer.
