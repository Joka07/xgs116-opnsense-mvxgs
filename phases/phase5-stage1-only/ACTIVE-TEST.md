# Stage-1-only hardware test

This build intentionally contains no HOST_READY/MMIO write path.

## Test A — passive attach

```sh
kldload ./mvxgs.ko
sysctl dev.mvxgs.0.status
sysctl dev.mvxgs.0.barmap_version
sysctl dev.mvxgs.0.target_cookie
sysctl dev.mvxgs.0.ctrl_flags
sysctl dev.mvxgs.0.mvmgmt_pattern
sysctl dev.mvxgs.0.active_stage
```

Expected baseline:
- BARMAP version `5`
- target cookie `0xd0fac10d`
- CTRL flags `1`
- MVMGMT pattern `0xaa55aa55`
- active stage `0`

## Test B — prepare five MSI-X vectors

```sh
sysctl dev.mvxgs.0.prepare_msix=1
sysctl dev.mvxgs.0.active_stage
sysctl dev.mvxgs.0.msix_allocated
sysctl dev.mvxgs.0.status
sysctl dev.mvxgs.0.ctrl_flags
sysctl dev.mvxgs.0.mvmgmt_pattern
sysctl dev.mvxgs.0.irq0_hits dev.mvxgs.0.irq1_hits dev.mvxgs.0.irq2_hits dev.mvxgs.0.irq3_hits dev.mvxgs.0.irq4_hits
dmesg | tail -100
pciconf -lBbcev pci0:1:0:0
```

Expected:
- `active_stage=1`
- `msix_allocated=5`
- CTRL remains `0x01`
- MVMGMT remains `0xaa55aa55`
- no NPU protocol/MMIO state has been written

Stop after this test and review the output.
