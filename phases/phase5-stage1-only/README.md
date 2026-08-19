# mvxgs Phase 5 — controlled HOST_READY experiment

Experimental FreeBSD/OPNsense driver for the Marvell `11ab:7080` endpoint in the tested Sophos XGS 116.

## What changed from Phase 4

Attach is still passive. Nothing is sent to the NPU merely by loading the module.

Phase 5 adds two explicit stages:

1. `prepare_msix=1` — allocate exactly five MSI-X vectors and install inert interrupt handlers that only count hits. This changes host PCI/MSI-X state but does **not** change the vendor NPU handshake.
2. `signal_host_ready=1` — perform the first vendor-protocol MMIO write: OR `0x02` into `CTRL+0x04`. It then polls for target bit `0x04` and snapshots the five H2T descriptor slots.

Stage 2 intentionally does **not**:
- acknowledge `mvmgmt` (`0xbb66bb66`)
- set `HOST_ALIVE` (`0x08`)
- allocate DMA memory
- enable SR-IOV / VFs
- ring H2T doorbells
- initialise GIU, NWA or RPC
- create a network interface

After Stage 2, the module refuses detach. **Reboot the appliance to return the NPU to its baseline state.**

## Why five MSI-X vectors

The recovered SFOS facility configuration accounts for five target-to-host doorbells in total. The SFOS boot log also allocates five T2H IRQ vectors. The tested PCI endpoint advertises 16 MSI-X entries.

## Current evidence

See `PHASE5-DIFF.md`. The full OPNsense/SFOS snapshots show:

- BARMAP: byte-identical
- BOOTCMD: byte-identical
- CTRL: target-only state `0x01` becomes runtime state `0x0f`
- MVMGMT: target pattern `0xaa55aa55` is consumed during host initialisation
- GIU/NWA/RPC: zero/pre-host under OPNsense and populated at SFOS runtime

## Important

This source has **not** been compiled against the exact OPNsense 26.7 kernel ABI in this workspace. Build it in a matching FreeBSD/OPNsense source environment before loading it.

For the first hardware test, run **Stage 1 only**, capture the requested output, and inspect it before attempting Stage 2. See `ACTIVE-TEST.md`.
