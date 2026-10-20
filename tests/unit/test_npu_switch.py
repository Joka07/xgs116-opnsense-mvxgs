# SPDX-License-Identifier: MIT
"""Execute real switch initialization against a file-backed SMI transaction mock."""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
SW = ROOT / 'npu/switch-init'


class SwitchInterlock(unittest.TestCase):
    def test_default_dry_run_and_write_guard(self):
        for script in [SW / 'sw-init.sh', ROOT / 'npu/startup/dp-autostart.sh']:
            result = subprocess.run(['sh', str(script)], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn('DRY RUN', result.stdout)
        result = subprocess.run(['sh', str(SW / 'swmdio.sh'), 'wr', '1', '6', '1'], capture_output=True)
        self.assertNotEqual(result.returncode, 0)

    def test_malformed_address_never_reaches_devmem(self):
        for args in [('rd', '32', '0'), ('rd', '1', '32'), ('rd', 'x', '4'),
                     ('rd', '1'), ('wr', '1', '6', '65536'), ('rd', '1;reboot', '0')]:
            result = subprocess.run(['sh', str(SW / 'swmdio.sh'), *args], capture_output=True)
            self.assertEqual(result.returncode, 2, (args, result.stderr))

    def run_switch(self, fail=False):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        work = Path(temp.name)
        mock = work / 'smi.sh'
        mock.write_text('''#!/bin/sh
set -eu
d=$(( $2 )); r=$(( $3 )); file="$MOCK_DIR/reg-$d-$r"
case "$1" in
wr)
  v=$(( $4 )); printf '%s %s %s\\n' "$d" "$r" "$v" >> "$MOCK_DIR/writes"
  if [ "${MOCK_FAIL:-no}" = yes ] && [ "$d:$r" = 3:6 ]; then exit 1; fi
  printf '0x%x\\n' "$v" > "$file" ;;
rd) if [ -f "$file" ]; then cat "$file"; else echo 0x0000; fi ;;
*) exit 1;; esac
''')
        env = dict(os.environ, SW=str(mock), XGS116_BOARD_CONFIRMED='yes', MOCK_DIR=str(work),
                   MOCK_FAIL='yes' if fail else 'no')
        result = subprocess.run(['sh', str(SW / 'sw-init.sh'), '--apply'], env=env,
                                text=True, capture_output=True)
        writes = [tuple(map(int, line.split())) for line in (work / 'writes').read_text().splitlines()]
        return result, writes

    def test_failed_isolation_never_enables_forwarding_or_phys(self):
        result, writes = self.run_switch(fail=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('Isolation failed', result.stderr)
        self.assertFalse(any(reg == 4 and value & 3 for dev, reg, value in writes))
        self.assertFalse(any(dev == 28 for dev, reg, value in writes))

    def test_all_maps_are_verified_before_forwarding(self):
        result, writes = self.run_switch()
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        enable = next(i for i, (d, r, v) in enumerate(writes) if r == 4 and v & 3)
        maps = {(d, v) for d, r, v in writes[:enable] if r == 6}
        self.assertEqual(maps, {(0, 0x3fe)} | {(p, 1) for p in range(1, 11)})


if __name__ == '__main__':
    unittest.main()
