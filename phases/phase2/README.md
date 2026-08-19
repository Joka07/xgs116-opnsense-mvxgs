# mvxgs Phase 2 — passive XGS 116 NPU handshake decoder

This is the second experimental FreeBSD/OPNsense driver stage for the Marvell NPU in a Sophos XGS 116 (`11ab:7080`).

## What changed from Phase 1

Phase 1 only claimed the PCI device and mapped BAR resources.

Phase 2 now contains a behavioural reimplementation of the **read side** of Sophos' initial `armada_pci` handshake:

- locate the vendor BAR map in the last 4 KiB of BAR2;
- verify BAR-map version `5`;
- verify target cookie `0xd0fac10d`;
- decode the five facility records (`ctrl`, `mvmgmt`, `nwa`, `rpc`, `giu`);
- translate Sophos' logical BAR-window offsets;
- read the known `ctrl` cookie `0xafacafac` and control flags;
- expose the decoded values under `dev.mvxgs.0.*`.

## Safety

This build is intentionally read-only from the NPU's perspective.

It does **not**:

- write MMIO registers;
- set the host-ready bit;
- enable SR-IOV;
- create VFs;
- enable PCI bus mastering;
- allocate DMA rings;
- allocate MSI/MSI-X interrupts;
- ring host-to-target doorbells;
- reset or upload firmware to the NPU;
- create an Ethernet interface.

That is deliberate.  We first need to know whether the NPU exposes the same live shared-memory handshake when booted with OPNsense.

## Build

Build against the exact FreeBSD/OPNsense kernel source matching the live target (the tested live USB reported FreeBSD 15.1 / OPNsense 26.7).

```sh
cd mvxgs-driver-phase2
make
```

The expected output is `mvxgs.ko`.

Do not use a module built against an unrelated FreeBSD kernel ABI.

## First OPNsense test

Boot the same OPNsense live USB used for the original hardware test.  Do not install it to the Sophos SSD.

Copy `mvxgs.ko` to the live system and run:

```sh
kldload ./mvxgs.ko
dmesg | grep -i mvxgs
sysctl dev.mvxgs.0
```

If the NPU was not ready when the module attached, wait a few seconds and rescan:

```sh
sysctl dev.mvxgs.0.rescan=1
sysctl dev.mvxgs.0
```

### Best-case result

Look for values equivalent to:

```text
dev.mvxgs.0.barmap_valid: 1
dev.mvxgs.0.barmap_version: 5
dev.mvxgs.0.target_cookie: 3506094349   # 0xd0fac10d
dev.mvxgs.0.ctrl_valid: 1
dev.mvxgs.0.ctrl_cookie: 2947329964     # 0xafacafac
```

and a status similar to:

```text
PASS: target barmap and ctrl handshake state are visible
```

The exact decimal rendering of cookies is not important; the dmesg line prints them in hex.

### If it does not pass

Send back:

```sh
dmesg | grep -i mvxgs
sysctl dev.mvxgs.0
pciconf -lBbcev pci0:1:0:0
```

Do **not** start writing random BAR values.  A failed passive scan tells us which earlier initialization stage is missing.

## Unload

```sh
kldunload mvxgs
```

## Current roadmap

- Phase 1: claim PF and map BARs — done
- Phase 2: decode target BAR map and ctrl handshake read-only — implemented here
- Phase 3: controlled host-ready handshake + MSI-X/doorbell discovery — only after Phase 2 passes
- Phase 4: management (`mvmgmt` / NWA) transport
- Phase 5: VF `11ab:7081` data-plane queues
- Phase 6: PPORT tagging and actual Port1..Port8/PortF1 FreeBSD interfaces

See `reverse-engineering/PROTOCOL.md` for the recovered protocol details.

## Easier Phase-2 test: no kernel-module build needed

For the specific XGS 116 tested here, OPNsense reported BAR2 at `0xfd000000`
with size `0x01000000`.  Live probing corrected an earlier off-by-one-page
assumption: the vendor BAR map is at physical address `0xfdffe000` (BAR2
end - `0x2000`).  The final BAR2 page at `0xfdfff000` contains a separate
`BOOTCMD!` structure.

Before compiling this module, the same handshake page can be checked from the
OPNsense live environment using the read-only helper:

```sh
sh tools/passive-opnsense-probe.sh
```

The expected first eight bytes, if the NPU has already exposed its target BAR
map, are:

```text
05 00 00 00 0d c1 fa d0
```

which decode as BAR-map version `5` and target cookie `0xd0fac10d`.

The target facility records observed on the XGS 116 decode as:

- logical BAR 0, facility 4 (`giu`), offset `0x0000`, size `0x4000`
- logical BAR 1, facility 0 (`ctrl`), offset `0x0000`, size `0x1000`
- logical BAR 1, facility 1 (`mvmgmt`), offset `0x1000`, size `0x1000`
- logical BAR 0, facility 2 (`nwa`), offset `0x4000`, size `0x10000`
- logical BAR 1, facility 3 (`rpc`), offset `0x2000`, size `0x100000`

Here logical BAR 0 maps to PF BAR0 and logical BAR 1 maps to the Sophos
window inside PF BAR2 beginning at `0xfdefc000` on this boot.

This helper only reads `/dev/mem`; it does not write NPU MMIO.  If the BAR
address changes on a later boot, do not use the hard-coded helper until the
new BAR2 location has been confirmed with `pciconf -lBbcev pci0:1:0:0`.
