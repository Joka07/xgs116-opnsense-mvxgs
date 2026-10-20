#!/bin/sh
# SPDX-License-Identifier: MIT
set -eu
HERE=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
. "$HERE/common.sh"
META=/usr/local/etc/xgs116-agnic/module.meta
MODULE=/boot/modules/if_agnic.ko
case "${1:-}" in
check)
    xgs_verify_module "$MODULE" "$META"
    xgs_platform "$META"
    xgs_ready || { xgs_error 'AGNIC is not initialized or recovery is required'; exit 1; }
    echo 'PASS: management/datapath initialized; port1..port9 present. This is not a forwarding test.'
    ;;
start)
    [ "$(id -u)" = 0 ] || { xgs_error 'Root is required to load the kernel module'; exit 1; }
    LOCK=/var/run/xgs116-agnic.lock
    FAILED=/var/run/xgs116-agnic.failed
    [ ! -e "$FAILED" ] || { xgs_log 'Startup already failed this boot; no automatic reload. Capture diagnostics.'; exit 1; }
    mkdir "$LOCK" 2>/dev/null || { xgs_error 'Another startup is running'; exit 1; }
    trap 'rmdir "$LOCK" 2>/dev/null || :' EXIT
    trap 'exit 1' HUP INT TERM
    if ! xgs_verify_module "$MODULE" "$META" || ! xgs_platform "$META" || ! xgs_pci; then
        : > "$FAILED"; xgs_log 'Preflight failed; module not loaded'; exit 1
    fi
    if kldstat -q -n if_agnic; then
        # An already attached driver must never be unloaded/reloaded implicitly.
        xgs_log 'if_agnic already loaded; checking existing state'
    elif ! kldload "$MODULE"; then
        : > "$FAILED"; xgs_log 'Module load failed; no retry this boot'; exit 1
    fi
    if ! xgs_wait_ready 60; then
        : > "$FAILED"; xgs_log 'Startup failed; no driver reload or NPU restart attempted'; exit 1
    fi
    xgs_log 'Management/datapath initialized and port1..port9 present; physical forwarding still requires validation'
    ;;
diagnose)
    date -u
    uname -a
    freebsd-version -ku
    opnsense-version
    pciconf -l | grep -i 'chip=0x708011ab' || :
    kldstat
    sysctl dev.agnic.0 || :
    for p in 1 2 3 4 5 6 7 8 9; do ifconfig "port$p" || :; done
    netstat -idb
    dmesg | tail -100
    ;;
*) echo 'Usage: xgs116-agnic {start|check|diagnose}' >&2; exit 2;;
esac
