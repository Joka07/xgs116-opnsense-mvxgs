#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Pinned, isolated static AArch64 dp_fwd build. Never executes the payload."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tarfile
import tempfile

MUSDK_REV = '278748af6e197672551ba220c8720d9ae0a8461e'
MUSDK_URL = 'https://github.com/MarvellEmbeddedProcessors/musdk-marvell.git'
MAMORU_REV = '9e53bbcb10f5ba9cd5f6a43dc5631fc8931cff05'
NPU = Path(__file__).resolve().parents[1]


def run(args, cwd=None, env=None, log=None):
    print('+', ' '.join(map(str, args)), flush=True)
    if log:
        with open(log, 'w') as f:
            proc = subprocess.run(args, cwd=cwd, env=env, stdout=f, stderr=subprocess.STDOUT)
        if proc.returncode:
            print(Path(log).read_text()[-12000:])
            raise SystemExit(f'Build failed; full log: {log}')
    else:
        subprocess.run(args, cwd=cwd, env=env, check=True)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--work', type=Path, required=True, help='output/work root outside the source checkout')
    source_group = p.add_mutually_exclusive_group()
    source_group.add_argument('--musdk-source', type=Path, help='existing Git clone; never changed')
    source_group.add_argument('--musdk-archive', type=Path, help='pinned original tar from corresponding-source package')
    p.add_argument('--musdk-archive-sha256', help='required digest from corresponding-source SOURCE.json')
    p.add_argument('--dsa-device', type=int, required=True, choices=range(32), metavar='0..31',
                   help='observed switch device; build selection is NOT hardware validation')
    p.add_argument('--swop-version', type=int, choices=[1, 2], required=True)
    p.add_argument('--cross-prefix', default='aarch64-linux-gnu-')
    p.add_argument('--sysroot', type=Path, help='optional relocated toolchain sysroot')
    p.add_argument('--jobs', type=int, default=4)
    args = p.parse_args()
    if args.jobs < 1 or args.jobs > 32:
        p.error('--jobs must be 1..32')
    work = args.work.resolve()
    if work == NPU or NPU in work.parents:
        p.error('--work must be outside npu sources')
    work.mkdir(parents=True, exist_ok=True)
    prefix = args.cross_prefix
    for tool in ['make', 'git', 'autoconf', 'automake', 'libtoolize', 'm4', 'pkg-config'] + [prefix + x for x in ['gcc', 'ar', 'ranlib', 'ld', 'strip', 'readelf', 'nm']]:
        if shutil.which(tool) is None:
            raise SystemExit(f'Missing build prerequisite: {tool}')
    stage = Path(tempfile.mkdtemp(prefix=f'swop-v{args.swop_version}-dev{args.dsa_device}-', dir=work))
    archive = stage / 'musdk.tar'
    if args.musdk_archive:
        if not args.musdk_archive_sha256 or sha(args.musdk_archive) != args.musdk_archive_sha256:
            p.error('MUSDK source archive SHA256 is missing or differs')
        shutil.copyfile(args.musdk_archive, archive)
    else:
        cache = args.musdk_source or work / 'musdk-source'
        if not cache.exists():
            run(['git', 'clone', MUSDK_URL, str(cache)])
        run(['git', '-C', str(cache), 'cat-file', '-e', MUSDK_REV + '^{commit}'])
        with archive.open('wb') as f:
            subprocess.run(['git', '-C', str(cache), 'archive', MUSDK_REV], stdout=f, check=True)
    src = stage / 'musdk'
    src.mkdir()
    with tarfile.open(archive) as tf:
        tf.extractall(src, filter='data')
    archive_digest = sha(archive)
    archive.unlink()
    patch = NPU / 'patches/musdk-r2a-slot-leak-reinit-teardown.patch'
    run(['git', 'apply', '--check', str(patch)], cwd=src)
    run(['git', 'apply', str(patch)], cwd=src)
    configure = src / 'configure.ac'
    text = configure.read_text()
    anchor = 'CFLAGS+="-Werror "'
    if text.count(anchor) != 1:
        raise SystemExit('Pinned MUSDK configure -Werror anchor drifted')
    configure.write_text(text.replace(anchor, '# warnings retained; contemporary compiler: ' + anchor))
    fw = NPU / 'firmware'
    shutil.copy2(fw / 'forwarder.c', src / 'apps/examples/giu/pkt_echo/pkt_echo.c')
    for name in ['tag_dsa.h', 'pport_hdr.h', 'portmap.h', 'dp_config.h', 'dp_swop.h', 'dp_swop.c', 'dp_sff.h', 'dp_sff.c']:
        shutil.copy2(fw / name, src / 'apps/include' / name)
    epoch = '1788865200'
    env = os.environ.copy()
    env.update({'SOURCE_DATE_EPOCH': epoch, 'TZ': 'UTC', 'LC_ALL': 'C',
                'CC': prefix+'gcc', 'AR': prefix+'ar', 'RANLIB': prefix+'ranlib', 'LD': prefix+'ld'})
    flags = (f'-O2 -g -DDP_DSA_DEV={args.dsa_device} -DDP_SWOP_CAP_VERSION={args.swop_version} '
             f'-ffile-prefix-map={stage}=. -fdebug-prefix-map={stage}=. '
             '-Wno-error=implicit-function-declaration -Wno-error=incompatible-pointer-types -Wno-error=int-conversion')
    if args.sysroot:
        if any(c.isspace() for c in str(args.sysroot.resolve())):
            p.error('--sysroot cannot contain whitespace')
        flags += (f' --sysroot={args.sysroot.resolve()}'
                  f' -ffile-prefix-map={args.sysroot.resolve()}=/toolchain-sysroot'
                  f' -fdebug-prefix-map={args.sysroot.resolve()}=/toolchain-sysroot')
    run(['./bootstrap'], cwd=src, env=env, log=stage/'bootstrap.log')
    run(['./configure', '--host=aarch64-linux-gnu', '--enable-static', '--disable-shared', '--enable-dma-addr=64',
         '--enable-pp2', '--enable-giu', '--enable-nmp', '--enable-sam=no', '--enable-neta=no',
         'CFLAGS='+flags, 'LDFLAGS=-static'],
         cwd=src, env=env, log=stage/'configure.log')
    if '-DMVCONF_DMA_PHYS_ADDR_T_SIZE=64' not in (src/'Makefile').read_text():
        raise SystemExit('MUSDK did not select 64-bit DMA addresses')
    run(['make', '-C', 'src', f'-j{args.jobs}'], cwd=src, env=env, log=stage/'make-library.log')
    run(['make', '-C', 'apps/examples', 'musdk_giu_pkt_echo', f'-j{args.jobs}', 'LDFLAGS=-all-static'],
        cwd=src, env=env, log=stage/'make-forwarder.log')
    binary = src/'apps/examples/musdk_giu_pkt_echo'
    if not binary.is_file():
        raise SystemExit('Expected forwarder artifact missing')
    headers = subprocess.check_output([prefix+'readelf','-h','-l',str(binary)],text=True)
    if 'AArch64' not in headers or 'INTERP' in headers:
        raise SystemExit('Artifact must be static AArch64 ELF (no runtime glibc dependency)')
    syms = subprocess.check_output([prefix+'nm',str(binary)],text=True)
    if ' dp_swop_service' not in syms or ' dp_sff_' not in syms:
        raise SystemExit('Artifact lacks our protocol handlers')
    out = stage/'out'
    out.mkdir()
    shutil.copy2(binary, out/'dp_fwd.debug')
    run([prefix+'strip','-o',str(out/'dp_fwd'),str(binary)])
    shutil.copy2(fw/'dp-nmp-config.txt',out/'dp-nmp-config.txt')
    (out/'build-profile.conf').write_text(f'dsa_device={args.dsa_device}\nswop_version={args.swop_version}\n')
    shutil.copytree(NPU/'startup',out/'startup')
    shutil.copytree(NPU/'switch-init',out/'switch-init')
    source_hashes = {str(path.relative_to(NPU)):sha(path) for path in sorted(NPU.rglob('*')) if path.is_file()}
    recorded_flags = flags.replace(str(stage), '<build>')
    if args.sysroot:
        recorded_flags = recorded_flags.replace(str(args.sysroot.resolve()), '<sysroot>')
    info = {'musdk_revision':MUSDK_REV,'mamoru_baseline':MAMORU_REV,'source_date_epoch':epoch,
            'compiler':subprocess.check_output([prefix+'gcc','--version'],text=True).splitlines()[0],
            'linker':subprocess.check_output([prefix+'ld','--version'],text=True).splitlines()[0],
            'compiler_flags':recorded_flags,
            'musdk_source_archive_sha256':archive_digest,
            'swop_capability_version':args.swop_version,'swop_request_version':1,
            'capability_offset_in_bar0':'0x13000','dsa_device':args.dsa_device,
            'static':True,'dma_address_bits':64,'source_hashes':source_hashes,
            'hardware_validated':False,'tested_legacy_payload_md5':'35c35a3c19311efd2b529a7693e76cd4',
            'legacy_payload_equivalence':False}
    (out/'BUILD-INFO.json').write_text(json.dumps(info,sort_keys=True,indent=2)+'\n')
    files = [path for path in sorted(out.rglob('*')) if path.is_file()]
    (out/'SHA256SUMS').write_text(''.join(f'{sha(path)}  {path.relative_to(out)}\n' for path in files))
    print(f'ARTIFACTS={out}')


if __name__ == '__main__':
    main()
