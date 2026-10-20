# Hardwaretests ohne Änderung der Firewallkonfiguration

Diese Tests wurden in der Cloud nur als Dry-Run und mit synthetischen Ergebnisdaten geprüft.
Die Hardwareläufe stehen aus. Sie benötigen eine serielle Recovery-Konsole, ein isoliertes
Testnetz, tatsächlich angeschlossene Originalports und vom Betreiber konfigurierte Adressen.
Es werden keine Adressen, VLANs, pf-Regeln oder DHCP-Dienste angelegt.

`collect.sh NEW_DIRECTORY` erstellt auf FreeBSD einen lesenden Snapshot. Jede fehlgeschlagene
Unterabfrage steht in `status.tsv`; das Gesamtskript endet dann ungleich null. Daten enthalten
Interface-/Routen-/MAC-Angaben und sollten vor Veröffentlichung geprüft werden.

`probe.py` prüft ICMP und MTU 1500 für ein konkretes bereits konfiguriertes Interface.
Quelladresse und Route werden vor Traffic geprüft. Ohne `--execute` wird nur der Plan ausgegeben.
Die Performance-Runner stehen in [../../docs/PERFORMANCE.md](../../docs/PERFORMANCE.md).

## Manuelle Abnahmematrix

| Test | Ablauf | Bestehenskriterium |
|---|---|---|
| Portzuordnung 1..9 | jeweils nur ein Kabel einstecken; Hostcapture auf allen Ports, NPU DSA-Quellport und Gegenstelle beobachten | nur erwartetes `portN` empfängt; MAC bleibt nach Neustart gleich |
| Link/Speed/Duplex | Kabel entfernen/stecken, Gegenstelle auf Autoneg; SFP-Modul dokumentieren | echte Gegenstellenmessung 1000/Full; unbekannte Hosttelemetrie als unbekannt protokollieren |
| ARP/ND/ICMP | IPv4-ARP und IPv6-ND vor erstem Ping erfassen, beide Richtungen testen | Anfragen und Antworten auf beiden Enden; keine systematischen Verluste |
| TCP/UDP | iperf vorwärts und rückwärts, Einzel-/Mehrfachstream | Empfängerwerte und Drops innerhalb festgelegter Grenzen |
| Admin down | ausgewähltes unproduktives Testinterface in OPNsense deaktivieren/aktivieren | kein RX/TX zum Hoststack im deaktivierten Zustand; andere Ports arbeiten weiter |
| VLANs 10/20/30/99 | externe Trunkgegenstelle, jeweils eigene Testadresse; Ethernetcaptures auf beiden Seiten | richtige Tags, kein untagged leak, MTU 1500 ohne Abschneiden |
| Frontportisolation | zwei PCs in gleicher Test-L2-Adressierung an verschiedenen Frontports; Hostforwarding für diese Probe nicht erlaubt | unicast/broadcast geht nicht direkt durch den Switch; beobachten auch während Boot |
| DHCP | eigener isolierter DHCP-Server/Client, Lease neu erwerben und erneuern | vollständige DORA bzw. DHCPv6-Austausch, korrekter Port/VLAN |
| IPv6 | ND, RA gemäß eigener Konfiguration, ICMPv6, TCP/UDP, MTU | bidirektional ohne unbeabsichtigte Filter-/Offloadfehler |
| NAT | externe Clients beidseits der Firewall, pf-Regeln durch Betreiber | Quellübersetzung im WAN-Capture korrekt; Rückverkehr dem richtigen LAN zugeordnet |
| Inter-VLAN | zwei externe Testclients in unterschiedlichen VLANs | erlaubter Verkehr geht über pf, verbotener wird verworfen; keine Switch-Abkürzung |
| Isolation nach Fehler | NPU-/Hostfehler und Neustart nur auf isoliertem Aufbau | zu keinem Zeitpunkt offene Front→Front-Bridge |

Für Isolation ein fehlender Ping allein nicht als Beweis werten: mit Capture und gezielt erzeugten
Broadcast-/Unicast-Frames nachweisen, dass die sendende Seite tatsächlich gesendet hat und die
empfangende Seite unabhängig funktionsfähig ist. Das Ziel ist eine negative Aussage mit positiven
Kontrollen, nicht ein möglicherweise defektes Testkabel.

## Diagnose des bekannten TX-Ausfalls

1. Hostsnapshot und Gegenstellen-Capture vor dem Traffic starten.
2. Eine kleine bekannte Anzahl ARP-/ICMP-Pakete senden; `tx_prod/tx_cons`, `rx_prod/rx_cons`,
   `bp_prod/bp_cons`, `rx_dropped`, `tx_dropped` dokumentieren.
3. Steigt `tx_prod` ohne `tx_cons`, GIU-/NPU-Verbrauch untersuchen. Bei beiden fortschreitend
   NPU-PP2-TX und Drops lesen; erst danach Switch/DSA/Gegenstelle eingrenzen.
4. Auf der NPU mit **der tatsächlich eingesetzten** `swmdio.sh` lesen:
   `rd 0 6`, `rd 0 4`, `rd 1 6`. Referenzwerte aus Issue #1: `0x03fe`, `0x017f`, `0x0001`.
   Abweichungen dokumentieren, nicht blind überschreiben.
5. Laufende `usfp`, `UMSD_NPU`, `NetAgent` und deren Startwrapper identifizieren. Änderungen an
   Switchmaps über die Zeit sprechen für einen konkurrierenden Schreiber. Kein automatisches
   `killall` gegen unbekannte Prozesse ausführen.
6. DSA-Device aus tatsächlicher Switchkonfiguration bzw. beobachteten DSA-Frames bestimmen und
   gegen den Buildparameter prüfen. RX kann funktionieren, während ein falsches DSA-Device TX
   verwirft. Danach einen neuen eindeutig versionierten Build testen.

## Portabler Test der Runner

```sh
python3 -m unittest discover -s tests/network -p 'test_*.py' -v
python3 -m unittest discover -s tests/performance -p 'test_*.py' -v
```

Diese Tests prüfen Argument-/Pfadvalidierung, Ergebnisparser und Fehlerstatus. Sie simulieren
keine AGNIC-Hardware und ersetzen die obige Matrix nicht.
