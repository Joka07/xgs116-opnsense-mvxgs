#!/bin/sh
# Passive read-only probe for the Sophos XGS 116 Marvell NPU BAR map.
# Target: the user's observed OPNsense/FreeBSD BAR2 mapping:
#   BAR2 base 0xfd000000, size 0x01000000
# The vendor BAR map lives in the last 4 KiB page => 0xfdfff000.
#
# This script READS physical memory only. It never writes to /dev/mem.

set -u

OUT=/tmp/mvxgs-barmap-page.bin
ERR=/tmp/mvxgs-dd.err
# 0xfdfff000 / 4096 = 1040383
PAGE_SKIP=1040383

if [ "$(id -u)" != "0" ]; then
    echo "ERROR: run as root"
    exit 1
fi

if [ ! -c /dev/mem ]; then
    echo "ERROR: /dev/mem is not available on this live system"
    exit 2
fi

echo "== mvxgs passive OPNsense probe =="
echo "Reading 4 KiB from physical 0xfdfff000 (read-only)..."
rm -f "$OUT" "$ERR"

if ! dd if=/dev/mem of="$OUT" bs=4096 skip="$PAGE_SKIP" count=1 2>"$ERR"; then
    echo "ERROR: /dev/mem read failed:"
    cat "$ERR"
    exit 3
fi

if [ -s "$ERR" ]; then
    cat "$ERR"
fi

echo
echo "First 128 bytes:"
hexdump -C -n 128 "$OUT"

echo
echo "First two 32-bit words (expected: 00000005 d0fac10d):"
od -An -tx4 -N8 "$OUT"

echo
echo "Saved full 4 KiB page to: $OUT"
echo "Do NOT use dd with of=/dev/mem. This probe is read-only."
