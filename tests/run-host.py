#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Run portable C/protocol, packaging, ext4 and runner tests; no appliance traffic."""
from pathlib import Path
import subprocess
import sys

root = Path(__file__).resolve().parents[1]
for suite in ('unit', 'network', 'performance'):
    result = subprocess.run([sys.executable, '-m', 'unittest', 'discover', '-s',
                             str(root / 'tests' / suite), '-p', 'test_*.py', '-v'], cwd=root)
    if result.returncode:
        raise SystemExit(result.returncode)
print('PASS: all portable suites completed; hardware tests are a separate acceptance step.')
