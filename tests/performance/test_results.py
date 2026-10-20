# SPDX-License-Identifier: MIT
import importlib.util
import json
from pathlib import Path
import unittest
spec = importlib.util.spec_from_file_location('xgs_iperf', Path(__file__).with_name('iperf.py'))
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


class Results(unittest.TestCase):
    def sample(self, end):
        return {'exit_code': 0, 'stdout': json.dumps({'end': end})}

    def test_nonzero_not_masked(self):
        self.assertEqual(mod.evaluate({'exit_code': 1}, 'tcp', 0, 0)['status'], 'failed')

    def test_empty_run_fails(self):
        self.assertEqual(mod.evaluate(self.sample({}), 'tcp', 0, 0)['status'], 'failed')

    def test_sender_only_fails(self):
        r = self.sample({'sum_sent': {'bits_per_second': 940e6}})
        self.assertEqual(mod.evaluate(r, 'tcp', 0, 0)['status'], 'failed')

    def test_receiver_threshold(self):
        r = self.sample({'sum_received': {'bits_per_second': 940e6, 'seconds': 30}})
        self.assertEqual(mod.evaluate(r, 'tcp', 930, 0)['status'], 'passed')
        self.assertEqual(mod.evaluate(r, 'tcp', 950, 0)['status'], 'failed')

    def test_udp_loss_fails(self):
        r = self.sample({'sum_received': {'bits_per_second': 600e6, 'seconds': 30, 'lost_percent': 1}})
        self.assertEqual(mod.evaluate(r, 'udp', 500, 0)['status'], 'failed')
        self.assertEqual(mod.evaluate(r, 'udp', 500, 2)['status'], 'passed')

    def test_zero_duration_fails(self):
        r = self.sample({'sum_received': {'bits_per_second': 940e6, 'seconds': 0}})
        self.assertEqual(mod.evaluate(r, 'tcp', 0, 0)['status'], 'failed')

    def test_short_run_fails(self):
        r = self.sample({'sum_received': {'bits_per_second': 940e6, 'seconds': 1}})
        self.assertEqual(mod.evaluate(r, 'tcp', 0, 0, 30)['status'], 'failed')

    def test_old_udp_sender_ignored(self):
        r = self.sample({'sum': {'bits_per_second': 940e6, 'seconds': 30, 'sender': True, 'lost_percent': 0}})
        self.assertEqual(mod.evaluate(r, 'udp', 0, 0)['status'], 'failed')


if __name__ == '__main__':
    unittest.main()
