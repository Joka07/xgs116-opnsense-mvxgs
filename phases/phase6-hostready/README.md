# mvxgs Phase 6

Experimental controlled HOST_READY handshake for the Sophos XGS 116 Marvell
PF `11ab:7080`.

Validated prerequisites on the user's XGS116:
- BARMAP v5 / cookie `0xd0fac10d`
- CTRL cookie `0xafacafac`, flags `0x01`
- MVMGMT target pattern `0xaa55aa55`
- exactly five FreeBSD MSI-X vectors allocated successfully
- no CTRL/MVMGMT change from MSI-X setup

Phase 6 adds a two-step arm/signal gate. The only NPU protocol write is
`CTRL.flags |= 0x02`. See `PHASE6-TEST.md`.
