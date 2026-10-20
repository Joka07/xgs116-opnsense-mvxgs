#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Explicit, source-bound TCP/UDP measurements with durable JSON and exit status."""
import argparse
import ipaddress
import json
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'network'))
from common import address, interface, check_path, output_dir, run, write_json


def evaluate(result, protocol, minimum_mbps, max_loss_percent, expected_seconds=0):
    if result['exit_code'] != 0:
        return {'status': 'failed', 'reason': 'iperf3 failed', 'exit_code': result['exit_code']}
    try:
        data = json.loads(result['stdout'])
        if data.get('error'):
            raise ValueError(data['error'])
        # Receiver goodput is the acceptance metric. Modern iperf3 exposes this
        # in sum_received; older UDP versions provide the receiver sum in sum.
        end = data['end']
        receiver = end.get('sum_received')
        if receiver is None and protocol == 'udp':
            candidate = end.get('sum')
            if candidate and candidate.get('sender') is False:
                receiver = candidate
        if receiver is None:
            raise ValueError('receiver result missing; update iperf3 on both peers')
        mbps = float(receiver['bits_per_second']) / 1e6
        if mbps <= 0 or float(receiver.get('seconds', 0)) <= 0:
            raise ValueError('no receiver traffic measured')
        if float(receiver.get('seconds', 0)) < expected_seconds * 0.9:
            raise ValueError('receiver measurement ended before the requested duration')
        loss = receiver.get('lost_percent')
        if protocol == 'udp' and loss is None:
            raise ValueError('UDP receiver loss missing')
        accepted = mbps >= minimum_mbps and (loss is None or float(loss) <= max_loss_percent)
        return {'status': 'passed' if accepted else 'failed', 'receiver_mbps': mbps,
                'lost_percent': loss, 'minimum_mbps': minimum_mbps,
                'max_loss_percent': max_loss_percent if protocol == 'udp' else None}
    except (KeyError, TypeError, ValueError) as exc:
        return {'status': 'failed', 'reason': str(exc)}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--interface', required=True, type=interface)
    p.add_argument('--source', required=True, type=address)
    p.add_argument('--peer', required=True, type=address)
    p.add_argument('--port', type=int, default=5201)
    p.add_argument('--seconds', type=int, default=30)
    p.add_argument('--streams', type=int, default=1)
    p.add_argument('--protocol', choices=['tcp', 'udp'], default='tcp')
    p.add_argument('--direction', choices=['tx', 'rx', 'both'], default='both')
    p.add_argument('--udp-mbps', type=float, default=100)
    p.add_argument('--minimum-mbps', type=float, default=0)
    p.add_argument('--max-loss-percent', type=float, default=0)
    p.add_argument('--output', required=True)
    p.add_argument('--execute', action='store_true')
    a = p.parse_args()
    if not 1 <= a.port <= 65535 or not 1 <= a.seconds <= 3600 or not 1 <= a.streams <= 16:
        p.error('port 1..65535, seconds 1..3600, streams 1..16 required')
    if not 0 < a.udp_mbps <= 10000 or not 0 <= a.minimum_mbps <= 10000 or not 0 <= a.max_loss_percent <= 100:
        p.error('invalid throughput or loss limit')
    if a.protocol == 'udp' and a.streams != 1:
        p.error('UDP uses one stream so --udp-mbps is unambiguous')
    version = ipaddress.ip_address(a.source).version
    if ipaddress.ip_address(a.peer).version != version:
        p.error('source and peer address families differ')
    commands = {}
    for direction in ('tx', 'rx') if a.direction == 'both' else (a.direction,):
        cmd = ['iperf3', '-c', a.peer, '-B', a.source, '-p', str(a.port),
               '-t', str(a.seconds), '-P', str(a.streams), '-J', '--get-server-output']
        if direction == 'rx': cmd += ['-R']
        if a.protocol == 'udp': cmd += ['-u', '-b', str(a.udp_mbps)+'M', '-l', '1452' if version == 6 else '1472']
        commands[direction] = cmd
    report = {'status': 'planned', 'commands': commands, 'parameters': vars(a),
              'scope': 'selected host/peer path only; this is not a forwarding/NAT benchmark unless endpoints straddle the firewall'}
    if not a.execute:
        print(json.dumps(report, indent=2)); return 0
    dest = output_dir(a.output)
    try:
        report['path'] = check_path(a.interface, a.source, a.peer)
        report['results'] = {}
        for direction, cmd in commands.items():
            result = run(cmd, timeout=a.seconds + 45)
            write_json(dest/(direction+'-command.json'), result)
            report['results'][direction] = evaluate(result, a.protocol, a.minimum_mbps, a.max_loss_percent, a.seconds)
        report['status'] = 'passed' if all(r['status'] == 'passed' for r in report['results'].values()) else 'failed'
    except (ValueError, RuntimeError) as exc:
        report['status'], report['error'] = 'failed', str(exc)
    write_json(dest/'result.json', report)
    print(report['status'], dest/'result.json')
    return 0 if report['status'] == 'passed' else 1


if __name__ == '__main__':
    sys.exit(main())
