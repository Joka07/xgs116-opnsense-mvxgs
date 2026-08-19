# Offline build on the XGS116 OPNsense live system

The live OPNsense currently has no working Ethernet interface, so it cannot
download its own source tree.

On another PC, download the exact OPNsense source snapshot for commit:

`12334a596709`

Save the archive on the FAT32 USB stick as:

`opnsense-src-12334a596709.tar.gz`

Put it either at the USB root or beside this driver folder.

Then on OPNsense:

```sh
mount_msdosfs /dev/da1s1 /tmp/usb
cd /tmp/usb/mvxgs-driver-phase5-stage1-only-offline
sh ./build-on-opnsense-offline.sh
```

The build runs entirely in `/tmp`.

Expected output module:

`/tmp/mvxgs-build/module/mvxgs.ko`
