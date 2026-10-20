# SPDX-License-Identifier: MIT
"""Portable tests of host packaging and policy; no hardware or kmod load occurs."""
import contextlib
import importlib.util
import io
import os
from pathlib import Path
import shutil
import subprocess
import tarfile
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("host_package", ROOT / "packaging/build-host-package.py")
package = importlib.util.module_from_spec(spec)
spec.loader.exec_module(package)
KERNEL_IDENT = "FreeBSD 15.1-RELEASE-p1 test-only-kernel-build"


class HostIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.work = Path(self.tmp.name)
        self.module = self.work / "test-only-not-a-kernel-module.o"
        subprocess.run(["cc", "-x", "c", "-c", "-o", str(self.module), "-"],
                       input=b"int package_test_fixture;\n", check=True, capture_output=True)
        self.archive = self.work / "host.tar.gz"
        with contextlib.redirect_stdout(io.StringIO()):
            package.build(self.module, KERNEL_IDENT, self.archive)
        with tarfile.open(self.archive) as tf:
            tf.extractall(self.work, filter="data")
        self.bundle = self.work / "xgs116-host"
        self.stage = self.work / "stage"
        self.stage.mkdir()
        self.meta = self.bundle / "payload/usr/local/etc/xgs116-agnic/module.meta"

    def shell(self, program, env=None):
        return subprocess.run(["sh", "-c", '. "$1"; ' + program, "sh", str(ROOT / "host/common.sh")],
                              text=True, capture_output=True, env=env)

    def install(self, *args):
        return subprocess.run(["sh", str(self.bundle / "installer/install-host.sh"),
                               "--bundle", str(self.bundle), "--stage-root", str(self.stage), *args],
                              text=True, capture_output=True)

    def rollback(self, backup, *args):
        return subprocess.run(["sh", str(ROOT / "host/rollback-host.sh"), str(backup),
                               "--stage-root", str(self.stage), *args], text=True, capture_output=True)

    def test_archive_is_byte_reproducible(self):
        other = self.work / "other.tar.gz"
        with contextlib.redirect_stdout(io.StringIO()):
            package.build(self.module, KERNEL_IDENT, other)
        self.assertEqual(self.archive.read_bytes(), other.read_bytes())

    def test_packager_rejects_non_elf_and_multiline_metadata(self):
        self.module.write_bytes(b"not an ELF")
        with self.assertRaises(ValueError):
            package.build(self.module, KERNEL_IDENT, self.work / "bad.tar.gz")
        with self.assertRaises(ValueError):
            package.build(ROOT / "README.md", "bad\nidentity", self.work / "bad2.tar.gz")

    def test_meta_not_executed_and_duplicate_rejected(self):
        sentinel = self.work / "must-not-exist"
        text = self.meta.read_text().replace(KERNEL_IDENT, '$(touch ' + str(sentinel) + ')')
        self.meta.write_text(text)
        result = self.shell(f'xgs_validate_meta "{self.meta}"')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse(sentinel.exists())
        with self.meta.open("a") as f:
            f.write("architecture=amd64\n")
        self.assertNotEqual(self.shell(f'xgs_validate_meta "{self.meta}"').returncode, 0)

    def test_exact_kernel_check(self):
        mocks = '''uname() {
case "$1" in -s) echo FreeBSD;; -m) echo amd64;; -r) echo 15.1-RELEASE-p1;;
-v) echo 'FreeBSD 15.1-RELEASE-p1 test-only-kernel-build';; esac; }
'''
        # Hyphens are valid command names, but not POSIX shell function names.
        commands = self.work / "commands"
        commands.mkdir()
        for name, value in [("freebsd-version", "15.1-RELEASE-p1"),
                            ("opnsense-version", "OPNsense 26.7.2 (amd64)")]:
            script = commands / name
            script.write_text(f"#!/bin/sh\nprintf '%s\\n' '{value}'\n")
            script.chmod(0o755)
        env = dict(os.environ, PATH=str(commands) + os.pathsep + os.environ["PATH"])
        result = self.shell(mocks + f'xgs_platform "{self.meta}"', env=env)
        self.assertEqual(result.returncode, 0, result.stderr)
        result = self.shell(mocks.replace("test-only-kernel-build", "another-build") +
                            f'xgs_platform "{self.meta}"', env=env)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Exact running kernel build", result.stderr)

    def test_readiness_requires_handshake_and_all_nine_ports(self):
        mocks = '''sysctl() { case "$2" in
*.recovery_required) echo 0;; *.mgmt_ready|*.datapath_ready) echo 1;; *.nports) echo 9;; esac; }
ifconfig() { echo 'lo0 port1 port2 port3 port4 port5 port6 port7 port8 port9'; }
'''
        self.assertEqual(self.shell(mocks + "xgs_ready").returncode, 0)
        self.assertNotEqual(self.shell(mocks.replace(" port9'", "'") + "xgs_ready").returncode, 0)
        self.assertNotEqual(self.shell(mocks.replace("*.recovery_required) echo 0", "*.recovery_required) echo 1") +
                                       "xgs_wait_ready 10").returncode, 0)
        self.assertNotEqual(self.shell(mocks.replace("*.mgmt_ready|*.datapath_ready) echo 1", "*.mgmt_ready|*.datapath_ready) echo 0") +
                                       "xgs_wait_ready 0").returncode, 0)

    def test_pci_rejects_conflicting_driver_or_multiple_endpoints(self):
        self.assertEqual(self.shell("pciconf() { echo 'none0@pci0:1:0:0: chip=0x708011ab'; }; xgs_pci").returncode, 0)
        self.assertNotEqual(self.shell("pciconf() { echo 'mvxgs0@pci0:1:0:0: chip=0x708011ab'; }; xgs_pci").returncode, 0)
        self.assertNotEqual(self.shell("pciconf() { printf 'none0@pci0:1:0:0: chip=0x708011ab\\nnone1@pci0:2:0:0: chip=0x708011ab\\n'; }; xgs_pci").returncode, 0)

    def test_default_dry_run_then_staging_install_and_rollback(self):
        result = self.install()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(list(self.stage.iterdir()), [])
        result = self.install("--apply")
        self.assertEqual(result.returncode, 0, result.stderr)
        hook = self.stage / "usr/local/etc/rc.syshook.d/early/50-xgs116-agnic"
        self.assertTrue(os.access(hook, os.X_OK))
        backup = next((self.stage / "var/backups/xgs116-agnic").iterdir())
        self.assertEqual(self.rollback(backup).returncode, 0)
        self.assertTrue(hook.exists())
        result = self.rollback(backup, "--apply")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse(hook.exists())
        self.assertFalse((self.stage / "boot/modules/if_agnic.ko").exists())

    def test_tampered_payload_fails_before_writes(self):
        (self.bundle / "payload/usr/local/libexec/xgs116-agnic/common.sh").write_text("bad\n")
        result = self.install("--apply")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("integrity failure", result.stderr)
        self.assertEqual(list(self.stage.iterdir()), [])

    def test_symlink_destination_refused(self):
        other = self.work / "elsewhere"
        other.mkdir()
        (self.stage / "boot").symlink_to(other, target_is_directory=True)
        self.assertNotEqual(self.install("--apply").returncode, 0)
        self.assertEqual(list(other.iterdir()), [])

    def test_staging_cannot_resolve_to_live_root(self):
        result = subprocess.run(['sh', str(self.bundle / 'installer/install-host.sh'),
                                 '--stage-root', '/tmp/..', '--apply'], capture_output=True, text=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('resolves to the live root', result.stderr)

    def test_replacement_backed_up_and_restored_and_tamper_refused(self):
        existing = self.stage / "boot/modules/if_agnic.ko"
        existing.parent.mkdir(parents=True)
        existing.write_bytes(b"previous-test-module")
        self.assertNotEqual(self.install("--apply").returncode, 0)
        result = self.install("--apply", "--replace-existing")
        self.assertEqual(result.returncode, 0, result.stderr)
        backup = next((self.stage / "var/backups/xgs116-agnic").iterdir())
        old = backup / "files/boot/modules/if_agnic.ko"
        self.assertEqual(old.read_bytes(), b"previous-test-module")
        old.write_bytes(b"corrupt-backup")
        self.assertNotEqual(self.rollback(backup, "--apply").returncode, 0)
        old.write_bytes(b"previous-test-module")
        result = self.rollback(backup, "--apply")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(existing.read_bytes(), b"previous-test-module")


if __name__ == "__main__":
    unittest.main()
