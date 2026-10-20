#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Build an experimental kmod with the pinned OPNsense sources, without installing."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import tempfile

REVISION = "12334a596709d195acb73f0f069da82c570a3d84"
ROOT = Path(__file__).resolve().parents[1]


def run(args, **kwargs):
    return subprocess.run(args, check=True, text=True, **kwargs)


def output(args):
    return run(args, stdout=subprocess.PIPE).stdout.strip()


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--src-tree", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--jobs", type=int, default=4)
    args = parser.parse_args()
    src, dest = args.src_tree.resolve(), args.output_dir.resolve()
    if not 1 <= args.jobs <= 32:
        parser.error("--jobs must be 1..32")
    if src == dest or src in dest.parents or ROOT / "driver" in dest.parents:
        parser.error("output must be outside kernel and driver source trees")
    if output(["git", "-C", str(src), "rev-parse", "HEAD"]) != REVISION:
        parser.error(f"kernel source must be exactly {REVISION}")
    run(["git", "-C", str(src), "diff", "--exit-code", "HEAD", "--", "sys", "share/mk"])
    if output(["git", "-C", str(src), "ls-files", "--others", "--exclude-standard", "--", "sys", "share/mk"]):
        parser.error("untracked kernel inputs are not allowed")
    versions = (src / "sys/conf/newvers.sh").read_text()
    if 'REVISION="15.1"' not in versions or 'BRANCH="RELEASE-p1"' not in versions:
        parser.error("kernel release does not match 15.1-RELEASE-p1")
    linux = platform.system() == "Linux"
    make = "bmake" if linux else "make"
    tools = [make, "clang", "ld.lld", "llvm-nm", "llvm-objcopy", "llvm-readelf",
             "gawk" if linux else "awk"]
    for tool in tools:
        if not shutil.which(tool):
            parser.error(f"missing build tool: {tool}")
    dest.mkdir(parents=True, exist_ok=True)
    # New staging directory on every run; no stale object can masquerade as a build.
    with tempfile.TemporaryDirectory(prefix="agnic-build-", dir=dest) as temp:
        stage = Path(temp) / "if_agnic"
        stage.mkdir()
        inputs = {}
        for p in sorted((ROOT / "driver/if_agnic").iterdir()):
            if p.suffix in (".c", ".h") or p.name == "Makefile":
                shutil.copy2(p, stage / p.name)
                inputs[p.name] = digest(p)
        env = dict(os.environ, NM="llvm-nm", SOURCE_DATE_EPOCH="0")
        command = [
            make, "-m", str(src / "share/mk"), "-C", str(stage),
            f"SYSDIR={src / 'sys'}", "MACHINE=amd64", "MACHINE_ARCH=amd64",
            "CC=clang --target=x86_64-unknown-freebsd15.1", "LD=ld.lld",
            "NM=llvm-nm", "OBJCOPY=llvm-objcopy", "STRIP=llvm-strip",
            f"AWK={'gawk' if linux else 'awk'}", f"-j{args.jobs}",
        ]
        if linux:
            command.append("XARGS_J=-I")
        with (dest / "build.log").open("w") as log:
            try:
                run(command, env=env, stdout=log, stderr=subprocess.STDOUT)
            except subprocess.CalledProcessError:
                print((dest / "build.log").read_text()[-10000:])
                raise
        module = stage / "if_agnic.ko"
        elf = output(["llvm-readelf", "-h", str(module)])
        if "FreeBSD" not in elf or "REL (Relocatable file)" not in elf or "X86-64" not in elf:
            raise RuntimeError(f"unexpected module format:\n{elf}")
        sections = output(["llvm-readelf", "-S", str(module)])
        if "modmetadata_set" not in sections:
            raise RuntimeError("module registration metadata missing")
        shutil.copyfile(module, dest / "if_agnic.ko")
        manifest = {
            "schema": 1, "status": "experimental-not-hardware-validated",
            "kernel_source_revision": REVISION, "kernel_release": "15.1-RELEASE-p1",
            "opnsense": "26.7", "architecture": "amd64",
            "compiler": output(["clang", "--version"]).splitlines()[0],
            "linker": output(["ld.lld", "--version"]),
            "driver_sources_sha256": inputs, "module_sha256": digest(module),
            "runtime_kernel_identity": None,
            "limitations": ["Not loaded in this Linux environment",
                            "Target kernel configuration and runtime identity must be verified before installation"],
        }
        (dest / "build-manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
        (dest / "SHA256SUMS").write_text(f"{digest(module)}  if_agnic.ko\n")
        print(json.dumps(manifest, indent=2))


if __name__ == "__main__":
    main()
