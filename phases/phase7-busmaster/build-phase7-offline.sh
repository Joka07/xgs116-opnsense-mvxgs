#!/bin/sh
set -eu

REV="${REV:-12334a596709}"
HERE=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
OUT="${OUT:-/tmp/mvxgs-phase7}"
EXISTING="/tmp/mvxgs-build/src/src-12334a596709d195acb73f0f069da82c570a3d84/sys"

echo "== mvxgs Phase 7 BUSMASTER build =="
echo "Kernel: $(uname -a)"
echo "Kernel/userland: $(freebsd-version -ku | tr '\n' ' ')"

[ "$(uname -m)" = "amd64" ] || { echo "ERROR: expected amd64"; exit 1; }
[ "$(freebsd-version -k)" = "15.1-RELEASE-p1" ] || {
    echo "ERROR: expected 15.1-RELEASE-p1"; exit 1;
}

SYSDIR=""
if [ -f "${EXISTING}/dev/pci/pcivar.h" ] && [ -f "${EXISTING}/conf/kmod.mk" ]; then
    SYSDIR="${EXISTING}"
    echo "Reusing exact source tree already extracted in /tmp."
else
    TARBALL=""
    for CAND in \
      "/tmp/usb/opnsense-src-${REV}.tar.gz" \
      "${HERE}/opnsense-src-${REV}.tar.gz"
    do
      if [ -f "${CAND}" ]; then TARBALL="${CAND}"; break; fi
    done
    [ -n "${TARBALL}" ] || {
      echo "ERROR: exact source tree/tarball not found."
      echo "Put opnsense-src-${REV}.tar.gz on the FAT32 USB stick."
      exit 1
    }
    rm -rf "${OUT}/src"
    mkdir -p "${OUT}/src"
    TOP=$(tar -tzf "${TARBALL}" | sed -n '1{s,/.*,,;p;}')
    tar -xzf "${TARBALL}" -C "${OUT}/src"
    SYSDIR="${OUT}/src/${TOP}/sys"
fi

[ -f "${SYSDIR}/dev/pci/pcivar.h" ] || { echo "ERROR: pcivar.h missing"; exit 1; }

rm -rf "${OUT}/module"
mkdir -p "${OUT}/module"
cp "${HERE}/mvxgs.c" "${HERE}/mvxgs_hw.h" "${HERE}/Makefile" "${OUT}/module/"

cd "${OUT}/module"
make clean >/dev/null 2>&1 || true
make SYSDIR="${SYSDIR}"

echo
echo "== Build result =="
ls -lh "${OUT}/module/mvxgs.ko"
sha256 "${OUT}/module/mvxgs.ko"
file "${OUT}/module/mvxgs.ko" 2>/dev/null || true
echo "Module: ${OUT}/module/mvxgs.ko"
