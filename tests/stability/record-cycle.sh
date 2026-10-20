#!/bin/sh
# SPDX-License-Identifier: MIT
# Record one side of an operator-controlled reboot/power/update test.
set -eu
if [ "$#" -ne 3 ]; then
    echo 'usage: sh record-cycle.sh CASE before|after NEW_OUTPUT_DIRECTORY' >&2
    exit 2
fi
case "$1" in warm|cold|power-loss|host-reboot|npu-reboot|opnsense-update) ;; *) echo 'invalid case' >&2; exit 2;; esac
case "$2" in before|after) ;; *) echo 'expected before or after' >&2; exit 2;; esac
[ ! -e "$3" ] || { echo "output already exists" >&2; exit 2; }
here=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
# collect.sh preserves each command exit status and does not change hardware.
rc=0
sh "$here/../network/collect.sh" "$3" || rc=$?
[ -d "$3" ] || exit "$rc"
printf 'case\t%s\nphase\t%s\nstatus\tOBSERVATION_ONLY\n' "$1" "$2" >"$3/cycle.tsv"
sysctl kern.boottime >"$3/boottime.txt" || rc=1
printf 'Compare before/after MACs, interface mapping, ring progress and independent peer traffic. A snapshot alone is not a passed recovery test.\n'
exit "$rc"
