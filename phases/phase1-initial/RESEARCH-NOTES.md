# Research notes

## Verified from the tested XGS 116

The provided `pciconf -lBbcev` output shows Marvell `11ab:7080` as an Ethernet-class PCIe endpoint with:

- BAR0: 1 MiB
- BAR2: 16 MiB
- BAR4: 16 MiB
- PCIe x4, 8.0 GT/s
- MSI-X: 16 messages
- SR-IOV: 6 VFs, VF device `0x7081`

FreeBSD 15.1 on OPNsense 26.7 leaves it unclaimed (`none`/`unknown`).

## Verified from Sophos material

A Sophos XGS hardware re-image log shows the installer:

1. detects the NPU on PCI
2. loads `mv_armada_drv`
3. loads `mv_pcinet_drv`
4. waits for `mvmgmt0`
5. configures a link-local IPv6 address to communicate with the NPU
6. updates/installs a root filesystem on the NPU
7. adds the Marvell pcinet interface to network configuration

This is the strongest evidence that the endpoint is a managed packet-processing subsystem rather than a conventional host NIC.

## Consequence for a FreeBSD port

A real port should be split conceptually into layers:

- `mvxgs_pci`: PCI attach, BARs, MSI-X, DMA tags
- `mvxgs_mbox`: control/mailbox channel to NPU
- `mvxgs_fw`: NPU firmware/rootfs negotiation and lifecycle
- `mvxgs_net`: host packet queues and FreeBSD ifnet/iflib integration
- `mvxgs_port`: physical port/link/PHY state exposed by NPU
- optional `mvxgs_iov`: SR-IOV PF/VF control once PF protocol is understood

The supplied Phase-1 `mvxgs.c` intentionally implements only the first, non-destructive subset of `mvxgs_pci`.
