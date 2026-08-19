#!/bin/sh
set -eu
REV="${REV:-12334a596709}"
WORK="${WORK:-/tmp/mvxgs-build}"
HERE=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)

echo "== mvxgs Stage-1-only build =="
echo "Kernel: $(uname -a)"
echo "Kernel/userland: $(freebsd-version -ku | tr '\n' ' ')"
echo "Source revision: ${REV}"
echo

[ "$(uname -m)" = "amd64" ] || { echo "ERROR: expected amd64"; exit 1; }
[ "$(freebsd-version -k)" = "15.1-RELEASE-p1" ] || { echo "ERROR: expected kernel 15.1-RELEASE-p1"; exit 1; }
command -v fetch >/dev/null 2>&1 || { echo "ERROR: fetch(1) not found"; exit 1; }
command -v tar >/dev/null 2>&1 || { echo "ERROR: tar(1) not found"; exit 1; }
command -v make >/dev/null 2>&1 || { echo "ERROR: make(1) not found"; exit 1; }
command -v cc >/dev/null 2>&1 || { echo "ERROR: cc(1) not found"; exit 1; }

rm -rf "${WORK}"
mkdir -p "${WORK}/module" "${WORK}/src"
cp "${HERE}/mvxgs.c" "${HERE}/mvxgs_hw.h" "${HERE}/Makefile" "${WORK}/module/"

TARBALL="${WORK}/opnsense-src-${REV}.tar.gz"
URL="https://github.com/opnsense/src/archive/${REV}.tar.gz"
echo "Fetching exact OPNsense src snapshot ${REV}..."
fetch -o "${TARBALL}" "${URL}"

TOP=$(tar -tzf "${TARBALL}" | sed -n '1{s,/.*,,;p;}')
[ -n "${TOP}" ] || { echo "ERROR: could not determine archive top directory"; exit 1; }
echo "Extracting source tree..."
tar -xzf "${TARBALL}" -C "${WORK}/src"
SYSDIR="${WORK}/src/${TOP}/sys"
[ -f "${SYSDIR}/dev/pci/pcivar.h" ] || { echo "ERROR: pcivar.h missing in exact source tree"; exit 1; }
[ -f "${SYSDIR}/conf/kmod.mk" ] || { echo "ERROR: kmod.mk missing in exact source tree"; exit 1; }

echo "Building with SYSDIR=${SYSDIR}"
cd "${WORK}/module"
make clean >/dev/null 2>&1 || true
make SYSDIR="${SYSDIR}"

echo
echo "== Build result =="
ls -lh "${WORK}/module/mvxgs.ko"
sha256 "${WORK}/module/mvxgs.ko"
file "${WORK}/module/mvxgs.ko" 2>/dev/null || true
echo "Module path: ${WORK}/module/mvxgs.ko"
echo "STOP after Stage 1 MSI-X test; this source contains no HOST_READY write path."
