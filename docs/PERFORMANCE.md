# Messplan für Durchsatz und Dauerlast

Auf dieser Cloud wurde kein Netzwerkverkehr über eine XGS 116 gemessen. Die XGS126-Werte
(~936 Mbit/s RX, ~572 Mbit/s Einzelstream-TX, ~819 Mbit/s TX mit vier Streams) sind fremde
Vergleichswerte und keine Zusage für den XGS-116-Build. Ein 1-Gbit/s-Ethernetlink erreicht mit
MTU 1500 typischerweise etwa 940 Mbit/s TCP-Nutzdatenrate, nicht 1000.

## Vier verschiedene Messstrecken

| Strecke | Datenpfad | Ziel / Aussage |
|---|---|---|
| gleicher VLAN, zwei Geräte am Zyxel | nur externer Switch | Gegenstellen-Baseline; beweist nichts über die XGS |
| Gegenstelle↔OPNsense selbst | ein Frontport + NPU-Trunk + Hoststack | RX/TX-Grundlage des Treibers, keine pf-Forwardingmessung |
| VLAN 10↔20 über OPNsense | Trunk rein, pf/Routing, Trunk raus | bis nahe 1 Gbit/s als Ziel; beide DMA-Richtungen und CPU werden belastet |
| LAN↔WAN mit NAT | Switch/NPU, pf/NAT, NPU/WAN | stabile 600 Mbit/s als Ziel; WAN-Gegenstelle begrenzt ggf. |
| mehrere Frontports gleichzeitig | gemeinsamer GIU-Trunk | Gesamtgrenze und Fairness; neun Ports bedeuten keine garantierten 9 Gbit/s |

Für Routing/NAT stehen **beide iperf-Endpunkte außerhalb** der Firewall, jeweils in den
betreffenden Netzen. Ein auf OPNsense gestarteter iperf-Prozess misst den Hoststack und darf nicht
als Inter-VLAN-/NAT-Ergebnis bezeichnet werden. Die Testwerkzeuge ändern keine Firewallregeln,
DHCP-Server oder produktiven Interfaceadressen.

## Reproduzierbare Messung

Vorbereitung: isoliertes Testnetz, eigene Adressierung und Regeln, auf der Gegenstelle
`iperf3 -s -p 5201`. Python 3 und iperf3 sind für die Runner nötig. Prüfe zunächst ohne `--execute`
die Befehle. Jede Ausführung benötigt ein **neues** Ergebnisverzeichnis.

```sh
python3 tests/network/probe.py --interface port1 \
  --source 192.0.2.1 --peer 192.0.2.2 --output /tmp/xgs-probe-01 --execute

python3 tests/performance/iperf.py --interface port1 \
  --source 192.0.2.1 --peer 192.0.2.2 --seconds 60 --streams 1 \
  --minimum-mbps 900 --output /tmp/xgs-tcp-01 --execute

python3 tests/performance/iperf.py --interface port1 \
  --source 192.0.2.1 --peer 192.0.2.2 --seconds 60 --streams 4 \
  --minimum-mbps 900 --output /tmp/xgs-tcp4-01 --execute

python3 tests/performance/iperf.py --interface port1 \
  --source 192.0.2.1 --peer 192.0.2.2 --protocol udp --udp-mbps 600 \
  --seconds 60 --max-loss-percent 0 --output /tmp/xgs-udp-01 --execute
```

TX und RX laufen nacheinander; `-R` fordert die Gegenrichtung an. Die JSON-Auswertung verlangt
Empfängerwerte und erhält den iperf-Exitstatus. Leere Läufe, fehlende Empfängerstatistik oder
Überschreitung des Verlustlimits schlagen fehl. `--minimum-mbps 0` prüft nur tatsächlichen
Verkehr, keine Leistungsanforderung. 900 Mbit/s oben ist eine beispielhafte Prüfschwelle, kein
bereits erreichtes Ergebnis. 940 Mbit/s bleibt das Einzelportziel.

Für IPv6 beide Adressen durch eigene globale/ULA-Adressen ersetzen. Der Runner prüft, dass die
Quelladresse dem gewünschten Interface gehört und die Route darüber läuft. Für VLANs das
bereits konfigurierte VLAN-Interface angeben. IPv4-MTU-Test verwendet DF mit 1472 Bytes ICMP-Payload;
IPv6 verwendet 1452. Captures müssen bei IPv6 zusätzlich ausschließen, dass der Sender einen
Fragmentheader einfügt. UDP-Payload ist 1472/1452 Bytes; ein pfadabhängig kleineres MTU benötigt
zunächst eine Diagnose, keine stille Reduktion des Zieltests.

## Parallelverkehr und Messgrenzen

Für mehrere unabhängige Streams Server auf getrennten Portnummern bzw. Gegenstellen starten.
Auf jedem Testclient einen eigenen Runner mit eigenem Quellinterface, `--port` und
Ergebnisverzeichnis ausführen. Ergebnisse zeitlich überlappend erfassen. Zusätzliche Parallelität
kann TX-Latenz überdecken: Einzelstream, vier Streams und UDP-Verlusttests getrennt ausweisen.

Vor und nach jedem Lauf `sh tests/network/collect.sh NEUES_VERZEICHNIS` auf dem Host ausführen;
auf der NPU den Forwarderlog und PP2/GIU-Zähler sichern. Auf der echten Gegenstelle mit tcpdump
prüfen, ob gesendete Frames dort eintreffen. `tx_packets` ist enqueue; `tx_cons` ist Verbrauch
im NPU; beide allein sind kein Frontport-Egressbeweis. Ringindices sind modular und dürfen für
Durchsatzdifferenzen nicht wie monoton wachsende Paketzähler behandelt werden.

## 72 Stunden und Neustarts

```sh
python3 tests/stability/soak.py --interface port1 \
  --source 192.0.2.1 --peer 192.0.2.2 --hours 72 \
  --minimum-mbps 600 --output /tmp/xgs-soak-01 --execute
```

Dieser Runner führt wiederholt 30 Sekunden TX und 30 Sekunden RX aus und speichert jeden
Einzellauf. Richtungswechsel erzeugen kurze Lücken; dies ist kein ununterbrochener Full-Duplex-Test.
Für echte gleichzeitige Dauerlast zwei unabhängige Endpunktpaare bzw. getrennte Serverports nutzen.
Er bricht beim ersten fehlgeschlagenen Lauf ab und schreibt `failed`; Unterbrechung schreibt
`interrupted`. Es gibt keine automatische Recovery, die einen Fehler unsichtbar machen würde.
Logs auf USB/externes Testmedium schreiben, falls der erwartete Platz in `/tmp` nicht reicht.

Für warme/kalte Starts, Stromausfall, Host-/NPU-Neustart und Updates jeweils vor/nach dem
**vom Betreiber kontrollierten** Ereignis:

```sh
sh tests/stability/record-cycle.sh cold before /tmp/cold-01-before
# Ereignis über vorbereitete Konsole durchführen; kein automatisch ausgelöster Stromausfall.
sh tests/stability/record-cycle.sh cold after /tmp/cold-01-after
```

Mindestens zehn Warmstarts und zehn vollständige Kaltstarts als Anfangsserie dokumentieren,
danach Stromausfall- und Reihenfolgetests. Je Zyklus: Bootzeit bis Handshake/9 Interfaces, MACs,
physische Portzuordnung, externe Erreichbarkeit, VLAN/NAT-Test und Fehlerlogs vergleichen.
Ein Snapshot ist `OBSERVATION_ONLY`, kein bestandener Recoverytest. NPU-Neustart bei laufendem
Host ist zunächst ein erwarteter Ausfalltest; autonome Wiederherstellung erst nach Beweis freigeben.
