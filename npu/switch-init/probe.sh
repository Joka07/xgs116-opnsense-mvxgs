#!/bin/sh
# SPDX-License-Identifier: MIT
# Reads switch registers; MDIO command transport writes do not change config.
set -eu
SW=${SW:-"$(dirname "$0")/swmdio.sh"}
r() { sh "$SW" rd "$1" "$2"; }
id=$(r 0 3)
ctl2=$(r 0x1b 0x1c)
printf 'switch_id=%s\ndsa_device=%s\n' "$id" "$((ctl2 & 31))"
# Device number from Global1 Control2, low5 (Linux mv88e6xxx/global1.h).
# Cross-check with DSA byte0 & 31 in real ingress traces; neither is universal.
for p in 0 1 2 3 4 5 6 7 8 9 10; do
  status=$(r "$p" 0); control=$(r "$p" 4); map=$(r "$p" 6)
  printf 'port=%s status=%s control=%s vlanmap=%s link=%s duplex=%s speed_code=%s\n' \
    "$p" "$status" "$control" "$map" "$(((status >> 11) & 1))" "$(((status >> 10) & 1))" "$(((status >> 8) & 3))"
done
