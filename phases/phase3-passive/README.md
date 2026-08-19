# mvxgs Phase 3 passive

Experimental, read-only FreeBSD/OPNsense diagnostic driver for the Marvell
`11ab:7080` NPU endpoint used by the tested Sophos XGS 116.

This revision validates:

- BAR map v5 / target cookie
- five target facilities
- CTRL cookie and target-ready state
- MVMGMT `0xaa55aa55` target pattern

It intentionally does **not** set HOST_READY, acknowledge pcinet, configure
MSI-X, create VFs, enable DMA, ring doorbells, or create an Ethernet interface.

See `REVERSE-ENGINEERING.md` for the recovered protocol state.

Build on a matching FreeBSD/OPNsense build host with the normal FreeBSD kernel
module build framework (`make`). Do not load on a production firewall.
