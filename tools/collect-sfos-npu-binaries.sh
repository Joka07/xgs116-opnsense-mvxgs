#!/bin/sh
# Sophos XGS NPU binary collector (read-only source side)
# Copies relevant Marvell/Sophos modules and metadata to an already-mounted USB stick.
# Usage: sh collect-sfos-npu-binaries.sh /tmp/usb

USB="${1:-/tmp/usb}"
OUT="$USB/xgs-npu-binaries"
KVER="$(uname -r 2>/dev/null)"

if [ ! -d "$USB" ]; then
  echo "USB mountpoint not found: $USB"
  exit 1
fi

mkdir -p "$OUT" || exit 1

echo "Sophos XGS NPU binary collector" > "$OUT/manifest.txt"
echo "date: $(date 2>/dev/null)" >> "$OUT/manifest.txt"
echo "kernel: $KVER" >> "$OUT/manifest.txt"
echo >> "$OUT/manifest.txt"

copy_one() {
  SRC="$1"
  if [ -f "$SRC" ]; then
    echo "COPY $SRC" | tee -a "$OUT/manifest.txt"
    cp -p "$SRC" "$OUT/" 2>>"$OUT/errors.txt" || true
  fi
}

# Core modules already identified on the XGS 116.
for f in \
  /lib/modules/$KVER/extra/mv_armada_drv.ko \
  /lib/modules/$KVER/extra/mv_pcinet_drv.ko \
  /lib/librte_pmd_armada_ep.so.20.0 \
  /lib/opkg/info/kmod-host-npu_drivers.control \
  /lib/opkg/info/kmod-host-npu_drivers.list \
  /lib/opkg/info/marvell_bsp.control \
  /lib/opkg/info/marvell_bsp.list
 do
  copy_one "$f"
 done

# Grab all related kernel modules we can find. This intentionally copies only files,
# not runtime memory and not configuration databases.
find /lib/modules/$KVER -type f \( \
  -name 'mv_*.ko' -o \
  -name 'usfp*.ko' -o \
  -name 'sp2fp*.ko' -o \
  -name 'fp2sp*.ko' -o \
  -name 'nfnetmap_queue*.ko' \
\) 2>/dev/null | while read f; do copy_one "$f"; done

# Useful package manifests: these tell us where firmware/userspace pieces live.
for f in /lib/opkg/info/*marvell* /lib/opkg/info/*npu*; do
  [ -f "$f" ] && copy_one "$f"
done

# Non-sensitive runtime metadata useful for matching symbols and layouts.
lsmod > "$OUT/lsmod.txt" 2>&1 || true
lspci -nnvv > "$OUT/lspci-nnvv.txt" 2>&1 || true
dmesg > "$OUT/dmesg.txt" 2>&1 || true
cat /sys/bus/pci/devices/0000:01:00.0/resource > "$OUT/pci-resource.txt" 2>&1 || true
cat /sys/bus/pci/devices/0000:01:00.0/config > "$OUT/pci-config.bin" 2>/dev/null || true

# Symbol addresses/names from the loaded modules. Addresses are only from this boot
# and are useful for reverse engineering; no firewall config is copied.
if [ -r /proc/kallsyms ]; then
  grep -Ei '(^|[[:space:]])(mv_|agnic|giu_|pcinet|pport|nwa_|nwa$|mvmgmt|sp2fp|fp2sp|usfp)' /proc/kallsyms \
    > "$OUT/kallsyms-marvell.txt" 2>/dev/null || true
fi

# Strings and file metadata if tools exist.
for f in "$OUT"/*.ko "$OUT"/*.so*; do
  [ -f "$f" ] || continue
  b="$(basename "$f")"
  file "$f" > "$OUT/$b.file.txt" 2>&1 || true
  sha256sum "$f" > "$OUT/$b.sha256.txt" 2>&1 || true
  strings "$f" > "$OUT/$b.strings.txt" 2>&1 || true
  if command -v readelf >/dev/null 2>&1; then
    readelf -h "$f" > "$OUT/$b.elf-header.txt" 2>&1 || true
    readelf -sW "$f" > "$OUT/$b.symbols.txt" 2>&1 || true
    readelf -rW "$f" > "$OUT/$b.relocs.txt" 2>&1 || true
  fi
done

sync

echo >> "$OUT/manifest.txt"
echo "DONE" >> "$OUT/manifest.txt"
echo "Collector complete: $OUT"
echo "After this: sync ; umount $USB"
