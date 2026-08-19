# Phase 7 — PCI Bus Mastering A/B test

## Why this phase exists

Observed PCI Command register:

- OPNsense/FreeBSD before busmaster: `0x0402`
- Fully running SFOS: `0x0406`

The only differing low command bit is `0x0004` (`BUSMASTEREN`).

The real SFOS `mv_armada_drv.ko` calls Linux `pci_set_master()` before the
facility handshake. FreeBSD's equivalent is `pci_enable_busmaster()`.

The previous Phase 6 test successfully wrote `HOST_READY` (`CTRL 0x01 -> 0x03`)
but the target never set bit `0x04`, so Phase 7 tests bus mastering as the
single changed variable.

## Important

The current Phase-6 boot is already at `CTRL=0x03`. Reboot before this test.

## After reboot: build offline

Mount the USB stick and build:

```sh
cd /tmp/usb/mvxgs-driver-phase7-busmaster
sh ./build-phase7-offline.sh
```

If `/tmp` was cleared by reboot, the script extracts the exact source tarball
`/tmp/usb/opnsense-src-12334a596709.tar.gz`.

## Load and validate baseline

```sh
kldload /tmp/mvxgs-phase7/module/mvxgs.ko
sysctl dev.mvxgs.0.pci_command_initial
sysctl dev.mvxgs.0.pci_command
sysctl dev.mvxgs.0.ctrl_flags
sysctl dev.mvxgs.0.mvmgmt_pattern
```

Expected PCI command is decimal `1026` = hex `0x0402`.

## Enable bus mastering — PCI config only

```sh
sysctl dev.mvxgs.0.enable_busmaster=1
sysctl dev.mvxgs.0.rescan=1
sysctl dev.mvxgs.0.pci_command
sysctl dev.mvxgs.0.busmaster_enabled_by_driver
pciconf -r -h pci0:1:0:0 0x04
```

Expected:

- `pciconf`: `0406`
- `busmaster_enabled_by_driver=1`
- CTRL remains `0x01`
- MVMGMT remains `0xaa55aa55`

Do not continue if the PCI command is not `0406`.

## Prepare MSI-X

```sh
sysctl dev.mvxgs.0.prepare_msix=1
sysctl dev.mvxgs.0.msix_allocated
sysctl dev.mvxgs.0.ctrl_flags
sysctl dev.mvxgs.0.mvmgmt_pattern
```

Expected: five MSI-X, CTRL still `1`.

## Arm

```sh
sysctl dev.mvxgs.0.arm_host_ready=1
sysctl dev.mvxgs.0.host_ready_armed
sysctl dev.mvxgs.0.status
```

Expected: armed `1`.

## Signal HOST_READY exactly once

```sh
sysctl dev.mvxgs.0.signal_host_ready=1
```

Do not repeat on timeout.

Immediately collect:

```sh
sysctl dev.mvxgs.0.ctrl_flags
sysctl dev.mvxgs.0.active_stage
sysctl dev.mvxgs.0.host_ready_sent
sysctl dev.mvxgs.0.status
sysctl dev.mvxgs.0.h2t0_valid
sysctl dev.mvxgs.0.h2t0_target_offset
sysctl dev.mvxgs.0.h2t0_data
sysctl dev.mvxgs.0.irq0_hits dev.mvxgs.0.irq1_hits dev.mvxgs.0.irq2_hits dev.mvxgs.0.irq3_hits dev.mvxgs.0.irq4_hits
pciconf -r -h pci0:1:0:0 0x04
dmesg | tail -120
```

Desired result is target bit `0x04`, i.e. CTRL becoming at least `0x07`, and
the first H2T descriptor becoming non-zero.

After HOST_READY, do not unload. Reboot to reset.
