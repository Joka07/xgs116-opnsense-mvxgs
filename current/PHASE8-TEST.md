# Phase 8 — one-shot HOST_ALIVE test

The current Phase-7 boot is already at CTRL `0x03`. Reboot before testing.

## Build after reboot

```sh
mount_msdosfs /dev/da1s1 /tmp/usb
cd /tmp/usb/mvxgs-driver-phase8-hostalive
sh ./build-phase8-offline.sh
```

## Load and reproduce Stage 1

```sh
kldload /tmp/mvxgs-phase8/module/mvxgs.ko
sysctl dev.mvxgs.0.enable_busmaster=1
sysctl dev.mvxgs.0.prepare_msix=1
pciconf -r -h pci0:1:0:0 0x04
```

Expected PCI command: `0406`.

## HOST_READY

```sh
sysctl dev.mvxgs.0.arm_host_ready=1
sysctl dev.mvxgs.0.signal_host_ready=1
sysctl dev.mvxgs.0.ctrl_flags
sysctl dev.mvxgs.0.status
```

Expected CTRL: `3`. Phase 8 returns immediately instead of timing out here.

## Arm HOST_ALIVE — no write

```sh
sysctl dev.mvxgs.0.arm_host_alive=1
sysctl dev.mvxgs.0.host_alive_armed
sysctl dev.mvxgs.0.ctrl_flags
sysctl dev.mvxgs.0.status
```

Expected: armed `1`, CTRL still `3`.

## One HOST_ALIVE pulse

```sh
sysctl dev.mvxgs.0.signal_host_alive=1
```

Do not repeat it.

Immediately collect:

```sh
sysctl dev.mvxgs.0.ctrl_flags
sysctl dev.mvxgs.0.active_stage
sysctl dev.mvxgs.0.host_alive_sent
sysctl dev.mvxgs.0.status
sysctl dev.mvxgs.0.h2t0_valid dev.mvxgs.0.h2t0_target_offset dev.mvxgs.0.h2t0_data
sysctl dev.mvxgs.0.h2t1_valid dev.mvxgs.0.h2t1_target_offset dev.mvxgs.0.h2t1_data
sysctl dev.mvxgs.0.h2t2_valid dev.mvxgs.0.h2t2_target_offset dev.mvxgs.0.h2t2_data
sysctl dev.mvxgs.0.h2t3_valid dev.mvxgs.0.h2t3_target_offset dev.mvxgs.0.h2t3_data
sysctl dev.mvxgs.0.h2t4_valid dev.mvxgs.0.h2t4_target_offset dev.mvxgs.0.h2t4_data
sysctl dev.mvxgs.0.irq0_hits dev.mvxgs.0.irq1_hits dev.mvxgs.0.irq2_hits dev.mvxgs.0.irq3_hits dev.mvxgs.0.irq4_hits
dmesg | tail -120
```

Desired result: CTRL gains target bit `0x04`; depending on heartbeat consumption
the observed value may be `0x0f` or another combination containing bits
`0x01|0x02|0x04`.

After HOST_READY/HOST_ALIVE, reboot to reset; do not unload.
