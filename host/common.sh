#!/bin/sh
# SPDX-License-Identifier: MIT
# Shared, side-effect-free validation routines. Never source artifact metadata.
XGS116_SOURCE_REV=12334a596709d195acb73f0f069da82c570a3d84
xgs_error() { printf 'xgs116-agnic: %s\n' "$*" >&2; }
xgs_log() { xgs_error "$*"; logger -t xgs116-agnic "$*" 2>/dev/null || :; }
xgs_hash() {
    if command -v sha256 >/dev/null 2>&1; then sha256 -q "$1"
    else sha256sum "$1" | awk '{print $1}'; fi
}
xgs_field() { awk -v key="$2" 'index($0,key "=")==1 {sub(/^[^=]*=/, ""); print}' "$1"; }
xgs_validate_meta() {
    [ -f "$1" ] && [ ! -L "$1" ] || { xgs_error 'Missing or symlinked module.meta'; return 1; }
    awk '
      /^[a-z_][a-z0-9_]*=/ {
        key=$0; sub(/=.*/, "", key);
        if (key !~ /^(format|architecture|freebsd_kernel|opnsense_series|source_revision|kernel_ident|module_sha256)$/ || seen[key]++) exit 1;
        if (length($0)==length(key)+1) exit 1;
        n++; next
      }
      {exit 1}
      END {if(n!=7) exit 1}
    ' "$1" || { xgs_error 'Invalid or duplicate metadata fields'; return 1; }
    [ "$(xgs_field "$1" format)" = 1 ] &&
    [ "$(xgs_field "$1" architecture)" = amd64 ] &&
    [ "$(xgs_field "$1" freebsd_kernel)" = 15.1-RELEASE-p1 ] &&
    [ "$(xgs_field "$1" opnsense_series)" = 26.7 ] &&
    [ "$(xgs_field "$1" source_revision)" = "$XGS116_SOURCE_REV" ] || {
        xgs_error 'Unsupported module target or source revision'; return 1;
    }
    xgs_field "$1" module_sha256 | awk 'length($0)!=64 || /[^0-9a-f]/ {exit 1}' || {
        xgs_error 'Invalid module digest'; return 1;
    }
}
xgs_verify_module() {
    xgs_validate_meta "$2" || return 1
    [ -f "$1" ] && [ ! -L "$1" ] || { xgs_error 'Missing or symlinked kernel module'; return 1; }
    [ "$(xgs_hash "$1")" = "$(xgs_field "$2" module_sha256)" ] || {
        xgs_error 'Kernel module SHA256 mismatch'; return 1;
    }
    file -b "$1" | grep -Eq 'ELF 64-bit LSB relocatable, x86-64' || {
        xgs_error 'Expected amd64 ELF relocatable kernel module'; return 1;
    }
}
xgs_platform() {
    xgs_validate_meta "$1" || return 1
    [ "$(uname -s)" = FreeBSD ] && [ "$(uname -m)" = amd64 ] || {
        xgs_error 'Requires FreeBSD amd64'; return 1;
    }
    [ "$(freebsd-version -k)" = "$(xgs_field "$1" freebsd_kernel)" ] || {
        xgs_error 'Installed kernel release differs from module target'; return 1;
    }
    [ "$(uname -r)" = "$(xgs_field "$1" freebsd_kernel)" ] || {
        xgs_error 'Running kernel release differs from module target (pending reboot/update?)'; return 1;
    }
    [ "$(uname -v)" = "$(xgs_field "$1" kernel_ident)" ] || {
        xgs_error 'Exact running kernel build differs from module target; rebuild required'; return 1;
    }
    # opnsense-version emits "OPNsense 26.7..."; accept point releases, reject 26.70.
    opnsense-version | grep -Eq '^OPNsense 26\.7([. _-]|$)' || {
        xgs_error 'Requires OPNsense 26.7 series'; return 1;
    }
}
xgs_pci() {
    xgs_endpoint=$(pciconf -l | awk 'tolower($0) ~ /chip=0x708011ab/ {print $1}')
    [ "$(printf '%s\n' "$xgs_endpoint" | awk 'NF {n++} END {print n+0}')" = 1 ] || {
        xgs_error 'Expected exactly one Marvell PCI endpoint 11ab:7080'; return 1;
    }
    case "$xgs_endpoint" in
    none*@*|agnic0@*) ;;
    *) xgs_error 'Marvell endpoint is bound to a conflicting driver; use console recovery to disable it'; return 1;;
    esac
}

xgs_ready() {
    [ "$(sysctl -n dev.agnic.0.recovery_required 2>/dev/null)" = 0 ] &&
    [ "$(sysctl -n dev.agnic.0.mgmt_ready 2>/dev/null)" = 1 ] &&
    [ "$(sysctl -n dev.agnic.0.datapath_ready 2>/dev/null)" = 1 ] &&
    [ "$(sysctl -n dev.agnic.0.nports 2>/dev/null)" = 9 ] || return 1
    xgs_interfaces=$(ifconfig -l) || return 1
    for xgs_port in 1 2 3 4 5 6 7 8 9; do
        case " $xgs_interfaces " in *" port$xgs_port "*) ;; *) return 1;; esac
    done
}
xgs_wait_ready() {
    xgs_remaining=$1
    while :; do
        if [ "$(sysctl -n dev.agnic.0.recovery_required 2>/dev/null)" = 1 ]; then
            xgs_error 'Driver requires recovery; capture diagnostics and use a controlled cold restart'; return 1
        fi
        xgs_ready && return 0
        [ "$xgs_remaining" -gt 0 ] || { xgs_error 'AGNIC handshake/9-port readiness deadline expired'; return 1; }
        sleep 1
        xgs_remaining=$((xgs_remaining - 1))
    done
}
