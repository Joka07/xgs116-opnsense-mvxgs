#!/bin/sh
# Read-only data collector for Sophos SFOS / installer shell.
# It does not modify PCI configuration, NPU firmware, disks, or interfaces.
# Some commands may not exist in the restricted SFOS shell; failures are kept.

OUT="${1:-/tmp/xgs-npu-collector.txt}"

run() {
    echo >> "$OUT"
    echo "===== $* =====" >> "$OUT"
    "$@" >> "$OUT" 2>&1 || true
}

: > "$OUT"
echo "Sophos XGS NPU collector - $(date 2>/dev/null)" >> "$OUT"

run uname -a
run cat /etc/os-release
run lspci -nnvv
run lspci -nnk
run ip -d link
run ip addr
run ip route
run lsmod
run dmesg

run modinfo mv_pcinet_drv
run modinfo mv_armada_drv

# Locate likely modules/firmware/scripts without changing anything.
run sh -c "find /lib /usr/lib /opt /boot -type f \( -name '*pcinet*' -o -name '*armada*' -o -name '*marvell*' -o -name '*npu*' \) 2>/dev/null | sort"

# Module metadata / hashes / printable symbols if paths can be resolved.
for mod in mv_pcinet_drv mv_armada_drv; do
    P="$(modinfo -n "$mod" 2>/dev/null)"
    if [ -n "$P" ] && [ -f "$P" ]; then
        run sha256sum "$P"
        run file "$P"
        run strings "$P"
        if command -v readelf >/dev/null 2>&1; then
            run readelf -h "$P"
            run readelf -S "$P"
            run readelf -sW "$P"
        fi
        if command -v objdump >/dev/null 2>&1; then
            run objdump -h "$P"
            run objdump -t "$P"
        fi
    fi
done

# PCI endpoint details.  First try the observed address, then search by ID.
DEV="0000:01:00.0"
if [ ! -d "/sys/bus/pci/devices/$DEV" ]; then
    DEV="$(grep -l '^0x11ab$' /sys/bus/pci/devices/*/vendor 2>/dev/null | while read f; do d=${f%/vendor}; [ "$(cat "$d/device" 2>/dev/null)" = "0x7080" ] && basename "$d" && break; done)"
fi

if [ -n "$DEV" ] && [ -d "/sys/bus/pci/devices/$DEV" ]; then
    run sh -c "echo $DEV"
    run cat "/sys/bus/pci/devices/$DEV/vendor"
    run cat "/sys/bus/pci/devices/$DEV/device"
    run cat "/sys/bus/pci/devices/$DEV/resource"
    run sh -c "hexdump -Cv /sys/bus/pci/devices/$DEV/config 2>/dev/null | head -n 64"
    run sh -c "ls -la /sys/bus/pci/devices/$DEV"
fi

# Interface-specific info if mvmgmt0 exists.
if ip link show mvmgmt0 >/dev/null 2>&1; then
    run ip -d link show mvmgmt0
    run ip addr show mvmgmt0
    if command -v ethtool >/dev/null 2>&1; then
        run ethtool -i mvmgmt0
        run ethtool -k mvmgmt0
        run ethtool -S mvmgmt0
    fi
fi

echo >> "$OUT"
echo "Collector complete: $OUT" >> "$OUT"
echo "$OUT"
