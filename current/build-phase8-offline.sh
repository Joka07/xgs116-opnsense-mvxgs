#!/bin/sh
set -eu

REV="${REV:-12334a596709}"
HERE=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
OUT="${OUT:-/tmp/mvxgs-phase8}"

echo "== mvxgs Phase 8 HOST_ALIVE build =="
echo "Kernel: $(uname -a)"
echo "Kernel/userland: $(freebsd-version -ku | tr '\n' ' ')"

[ "$(uname -m)" = "amd64" ] || { echo "ERROR: expected amd64"; exit 1; }
[ "$(freebsd-version -k)" = "15.1-RELEASE-p1" ] || {
    echo "ERROR: expected 15.1-RELEASE-p1"; exit 1;
}

TARBALL=""
for CAND in \
  "/tmp/usb/opnsense-src-${REV}.tar.gz" \
  "${HERE}/opnsense-src-${REV}.tar.gz"
do
  if [ -f "${CAND}" ]; then TARBALL="${CAND}"; break; fi
done
[ -n "${TARBALL}" ] || {
  echo "ERROR: exact source tarball not found."
  exit 1
}

rm -rf "${OUT}"
mkdir -p "${OUT}/src" "${OUT}/module"
TOP=$(tar -tzf "${TARBALL}" | sed -n '1{s,/.*,,;p;}')
tar -xzf "${TARBALL}" -C "${OUT}/src"
SYSDIR="${OUT}/src/${TOP}/sys"
[ -f "${SYSDIR}/dev/pci/pcivar.h" ] || { echo "ERROR: pcivar.h missing"; exit 1; }

cp "${HERE}/mvxgs.c" "${HERE}/mvxgs_hw.h" "${HERE}/Makefile" "${OUT}/module/"
cd "${OUT}/module"
make SYSDIR="${SYSDIR}"

echo
echo "== Build result =="
ls -lh "${OUT}/module/mvxgs.ko"
sha256 "${OUT}/module/mvxgs.ko"
file "${OUT}/module/mvxgs.ko" 2>/dev/null || true
echo "Module: ${OUT}/module/mvxgs.ko"
