# XGS116 / Marvell 11ab:7080 — Phase 4 findings

## Verified target state under OPNsense, before host initialization

Observed manually on the XGS116:

- BAR-map version: `5`
- target cookie: `0xd0fac10d`
- control cookie: `0xafacafac`
- control flags: `0x00000001`
- mvmgmt handshake at `mvmgmt + 0x18`: `0xaa55aa55`
- GIU first page: zero before host initialization
- NWA first page: zero before host initialization
- BOOTCMD page begins with `BOOTCMD!`, version/state word `2`

This proves that the target/NPU is already alive before the host driver performs
its active initialization.

## Verified steady-state SFOS snapshot

A read-only MMIO snapshot taken after SFOS fully initialized shows:

### CTRL

- `+0x00 = 0xafacafac`
- `+0x04 = 0x0000000f`
- `+0x08 = 0x00000005`
- `+0x10 = 0x00280040`
- `+0x18 = 0x000000a4`

Reverse engineering of `mv_armada_drv.ko` proves:

- bit `0x01` is waited on before host initialization (target-ready condition)
- the host ORs bit `0x02` after facility/interrupt setup
- the H2T-doorbell worker waits for bit `0x04` before consuming target H2T descriptors
- `mv_facility_host_is_alive()` ORs bit `0x08`

Therefore runtime `0x0f` is consistent with all four handshake conditions being set.
The precise vendor name for bit `0x04` is not known; functionally it gates availability
of target-provided Host->Target doorbell descriptors.

### Static facility configuration recovered from mv_armada_drv.ko

The five configured facilities are:

| ID | name | H->T doorbells | T->H doorbells | DMA engines |
|---:|---|---:|---:|---:|
| 0 | ctrl | 0 | 0 | 0 |
| 1 | mvmgmt | 0 | 1 | 1 |
| 2 | nwa | 0 | 0 | 0 |
| 3 | rpc | 1 | 0 | 1 |
| 4 | giu | 4 | 4 | 0 |

Totals: 5 Host->Target doorbells and 5 Target->Host/MSI-X doorbells.

### MVMGMT

Before host initialization:

- `+0x10 = 0x80`
- `+0x14 = 0x01`
- `+0x18 = 0xaa55aa55`

`mv_pcinet_drv.ko` waits for `0xaa55aa55`, writes `0xbb66bb66`, and then calls
its main `pcinet_init()` routine.

After SFOS initialization the same region contains non-zero host/queue addresses and
`+0x10 = 0x83`; the original handshake magic has been consumed/cleared.

### NWA

After SFOS initialization NWA begins with `0xcafebabe`. Static disassembly of
`mv_nwa_host.ko` shows an explicit write of `0xcafebabe`, so this is a host-generated
NWA initialization marker, not a target boot signature.

### GIU / RPC

Both regions are zero before host initialization (observed first page for GIU/NWA)
and populated under SFOS. They belong to later host-side initialization stages.

## Safe next step

Capture the exact same full windows under OPNsense using
`OPNSENSE-MMIO-COLLECTOR.sh`, then compare against the SFOS snapshot. Do not set
CTRL host-ready or acknowledge mvmgmt yet: SFOS allocates/configures the required
interrupt/doorbell state before setting host-ready.

## Planned active Phase 5

Only after the full pre-init snapshot is captured:

1. map and validate facilities
2. allocate exactly five MSI-X vectors
3. construct local per-facility T->H vector map
4. prepare H->T descriptor discovery state
5. set CTRL host-ready (`0x02`) only after 1-4 succeeded
6. wait for target-side `0x04`
7. consume target H->T doorbell descriptors
8. acknowledge/initialize mvmgmt
9. bring up a minimal management transport before GIU datapath work

No SR-IOV or packet DMA should be enabled until the management/control path is stable.
