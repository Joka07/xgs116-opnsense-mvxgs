# mvxgs — experimental Sophos XGS / Marvell 11ab:7080 FreeBSD probe driver

## What this is

This is **Phase 1**, not a working Ethernet driver yet.

It binds FreeBSD/OPNsense to the Marvell PCIe endpoint observed on a Sophos XGS 116:

- PCI vendor: `0x11ab` (Marvell)
- PF device: `0x7080`
- advertised VF device: `0x7081`
- observed BARs: BAR0 = 1 MiB, BAR2 = 16 MiB, BAR4 = 16 MiB
- PCIe x4 @ 8.0 GT/s on the tested unit
- MSI-X: 16 vectors advertised
- SR-IOV: up to 6 VFs advertised

The module deliberately does **not** touch unknown NPU registers. It maps the BARs and proves that a FreeBSD driver can claim the endpoint safely enough for the next reverse-engineering stage.

## Why this is not Ethernet yet

Sophos' XGS installer loads two Marvell-specific Linux modules (`mv_armada_drv` and `mv_pcinet_drv`), waits for an `mvmgmt0` management interface, then talks to and updates a separate NPU root filesystem. That strongly indicates that `11ab:7080` is not a conventional MAC/NIC where adding a PCI ID to an existing FreeBSD driver is sufficient.

A functional FreeBSD driver still needs at least:

1. NPU bring-up / reset sequence
2. host-to-NPU mailbox protocol
3. firmware / rootfs boot or negotiation rules
4. shared-memory/DMA queue layout
5. interrupt cause/ack registers
6. RX/TX descriptor format
7. physical-port enumeration and link-state protocol
8. probably the mapping between management channel, packet channel and SR-IOV VFs

Do not invent these register definitions. Wrong MMIO or DMA writes can hang or corrupt the NPU state.

## Build target

Build against the **same OPNsense/FreeBSD source ABI as the target**. The tested live system reported OPNsense 26.7 / FreeBSD 15.1-RELEASE-p1.

OPNsense publishes its source and build tooling. A clean build VM is safer than compiling on the live firewall.

Typical outline on a FreeBSD build VM:

```sh
pkg install -y git
git clone https://github.com/opnsense/src /usr/src
# Check out the branch/revision matching the target OPNsense build.
cd /path/to/mvxgs-driver
make
```

If the exact OPNsense branch differs, match it before building. Kernel modules can fail to load or crash when built against an incompatible ABI.

## Test on the OPNsense live USB

Copy `mvxgs.ko` to the live system, then:

```sh
kldload ./mvxgs.ko
dmesg | tail -n 40
pciconf -lv
```

Expected change:

- before: `none0@pci0:1:0:0`
- after:  `mvxgs0@pci0:1:0:0`

Expected attach messages should list BAR0/BAR2/BAR4 and MSI/MSI-X counts.

Unload:

```sh
kldunload mvxgs
```

Because this Phase 1 driver does not enable bus mastering, allocate interrupts, or access MMIO registers, it is intentionally conservative.

## Collect the missing information from SFOS

Boot the original Sophos installation and run the read-only collector from a shell with enough privileges:

```sh
sh collect-sfos-npu.sh /tmp/xgs-npu.txt
```

Bring `/tmp/xgs-npu.txt` back for analysis.

The most valuable items are:

- `modinfo` for `mv_pcinet_drv` / `mv_armada_drv`
- exact module file names and hashes
- `strings` / exported symbol tables
- `lspci -nnvv` while SFOS has the NPU running
- the sysfs PCI resource map
- `mvmgmt0` driver metadata
- names/paths of NPU firmware and rootfs images

## Current status

- PCI binding scaffold: implemented
- BAR resource mapping: implemented
- MSI/MSI-X discovery: implemented
- DMA: intentionally not implemented
- interrupt allocation: intentionally not implemented
- mailbox: unknown
- firmware boot: unknown
- network interfaces: not implemented
- RX/TX: not implemented

