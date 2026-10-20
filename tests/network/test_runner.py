# SPDX-License-Identifier: MIT
import importlib.util
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent))
import common


class Runner(unittest.TestCase):
    def test_address_rejects_shell_text(self):
        with self.assertRaises(ValueError):
            common.address('192.0.2.1;reboot')

    def test_interface_rejects_option(self):
        with self.assertRaises(ValueError):
            common.interface('--help')

    def test_existing_output_not_overwritten(self):
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises(FileExistsError): common.output_dir(d)

    def test_timeout_failure(self):
        with patch.object(common.subprocess, 'run', side_effect=subprocess.TimeoutExpired(['ping'], 3)):
            self.assertEqual(common.run(['ping'])['exit_code'], 124)

    def test_execution_rejects_linux(self):
        with patch.object(common.platform, 'system', return_value='Linux'):
            with self.assertRaises(RuntimeError): common.check_path('port1', '192.0.2.1', '192.0.2.2')

    def test_wrong_route_rejected(self):
        replies = [{'exit_code': 0, 'stdout': 'port1: flags=UP\n inet 192.0.2.1 netmask 0xffffff00\n', 'stderr': ''},
                   {'exit_code': 0, 'stdout': ' interface: port2\n', 'stderr': ''}]
        with patch.object(common.platform, 'system', return_value='FreeBSD'), patch.object(common, 'run', side_effect=replies):
            with self.assertRaises(RuntimeError): common.check_path('port1', '192.0.2.1', '192.0.2.2')

    def test_unassigned_source_rejected(self):
        reply = {'exit_code': 0, 'stdout': 'port1: flags=UP\n inet 192.0.2.4 netmask 0xffffff00\n', 'stderr': ''}
        with patch.object(common.platform, 'system', return_value='FreeBSD'), patch.object(common, 'run', return_value=reply):
            with self.assertRaises(RuntimeError): common.check_path('port1', '192.0.2.1', '192.0.2.2')


if __name__ == '__main__': unittest.main()
