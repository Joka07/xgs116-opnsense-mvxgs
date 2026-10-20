#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Check an already configured FreeBSD interface; no network settings are changed."""
import argparse
import ipaddress
import re
import sys
from common import address, interface, check_path, output_dir, run, write_json


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--interface', required=True, type=interface)
    p.add_argument('--source', required=True, type=address)
    p.add_argument('--peer', required=True, type=address)
    p.add_argument('--mtu', type=int, default=1500)
    p.add_argument('--count', type=int, default=10)
    p.add_argument('--output', required=True)
    p.add_argument('--execute', action='store_true')
    a = p.parse_args()
    if not 1280 <= a.mtu <= 1500 or not 1 <= a.count <= 100:
        p.error('MTU must be 1280..1500 and count 1..100')
    v = ipaddress.ip_address(a.source).version
    if ipaddress.ip_address(a.peer).version != v:
        p.error('source and peer address families differ')
    binary = 'ping6' if v == 6 else 'ping'
    # IPv4 -D forbids fragmentation. IPv6 routers never fragment; captures must
    # still confirm the sender did not insert a Fragment header.
    base = [binary, '-n', '-c', str(a.count), '-S', a.source]
    commands = [base + [a.peer],
                base + (['-D'] if v == 4 else []) + ['-s', str(a.mtu - (48 if v == 6 else 28)), a.peer]]
    report = {'status': 'planned', 'interface': a.interface, 'source': a.source,
              'peer': a.peer, 'mtu': a.mtu, 'commands': commands,
              'scope': 'ICMP reachability and full-MTU echo; no claim about VLAN isolation, NAT, DHCP or Ethernet link rate'}
    if not a.execute:
        print(__import__('json').dumps(report, indent=2)); return 0
    dest = output_dir(a.output)
    try:
        report['path'] = check_path(a.interface, a.source, a.peer)
        report['results'] = [run(cmd, timeout=a.count + 30) for cmd in commands]
        for result in report['results']:
            loss = re.search(r'([0-9.]+)% packet loss', result['stdout'])
            result['zero_loss'] = loss is not None and float(loss.group(1)) == 0
        report['status'] = 'passed' if all(x['exit_code'] == 0 and x['zero_loss'] for x in report['results']) else 'failed'
    except (ValueError, RuntimeError) as exc:
        report['status'], report['error'] = 'failed', str(exc)
    write_json(dest/'result.json', report)
    print(report['status'], dest/'result.json')
    return 0 if report['status'] == 'passed' else 1


if __name__ == '__main__':
    sys.exit(main())
