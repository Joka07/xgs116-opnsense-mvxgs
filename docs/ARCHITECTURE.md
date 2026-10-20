# XGS-116-Datenpfad und Grenzen

Der x86-Host übernimmt OPNsense, pf, NAT, IPv4-/IPv6-Routing und VLAN-Konfiguration.
Der CN9130 transportiert Frames zwischen Switch und PCIe. Diese Integration enthält keinen
NPU-Firewall-Offload. Der bestehende `current/mvxgs`-Treiber erforscht nur den Kontrollpfad und
wird nicht zusammen mit `if_agnic` an dasselbe PCI-Gerät gebunden.

```text
RJ45 1..8 / SFP
       |
88E6193X, isolierte Frontports → CPU-Port 0
       | DSA-Tags
CN9130 / Linux / PP2 / dp_fwd + MUSDK NMP/GIU
       | PCIe, gemeinsamer DMA-Trunk (11ab:7080)
FreeBSD if_agnic → port1..port9 → OPNsense / pf
```

## Komponenten und Verträge

| Komponente | Aufgabe / Grenze |
|---|---|
| `if_agnic.c`, `agnic_barmap.h`, `agnic_ctrl.h` | PF-Erkennung, BAR0/2/4, Facilities, CTRL-Cookies, Interrupts, Lebensdauer |
| `agnic_mgmt.c`, `agnic_giu.h` | AGNIC-Kommando-/Notifikationsringe, Echo, PF_INIT/TC_ADD/Q_ADD/INIT_DONE/ENABLE |
| `agnic_txrx.c` | Host-DMA, 36-Bit-Adresslimit, RX/TX-Ringe und Buffer-Pool; MSI-X und Poll-Fallback |
| `agnic_pport.c` | neun ifnets, Portpräfix, MAC-/Adminzustand, Hoststatistik |
| `agnic_nwa.c` | Sophos NW_AGENT-Mailbox; offene Firmware bietet diese API nicht automatisch |
| `agnic_pcinet.c` | internes `mvmgmt0` zur NPU-Verwaltung; eigener Facility-Vertrag |
| `forwarder.c`, MUSDK `pf*.c` | PP2↔GIU-Datenpfad und Management-Queue-Registrierung |
| `dp_swop.c/h` | optionale Switchdiagnose über den Custom-Kanal; Capability und Nachrichtenform getrennt versionieren |
| `sw-init.sh`, `swmdio.sh` | Switch-/PHY-/SerDes-Initialisierung; Isolation vor Freigabe der Frontports |
| ursprünglicher NPU-Kernel + Module | PCIe-Endpoint, CMA/UIO, DMA, Facility-Basis; vom eigenen Gerät, nicht neu implementiert |

BAR-Größen 1 MiB/16 MiB/16 MiB, BARMAP v5 und Cookie `0xd0fac10d` sind Erwartungen aus der
Referenzhardware. Unpassende Werte müssen den Attach stoppen. BAR4 dient H2T-Doorbells;
Indices zeigen Producer-/Consumer-Fortschritt, Interrupts sind kein Ersatz für das Prüfen der Ringe.

## 66-Byte-Präfix und VLAN

Vor dem tatsächlichen Ethernetframe liegen zwei Tagbytes und 64 Metadatenbytes. Tagbyte 0
`0x81..0x89` bezeichnet Frontport 1..9; Byte 1 ist null. Dieses Präfix ist weder ein VLAN-Tag
noch eine Ethernetadresse. RX entfernt es vor Übergabe an den Hoststack, TX setzt es vor dem DMA.

Ein MTU-1500-Frame benötigt ohne FCS `1500+14=1514` Bytes, mit 802.1Q `1518` Bytes; auf dem
DMA-Trunk kommen 66 hinzu: **1580 bzw. 1584 Bytes**. Falls ein bestimmter Hardwarepfad FCS
mitliefert, sind weitere 4 Bytes getrennt zu berücksichtigen. Die genaue FCS-Behandlung darf
nicht aus einer zufällig ausreichend großen 2048-Byte-Allokation abgeleitet werden. Der
PF_INIT-Framewert, die NPU-Buffergröße, RX-Längenprüfung und TX-Kopiergrenze müssen übereinstimmen.
VLAN-Tags müssen den Weg unverändert durchlaufen; nicht implementierte Offloads dürfen nicht
beworben werden. Jumbo-MTU ist derzeit kein Abnahmeziel.

## Isolation und Switchzustand

Frontports dürfen nur Richtung CPU weiterleiten; CPU darf die vorgesehenen Frontports erreichen.
Die Maps aller Switchports werden geprüft, bevor die Front-PHYs freigegeben werden. Ein nicht
bestätigter Registerwert ist ein Fehler. Fremde `NetAgent`-/`UMSD_NPU`-/`usfp`-Prozesse können Maps
nachträglich ändern; eine einmal erfolgreiche Initialisierung beweist keine dauerhafte Isolation.
SFP-Einstellungen hängen vom Modul und Gegenport ab. Die Zuordnung PortF1→`port9` ist auf dem
Gerät durch Linkwechsel und Paketmitschnitt zu bestätigen.

## Neustarts und Telemetrie

Der Host veröffentlicht DMA-Ringadressen; NPU-PF-Objekte halten diese über ihre Lebensdauer.
Ein neu gestarteter NPU-Prozess besitzt nicht zwangsläufig wieder gültige Ringverbindungen.
MUSDK-Reinit-Korrekturen beheben konkrete Lecks, beweisen aber keine beliebige Restartreihenfolge.
Daher keine automatische schnelle Respawn-/KLD-Reload-Schleife. Nach erkanntem Verlust wird
Fehlerstatus gemeldet; kontrollierte Recovery erfolgt anhand der dokumentierten Hardwaretests.

Ein administrativ aktives ifnet oder ein erfolgreiches `CC_PF_ENABLE` beweist keine physische
Carrier-Verbindung. Stock-NW_AGENT kann individuelle Link-/Speed-/Duplexdaten liefern; im offenen
Pfad bleiben diese ohne validierte Telemetrie **unbekannt**. Ein späterer SWOP-Linkmonitor darf nur
bei exakt passender Capability, bestätigtem Slot und laufendem Responder senden. Ein veraltetes
Magic im BAR überlebt einen Prozessabsturz und ist allein kein Liveness-Beweis.
