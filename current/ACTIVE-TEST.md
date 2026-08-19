# Phase 5 hardware test sequence

## Test A — module attach (passive)

Load the ABI-matched module and inspect:

```sh
kldload ./mvxgs.ko
sysctl dev.mvxgs.0.status
sysctl dev.mvxgs.0.barmap_version
sysctl dev.mvxgs.0.target_cookie
sysctl dev.mvxgs.0.ctrl_flags
sysctl dev.mvxgs.0.mvmgmt_pattern
sysctl dev.mvxgs.0.active_stage
```

Expected baseline on the tested XGS116:

- BARMAP version: `5`
- target cookie: `0xd0fac10d`
- CTRL flags: `1`
- MVMGMT pattern: `0xaa55aa55`
- active stage: `0`

## Test B — Stage 1 only: MSI-X preparation

```sh
sysctl dev.mvxgs.0.prepare_msix=1
sysctl dev.mvxgs.0.active_stage
sysctl dev.mvxgs.0.msix_allocated
sysctl dev.mvxgs.0.status
sysctl dev.mvxgs.0.ctrl_flags
sysctl dev.mvxgs.0.mvmgmt_pattern
sysctl dev.mvxgs.0.irq0_hits dev.mvxgs.0.irq1_hits dev.mvxgs.0.irq2_hits dev.mvxgs.0.irq3_hits dev.mvxgs.0.irq4_hits
dmesg | tail -80
pciconf -lBbcev pci0:1:0:0
```

Expected:

- `active_stage=1`
- `msix_allocated=5`
- CTRL still `0x01`
- MVMGMT still `0xaa55aa55`
- no NPU protocol state has been written

At this point **stop and inspect the output before Stage 2**.

## Stage 2 — intentionally not part of the first test

The module contains the gated `signal_host_ready` path, but do not invoke it until the Stage-1 output has been reviewed. Once invoked, reboot is the supported rollback path.
