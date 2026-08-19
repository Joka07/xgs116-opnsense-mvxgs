# Phase 7 findings

## FreeBSD MSI-X table after Stage 1

The XGS116 MSI-X table is BAR0 + `0x1000`. After FreeBSD allocated five
vectors, the first five 16-byte entries were:

| entry | message address | data | vector control |
|---|---:|---:|---:|
| 0 | `0xfee11000` | `0x32` | `0x0` |
| 1 | `0xfee12000` | `0x32` | `0x0` |
| 2 | `0xfee13000` | `0x32` | `0x0` |
| 3 | `0xfee10000` | `0x36` | `0x0` |
| 4 | `0xfee11000` | `0x33` | `0x0` |

Thus all five requested entries are populated and unmasked. Entries after
those remain masked/unused.

The different message addresses/data versus SFOS are expected to be
OS/platform interrupt-routing details; the endpoint consumes its MSI-X table
by vector index.

## Phase 6 result

- CTRL before write: `0x01`
- HOST_READY write read back: `0x03`
- target did not set `0x04` within 5 seconds
- H2T descriptor remained zero
- IRQ hit counters remained zero
- PCI Command register under FreeBSD was `0x0402`
- fully running SFOS captured `0x0406`

The missing bit is `0x0004`, PCI Bus Master Enable. Static analysis of the
vendor driver also showed `pci_set_master()` before facility initialization.
Phase 7 changes only this precondition before repeating the handshake.
