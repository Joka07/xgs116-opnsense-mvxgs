#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Build a deterministic host staging archive; no target or repository mutations.

The caller supplies the exact target uname -v, after building against the pinned
source. Metadata is a provenance assertion, not a substitute for hardware tests.
"""
import argparse
import gzip
import hashlib
import io
import pathlib
import struct
import tarfile

SOURCE_REVISION = "12334a596709d195acb73f0f069da82c570a3d84"
ROOT = pathlib.Path(__file__).resolve().parents[1]


def build(module, kernel_ident, output):
    data = module.read_bytes()
    if len(data) < 20 or data[:6] != b"\x7fELF\x02\x01":
        raise ValueError("module must be a 64-bit little-endian ELF file")
    elf_type, machine = struct.unpack_from("<HH", data, 16)
    if (elf_type, machine) != (1, 62):
        raise ValueError("module must be an amd64 ELF relocatable object")
    if not kernel_ident or any(c in kernel_ident for c in "\r\n\x00"):
        raise ValueError("provide the exact target uname -v as a single line")
    meta = ("format=1\narchitecture=amd64\nfreebsd_kernel=15.1-RELEASE-p1\n"
            "opnsense_series=26.7\nsource_revision=" + SOURCE_REVISION +
            "\nkernel_ident=" + kernel_ident + "\nmodule_sha256=" +
            hashlib.sha256(data).hexdigest() + "\n").encode()
    files = {
        "payload/boot/modules/if_agnic.ko": (data, 0o644),
        "payload/usr/local/etc/xgs116-agnic/module.meta": (meta, 0o644),
        "payload/usr/local/libexec/xgs116-agnic/common.sh": ((ROOT / "host/common.sh").read_bytes(), 0o755),
        "payload/usr/local/libexec/xgs116-agnic/agnic-control.sh": ((ROOT / "host/agnic-control.sh").read_bytes(), 0o755),
        "payload/usr/local/etc/rc.syshook.d/early/50-xgs116-agnic": ((ROOT / "host/50-xgs116-agnic").read_bytes(), 0o755),
        "payload/usr/local/etc/rc.syshook.d/update/50-xgs116-agnic": ((ROOT / "host/50-xgs116-agnic-update").read_bytes(), 0o755),
    }
    files["SHA256SUMS"] = ("".join(hashlib.sha256(content).hexdigest() + "  " + name + "\n"
                                     for name, (content, _) in sorted(files.items())).encode(), 0o644)
    for rel in ("installer/install-host.sh", "installer/preflight.sh", "installer/verify.sh",
                "host/common.sh", "host/rollback-host.sh"):
        files[rel] = ((ROOT / rel).read_bytes(), 0o755)
    files["README.txt"] = ((ROOT / "host/README.md").read_bytes(), 0o644)
    with output.open("xb") as target:
        with gzip.GzipFile(filename="", mode="wb", fileobj=target, mtime=0) as compressed:
            with tarfile.open(fileobj=compressed, mode="w", format=tarfile.USTAR_FORMAT) as archive:
                for rel, (content, mode) in sorted(files.items()):
                    info = tarfile.TarInfo("xgs116-host/" + rel)
                    info.size = len(content)
                    info.mode = mode
                    info.mtime = info.uid = info.gid = 0
                    info.uname = info.gname = "root"
                    archive.addfile(info, io.BytesIO(content))
    digest = hashlib.sha256(output.read_bytes()).hexdigest()
    output.with_name(output.name + ".sha256").write_text(digest + "  " + output.name + "\n")
    print(digest + "  " + str(output))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--module", type=pathlib.Path, required=True)
    parser.add_argument("--kernel-ident", required=True, help="exact target `uname -v`; never guess this")
    parser.add_argument("--output", type=pathlib.Path, required=True)
    args = parser.parse_args()
    build(args.module, args.kernel_ident, args.output)


if __name__ == "__main__":
    main()
