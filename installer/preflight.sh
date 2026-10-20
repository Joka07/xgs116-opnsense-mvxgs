#!/bin/sh
# SPDX-License-Identifier: MIT
set -eu
HERE=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
. "$HERE/../host/common.sh"
usage() { echo 'Usage: preflight.sh BUNDLE_DIRECTORY' >&2; exit 2; }
[ "$#" = 1 ] || usage
BUNDLE=$1
META="$BUNDLE/payload/usr/local/etc/xgs116-agnic/module.meta"
MODULE="$BUNDLE/payload/boot/modules/if_agnic.ko"
xgs_verify_module "$MODULE" "$META"
xgs_platform "$META"
xgs_pci
printf '%s\n' 'PASS: module hash, amd64 ELF, exact kernel build, OPNsense series and PCI identity.'
printf '%s\n' 'Hardware forwarding, port mapping, isolation and NPU persistence require target tests.'
