#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Bundle experimental, locally built artifacts with source, licenses and evidence."""
import argparse
import gzip
import hashlib
import io
import json
from pathlib import Path
import tarfile

ROOT = Path(__file__).resolve().parents[1]


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--artifacts', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    a = p.parse_args()
    files = {}
    for name in ('driver', 'npu', 'source', 'validation'):
        base = a.artifacts / name
        if not base.is_dir():
            p.error('missing artifact component: ' + name)
        for path in sorted(base.rglob('*')):
            if path.is_symlink():
                p.error('artifact symlinks are not permitted')
            if path.is_file():
                files[path.relative_to(a.artifacts).as_posix()] = path.read_bytes()
    source = list((a.artifacts / 'source').glob('*.tar.gz'))
    if len(source) != 1:
        p.error('exactly one corresponding-source archive is required')
    for path in sorted((ROOT / 'LICENSES').glob('*.txt')):
        files['LICENSES/' + path.name] = path.read_bytes()
    files['LICENSE'] = (ROOT / 'LICENSE').read_bytes()
    files['README.txt'] = (
        'EXPERIMENTAL XGS116 DEVELOPMENT ARTIFACTS\n'
        'No appliance, packet-forwarding, flash or recovery acceptance has run.\n'
        'driver/: FreeBSD15.1-RELEASE-p1 amd64 module, build inputs and log.\n'
        'npu/: static ARM64 SWOPv1/v2 samples, DSA device2 UNVALIDATED.\n'
        'source/: full integration plus original pinned MUSDK sources.\n'
        'validation/: executed portable tests/build evidence.\n'
        'Extract source/ archive and read docs/INSTALL.md, NPU-SETUP.md,\n'
        'RECOVERY.md and REMAINING.md before any target operation.\n'
        'Bind the host installation package to the actual target uname -v.\n'
        'Confirm DSA device and SWOP slot on the appliance before NPU use.\n'
        'No proprietary modules, SSH keys or original firmware are included.\n'
    ).encode()
    info = {'schema': 1, 'status': 'experimental', 'hardware_validated': False,
            'module_target': 'OPNsense26.7/FreeBSD15.1-RELEASE-p1/amd64',
            'target_kernel_identity_confirmed': False,
            'files_sha256': {n: hashlib.sha256(d).hexdigest() for n, d in sorted(files.items())}}
    files['RELEASE.json'] = (json.dumps(info, indent=2, sort_keys=True) + '\n').encode()
    files['SHA256SUMS'] = ''.join(hashlib.sha256(d).hexdigest() + '  ' + n + '\n'
                                    for n, d in sorted(files.items())).encode()
    with a.output.open('xb') as target:
        with gzip.GzipFile(filename='', mode='wb', fileobj=target, mtime=0) as compressed:
            with tarfile.open(fileobj=compressed, mode='w', format=tarfile.PAX_FORMAT) as archive:
                for name, data in sorted(files.items()):
                    entry = tarfile.TarInfo('xgs116-experimental/' + name)
                    entry.size, entry.mtime, entry.uid, entry.gid, entry.mode = len(data), 0, 0, 0, 0o644
                    entry.uname = entry.gname = 'root'
                    archive.addfile(entry, io.BytesIO(data))
    digest = hashlib.sha256(a.output.read_bytes()).hexdigest()
    a.output.with_name(a.output.name + '.sha256').write_text(digest + '  ' + a.output.name + '\n')
    print(digest + '  ' + str(a.output))


if __name__ == '__main__':
    main()
