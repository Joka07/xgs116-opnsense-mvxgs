#!/bin/sh
set -u
P="dev.mvxgs.0"
echo "=== baseline ==="
sysctl "$P.status" "$P.barmap_version" "$P.target_cookie" "$P.ctrl_flags" "$P.mvmgmt_pattern" "$P.active_stage"
echo "=== prepare five MSI-X vectors ==="
sysctl "$P.prepare_msix=1" || exit $?
echo "=== after stage1 ==="
sysctl "$P.active_stage" "$P.msix_allocated" "$P.status" "$P.ctrl_flags" "$P.mvmgmt_pattern"
sysctl "$P.irq0_hits" "$P.irq1_hits" "$P.irq2_hits" "$P.irq3_hits" "$P.irq4_hits"
echo "=== recent dmesg ==="
dmesg | tail -80
echo "=== PCI endpoint ==="
pciconf -lBbcev pci0:1:0:0
