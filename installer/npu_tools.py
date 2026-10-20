#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Private NPU backups and offline ext4 preparation. Never writes a block device."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import stat
import subprocess
import sys
import tempfile

REPO = Path(__file__).resolve().parents[1]
DEVICE = re.compile(r"/dev/(?:mmcblk[0-9]+(?:p[0-9]+|boot[01])?|mtd[0-9]+)")
SAFE_PATH = re.compile(r"/[A-Za-z0-9_./+-]+")
MODULES = ("musdk_cma.ko", "mv_dmax2_uio.ko", "uio_pdrv_genirq.ko")
INVENTORY = r"""
set -eu
[ "$(uname -s)" = Linux ] || exit 20
printf 'K\t%s\n' "$(uname -r)"
awk '$2=="/" {printf "R\t%s\t%s\t%s\n",$1,$3,$4}' /proc/mounts
for t in $(cat /proc/cmdline); do
 case "$t" in root=/dev/mmcblk*) printf 'C\t%s\n' "${t#root=}";; esac
done
for p in /sys/class/block/mmcblk*; do
 [ -e "$p/size" ] || continue
 printf 'B\t/dev/%s\t%s\n' "${p##*/}" "$(cat "$p/size")"
done
if [ -r /proc/mtd ]; then
 awk 'NR>1 {sub(":","",$1);printf "F\t/dev/%s\t%s\n",$1,$2}' /proc/mtd
fi
awk '{printf "M\t%s\t%s\t%s\n",$1,$2,$4}' /proc/mounts
"""


class SafetyError(Exception):
    pass


def require(condition, message):
    if not condition:
        raise SafetyError(message)


def sha256(path):
    digest = hashlib.sha256()
    with open(path, "rb") as f:
        for data in iter(lambda: f.read(1024 * 1024), b""):
            digest.update(data)
    return digest.hexdigest()


def regular(path):
    path = Path(path)
    require(path.is_file() and not path.is_symlink(), f"Not a regular file: {path}")
    return path


def private_output(path):
    """Keep appliance originals, private keys and custom firmware outside this checkout."""
    path = Path(path).resolve()
    require(not path.is_relative_to(REPO), "Private output must be outside the Git checkout")
    require(not path.exists(), f"Refusing to overwrite: {path}")
    return path


def save_json(path, obj):
    with open(path, "x", encoding="utf8") as f:
        json.dump(obj, f, indent=2, sort_keys=True)
        f.write("\n")
    os.chmod(path, 0o600)


def device(value):
    require(bool(DEVICE.fullmatch(value)), f"Unsupported block/flash device: {value}")
    return value


def parse_inventory(text):
    result = {"schema": 1, "blocks": {}, "flash": {}, "mounts": []}
    roots = []
    for line in text.splitlines():
        part = line.split("\t")
        if part[0] == "K" and len(part) == 2:
            result["kernel_release"] = part[1]
        elif part[0] == "R" and len(part) == 4:
            roots.append(part[1:])
        elif part[0] == "C" and len(part) == 2:
            require("cmdline_root" not in result, "Ambiguous kernel root arguments")
            result["cmdline_root"] = device(part[1])
        elif part[0] == "B" and len(part) == 3:
            result["blocks"][device(part[1])] = int(part[2]) * 512
        elif part[0] == "F" and len(part) == 3:
            result["flash"][device(part[1])] = int(part[2], 16)
        elif part[0] == "M" and len(part) == 4:
            result["mounts"].append(dict(zip(("source", "mountpoint", "options"), part[1:])))
        else:
            raise SafetyError("Unexpected inventory output; refusing ambiguous device layout")
    require(len(roots) == 1, "Exactly one root mount is required")
    root, filesystem, options = roots[0]
    if root == "/dev/root":
        root = result.get("cmdline_root", "")
    device(root)
    require(re.fullmatch(r"/dev/mmcblk[0-9]+p[0-9]+", root), "Root must resolve to an eMMC partition")
    require(result.get("cmdline_root", root) == root, "Mount and kernel root arguments disagree")
    require(filesystem == "ext4", "Only original ext4 rootfs images are supported")
    require(root in result["blocks"], "Active root missing from block inventory")
    result.update(root_device=root, root_options=options, filesystem=filesystem,
                  disk_device=re.sub(r"p[0-9]+$", "", root))
    require(result["disk_device"] in result["blocks"], "Parent eMMC disk is missing")
    require(result.get("kernel_release") and "/" not in result["kernel_release"], "Missing/invalid kernel release")
    return result


def assert_quiescent(inventory):
    require("ro" in inventory["root_options"].split(","), "Rootfs must be mounted read-only for a consistent backup")
    disk = inventory["disk_device"]
    for mount in inventory["mounts"]:
        source = mount["source"]
        # /persistent is often writable. Do not silently remount or freeze it.
        if source.startswith(disk) or source in inventory["flash"] or mount["mountpoint"] == "/persistent":
            require("ro" in mount["options"].split(","),
                    f"Writable storage mount {mount['mountpoint']}; quiesce it from the console first")


def ssh_base(args):
    require(args.host and not args.host.startswith("-") and not any(c.isspace() for c in args.host),
            "Supply an explicit SSH destination, e.g. root@fe80::...%mvmgmt0")
    result = ["ssh", "-T", "-o", "BatchMode=yes", "-o", "StrictHostKeyChecking=yes",
              "-o", "ConnectTimeout=10", "-o", "ServerAliveInterval=15",
              "-o", "ServerAliveCountMax=3"]
    if args.identity:
        result += ["-i", str(regular(args.identity))]
    if args.known_hosts:
        result += ["-o", f"UserKnownHostsFile={regular(args.known_hosts)}"]
    return result + [args.host]


def remote_inventory(ssh):
    proc = subprocess.run(ssh + ["sh"], input=INVENTORY, text=True,
                          capture_output=True, check=True)
    return parse_inventory(proc.stdout)


def backup(args):
    ssh = ssh_base(args)
    inventory = remote_inventory(ssh)
    assert_quiescent(inventory)
    disk = inventory["disk_device"]
    devices = {disk: inventory["blocks"][disk], inventory["root_device"]: inventory["blocks"][inventory["root_device"]]}
    devices.update({p: size for p, size in inventory["blocks"].items() if p in (disk + "boot0", disk + "boot1")})
    devices.update(inventory["flash"])
    require(inventory["flash"], "SPI partition inventory is missing; full backup cannot be established")
    out = private_output(args.out)
    if not args.apply:
        print(json.dumps({"mode": "dry-run", "inventory": inventory, "read_only_backup_devices": devices,
                          "private_destination": str(out)}, indent=2))
        return
    out.mkdir(mode=0o700, parents=True)
    manifest = {"schema": 1, "kind": "npu-backup", "inventory": inventory, "files": {}, "complete": False}
    save_json(out / "inventory.json", inventory)
    # Capture boot variables privately for console recovery; never print their values.
    env = subprocess.run(ssh + ["fw_printenv"], capture_output=True, check=True).stdout
    require(env, "Empty boot environment; record recovery information before backup")
    (out / "uboot-environment.txt").write_bytes(env)
    os.chmod(out / "uboot-environment.txt", 0o600)
    manifest["files"]["uboot-environment.txt"] = {"sha256": sha256(out / "uboot-environment.txt"), "size": len(env)}
    for dev, size in devices.items():
        require(size > 0, f"Invalid size for {dev}")
        name = "rootfs.ext4" if dev == inventory["root_device"] else Path(dev).name + ".img"
        partial = out / (name + ".partial")
        with open(partial, "xb") as f:
            os.chmod(partial, 0o600)
            subprocess.run(ssh + [f"dd if={device(dev)} bs=1048576"], stdout=f, check=True)
        require(partial.stat().st_size == size, f"Short backup of {dev}; partial retained")
        local_hash = sha256(partial)
        remote_hash = subprocess.run(ssh + [f"sha256sum {device(dev)}"], capture_output=True,
                                     text=True, check=True).stdout.split()[0]
        require(local_hash == remote_hash, f"Backup checksum mismatch for {dev}; partial retained")
        partial.rename(out / name)
        manifest["files"][name] = {"sha256": local_hash, "size": size, "device": dev}
        print(f"Verified read-only backup: {dev} ({size} bytes)")
    require(remote_inventory(ssh) == inventory, "NPU inventory changed during backup; no complete manifest issued")
    manifest["complete"] = True
    save_json(out / "manifest.json", manifest)
    print(f"Complete private backup: {out}. Copy this directory off the appliance.")


def load_backup(directory):
    directory = Path(directory).resolve()
    manifest = json.loads(regular(directory / "manifest.json").read_text())
    require(manifest.get("schema") == 1 and manifest.get("kind") == "npu-backup" and manifest.get("complete") is True,
            "A complete backup manifest is required")
    inventory = manifest["inventory"]
    require(inventory["root_device"] != inventory["disk_device"], "Invalid backup inventory")
    require("rootfs.ext4" in manifest["files"], "Active original rootfs image is missing")
    require("uboot-environment.txt" in manifest["files"], "Original boot environment is missing")
    require(manifest["files"]["rootfs.ext4"].get("device") == inventory["root_device"],
            "Original rootfs image is not tied to the inventoried active root")
    required_devices = {inventory["disk_device"], inventory["root_device"], *inventory["flash"]}
    required_devices.update(p for p in inventory["blocks"]
                            if p in (inventory["disk_device"] + "boot0", inventory["disk_device"] + "boot1"))
    sizes = dict(inventory["blocks"], **inventory["flash"])
    backed_devices = set()
    for name, meta in manifest["files"].items():
        require(Path(name).name == name and name not in (".", ".."), "Unsafe manifest filename")
        path = regular(directory / name)
        require(path.stat().st_size == meta["size"] and sha256(path) == meta["sha256"], f"Backup verification failed: {name}")
        if "device" in meta:
            dev = device(meta["device"])
            require(dev in sizes and meta["size"] == sizes[dev], f"Backup does not cover the full device: {dev}")
            backed_devices.add(dev)
    require(required_devices <= backed_devices, "Full eMMC/active rootfs/SPI backup set is incomplete")
    return directory, manifest


def image_path(value):
    require(bool(SAFE_PATH.fullmatch(value)) and ".." not in PurePosixPath(value).parts,
            f"Unsafe image path: {value}")
    return value


def debug_quote(value):
    value = str(value)
    require(not any(c in value for c in "\r\n\0"), "Control character in debugfs argument")
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


def debugfs(image, command, write=False, missing_ok=False):
    tool = shutil.which("debugfs")
    require(tool is not None, "Install e2fsprogs (debugfs and e2fsck) on the Linux build host")
    argv = [tool] + (["-w"] if write else []) + ["-R", command, str(regular(image))]
    result = subprocess.run(argv, capture_output=True, text=True, check=True)
    errors = "\n".join(line for line in result.stderr.splitlines() if not line.startswith("debugfs "))
    if errors and missing_ok and "File not found by ext2_lookup" in errors:
        return None
    require(not errors, f"debugfs rejected operation: {errors}")
    return result.stdout


def image_stat(image, name, missing_ok=False):
    return debugfs(image, "stat " + debug_quote(image_path(name)), missing_ok=missing_ok)


def fsck(image):
    require(shutil.which("e2fsck"), "Install e2fsprogs on the Linux build host")
    result = subprocess.run(["e2fsck", "-fn", str(regular(image))], capture_output=True, text=True)
    require(result.returncode == 0, "Original/candidate filesystem is not clean; inspect it without modifying the backup:\n" +
            result.stdout + result.stderr)


def list_files(image, base):
    """Only inspect regular files/directories, never follow image symlinks."""
    result = debugfs(image, "ls -p " + debug_quote(image_path(base)), missing_ok=True)
    if result is None:
        return []
    files = []
    for line in result.splitlines():
        if not line.strip():
            continue
        part = line.split("/")
        require(len(part) >= 7, "Unrecognized debugfs directory listing")
        _, inode, mode, uid, gid, name, size, *_ = part
        if inode == "0" or name in (".", ".."):
            continue
        path = image_path(base.rstrip("/") + "/" + name)
        kind = int(mode, 8)
        if stat.S_ISDIR(kind):
            files.extend(list_files(image, path))
        elif stat.S_ISREG(kind):
            files.append(path)
    return files


def extract(args):
    source, manifest = load_backup(args.backup)
    image = source / "rootfs.ext4"
    fsck(image)
    kernel = manifest["inventory"]["kernel_release"]
    files = list_files(image, "/lib/modules/" + kernel) + list_files(image, "/opt/dp")
    selected = {}
    for name in MODULES:
        matches = [p for p in files if PurePosixPath(p).name == name]
        require(len(matches) == 1, f"Expected one {name} for {kernel}; found {len(matches)}. Inspect the original image.")
        selected[name] = matches[0]
    out = private_output(args.out)
    if not args.apply:
        print(json.dumps({"mode": "dry-run", "kernel_release": kernel, "module_sources": selected,
                          "private_destination": str(out)}, indent=2))
        return
    out.mkdir(mode=0o700, parents=True)
    result = {"schema": 1, "kind": "private-vendor-modules", "kernel_release": kernel,
              "original_rootfs_sha256": manifest["files"]["rootfs.ext4"]["sha256"], "files": {}}
    for name, origin in selected.items():
        destination = out / name
        debugfs(image, "dump -p " + debug_quote(origin) + " " + debug_quote(destination))
        regular(destination)
        os.chmod(destination, 0o600)
        result["files"][name] = {"sha256": sha256(destination), "source_path": origin}
    save_json(out / "manifest.json", result)
    print(f"Extracted own-appliance modules to {out}; do not redistribute this directory.")


def payload_files(root):
    root = Path(root).resolve()
    require(root.is_dir(), "Payload directory is missing")
    result = {}
    for path in sorted(root.rglob("*")):
        require(not path.is_symlink(), f"Payload symlink is not permitted: {path}")
        require(path.is_file() or path.is_dir(), f"Payload special file is not permitted: {path}")
        if path.is_file():
            relative = path.relative_to(root).as_posix()
            image_path("/opt/xgs116/" + relative)
            result[relative] = path
    for name in ("dp_fwd", "dp-nmp-config.txt", "board.conf", "startup/dp-autostart.sh",
                 "switch-init/sw-init.sh", "switch-init/swmdio.sh", "build-profile.conf",
                 "BUILD-INFO.json", "SHA256SUMS"):
        require(name in result, f"Payload is missing {name}")
    listed = set()
    for line in result["SHA256SUMS"].read_text().splitlines():
        match = re.fullmatch(r"([0-9a-f]{64})  ([A-Za-z0-9_./+-]+)", line)
        require(match is not None, "Invalid payload checksum manifest")
        expected, name = match.groups()
        require(not name.startswith("/") and ".." not in PurePosixPath(name).parts and
                name not in listed and name in result, "Unsafe or duplicate payload checksum path")
        require(sha256(result[name]) == expected, f"Payload checksum mismatch: {name}")
        listed.add(name)
    required = {"dp_fwd", "dp-nmp-config.txt", "startup/dp-autostart.sh",
                "switch-init/sw-init.sh", "switch-init/swmdio.sh", "build-profile.conf", "BUILD-INFO.json"}
    require(required <= listed, "Payload manifest does not cover all startup and binary inputs")
    board = {}
    for line in result["board.conf"].read_text().splitlines():
        if not line or line.startswith("#"):
            continue
        key, sep, value = line.partition("=")
        require(sep and key not in board, "Duplicate or malformed board field")
        board[key] = value
    require(board.get("board_confirmed") == "yes" and board.get("swop_slot_confirmed") == "yes",
            "Board mapping and NWA+0xf000 slot survey must be confirmed on the appliance")
    require(re.fullmatch(r"[0-9]{1,2}", board.get("dsa_device", "")) is not None and
            0 <= int(board["dsa_device"]) <= 31, "Invalid board DSA device")
    info = json.loads(result["BUILD-INFO.json"].read_text())
    require(info.get("dsa_device") == int(board["dsa_device"]), "Forwarder DSA target differs from board")
    require(info.get("swop_capability_version") in (1, 2), "Unsupported SWOP build profile")
    profile = result["build-profile.conf"].read_text()
    require(profile == f'dsa_device={int(board["dsa_device"])}\nswop_version={info["swop_capability_version"]}\n',
            "Build profile and build provenance disagree")
    return result


def ensure_image_dirs(image, directory):
    accumulated = ""
    for item in PurePosixPath(directory).parts[1:]:
        accumulated += "/" + item
        info = image_stat(image, accumulated, missing_ok=True)
        if info is None:
            debugfs(image, "mkdir " + debug_quote(accumulated), write=True)
        else:
            require("Type: directory" in info, f"Image parent must be a directory, never a symlink: {accumulated}")


def put_image_file(image, source, target, mode):
    target = image_path(target)
    ensure_image_dirs(image, str(PurePosixPath(target).parent))
    require(image_stat(image, target, missing_ok=True) is None, f"Refusing to overwrite original image file: {target}")
    debugfs(image, "write " + debug_quote(regular(source)) + " " + debug_quote(target), write=True)
    for field, value in (("mode", oct(stat.S_IFREG | mode)), ("uid", "0"), ("gid", "0")):
        # debugfs's numeric parser accepts C-style octal, not Python's 0o prefix.
        if field == "mode":
            value = "0" + format(stat.S_IFREG | mode, "o")
        debugfs(image, f"set_inode_field {debug_quote(target)} {field} {value}", write=True)


def validate_profile(profile, inventory):
    require(profile.get("schema") == 1, "Unsupported boot profile schema")
    require(profile.get("kernel_release") == inventory["kernel_release"], "Boot profile kernel does not match own-appliance backup")
    require(profile.get("serial_recovery_confirmed") is True, "Serial recovery must be checked on this appliance")
    require(profile.get("stock_service_startup_reviewed") is True, "Review stock service startup and base module loading first")
    disabled = profile.get("disable_paths")
    require(isinstance(disabled, list) and disabled, "List the inspected stock dataplane/service startup files to disable")
    for path in disabled:
        image_path(path)
        require(path.startswith(("/etc/init.d/", "/opt/sophos/")), "Only reviewed service paths may be disabled")
        require(not path.endswith(("/rcS", "/rc", "/init")), "Never disable the root init sequence")
    return disabled


def prepare(args):
    source, manifest = load_backup(args.backup)
    inventory = manifest["inventory"]
    target = device(args.target_slot)
    require(target in inventory["blocks"] and re.fullmatch(re.escape(inventory["disk_device"]) + r"p[0-9]+", target),
            "Target must be an inventoried partition on the same eMMC")
    require(target != inventory["root_device"], "Refusing the active rootfs slot")
    image = source / "rootfs.ext4"
    require(inventory["blocks"][target] >= image.stat().st_size, "Target slot is smaller than the original rootfs")
    fsck(image)
    for boot in ("/boot/Image", "/boot/cn9130-Sophos-XGS116.dtb", "/etc/init.d/rcS", "/usr/sbin/sshd"):
        info = image_stat(image, boot)
        require(info and "Type: regular" in info, f"Required original boot/recovery file missing: {boot}")
    rc = debugfs(image, "cat /etc/init.d/rcS")
    require("/etc/init.d/S??*" in rc or "/etc/init.d/S[0-9][0-9]*" in rc,
            "Unsupported init dispatch: verify how this original rootfs starts services before preparing it")
    profile = json.loads(regular(args.boot_profile).read_text())
    disabled = validate_profile(profile, inventory)
    for path in disabled:
        info = image_stat(image, path)
        require(info and "Type: regular" in info, f"Service disable target must be an inspected regular file: {path}")
    files = payload_files(args.payload)
    # Kernel modules may remain at their original matching /lib/modules location.
    # Any modules supplied in the payload must have a verified own-appliance manifest.
    modules = [name for name in files if name.endswith(".ko")]
    if modules:
        require(args.vendor_manifest, "A private extraction manifest is required for payload kernel modules")
        vendor = json.loads(regular(args.vendor_manifest).read_text())
        require(vendor.get("kind") == "private-vendor-modules" and vendor.get("kernel_release") == inventory["kernel_release"],
                "Payload module manifest has incompatible kernel provenance")
        require(vendor.get("original_rootfs_sha256") == manifest["files"]["rootfs.ext4"]["sha256"], "Modules come from a different rootfs")
        for name in modules:
            meta = vendor["files"].get(PurePosixPath(name).name, {})
            require(sha256(files[name]) == meta.get("sha256"), f"Unverified vendor module: {name}")
    out = private_output(args.out)
    description = {"schema": 1, "kind": "npu-offline-candidate", "hardware_validated": False,
                   "original_rootfs_sha256": manifest["files"]["rootfs.ext4"]["sha256"],
                   "original_root_device": inventory["root_device"], "intended_inactive_slot": target,
                   "kernel_release": inventory["kernel_release"], "disabled_services": disabled,
                   "boot_profile_sha256": sha256(args.boot_profile),
                   "payload_sha256": {name: sha256(path) for name, path in files.items()},
                   "bootloader_modified": False, "storage_written": False}
    if not args.apply:
        print(json.dumps(dict(description, mode="dry-run", private_destination=str(out)), indent=2))
        return
    out.mkdir(mode=0o700, parents=True)
    candidate = out / "rootfs-xgs116.ext4"
    shutil.copyfile(image, candidate)
    os.chmod(candidate, 0o600)
    # Rename only approved service files inside the *regular image copy*. debugfs
    # link/unlink changes directory entries and preserves original inode data.
    for path in disabled:
        # A suffix still matches rcS's S??* glob. Hide the original under a
        # dot-prefixed sibling instead, preserving it for offline recovery.
        saved = str(PurePosixPath(path).parent / (".xgs116-disabled-" + PurePosixPath(path).name))
        require(image_stat(candidate, saved, missing_ok=True) is None, f"Already modified image: {saved}")
        debugfs(candidate, "link " + debug_quote(path) + " " + debug_quote(saved), write=True)
        debugfs(candidate, "unlink " + debug_quote(path), write=True)
    for name, path in files.items():
        mode = 0o755 if name.endswith(".sh") or name == "dp_fwd" else 0o600
        put_image_file(candidate, path, "/opt/xgs116/" + name, mode)
    hook = """#!/bin/sh
# SPDX-License-Identifier: MIT
# One launch per NPU boot; a failure requires console diagnosis, not a restart loop.
case "$1" in
start|'')
    [ ! -e /tmp/xgs116-start-attempted ] || exit 0
    : > /tmp/xgs116-start-attempted
    DP=/opt/xgs116 /bin/sh /opt/xgs116/startup/dp-autostart.sh --apply >/tmp/xgs116-startup.log 2>&1 &
    ;;
stop) echo 'Automatic dataplane stop is disabled; use coordinated host/NPU recovery.' >&2; exit 1 ;;
*) exit 1 ;;
esac
"""
    with tempfile.TemporaryDirectory() as temp:
        hook_path = Path(temp) / "S99xgs116"
        hook_path.write_text(hook)
        put_image_file(candidate, hook_path, "/etc/init.d/S99xgs116", 0o755)
    fsck(candidate)
    # Verify the original wasn't altered by any debugfs operation.
    require(sha256(image) == manifest["files"]["rootfs.ext4"]["sha256"], "Original backup changed unexpectedly")
    description.update(candidate_sha256=sha256(candidate), candidate_size=candidate.stat().st_size)
    save_json(out / "candidate.json", description)
    print(f"Offline candidate verified: {candidate}. No device or U-Boot variable was written.")


def rollback(args):
    source, manifest = load_backup(args.backup)
    inventory = manifest["inventory"]
    plan = {"mode": "read-only-plan", "original_root_device": inventory["root_device"],
            "original_boot_environment": str(source / "uboot-environment.txt"),
            "verified_backup": str(source),
            "steps": [
                "Use the already-tested NPU serial console; interrupt U-Boot before boot.",
                "Inspect printenv bootcmd bootargs and compare with the private original environment backup.",
                "For one boot, use the original bootcmd and bootargs values in RAM only; do not saveenv.",
                "Confirm the original kernel and original root partition are running.",
                "Coordinate an x86 host restart to recreate stale PCIe/DMA rings.",
                "Permanent boot-variable changes and any partition restore need separate explicit approval and hardware validation."
            ],
            "automatic_rollback_proven": False,
            "writes_performed": False}
    print(json.dumps(plan, indent=2))


def parser():
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest="action", required=True)
    b = sub.add_parser("backup", help="Read-only remote inventory and full private backup; dry-run by default")
    b.add_argument("--host", required=True)
    b.add_argument("--identity")
    b.add_argument("--known-hosts")
    b.add_argument("--out", required=True)
    b.add_argument("--apply", action="store_true", help="Write backup files locally; never changes the NPU")
    b.set_defaults(func=backup)
    e = sub.add_parser("extract", help="Extract own modules from a verified original ext4 backup")
    e.add_argument("--backup", required=True)
    e.add_argument("--out", required=True)
    e.add_argument("--apply", action="store_true")
    e.set_defaults(func=extract)
    s = sub.add_parser("prepare", help="Build an offline ext4 candidate; no device writes or boot switching")
    s.add_argument("--backup", required=True)
    s.add_argument("--payload", required=True)
    s.add_argument("--boot-profile", required=True)
    s.add_argument("--vendor-manifest")
    s.add_argument("--target-slot", required=True)
    s.add_argument("--out", required=True)
    s.add_argument("--apply", action="store_true")
    s.set_defaults(func=prepare)
    r = sub.add_parser("rollback", help="Verify originals and display a serial recovery plan")
    r.add_argument("--backup", required=True)
    r.set_defaults(func=rollback)
    return p


def main(argv=None):
    os.umask(0o077)
    args = parser().parse_args(argv)
    try:
        args.func(args)
    except (SafetyError, OSError, ValueError, KeyError, subprocess.CalledProcessError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
