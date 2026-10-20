# XGS116 FreeBSD AGNIC integration (experimental)

This directory imports the BSD-2-Clause FreeBSD driver from
`mamoru-xgs-npu` commit `9e53bbcb10f5ba9cd5f6a43dc5631fc8931cff05`.
The original sources and license are preserved. The XGS126 driver at
`960f5517adb234626aaad2353fa2f1ee8e3cd864` was compared for its buffer-pool
refill and MSI-X fixes; this integration uses its refill strategy and
armed-vector guard, with strict index validation instead of masking invalid
indices or adopting device cursors after a reattach. Copyright (c) 2026 The
Mamoru Project; Copyright (c) 2026 Michael Piorkowski (XGS126 changes).
Integration additions are BSD-2-Clause, Copyright (c) 2026 XGS116 integration
contributors. See `LICENSE`.

## Concrete changes

* Accept BAR map version 5 only; bound facility windows by mapped BAR sizes and
  reject implausible geometry before any derived MMIO access.
* Keep the 36-bit DMA ceiling. Acknowledge partial allocation failures without
  leaking a successfully loaded DMA map. Reject invalid raw device indices;
  never turn poisoned indices into apparently valid indices by masking.
* Refill the buffer pool toward available capacity on every RX pass, including
  passes without completions. A transient allocation failure can recover.
* Use a one-tick-minimum, 1 ms requested RX poll fallback, with one bounded ring
  pass, and advertise an MSI-X queue vector only when its handler was armed.
* Include 66-byte port prefix, 1500-byte MTU, Ethernet header, one VLAN tag and
  conservative FCS allowance in the 1588-byte PF_INIT frame limit. Reject MTUs
  above 1500 until larger buffers and firmware limits are validated. Advertise
  `IFCAP_VLAN_MTU` without checksum or VLAN tag insertion offloads.
* Validate both tag bytes and the complete minimum frame length; a bad tag
  cannot route traffic to another physical interface. Validate RX offset+length
  without integer overflow.
* Create exactly nine front-panel interfaces or unwind the partial allocation.
  Respect administrative `IFF_UP` in RX/TX and mirror administrative changes to
  NW_AGENT when present. Declare `IFF_NEEDSEPOCH` for FreeBSD's network receive
  epoch wrapper. Interface counters measure host delivery/enqueue, not all
  switch MIB traffic.
* Generate per-appliance, stable, locally administered MAC prefixes from a
  validated SMBIOS UUID; alternatively use an explicit `hw.agnic.mac_base`.
* Implement read-only SWOP PORTS telemetry for the open firmware. Capability
  version and feature marker are validated, request and response magic differ,
  and response length/version/op/status/count must agree. Three failed queries
  stop subsequent requests and leave link state unknown. Status bits provide
  carrier, duplex and 10/100/1000 speed. Speed encoding 3 is left unknown; it
  must not be assumed to be 1 Gbit/s, especially for the SFP SerDes lane.
* Recognize both legacy SWOP capability at NWA+0 and the new nonoverlapping
  NWA+0xf000 slot. NW_AGENT request/response bounds must stay within its
  advertised buffer and below the relocated SWOP area. No SWOP write operation
  is implemented by the driver.
* Detect capability loss/change and invalid indices as `recovery_required`.
  Stop using the datapath rather than guessing new queue ownership. Retain
  DMA allocations after an ambiguous partial queue-registration failure.
* Refuse hot unload once any DMA address has been published. The upstream
  fire-and-forget DISABLE command does not prove that device DMA has stopped.
  Device shutdown requests DISABLE and disables PCI bus mastering without
  freeing device-visible allocations. No FLR or automatic NPU reset is issued.

## Build and validation

Use `build/build-driver.py` from the repository root with the exact OPNsense
source revision `12334a596709d195acb73f0f069da82c570a3d84`. It stages the
module sources in a separate directory; no generated files enter this source
directory. Native FreeBSD `make` using that source tree is also supported:

```sh
make SYSDIR=/path/to/opnsense-src/sys
```

Portable validation exercises the actual predicates used by the kernel driver:

```sh
python3 -m unittest discover -s tests/unit -p 'test_driver*.py' -v
```

It compiles a C test with undefined-behavior sanitizer and covers all nine
port tags, malformed tags and frames, full VLAN frame geometry, RX overflow,
invalid ring indices, SWOP capability compatibility and spoofed request echoes,
UUID validity and per-port MAC uniqueness. It does not execute DMA, interrupt
handlers or the NPU protocol on physical hardware.

## MAC configuration

The driver's default derives a 38-bit local prefix from
`smbios.system.uuid` and uses final octets 01..09 for physical port numbers.
A missing, malformed, null or all-ones UUID refuses port creation. Systems with
cloned/duplicate SMBIOS UUIDs need distinct manually provisioned prefixes.
To use an explicitly allocated prefix, set this persistent OPNsense tunable
before loading the module:

```text
hw.agnic.mac_base="02:12:34:56:78:00"
```

The example is illustrative: allocate a distinct prefix for each appliance.
The last octet must be 00 and the first byte must be local/unicast. A change
of this setting changes interface MACs and may affect existing assignments.
`mvmgmt0` retains its original internal management MAC for compatibility with
stock NPU management; it must not be bridged to front-panel networks.

## Readiness and diagnostics

Read-only `dev.agnic.0` sysctls:

| Field | Meaning |
|---|---|
| `mgmt_ready` | DEV_MGMT_READY and PF management echo succeeded |
| `datapath_ready` | queues enabled and all nine front-panel ifnets created |
| `nports` | actual number of created front-panel interfaces |
| `recovery_required` | state became invalid; a controlled reboot is required |
| `rx_prod`, `rx_cons` | live device producer and host consumer |
| `tx_prod`, `tx_cons` | host producer and device consumer |
| `bp_prod`, `bp_cons` | host free-buffer producer and NPU consumer |
| `rx_frames`, `rx_dropped`, `tx_packets`, `tx_dropped` | host-side datapath counters |
| `ring_errors`, `bp_alloc_failures`, `rx_bad_tag` | invalid indices, allocation pressure, rejected port framing/admin-down traffic |
| `swop_version`, `swop_errors` | capability generation and failed read-only telemetry |

`datapath_ready=1` does not prove packets left a front-panel port.
`tx_cons` advancement proves descriptor consumption only. Correlate NPU
counters, switch registers and captures from an external test peer.
Interface carrier begins UNKNOWN and remains UNKNOWN without validated
telemetry; a loaded module does not prove a 1 Gbit/s link.

## Remaining hardware validation and limitations

The identity mapping switch devices 1..9 to `port1`..`port9` follows Mamoru's
XGS116 board descriptor and must be checked against this appliance's labels.
SWOP transport uses MUSDK CUSTOM destination type 3, guest id 2, command code
0x80; the callback echoes code and correlation id. It is implemented and built,
but link and full-duplex readings still require cable-toggle tests on the target.
The SFP lane's actual media/module behavior remains unvalidated.

The driver cannot enforce switch port isolation by host demultiplexing alone.
The NPU must program and verify CPU-only front-port VLAN maps before network
use. No direct L2 bypass may remain. Hardware acceptance must test this.

The new v1-profile firmware is source-built and is not the previously tested
payload identified by MD5 `35c35a3c19311efd2b529a7693e76cd4`; both v1 and v2
profiles require end-to-end validation. The driver performs no flash writes.
Automatic NPU reboot recovery, live module unload and hot reattach are **not
supported**. Recovery detection cannot identify every restart that reuses the
same capability words; until an explicit firmware generation protocol exists,
a physical NPU restart requires a controlled host reboot. MSI-X ordering, DMA
coherency, 72-hour stability and throughput remain hardware acceptance work.
