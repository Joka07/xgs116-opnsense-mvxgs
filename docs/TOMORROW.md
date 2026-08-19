# Tomorrow: Phase 8 hardware test

Phase 8 has **not been tested yet**. Start from a clean reboot because the last Phase 7 run left CTRL at `0x03`.

## 0. Put these files on the FAT32 USB stick

- folder `mvxgs-driver-phase8-hostalive/`
- `opnsense-src-12334a596709.tar.gz`

The exact OPNsense source snapshot is needed because the live installer has no working onboard NIC and `/usr/src` is unavailable.

## 1. Reboot to reset NPU state

If a USB filesystem is mounted:

```sh
cd /
sync
umount /tmp/usb
reboot
```

After OPNsense comes back, enter shell and mount the stick:

```sh
mkdir -p /tmp/usb
mount_msdosfs /dev/da1s1 /tmp/usb
```

If the USB device number changes, check `camcontrol devlist` / `ls /dev/da*` first.

## 2. Build Phase 8 offline

```sh
cd /tmp/usb/mvxgs-driver-phase8-hostalive
sh ./build-phase8-offline.sh
```

Expected module:

```text
/tmp/mvxgs-phase8/module/mvxgs.ko
```

Before loading, verify:

```sh
ls -lh /tmp/mvxgs-phase8/module/mvxgs.ko
file /tmp/mvxgs-phase8/module/mvxgs.ko
sha256 /tmp/mvxgs-phase8/module/mvxgs.ko
```

If the build fails, stop and preserve the compiler output.

## 3. Load Phase 8 and verify untouched baseline

```sh
kldload /tmp/mvxgs-phase8/module/mvxgs.ko
sysctl dev.mvxgs.0.ctrl_flags
sysctl dev.mvxgs.0.mvmgmt_pattern
sysctl dev.mvxgs.0.active_stage
```

Expected:

- CTRL `1` (`0x01`)
- MVMGMT `2857740885` (`0xaa55aa55`)
- active stage `0`

Do not continue if the baseline differs.

## 4. Enable PCI bus mastering

```sh
sysctl dev.mvxgs.0.enable_busmaster=1
pciconf -r -h pci0:1:0:0 0x04
sysctl dev.mvxgs.0.ctrl_flags
sysctl dev.mvxgs.0.mvmgmt_pattern
```

Expected before MSI-X:

- PCI command `0006`
- CTRL still `1`
- MVMGMT still `0xaa55aa55`

## 5. Allocate five MSI-X vectors

```sh
sysctl dev.mvxgs.0.prepare_msix=1
pciconf -r -h pci0:1:0:0 0x04
sysctl dev.mvxgs.0.msix_allocated
sysctl dev.mvxgs.0.ctrl_flags
sysctl dev.mvxgs.0.mvmgmt_pattern
```

Expected:

- PCI command `0406`
- MSI-X allocated `5`
- CTRL still `1`
- MVMGMT still `0xaa55aa55`

## 6. HOST_READY

Arm first (arming does not write MMIO):

```sh
sysctl dev.mvxgs.0.arm_host_ready=1
sysctl dev.mvxgs.0.host_ready_armed
sysctl dev.mvxgs.0.status
```

Expected armed = `1`.

Then exactly once:

```sh
sysctl dev.mvxgs.0.signal_host_ready=1
```

Phase 8 should return immediately. Check:

```sh
sysctl dev.mvxgs.0.ctrl_flags
sysctl dev.mvxgs.0.status
```

Expected CTRL = `3` (`0x03`).

## 7. HOST_ALIVE — the new experiment

Arm it first:

```sh
sysctl dev.mvxgs.0.arm_host_alive=1
sysctl dev.mvxgs.0.host_alive_armed
sysctl dev.mvxgs.0.ctrl_flags
sysctl dev.mvxgs.0.status
```

Expected:

- armed = `1`
- CTRL still `3`

Then send **one** HOST_ALIVE pulse:

```sh
sysctl dev.mvxgs.0.signal_host_alive=1
```

Do not repeat this command, even if it times out.

Immediately capture:

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

## 8. What success looks like

The key question is whether target bit `0x04` appears after HOST_ALIVE.

Possible useful result:

- CTRL goes from `0x03` to a value containing `0x08` and then target `0x04`
- ideally final CTRL `0x0f`
- one or more H2T descriptors become valid/non-zero
- possibly MSI-X handler counters increment

If CTRL stays at `0x0b` with no `0x04`, the heartbeat bit alone is not sufficient and the next investigation should compare additional vendor initialization around the heartbeat / facility worker.

## 9. After any active HOST_READY/HOST_ALIVE test

Do **not** unload the driver. Reboot is the reset path.
