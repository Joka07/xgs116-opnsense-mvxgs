#!/bin/sh
# SPDX-License-Identifier: MIT
# Read-only host snapshot. No kldload, sysctl assignments or interface changes.
set -eu
[ "$#" -eq 1 ] || { echo 'usage: sh collect.sh NEW_OUTPUT_DIRECTORY' >&2; exit 2; }
[ "$(uname -s)" = FreeBSD ] || { echo 'FreeBSD host required' >&2; exit 2; }
umask 077
mkdir "$1"
out=$(cd "$1" && pwd)
failed=0
record() {
    name=$1; shift
    if "$@" >"$out/$name.txt" 2>"$out/$name.err"; then
        printf '%s\t0\n' "$name" >>"$out/status.tsv"
    else
        rc=$?
        printf '%s\t%s\n' "$name" "$rc" >>"$out/status.tsv"
        failed=1
    fi
}
record date date -u
record kernel uname -a
record base freebsd-version -ku
record pci pciconf -lv
record driver sysctl dev.agnic.0
record tunables sysctl hw.agnic
record interfaces ifconfig -a
record counters netstat -ibdn
record routes netstat -rn
record modules kldstat
record dmesg dmesg
# Caller must interpret these readings together with a peer capture. A TX
# consumer advance establishes only that the NPU consumed descriptors.
printf 'Snapshot: %s (command failures: %s)\n' "$out" "$failed"
exit "$failed"
