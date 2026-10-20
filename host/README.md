# Experimental OPNsense host integration

This integration targets **OPNsense 26.7, FreeBSD 15.1-RELEASE-p1, amd64** and the
exact kernel source revision `12334a596709d195acb73f0f069da82c570a3d84`. It cannot
make an NPU image persistent or prove physical packet forwarding. The first
installation and every ABI update need serial-console access and a tested
recovery path. Do not use this experimental package as a production firewall
before the repository's hardware acceptance tests pass.

## Build and package

Build `driver/if_agnic` against the exact target kernel sources using the main
build instructions. On the target, record `uname -v`; never guess the string.
The packaging tool runs on Python 3 and validates the ELF architecture, then
creates a deterministic gzip/tar archive and SHA256 file:

```
python3 packaging/build-host-package.py \
  --module /path/to/if_agnic.ko \
  --kernel-ident 'the exact complete target uname -v output' \
  --output /path/to/xgs116-host.tar.gz
```

The metadata records the build target asserted by the packager. It does **not**
prove that an arbitrary input object was built from the pinned sources. Retain
the build log and source provenance alongside the archive. Compare the archive
SHA256 over a trusted channel before extraction; checksum files detect damage,
not a malicious publisher. No proprietary files enter this archive.

The archive is a transparent staging package, not a FreeBSD `pkg` package or an
OPNsense repository plugin. Installation uses documented executable syshooks;
it neither modifies OPNsense core files nor edits its interface assignments.

## Install on the target

Extract into a new empty directory and run:

```
cd xgs116-host
sh installer/preflight.sh .
sh installer/install-host.sh --bundle .
sh installer/install-host.sh --bundle . --apply
```

The default is a dry run. Live installation requires matching `uname -v`, running
and installed kernel releases, OPNsense series, module digest/ELF architecture,
and exactly one unclaimed or AGNIC-bound PCI endpoint `11ab:7080`. Existing
files require `--replace-existing`; a checksummed copy is retained under
`/var/backups/xgs116-agnic/install.*` before replacement. Source and destination
symlinks are rejected. No module is loaded during installation.

For a disposable offline filesystem, `--stage-root /absolute/existing/directory`
skips running-host and PCI checks and installs only there when `--apply` is given.
Such staging is **not** evidence of FreeBSD compatibility or hardware readiness.

After the NPU is independently prepared, make the first controlled boot with a
serial console. `early/50-xgs116-agnic` runs before OPNsense network setup. It
checks the exact module target, loads once, and waits at most 60 readiness polls
for `mgmt_ready=1`, `datapath_ready=1`, `nports=9`, `recovery_required=0` and all
nine `portN` interfaces. Driver attach has its own internal bounded waits, so
total boot time also includes those waits. OPNsense performs its normal network
configuration afterwards. No interface address or firewall rule is changed by
the package. The hook logs failures and latches a failure for the remainder of
the boot; it never cycles the NPU or unloads/reloads a driver to retry.

```
/usr/local/libexec/xgs116-agnic/agnic-control.sh check
/usr/local/libexec/xgs116-agnic/agnic-control.sh diagnose > /tmp/xgs116-diagnostics.txt
```

Initialization is not a forwarding test: verify RX and TX at the peer and NPU,
VLAN isolation, every physical port and power-cycle behavior. NPU restarts can
invalidate DMA rings. `recovery_required` detects known ring/reset failures;
it is not a complete liveness oracle. Use a controlled cold restart via serial
console when required; there is no automatic reattach/restart loop.

## Updates and host rollback

An `update` syshook checks compatibility/readiness after OPNsense core updates.
The early hook refuses loading on a different kernel build. Rebuild and package
for the exact supported kernel; **this release intentionally refuses other
kernel releases/source revisions**. An upgrade to another revision requires a
reviewed code/metadata update and hardware regression tests, not overriding a
version check. Preserve console access before any OPNsense update.

If boot fails, enter single-user/serial recovery and disable the early hook
before the next boot by removing its executable bit or moving it aside. Restore
it to its original path/mode before the checksum-based rollback below; alternatively
restore the backed-up files manually from console, checking backup digests first.
Do not unload an active experimental DMA module. Once the module is absent:

```
sh host/rollback-host.sh /var/backups/xgs116-agnic/install.ABC123
sh host/rollback-host.sh /var/backups/xgs116-agnic/install.ABC123 --apply
```

Rollback refuses changed installed files, corrupt backups and symlink paths. It
restores host files only; NPU partitions and U-Boot are untouched. If the module
is already loaded, rollback refuses and requires console recovery. Preserve a
copy of this unpacked package for access to the rollback command.

Official mechanism: OPNsense `docs` repository,
`source/development/backend/autorun.rst` at
`ea0d9dd5b2c448e8676f3c55bf7725dab2acab9b`; `early` runs before networking,
`update` after a core package update, and plugin hook prefix `50-` is documented.
