# SPDX-License-Identifier: MIT
"""Small execution helpers for explicitly requested hardware measurements."""
import ipaddress
import json
import os
import platform
import re
import subprocess
from pathlib import Path


def address(value):
    ipaddress.ip_address(value)
    return value


def interface(value):
    if not re.fullmatch(r'(?:port[1-9]|vlan[0-9]+|[A-Za-z][A-Za-z0-9_]*[0-9]+)(?:\.[0-9]+)?', value):
        raise ValueError('invalid interface name')
    return value


def output_dir(value):
    path = Path(value)
    path.mkdir(parents=True, exist_ok=False, mode=0o700)
    return path


def run(argv, timeout=30):
    try:
        result = subprocess.run(argv, text=True, capture_output=True, timeout=timeout,
                                env=dict(os.environ, LC_ALL="C"))
        return {'argv': argv, 'exit_code': result.returncode,
                'stdout': result.stdout, 'stderr': result.stderr}
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {'argv': argv, 'exit_code': 124 if isinstance(exc, subprocess.TimeoutExpired) else 127,
                'stdout': '', 'stderr': str(exc)}


def write_json(path, data):
    Path(path).write_text(json.dumps(data, indent=2) + '\n')


def check_path(ifname, source, peer):
    """Require the specified source to belong to the interface and route to use it."""
    if platform.system() != 'FreeBSD':
        raise RuntimeError('hardware execution requires FreeBSD; omit --execute to inspect the plan')
    local, remote = ipaddress.ip_address(source), ipaddress.ip_address(peer)
    if local.version != remote.version:
        raise ValueError('source and peer address families differ')
    info = run(['ifconfig', ifname])
    if info['exit_code']:
        raise RuntimeError(info['stderr'])
    addresses = []
    for line in info['stdout'].splitlines():
        words = line.strip().split()
        if len(words) > 1 and words[0] in ('inet', 'inet6'):
            addresses.append(ipaddress.ip_address(words[1].split('%')[0]))
    if local not in addresses:
        raise RuntimeError(f'{source} is not assigned to {ifname}')
    route = run(['route', '-n', 'get', '-inet6' if local.version == 6 else '-inet', peer])
    match = re.search(r'^\s*interface:\s*(\S+)', route['stdout'], re.M)
    if route['exit_code'] or not match or match.group(1) != ifname:
        raise RuntimeError('route does not use the requested interface; configure the isolated test network first')
    return {'ifconfig': info, 'route': route}
