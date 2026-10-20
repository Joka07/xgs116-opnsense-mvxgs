#!/bin/sh
# SPDX-License-Identifier: MIT
set -eu
HERE=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
exec python3 "$HERE/npu_tools.py" backup "$@"
