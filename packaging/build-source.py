#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Deterministic integration sources plus the exact original MUSDK dependency."""
import argparse
import gzip
import hashlib
import io
import json
from pathlib import Path
import subprocess
import tarfile

ROOT = Path(__file__).resolve().parents[1]
MUSDK_REV = '278748af6e197672551ba220c8720d9ae0a8461e'


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--musdk-source', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    args = p.parse_args()
    subprocess.run(['git', '-C', str(args.musdk_source), 'cat-file', '-e', MUSDK_REV + '^{commit}'], check=True)
    dependency = subprocess.check_output(['git', '-C', str(args.musdk_source), 'archive', MUSDK_REV])
    files = {}
    for directory in ('build', 'driver', 'host', 'installer', 'npu', 'packaging', 'tests', 'LICENSES'):
        for path in sorted((ROOT / directory).rglob('*')):
            if path.is_file() and '__pycache__' not in path.parts and path.suffix != '.pyc':
                if path.is_symlink():
                    raise ValueError('unexpected source symlink: ' + str(path))
                files[path.relative_to(ROOT).as_posix()] = path.read_bytes()
    for name in ('README.md', 'LICENSE', '.gitignore'):
        files[name] = (ROOT / name).read_bytes()
    # The legacy research directories remain in Git; this artifact contains
    # exactly the new integration and its complete corresponding dependencies.
    files['README.md'] = files['README.md'].split(b'\n## Historischer mvxgs-Forschungsstand')[0] + b'\n'
    for name in ('ARCHITECTURE', 'COMPATIBILITY', 'BUILD', 'INSTALL', 'NPU-SETUP', 'TROUBLESHOOTING',
                 'RECOVERY', 'PERFORMANCE', 'SOURCE-REFERENCES', 'VALIDATION', 'REMAINING'):
        files['docs/' + name + '.md'] = (ROOT / 'docs' / (name + '.md')).read_bytes()
    dependency_name = 'dependencies/musdk-' + MUSDK_REV + '.tar'
    files[dependency_name] = dependency
    source = {'schema': 1, 'musdk_revision': MUSDK_REV,
              'musdk_archive': dependency_name,
              'musdk_archive_sha256': hashlib.sha256(dependency).hexdigest(),
              'files_sha256': {name: hashlib.sha256(data).hexdigest() for name, data in sorted(files.items())},
              'proprietary_files_included': False,
              'rebuild': 'Use npu/build/build.py --musdk-archive <musdk_archive> --musdk-archive-sha256 <musdk_archive_sha256> and the documented compiler/profile arguments.'}
    files['SOURCE.json'] = (json.dumps(source, indent=2, sort_keys=True) + '\n').encode()
    with args.output.open('xb') as target:
        with gzip.GzipFile(filename='', mode='wb', fileobj=target, mtime=0) as compressed:
            with tarfile.open(fileobj=compressed, mode='w', format=tarfile.PAX_FORMAT) as archive:
                for name, data in sorted(files.items()):
                    entry = tarfile.TarInfo('xgs116-source/' + name)
                    entry.size, entry.mtime, entry.uid, entry.gid = len(data), 0, 0, 0
                    entry.mode = 0o755 if name.endswith(('.py', '.sh')) else 0o644
                    entry.uname = entry.gname = 'root'
                    archive.addfile(entry, io.BytesIO(data))
    digest = hashlib.sha256(args.output.read_bytes()).hexdigest()
    args.output.with_name(args.output.name + '.sha256').write_text(digest + '  ' + args.output.name + '\n')
    print(digest + '  ' + str(args.output))


if __name__ == '__main__':
    main()
