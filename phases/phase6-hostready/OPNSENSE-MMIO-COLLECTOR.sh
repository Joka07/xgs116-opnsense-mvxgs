#!/bin/sh
# Read-only MMIO snapshot collector for OPNsense/FreeBSD on Sophos XGS116.
# Requires /dev/mem. DOES NOT WRITE TO MMIO OR PCI CONFIGURATION.
set -u
OUT="${1:-/tmp/xgs-opnsense-mmio}"
mkdir -p "$OUT" || exit 1

log() { echo "$*" | tee -a "$OUT/collector.txt"; }
dump() {
    name="$1"; skip="$2"; count="$3"
    log "dump $name: skip=$skip count=$count"
    dd if=/dev/mem of="$OUT/$name.bin" bs=4096 skip="$skip" count="$count" 2>>"$OUT/collector.txt" || exit 1
}

: > "$OUT/collector.txt"
log "XGS OPNsense MMIO snapshot - $(date 2>/dev/null)"
uname -a >> "$OUT/collector.txt" 2>&1 || true
pciconf -lBbcev pci0:1:0:0 > "$OUT/pciconf.txt" 2>&1 || true

# BAR0
# 0xfe000000 GIU, 16 KiB
# 0xfe004000 NWA, 64 KiB
dump giu     1040384 4
dump nwa     1040388 16

# PF BAR2 host window starts at 0xfdefc000
dump ctrl    1040124 1
dump mvmgmt  1040125 1
dump rpc     1040126 1

# End-of-BAR2 target metadata pages
dump barmap  1040382 1
dump bootcmd 1040383 1

sync
log "Collector complete: $OUT"
echo "$OUT"
