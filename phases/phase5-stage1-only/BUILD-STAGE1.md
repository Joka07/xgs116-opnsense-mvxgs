# Build on the observed OPNsense 26.7 live system

Target observed in the live system:
- FreeBSD kernel/userland: `15.1-RELEASE-p1`
- source revision from `uname -a`: `12334a596709`
- root filesystem is read-only
- `/tmp` is writable and large

The helper downloads the exact source snapshot to `/tmp`, builds with `SYSDIR=<exact-source>/sys`, and leaves `/` untouched.

From the FAT32 USB mount:

```sh
sh /tmp/usb/mvxgs-driver-phase5-stage1-only/build-on-opnsense.sh
```

Result:

```text
/tmp/mvxgs-build/module/mvxgs.ko
```

Then perform only the commands in `ACTIVE-TEST.md`.
