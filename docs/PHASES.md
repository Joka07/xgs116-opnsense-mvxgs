# Phase history

| Phase | Purpose | Result |
|---|---|---|
| 1 | Initial FreeBSD diagnostic driver skeleton | source foundation |
| 2 | Expand BAR/facility discovery | NPU PCI/BAR topology established |
| 3 | Passive MVMGMT visibility | target magic confirmed |
| 4 | Passive full MMIO comparison | SFOS vs OPNsense state differences captured |
| 5 | Stage-1-only MSI-X setup | 5 vectors successfully allocated, no NPU state change |
| 6 | First HOST_READY write | CTRL `0x01 -> 0x03`, target did not set `0x04` |
| 7 | Add PCI bus mastering | command matches SFOS (`0x0406` with MSI-X), HOST_READY still stalls at `0x03` |
| 8 | One-shot HOST_ALIVE after HOST_READY | **prepared, not tested yet** |
