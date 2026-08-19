# Phase 6 — first controlled HOST_READY write

This revision performs only one NPU protocol write:
`CTRL.flags |= 0x02`.

It does not acknowledge MVMGMT, set HOST_ALIVE, enable SR-IOV, configure
packet DMA, ring doorbells, or create an interface.

## Build
```sh
cd /tmp/usb/mvxgs-driver-phase6-hostready
sh ./build-phase6-on-current-opnsense.sh
```

## Replace Stage-1-only module
```sh
kldunload mvxgs
kldstat | grep mvxgs
kldload /tmp/mvxgs-phase6/module/mvxgs.ko
```
`kldstat | grep mvxgs` should print nothing between unload and load.

## Validate baseline
```sh
sysctl dev.mvxgs.0.ctrl_flags
sysctl dev.mvxgs.0.mvmgmt_pattern
sysctl dev.mvxgs.0.active_stage
```
Expected: `1`, `2857740885`, `0`.

## Prepare MSI-X again
```sh
sysctl dev.mvxgs.0.prepare_msix=1
sysctl dev.mvxgs.0.active_stage
sysctl dev.mvxgs.0.msix_allocated
sysctl dev.mvxgs.0.ctrl_flags
sysctl dev.mvxgs.0.mvmgmt_pattern
```
Expected: stage `1`, MSI-X `5`, CTRL `1`, MVMGMT `2857740885`.

## Arm (no MMIO write)
```sh
sysctl dev.mvxgs.0.arm_host_ready=1
sysctl dev.mvxgs.0.host_ready_armed
sysctl dev.mvxgs.0.status
```
Expected: armed `1`.

## First protocol write
Keep the serial console open:
```sh
sysctl dev.mvxgs.0.signal_host_ready=1
```

Then immediately:
```sh
sysctl dev.mvxgs.0.ctrl_flags
sysctl dev.mvxgs.0.active_stage
sysctl dev.mvxgs.0.host_ready_sent
sysctl dev.mvxgs.0.host_ready_armed
sysctl dev.mvxgs.0.status
sysctl dev.mvxgs.0.h2t0_valid dev.mvxgs.0.h2t0_target_offset dev.mvxgs.0.h2t0_data
sysctl dev.mvxgs.0.h2t1_valid dev.mvxgs.0.h2t1_target_offset dev.mvxgs.0.h2t1_data
sysctl dev.mvxgs.0.h2t2_valid dev.mvxgs.0.h2t2_target_offset dev.mvxgs.0.h2t2_data
sysctl dev.mvxgs.0.h2t3_valid dev.mvxgs.0.h2t3_target_offset dev.mvxgs.0.h2t3_data
sysctl dev.mvxgs.0.h2t4_valid dev.mvxgs.0.h2t4_target_offset dev.mvxgs.0.h2t4_data
sysctl dev.mvxgs.0.irq0_hits dev.mvxgs.0.irq1_hits dev.mvxgs.0.irq2_hits dev.mvxgs.0.irq3_hits dev.mvxgs.0.irq4_hits
dmesg | tail -120
```

Stop there. After HOST_READY, do not unload the driver; reboot is the reset.
