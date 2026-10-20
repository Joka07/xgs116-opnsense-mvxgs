#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Opt-in long-running bidirectional traffic; never reboots a host or NPU."""
import argparse
import json
from pathlib import Path
import sys
import time
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'network'))
from common import address, interface, output_dir, run, write_json


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--interface', required=True, type=interface)
    p.add_argument('--source', required=True, type=address)
    p.add_argument('--peer', required=True, type=address)
    p.add_argument('--port', type=int, default=5201)
    p.add_argument('--hours', type=float, default=72)
    p.add_argument('--minimum-mbps', type=float, default=0)
    p.add_argument('--output', required=True)
    p.add_argument('--execute', action='store_true')
    a = p.parse_args()
    if not 0 < a.hours <= 72 or not 1 <= a.port <= 65535 or not 0 <= a.minimum_mbps <= 10000:
        p.error('hours must be >0 and <=72, port 1..65535, minimum Mbps 0..10000')
    runner = Path(__file__).resolve().parents[1]/'performance/iperf.py'
    report = {'status': 'planned', 'parameters': vars(a), 'cycles': [],
              'scope': 'repeated 30-second TCP TX/RX phases; switching directions creates short gaps, not uninterrupted full-duplex load'}
    if not a.execute:
        print(json.dumps(report, indent=2)); return 0
    dest = output_dir(a.output)
    began = time.monotonic()
    report['status'] = 'running'
    write_json(dest/'result.json', report)
    try:
        while time.monotonic() - began < a.hours * 3600:
            number = len(report['cycles']) + 1
            target = dest/f'cycle-{number:05d}'
            cmd = [sys.executable, str(runner), '--interface', a.interface, '--source', a.source,
                   '--peer', a.peer, '--port', str(a.port), '--seconds', '30', '--direction', 'both',
                   '--minimum-mbps', str(a.minimum_mbps), '--output', str(target), '--execute']
            result = run(cmd, timeout=160)
            record = {'number': number, 'elapsed_seconds': time.monotonic()-began,
                      'exit_code': result['exit_code']}
            report['cycles'].append(record)
            write_json(dest/f'cycle-{number:05d}-command.json', result)
            write_json(dest/'result.json', report)
            if result['exit_code']:
                report['status'] = 'failed'; break
        else:
            report['status'] = 'completed'
    except KeyboardInterrupt:
        report['status'] = 'interrupted'
    report['elapsed_seconds'] = time.monotonic() - began
    write_json(dest/'result.json', report)
    print(report['status'], dest/'result.json')
    return 0 if report['status'] == 'completed' and report['cycles'] else 1


if __name__ == '__main__':
    sys.exit(main())
