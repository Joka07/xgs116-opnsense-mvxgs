# Sophos XGS 116 / Marvell 11ab:7080 — OPNsense FreeBSD-Treiberforschung

Experimentelle Clean-Room-Kompatibilitätsarbeit für den Marvell-NPU/Endpoint in einer Sophos XGS 116. Ziel ist, die onboard Ethernet-Ports unter OPNsense / FreeBSD nutzbar zu machen.

> **Stand:** Forschungsprototyp. Noch kein funktionierendes Ethernet-Interface. **Phase 8 ist vorbereitet, aber noch nicht auf der Hardware getestet.**

## Zielsystem

- Appliance: Sophos XGS 116
- PCI PF: `11ab:7080` (Marvell), Klasse Ethernet
- VF Device ID: `11ab:7081`
- OPNsense: `26.7`
- FreeBSD Kernel/Userland: `15.1-RELEASE-p1`
- Kernel-Build: `stable/26.7-n283674-12334a596709`
- Architektur: `amd64`

### PF-Ressourcen

- BAR0: `0xfe000000`, 1 MiB
- BAR2: `0xfd000000`, 16 MiB
- BAR4: `0xfc000000`, 16 MiB
- MSI: bis 32
- MSI-X: 16 Einträge
- SR-IOV: 6 VFs unterstützt

## Was bereits bewiesen ist

1. Der NPU bootet selbständig und stellt vor dem Host-Treiber eine BAR-Map bereit.
2. Unser eigener FreeBSD-Kernel-Treiber kann an `11ab:7080` attachen, alle drei BARs mappen und die Facilities korrekt lesen.
3. BARMAP: Version `5`, Target-Cookie `0xd0fac10d`.
4. CTRL-Cookie: `0xafacafac`.
5. Initiale CTRL-Flags: `0x01` (TARGET_READY).
6. Initiales MVMGMT-Muster: `0xaa55aa55`.
7. FreeBSD kann exakt fünf MSI-X-Vektoren mit Handlern reservieren, ohne den NPU-Protokollzustand zu verändern.
8. PCI Bus Mastering lässt sich sauber aktivieren (`0x0002 -> 0x0006`; mit MSI-X `0x0406`).
9. HOST_READY setzt CTRL von `0x01` auf `0x03`; der Target setzt dadurch alleine noch nicht `0x04`.
10. Im Vendor-Treiber wurde ein periodischer Heartbeat gefunden, der `mv_facility_host_is_alive()` aufruft und CTRL-Bit `0x08` (HOST_ALIVE) setzt. Das ist der nächste Phase-8-Test.

## Facility-Map

| Facility | Logischer BAR | Offset | Grösse |
|---|---:|---:|---:|
| `giu` | 0 | `0x0000` | `0x4000` |
| `ctrl` | 1 | `0x0000` | `0x1000` |
| `mvmgmt` | 1 | `0x1000` | `0x1000` |
| `nwa` | 0 | `0x4000` | `0x10000` |
| `rpc` | 1 | `0x2000` | `0x100000` |

Logisches BAR-Mapping:

- logical BAR 0 -> PF BAR0
- logical BAR 1 -> spezielles PF-BAR2-Fenster ab physisch `0xfdefc000`
- logical BAR 2 -> PF BAR4

BARMAP liegt bei `0xfdffe000`; die Folgeseite bei `0xfdfff000` enthält `BOOTCMD!`.

## Doorbell-/Interrupt-Topologie

Aktuell korrigierte Richtung:

- Target -> Host / MSI-X: `mvmgmt=1`, `giu=4` -> **5 gesamt**
- Host -> Target: `rpc=1`, `giu=4` -> **5 gesamt**

## Repo-Aufbau

- `current/` — aktueller Stand, Phase 8
- `phases/` — historische Treiberstände
- `captures/` — SFOS-/OPNsense-MMIO-Dumps und Konsolenlogs
- `docs/STATUS.md` — alle Erkenntnisse
- `docs/TOMORROW.md` — exakter Ablauf für morgen
- `docs/PHASES.md` — Phasenübersicht
- `docs/SAFETY.md` — Sicherheitsregeln
- `tools/` — Collector-Skripte

## Aktueller Stand

Der neueste Source liegt in `current/` bzw. `phases/phase8-hostalive/`.

Phase 8 testet nach HOST_READY **einen einzelnen HOST_ALIVE-Puls**. Noch nicht enthalten sind permanenter Heartbeat, MVMGMT-ACK, DMA-Datapath, SR-IOV-Datapath, GIU/NWA-Init oder ein echtes Ethernet-`ifnet`.

**Morgen zuerst [`docs/TOMORROW.md`](docs/TOMORROW.md) lesen.**

## Clean-Room / Vendor-Dateien

Im Repo liegen unser eigener FreeBSD-Source, abgeleitete Protokoll-Erkenntnisse, Logs und Read-only-Captures. Proprietäre Sophos/Marvell-Binärmodule und vollständige daraus erzeugte Disassemblies werden bewusst nicht mit veröffentlicht.
