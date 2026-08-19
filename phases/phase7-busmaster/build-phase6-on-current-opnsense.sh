#!/bin/sh
set -eu
HERE=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
OUT="${OUT:-/tmp/mvxgs-phase6}"
EXISTING="/tmp/mvxgs-build/src/src-12334a596709d195acb73f0f069da82c570a3d84/sys"

echo "== mvxgs Phase 6 HOST_READY build =="
echo "Kernel: $(uname -a)"
echo "Kernel/userland: $(freebsd-version -ku | tr '\n' ' ')"

[ "$(uname -m)" = "amd64" ] || { echo "ERROR: expected amd64"; exit 1; }
[ "$(freebsd-version -k)" = "15.1-RELEASE-p1" ] || {
    echo "ERROR: expected 15.1-RELEASE-p1"; exit 1;
}

if [ ! -f "${EXISTING}/dev/pci/pcivar.h" ]; then
    echo "ERROR: exact source tree is not present in /tmp."
    echo "Keep the current boot/session or use the offline source tarball builder."
    exit 1
fi

rm -rf "${OUT}/module"
mkdir -p "${OUT}/module"
cp "${HERE}/mvxgs.c" "${HERE}/mvxgs_hw.h" "${HERE}/Makefile" "${OUT}/module/"
cd "${OUT}/module"
make clean >/dev/null 2>&1 || true
make SYSDIR="${EXISTING}"

echo
echo "== Build result =="
ls -lh "${OUT}/module/mvxgs.ko"
sha256 "${OUT}/module/mvxgs.ko"
file "${OUT}/module/mvxgs.ko" 2>/dev/null || true
echo "Module: ${OUT}/module/mvxgs.ko"
