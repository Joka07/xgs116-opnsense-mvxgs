#!/bin/sh
# SPDX-License-Identifier: MIT
# Hardware dates in the upstream comments describe the original reference box;
# this integration has no local hardware measurements yet.
# Native MV88E6193X switch access on the XGS116 NPU — raw orion-SMI @ 0xf212a200,
# multi-chip SMI address 2 indirect protocol. NO libsbsp / mvmdio_uio / kernel rebuild.
# DEV (multi-chip indirect): port0=0x00 .. port10=0x0a, global1=0x1b, global2=0x1c.
# VERIFIED ON HARDWARE 2026-09-01. The earlier port base of 0x10 was the SINGLE-chip
# PHY-address convention and is WRONG for the SMI-addr-2 indirect protocol used here.
# It failed silently: every port register read back 0x0000 with the SMI VALID bit SET,
# so a wrong address was indistinguishable from a genuinely-zero register. Only reg3
# (Switch ID) answered, because it reads 0x1930 at any device address. Corrected base
# gives status/vlanmap that match known link state exactly (port1 up 1000, port9 up
# 2500 = PortF1, ports 2-8 down, CPU port 0 vlanmap 0x03fe).
# SMI-cmd bits: busy(15) mode-c22(12) op(11:10 read=10/write=01) dev(9:5) reg(4:0).
# Outer orion SMI @ base: data(15:0) phy(20:16) reg(25:21) readop(26) valid(27) busy(28).
set -eu
SMI=0xf212a200
dm() { busybox devmem "$@"; }

owait() {  # wait outer orion SMI busy (bit28) clear
  i=0; while [ $i -lt 200 ]; do
    r=$(dm $SMI 32); [ $(( r & 0x10000000 )) -eq 0 ] && return 0; i=$((i+1))
  done; echo "owait timeout" >&2; return 1
}
swbusy() {  # wait switch SMI-command busy (phy2 reg0 bit15) clear
  i=0; while [ $i -lt 200 ]; do
    dm $SMI 32 0x04020000 >/dev/null || return 1; owait || return 1; c=$(dm $SMI 32) || return 1
    [ $(( c & 0x8000 )) -eq 0 ] && return 0; i=$((i+1))
  done; echo "swbusy timeout" >&2; return 1
}
swrd() {  # DEV REG -> 0xhhhh, or "INVALID" if the SMI transaction did not complete
  swbusy || return 1
  dm $SMI 32 $(( 0x20000 | 0x9800 | ($1<<5) | $2 )) >/dev/null || return 1; owait || return 1
  swbusy || return 1
  dm $SMI 32 0x04220000 >/dev/null || return 1; owait || return 1; v=$(dm $SMI 32) || return 1
  # Bit 27 is the outer-SMI ReadValid flag. Without this test a transaction that never
  # completed returns 0x0000, indistinguishable from a register that genuinely reads zero.
  # NOTE: this does NOT catch a wrong DEVICE address -- the 2026-09-01 base-address bug
  # returned valid=1 with data=0x0000. Valid means "the bus answered", not "you asked the
  # right thing". Correlate values against independently-known state before trusting a map.
  [ $(( (v>>27) & 1 )) -eq 1 ] || { echo INVALID; return 1; }
  printf '0x%04x\n' $(( v & 0xffff ))
}
swwr() {  # DEV REG VAL
  swbusy || return 1
  dm $SMI 32 $(( 0x220000 | ($3 & 0xffff) )) >/dev/null || return 1; owait || return 1
  dm $SMI 32 $(( 0x20000 | 0x9400 | ($1<<5) | $2 )) >/dev/null || return 1; owait || return 1
  swbusy || return 1
}
number() {
  value=$1
  [ "${#value}" -le 6 ] || { echo 'Numeric argument too long' >&2; return 2; }
  case "$value" in
    0x*) digits=${value#0x}; case "$digits" in ''|*[!0-9a-fA-F]*) return 2;; esac ;;
    *) case "$value" in ''|*[!0-9]*) return 2;; esac
       while [ "${value#0}" != "$value" ]; do value=${value#0}; done
       value=${value:-0} ;;
  esac
  printf '%s\n' "$((value))"
}
validate_address() {
  case "$dev" in 0|1|2|3|4|5|6|7|8|9|10|27|28) ;; *) return 2;; esac
  [ "$reg" -le 31 ] || return 2
}
case "${1:-}" in
  rd) [ "$#" = 3 ] || exit 2
      dev=$(number "$2"); reg=$(number "$3"); validate_address
      swrd "$dev" "$reg" ;;
  # The trailing echo used to be the LAST command in this branch, which meant the branch
  # ALWAYS exited 0 and swwr's return code was destroyed inside the tool -- a write that
  # timed out on the SMI bus still printed "wrote ...". A caller could not detect it even
  # if it checked. Failure is now loud on stderr and non-zero.
  # NOTE: success here means THE BUS TRANSACTION COMPLETED, not that the register holds the
  # value. Only a read-back proves that; see wv() in sw-init.sh.
  wr) [ "$#" = 4 ] || exit 2
      dev=$(number "$2"); reg=$(number "$3"); val=$(number "$4"); validate_address
      [ "$val" -le 65535 ] || exit 2
      [ "${SW_MDIO_WRITE:-0}" = 1 ] || { echo "Write disabled: use verified sw-init --apply" >&2; exit 1; }
      swwr "$dev" "$reg" "$val" ||
        { echo "WRITE FAILED dev=$2 reg=$3 val=$4 (SMI busy/timeout)" >&2; exit 1; }
      echo "wrote dev=$2 reg=$3 val=$4" ;;
  id) swrd 0x00 3 ;;
  dump) for p in 0x00 0x01 0x02 0x03 0x04 0x05 0x06 0x07 0x08 0x09 0x0a; do
          printf 'dev %s reg0(status)=%s reg3(id)=%s\n' "$p" "$(swrd $(($p)) 0)" "$(swrd $(($p)) 3)"; done ;;
  *) echo "usage: $0 {rd DEV REG | wr DEV REG VAL | id | dump}  (DEV: port0=0x00..port10=0x0a, g1=0x1b, g2=0x1c)" >&2; exit 2 ;;
esac
