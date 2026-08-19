# Why Phase 6 can proceed

The real SFOS `mv_armada_drv.ko` was statically analysed.

Before setting CTRL `HOST_READY` it:
1. waits for target-ready bit `0x01`;
2. creates host-side facility metadata;
3. counts 5 total target-to-host MSI-X channels;
4. allocates exactly 5 PCI IRQ vectors;
5. obtains each Linux IRQ via `pci_irq_vector()` and stores those values only
   in host-side metadata;
6. ORs `0x02` into CTRL flags.

The Linux IRQ numbers are not written into the shared NPU MMIO handshake.
After HOST_READY, the vendor worker waits for target bit `0x04`. It then
consumes five 16-byte H2T descriptors beginning at CTRL `+0x10`; each contains
a target offset and 32-bit doorbell data.

The user's Stage-1 test confirmed FreeBSD can allocate the same five MSI-X
entries with inert handlers while CTRL remains `0x01` and MVMGMT remains
`0xaa55aa55`.
