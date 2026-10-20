# SPDX-License-Identifier: MIT
"""Safety and actual offline ext4 transformation tests (no appliance required)."""
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("npu_tools", ROOT / "installer/npu_tools.py")
npu = importlib.util.module_from_spec(spec)
spec.loader.exec_module(npu)


def inventory_text(root="/dev/mmcblk0p2", mode="ro"):
    return (
        "K\t4.14.fixture\n"
        f"R\t{root}\text4\t{mode},relatime\n"
        "C\t/dev/mmcblk0p2\n"
        "B\t/dev/mmcblk0\t262144\n"
        "B\t/dev/mmcblk0p2\t65536\n"
        "B\t/dev/mmcblk0p3\t65536\n"
        "F\t/dev/mtd0\t00000010\n"
        "F\t/dev/mtd1\t00000010\n"
        f"M\t{root}\t/\t{mode},relatime\n"
    )


class Safety(unittest.TestCase):
    def test_inventory_identifies_actual_active_slot(self):
        result = npu.parse_inventory(inventory_text())
        self.assertEqual(result["root_device"], "/dev/mmcblk0p2")
        self.assertEqual(result["disk_device"], "/dev/mmcblk0")
        npu.assert_quiescent(result)

    def test_dev_root_resolved_against_cmdline(self):
        self.assertEqual(npu.parse_inventory(inventory_text("/dev/root"))["root_device"],
                         "/dev/mmcblk0p2")

    def test_mount_root_mismatch_rejected(self):
        with self.assertRaises(npu.SafetyError):
            npu.parse_inventory(inventory_text("/dev/mmcblk0p3"))

    def test_writable_storage_rejected(self):
        for text in (inventory_text(mode="rw"), inventory_text() + "M\t/dev/mmcblk0p4\t/persistent\trw\n"):
            with self.assertRaises(npu.SafetyError):
                npu.assert_quiescent(npu.parse_inventory(text))

    def test_device_and_image_command_injection_rejected(self):
        for value in ("/dev/mtd0; reboot", "/dev/sda", "/dev/mmcblk0p2\nx"):
            with self.assertRaises(npu.SafetyError):
                npu.device(value)
        for value in ("/etc/../boot/x", '/tmp/x"; rm /', "/tmp/x\nwrite y"):
            with self.assertRaises(npu.SafetyError):
                npu.image_path(value)

    def test_private_originals_cannot_be_written_into_repository(self):
        with self.assertRaises(npu.SafetyError):
            npu.private_output(ROOT / "vendor-files-test")

    def test_payload_symlink_is_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "evil").symlink_to("/etc/passwd")
            with self.assertRaises(npu.SafetyError):
                npu.payload_files(d)

    def test_blank_safety_profile_is_rejected(self):
        with self.assertRaises(npu.SafetyError):
            npu.validate_profile(json.loads((ROOT / "installer/npu-boot-profile.example.json").read_text()),
                                 npu.parse_inventory(inventory_text()))


@unittest.skipUnless(all(shutil.which(x) for x in ("debugfs", "mke2fs", "e2fsck")),
                     "e2fsprogs is needed for real ext4 integration tests")
class Ext4Integration(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.work = Path(self.temp.name)
        self.backup = self.work / "backup"
        self.backup.mkdir()
        tree = self.work / "tree"
        fixture = {
            "boot/Image": b"fixture kernel",
            "boot/cn9130-Sophos-XGS116.dtb": b"fixture device tree",
            "etc/init.d/rcS": b'#!/bin/sh\nfor x in /etc/init.d/S??*; do "$x" start; done\n',
            "etc/init.d/S80vendor-dataplane": b"#!/bin/sh\nexec usfp\n",
            "usr/sbin/sshd": b"fixture sshd",
        }
        for name in npu.MODULES:
            fixture["lib/modules/4.14.fixture/extra/" + name] = name.encode()
        for name, content in fixture.items():
            p = tree / name
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_bytes(content)
        self.image = self.backup / "rootfs.ext4"
        with open(self.image, "wb") as f:
            f.truncate(32 * 1024 * 1024)
        subprocess.run(["mke2fs", "-q", "-F", "-t", "ext4", "-d", str(tree), str(self.image)], check=True)
        inventory = npu.parse_inventory(inventory_text())
        files = {"rootfs.ext4": {"size": self.image.stat().st_size,
                                "sha256": npu.sha256(self.image), "device": inventory["root_device"]}}
        # Sparse fixture storage has the real inventoried sizes. It is only a
        # fake whole-disk backup; the rootfs image itself is a real ext4 FS.
        for name, device in (("mmcblk0.img", inventory["disk_device"]), ("mtd0.img", "/dev/mtd0"),
                             ("mtd1.img", "/dev/mtd1")):
            p = self.backup / name
            with open(p, "wb") as f:
                f.write(b"fixture-original")
                f.truncate(inventory["blocks"].get(device, inventory["flash"].get(device)))
            files[name] = {"size": p.stat().st_size, "sha256": npu.sha256(p), "device": device}
        (self.backup / "uboot-environment.txt").write_text("bootargs=fixture\n")
        env = self.backup / "uboot-environment.txt"
        files[env.name] = {"size": env.stat().st_size, "sha256": npu.sha256(env)}
        self.manifest = {"schema": 1, "kind": "npu-backup", "complete": True,
                         "inventory": inventory, "files": files}
        (self.backup / "manifest.json").write_text(json.dumps(self.manifest))
        self.payload = self.work / "payload"
        for name in ("dp_fwd", "dp-nmp-config.txt", "board.conf", "startup/dp-autostart.sh",
                     "switch-init/sw-init.sh", "switch-init/swmdio.sh"):
            p = self.payload / name
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text("fixture payload " + name)
        (self.payload / "board.conf").write_text("board_confirmed=yes\nswop_slot_confirmed=yes\ndsa_device=2\n")
        (self.payload / "build-profile.conf").write_text("dsa_device=2\nswop_version=1\n")
        (self.payload / "BUILD-INFO.json").write_text(json.dumps({"dsa_device": 2, "swop_capability_version": 1}))
        (self.payload / "SHA256SUMS").write_text("".join(
            f"{npu.sha256(p)}  {p.relative_to(self.payload)}\n"
            for p in sorted(self.payload.rglob("*")) if p.is_file() and p.name != "board.conf"))
        self.profile = self.work / "profile.json"
        self.profile.write_text(json.dumps({
            "schema": 1, "kernel_release": "4.14.fixture", "serial_recovery_confirmed": True,
            "stock_service_startup_reviewed": True, "disable_paths": ["/etc/init.d/S80vendor-dataplane"],
        }))

    def args(self, action, *rest):
        return npu.parser().parse_args([action, "--backup", str(self.backup), *rest])

    def prep_args(self, *extra):
        return self.args("prepare", "--payload", str(self.payload), "--boot-profile", str(self.profile),
                         "--target-slot", "/dev/mmcblk0p3", "--out", str(self.work / "candidate"), *extra)

    def test_real_image_prepare_preserves_original_and_boot_files(self):
        before = npu.sha256(self.image)
        npu.prepare(self.prep_args("--apply"))
        candidate = self.work / "candidate/rootfs-xgs116.ext4"
        npu.fsck(candidate)
        self.assertEqual(before, npu.sha256(self.image))
        self.assertIsNone(npu.image_stat(candidate, "/etc/init.d/S80vendor-dataplane", missing_ok=True))
        self.assertIn("Type: regular", npu.image_stat(candidate, "/etc/init.d/.xgs116-disabled-S80vendor-dataplane"))
        self.assertIn("Mode:  0755", npu.image_stat(candidate, "/etc/init.d/S99xgs116"))
        hook = npu.debugfs(candidate, "cat /etc/init.d/S99xgs116")
        self.assertIn("dp-autostart.sh --apply", hook)
        dumped = self.work / "Image"
        npu.debugfs(candidate, 'dump /boot/Image ' + npu.debug_quote(dumped))
        self.assertEqual(dumped.read_bytes(), b"fixture kernel")
        result = json.loads((self.work / "candidate/candidate.json").read_text())
        self.assertEqual(result["candidate_sha256"], npu.sha256(candidate))
        self.assertFalse(result["hardware_validated"])
        self.assertFalse(result["bootloader_modified"])

    def test_dry_run_writes_no_candidate(self):
        npu.prepare(self.prep_args())
        self.assertFalse((self.work / "candidate").exists())

    def test_active_slot_rejected(self):
        args = self.prep_args("--apply")
        args.target_slot = "/dev/mmcblk0p2"
        with self.assertRaises(npu.SafetyError):
            npu.prepare(args)
        self.assertFalse((self.work / "candidate").exists())

    def test_tampered_backup_is_rejected(self):
        (self.backup / "mtd0.img").write_bytes(b"tampered")
        with self.assertRaises(npu.SafetyError):
            npu.load_backup(self.backup)

    def test_tampered_payload_is_rejected(self):
        (self.payload / "dp_fwd").write_bytes(b"damaged")
        with self.assertRaisesRegex(npu.SafetyError, "Payload checksum mismatch"):
            npu.prepare(self.prep_args("--apply"))
        self.assertFalse((self.work / "candidate").exists())

    def test_unsurveyed_swop_slot_is_rejected(self):
        (self.payload / "board.conf").write_text("board_confirmed=yes\ndsa_device=2\n")
        with self.assertRaisesRegex(npu.SafetyError, "slot survey"):
            npu.prepare(self.prep_args("--apply"))

    def test_manifest_traversal_is_rejected(self):
        self.manifest["files"]["../file"] = {"size": 0, "sha256": ""}
        (self.backup / "manifest.json").write_text(json.dumps(self.manifest))
        with self.assertRaises(npu.SafetyError):
            npu.load_backup(self.backup)

    def test_extracts_matching_private_modules(self):
        out = self.work / "modules"
        npu.extract(self.args("extract", "--out", str(out), "--apply"))
        manifest = json.loads((out / "manifest.json").read_text())
        for name in npu.MODULES:
            self.assertEqual((out / name).read_bytes(), name.encode())
            self.assertEqual(manifest["files"][name]["sha256"], npu.sha256(out / name))
        self.assertEqual(manifest["kernel_release"], "4.14.fixture")

    def test_image_parent_symlink_refused(self):
        npu.debugfs(self.image, "symlink /opt /etc", write=True)
        # Intentionally update fixture hash to test the structural check, not tamper detection.
        self.manifest["files"]["rootfs.ext4"]["sha256"] = npu.sha256(self.image)
        (self.backup / "manifest.json").write_text(json.dumps(self.manifest))
        with self.assertRaisesRegex(npu.SafetyError, "directory, never a symlink"):
            npu.prepare(self.prep_args("--apply"))
        self.assertFalse((self.work / "candidate/candidate.json").exists())


if __name__ == "__main__":
    unittest.main()
