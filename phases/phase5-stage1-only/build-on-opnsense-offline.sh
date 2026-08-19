#!/bin/sh
set -eu

REV="${REV:-12334a596709}"
WORK="${WORK:-/tmp/mvxgs-build}"
HERE=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)

echo "== mvxgs Stage-1-only OFFLINE build =="
echo "Kernel: $(uname -a)"
echo "Kernel/userland: $(freebsd-version -ku | tr '\n' ' ')"
echo "Source revision: ${REV}"
echo

[ "$(uname -m)" = "amd64" ] || {
  echo "ERROR: expected amd64"
  exit 1
}

[ "$(freebsd-version -k)" = "15.1-RELEASE-p1" ] || {
  echo "ERROR: expected kernel 15.1-RELEASE-p1"
  exit 1
}

command -v tar >/dev/null 2>&1 || {
  echo "ERROR: tar(1) not found"
  exit 1
}
command -v make >/dev/null 2>&1 || {
  echo "ERROR: make(1) not found"
  exit 1
}
command -v cc >/dev/null 2>&1 || {
  echo "ERROR: cc(1) not found"
  exit 1
}

# Look for the source archive beside this script first, then at USB root.
TARBALL=""
for CAND in \
  "${HERE}/opnsense-src-${REV}.tar.gz" \
  "${HERE}/src-${REV}.tar.gz" \
  "/tmp/usb/opnsense-src-${REV}.tar.gz" \
  "/tmp/usb/src-${REV}.tar.gz" \
  "/tmp/usb/${REV}.tar.gz"
do
  if [ -f "${CAND}" ]; then
    TARBALL="${CAND}"
    break
  fi
done

if [ -z "${TARBALL}" ]; then
  echo "ERROR: source tarball not found."
  echo
  echo "Put one of these files on the FAT32 USB stick:"
  echo "  opnsense-src-${REV}.tar.gz"
  echo "  src-${REV}.tar.gz"
  echo
  echo "Expected USB mount: /tmp/usb"
  exit 1
fi

echo "Using source archive:"
echo "  ${TARBALL}"
echo

rm -rf "${WORK}"
mkdir -p "${WORK}/module" "${WORK}/src"

cp "${HERE}/mvxgs.c" "${HERE}/mvxgs_hw.h" "${HERE}/Makefile" "${WORK}/module/"

echo "Checking archive..."
TOP=$(tar -tzf "${TARBALL}" | sed -n '1{s,/.*,,;p;}')
[ -n "${TOP}" ] || {
  echo "ERROR: could not determine archive top directory"
  exit 1
}

echo "Archive top directory: ${TOP}"
echo "Extracting to ${WORK}/src ..."
tar -xzf "${TARBALL}" -C "${WORK}/src"

SYSDIR="${WORK}/src/${TOP}/sys"

[ -f "${SYSDIR}/dev/pci/pcivar.h" ] || {
  echo "ERROR: ${SYSDIR}/dev/pci/pcivar.h missing"
  exit 1
}

[ -f "${SYSDIR}/conf/kmod.mk" ] || {
  echo "ERROR: ${SYSDIR}/conf/kmod.mk missing"
  exit 1
}

echo
echo "Building with:"
echo "  SYSDIR=${SYSDIR}"
echo

cd "${WORK}/module"
make clean >/dev/null 2>&1 || true
make SYSDIR="${SYSDIR}"

echo
echo "== Build result =="
ls -lh "${WORK}/module/mvxgs.ko"
sha256 "${WORK}/module/mvxgs.ko"
file "${WORK}/module/mvxgs.ko" 2>/dev/null || true
echo
echo "Module path:"
echo "  ${WORK}/module/mvxgs.ko"
echo
echo "STOP after the Stage-1 MSI-X test."
echo "This source contains no HOST_READY protocol write path."
