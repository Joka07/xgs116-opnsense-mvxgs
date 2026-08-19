#!/bin/sh
# Read-only SFOS snapshot collector for Sophos XGS 116 Marvell NPU.
# It reads PCIe BAR-backed shared-memory regions through /dev/mem.
# It NEVER writes to /dev/mem or PCI config space.

OUT="${1:-/tmp/usb/xgs-sfos-mmio}"
mkdir -p "$OUT" || exit 1

if [ ! -r /dev/mem ]; then
    echo "ERROR: /dev/mem is not readable" >&2
    exit 1
fi

log="$OUT/collector.txt"
: > "$log"
echo "XGS SFOS MMIO snapshot - $(date 2>/dev/null)" >> "$log"
uname -a >> "$log" 2>&1

# Physical page numbers (address / 4096), confirmed on this XGS116 sample.
# BAR0  0xfe000000: GIU at +0x0000, NWA at +0x4000
# BAR2 window base 0xfdefc000: CTRL +0x0000, MVMGMT +0x1000, RPC +0x2000
# BAR2 tail: BARMAP 0xfdffe000, BOOTCMD 0xfdfff000

dump_pages() {
    name="$1"; skip="$2"; count="$3"
    echo "dump $name: skip=$skip count=$count" >> "$log"
    dd if=/dev/mem of="$OUT/$name.bin" bs=4096 skip="$skip" count="$count" >> "$log" 2>&1 || return 1
    if command -v hexdump >/dev/null 2>&1; then
        hexdump -C -n 512 "$OUT/$name.bin" > "$OUT/$name.head.txt" 2>&1 || true
    fi
    return 0
}

# BAR0 shared-memory facilities.
dump_pages giu     1040384 4      # 0xfe000000, 0x4000 bytes
dump_pages nwa     1040388 16     # 0xfe004000, 0x10000 bytes

# BAR2 mapped facility window.
dump_pages ctrl    1040124 1      # 0xfdefc000
dump_pages mvmgmt  1040125 1      # 0xfdefd000
dump_pages rpc     1040126 1      # 0xfdefe000 (first page only)

# BAR2 metadata pages.
dump_pages barmap  1040382 1      # 0xfdffe000
dump_pages bootcmd 1040383 1      # 0xfdfff000

# Useful state around the active driver; failures are harmless on stripped SFOS.
cat /sys/bus/pci/devices/0000:01:00.0/sriov_numvfs > "$OUT/sriov_numvfs.txt" 2>&1 || true
cat /sys/bus/pci/devices/0000:01:00.0/sriov_totalvfs > "$OUT/sriov_totalvfs.txt" 2>&1 || true
readlink /sys/bus/pci/devices/0000:01:00.0/driver > "$OUT/pf-driver.txt" 2>&1 || true
ip -d link > "$OUT/ip-link.txt" 2>&1 || true
dmesg > "$OUT/dmesg.txt" 2>&1 || true
sync

echo "Collector complete: $OUT" | tee -a "$log"
