# Kompatibilität und offene Abnahme

**Experimentell, nicht für die unbeaufsichtigte Hauptfirewall freigegeben.** Die Cloudprüfungen
belegen Quellcode-/Build-Eigenschaften. Sie belegen keine funktionierenden Originalports,
Stromausfall-Recovery oder Durchsatzwerte auf der konkreten XGS 116.

## Ziel und notwendige Eingaben

| Bereich | Festlegung | Noch am Gerät zu bestätigen |
|---|---|---|
| Host | OPNsense 26.7, FreeBSD `15.1-RELEASE-p1`, amd64 | `uname -K`, `freebsd-version -ku`, Kernelbuild; passende Quelldateien allein beweisen keine geladene ABI |
| Kernelquelle | OPNsense `12334a596709d195acb73f0f069da82c570a3d84` | Übereinstimmung mit dem tatsächlich gebooteten Image |
| PCI | PF `11ab:7080`, BAR0/2/4 1/16/16 MiB, BARMAP v5 | Attach/Reset-/Bootreihenfolge auf Zielgerät |
| Ports | RJ45 1..8→`port1..port8`, SFP→`port9` | Kabel einzeln umstecken, Tags, MACs und Link korrelieren |
| Switch | 88E6193X, CPU-Port 0 | Device-Nummer, SFP-Modus, Isolation und fremde Schreiber |
| DMA | 36-Bit-Hostadressen, gemeinsamer Trunk | Dauerlast, Cache-/Ordering-/Interruptverhalten |
| NPU | vorhandener Linux-Kernel und eigene Vendor-Module | Version/vermagic, UIO-Geräte, Bootkette, Module abhängigkeiten |
| Persistenz | eigene gesicherte Rootfs-Basis + validiertes Offline-Overlay | Slots, Platz, Initreihenfolge, serieller Rückweg; keine automatische A/B-Recovery belegt |

## SWOP und NW_AGENT

Drei Dinge sind auseinanderzuhalten:

1. Das 66-Byte-Portpräfix gehört zum Datenpfad.
2. `DP_SWOP_VERSION=1` beschreibt im aktuellen Mamoru-Header das SWOP-Nachrichtenformat.
3. `DP_SWOP_CAP_VERSION=2` beschreibt den **Capability-Carrier** mit drei Wörtern. Der historisch
   getestete Payload verwendet Carrier v1 mit zwei Wörtern. Die zusätzliche Version verhindert,
   dass nach einem Downgrade ein altes Featurewort fälschlich weitere Opcodes freigibt.

Ein Source-Build mit Carrier v2 ist nicht automatisch mit dem historisch getesteten Binary
identisch oder hardwarevalidiert. Der historische MD5 `35c35a3c19311efd2b529a7693e76cd4` bleibt eine
Vergleichskennung. Eigene Artefakte erhalten SHA-256 und Buildmetadaten; keine Behauptung, denselben
Payload reproduziert zu haben, solange Toolchain/Quellstand/Buildinputs nicht nachgewiesen sind.

Das Original veröffentlicht bei BAR0 `0x4000` und überschreibt dort NW_AGENT. Die XGS126-Verlagerung
um `0xf000` innerhalb des 64-KiB-Fensters ist ein möglicher disjunkter Bereich, kein Beweis freien
Speichers auf dieser XGS 116. Vor Capability-Publikation: Fenster passiv sichern, mit laufender
Originalfirmware und bei Mailboxverkehr vergleichen, Größe und Reservierung dokumentieren. Keine
unbeantworteten Probe-Nachrichten zur vermeintlichen Capability-Erkennung senden.

## Grenzen mit offenen NPU-Diensten

Der offene Forwarder ersetzt nicht die komplette Vendor-Basis. Endpoint-/CMA-/UIO-/DMA-Module
müssen weiterhin zum eigenen NPU-Kernel passen. Ohne NW_AGENT-Dienst fehlen dessen Portsteuerung
und individuelle physische Linkdaten; der Host muss dies sichtbar als unbekannt behandeln. Ein
statisches `1000baseT`-/Carrier-UP-Fallback ist kein Nachweis von Speed/Duplex. Der SFP braucht
zusätzlich ein nachgewiesen kompatibles Modul und SerDes-Profil.

Wiederholtes `CC_PF_INIT` und Host-Reattach sind separate Tests gegenüber einem Kaltstart.
Korrekturen an MUSDK-Ressourcen und Hostteardown begründen keine automatische NPU-Restartfreigabe.
Ein fehlgeschlagener Attach oder NPU-Neustart kann einen kontrollierten vollständigen Neustart
verlangen; keine unkontrollierte Wiederholung aktiver Initialisierung.

## Erforderliche Hardwareabnahme

| Prüfung | Mindestnachweis | Status dieser Cloudarbeit |
|---|---|---|
| 9 Portidentitäten | ein Kabel pro Anschluss, RX-Tag/ifnet und stabile individuelle MAC | ausstehend |
| RJ45-Link | jeder Port 1000 Mbit/s, Full-Duplex, Gegenstelle bestätigt | ausstehend |
| SFP | Modultyp, Speed, bidirektionales Traffic-/Linkereignis | ausstehend |
| RX/TX | ARP/ND, ICMP, TCP, UDP in beide Richtungen, externe Captures | ausstehend |
| VLAN/MTU | VLAN 10/20/30/99, MTU 1500, Tag auf beiden Seiten, keine Trunkverluste | ausstehend |
| Isolation | unerlaubtes Front→Front-L2 bleibt blockiert, auch während Boot und Reinit | ausstehend |
| DHCP/IPv4/IPv6 | Client-Lease, ND/RA gemäß eigener Konfiguration, Routing in beide Richtungen | ausstehend |
| NAT/WAN | reale 600-Mbit/s-Strecke mit NAT und passenden CPU-/Ringzählern | ausstehend |
| Reboots | mehrere warme/kalte Host-/Gesamtstarts, beide NPU/Host-Reihenfolgen | ausstehend |
| Stromausfall | vollständiger autonomer Start ohne Netzwerk-/SSH-Nacharbeit | ausstehend |
| Dauerlast | mindestens 72 h, mehrere Ports, Traffic/Ring-/Fehlerzeitreihen | ausstehend |
| Updates | ABI-Fehler wird kontrolliert erkannt; Neubau, erneute Abnahme | ausstehend |
| Recovery | serielle Rückkehr zur gesicherten Originalumgebung praktisch ausgeführt | ausstehend |

Die ausführbaren Messhilfen und die manuelle Testmatrix stehen in [PERFORMANCE.md](PERFORMANCE.md)
und `tests/network/README.md`. Die Abschlussdokumentation der Hauptaufgabe nennt die tatsächlich
in der Cloud ausgeführten Tests/Builds; diese Tabelle bleibt bewusst eine Hardwareabnahme.
