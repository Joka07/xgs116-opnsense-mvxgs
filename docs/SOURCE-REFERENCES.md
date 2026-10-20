# Quellen, Revisionen und Befunde

Lizenzergänzung dieser Integration: Das korrigierte tag_dsa.h enthält
VLAN-/CFI-Konvertierung nach Linux v6.12 net/dsa/tag_dsa.c
(Marvell-Copyright 2008–2009, GPL-2.0-or-later); seine Mamoru-Herkunft
bleibt vermerkt. Der kombinierte Forwarder wird unter der GPLv2-Option
verwendet. MUSDK trägt zusätzlich ein BSD-3-Clause-Root-LICENSE und
Dateien mit eigenen Lizenzoptionen; diese Originaltexte liegen im
vollständigen Dependencyarchiv. BSD-3-Clause-MUSDK.txt ist auch unter
LICENSES enthalten. Keine pauschale Neulizenzierung der historischen
mvxgs-Forschung oder proprietärer Originale.

Stand der Recherche: 20. Oktober 2026. Diese Integration ist experimentell. Aussagen aus
Upstream-Berichten sind fremde Messungen und ersetzen keine Abnahme dieser Änderungen auf der XGS 116.

## Festgehaltene Eingaben

| Quelle | Revision | Verwendung / Lizenz |
|---|---|---|
| [Mamoru XGS NPU](https://github.com/samuelleb11/mamoru-xgs-npu) | `9e53bbcb10f5ba9cd5f6a43dc5631fc8931cff05` (21.09.2026) | primäre XGS-116-Referenz; FreeBSD-Treiber BSD-2-Clause; Firmwarehilfen MIT; Marvell `forwarder.c` GPL-2.0 |
| [XGS126 NPU FreeBSD](https://github.com/piorkowskim79/xgs126-npu-freebsd) | `960f5517adb234626aaad2353fa2f1ee8e3cd864` (18.09.2026) | selektive Treiber-/MUSDK-Korrekturen; Treiber BSD-2-Clause, eigene Skripte/Dokumentation MIT; jeweilige Originalhinweise gelten |
| [Marvell MUSDK](https://github.com/MarvellEmbeddedProcessors/musdk-marvell) | `278748af6e197672551ba220c8720d9ae0a8461e` | SDK-10.3.5.0-PR2-Basis für den Forwarder; siehe enthaltene Dateilizenzen |
| [OPNsense src](https://github.com/opnsense/src) | `12334a596709d195acb73f0f069da82c570a3d84` | vom vorhandenen Zielsystem dokumentierte Kernelquelle; muss zur tatsächlich gestarteten Kernelversion passen |
| bestehendes XGS-116-Forschungsrepository | `bd7dbb3b724db62741dca49c2c509725f798413c` | Phase-8-`mvxgs` bleibt historische, separate Kontrollpfadforschung |
| [OPNsense docs](https://github.com/opnsense/docs) | `ea0d9dd5b2c448e8676f3c55bf7725dab2acab9b` (master beim Abruf) | offizielle Quelltexte `source/development/backend/autorun.rst`, `source/manual/settingsmenu.rst`, `source/manual/software_included.rst` |

Die beiden Projekt-Checkouts wurden einschließlich Dokumentation, Quellkomponenten und
Build-/Deploy-Skripten verglichen. Die Analyse ist keine formale vollständige Sicherheitsprüfung.
Mamoru enthält ebenfalls einen Linux-Treiber; er dient als Protokollvergleich, wird hier aber
nicht als OPNsense-Komponente installiert. Vendor-Payloads, NPU-Rootfs, Kernel/DTB und
mitgelieferte SSH-Schlüssel werden nicht in diese Integration übernommen.

## GitHub-Issues

Die öffentlichen offenen und geschlossenen Issue-Listen wurden am 20.10.2026 über GitHub-HTML
abgerufen: Mamoru zeigte ein offenes Issue (#1), keine geschlossenen; XGS126 zeigte keine offenen
oder geschlossenen Issues. Der GitHub-API-Zugang war im Cloud-Netz gesperrt. Issue #1 mit seinen
drei Kommentaren war vollständig im HTML enthalten; es wurde nicht aus dem Titel allein bewertet.

[Issue #1](https://github.com/samuelleb11/mamoru-xgs-npu/issues/1):

- **07.09.** Unter der originalen Sophos-Datenebene funktionieren PCIe, 36-Bit-DMA,
  Managementhandshake und `port1..port9`; Pakete erreichen NPU `eth0`, aber keine Host-RX-Completion.
- **[16.09.](https://github.com/samuelleb11/mamoru-xgs-npu/issues/1#issuecomment-5701867567)**
  Der Maintainer berichtet bidirektionales ICMP auf einer XGS 116 unter OPNsense 26.7. Er verlangt
  den vorgebauten Payload mit MD5 `35c35a3c19311efd2b529a7693e76cd4`; der neuere Source-Build ist
  ausdrücklich nicht als kompatibel nachgewiesen. MD5 identifiziert diese historische Probe,
  ist keine ausreichende heutige Integritätsprüfung.
- **[19.09.](https://github.com/samuelleb11/mamoru-xgs-npu/issues/1#issuecomment-5745317700)**
  Auf der zweiten XGS 116 funktioniert RX mit diesem Payload. FreeBSD erzeugt ARP-Antworten, der
  Laptop empfängt sie nicht. `rx_prod=rx_cons=71`, keine RX-Drops; `tx_packets=7` beweist nur das
  Einreihen. `NetAgent` läuft noch, `usfp` und `UMSD_NPU` sind gestoppt. Beim ersten Switchlauf
  liest Port 4 Register 6 `0x000f` statt des geschriebenen `0x0001`; der Interlock hält PHYs dunkel.
- **[21.09.](https://github.com/samuelleb11/mamoru-xgs-npu/issues/1#issuecomment-5766639394)**
  Der Maintainer nennt `p0:r6=0x03fe`, `p0:r4=0x017f`, `p1:r6=0x0001` als Messwerte seines
  funktionierenden Geräts. Konkurrierende Vendor-Prozesse können Maps überschreiben.
  `tx_cons`, das `tx_prod` folgt, zeigt NPU-Verbrauch; es beweist weiterhin keine Zustellung am
  Frontport. `dp_fwd` beantwortet NW_AGENT nicht; `mac_set` ist auf seinem offenen Testpfad
  nicht nötig. Bei laufendem `NetAgent` können dessen Richtlinien dennoch relevant sein.

## Übertragbare XGS126-Erkenntnisse

- Remote-Queue-Arrays bei wiederholtem `CC_PF_INIT` leeren und alte PF-Datenpfadobjekte kontrolliert
  abbauen: allgemeine Lebensdauerfehler in `pf_topology.c`/`pf.c`, keine Portnummernfrage.
- SWOP-Capability bei NW_AGENT-Offset 0 kollidiert mit dessen `CAFEBABE`-Mailbox. XGS126 verschiebt
  sie innerhalb des Fensters nach `0xf000`; eine Vermessung auf der konkreten XGS 116 bleibt nötig.
- DSA `DP_DSA_DEV` muss zur **konfigurierten Switch-Gerätenummer** passen. Der Bericht nennt 0
  nach Vendor-Initialisierung bzw. 2 auf dem offenen XGS126-Pfad. Weder Modellname noch SMI-Adresse
  allein beweisen den richtigen Wert für diese XGS 116.
- RX/TX-Ringfortschritt, NPU GIU-/PP2-Zähler und externe Paketmitschnitte müssen gemeinsam ausgewertet
  werden. Metadatenzähler aus einer bestimmten Forwarder-Erweiterung sind kein universelles ABI.
- Die XGS126-Bootskripte enthalten feste Slot-/Partitionswerte und automatische Respawn-/Bootänderungen;
  diese werden nicht als sichere XGS-116-Installationsvorgabe übernommen.

## Offizielle OPNsense-Integration

Die Webseiten unter `docs.opnsense.org` waren aus dieser Cloud gesperrt; die offiziellen
Quelltexte im OPNsense-GitHub-Repository waren erreichbar:

- [autorun.rst](https://github.com/opnsense/docs/blob/ea0d9dd5b2c448e8676f3c55bf7725dab2acab9b/source/development/backend/autorun.rst):
  `rc.syshook.d/early` läuft vor Netzwerkstart, `start` danach; ausführbare Plugins verwenden
  gewöhnlich Präfix `50-`. Ein Modul, dessen Interfaces OPNsense konfigurieren soll, muss vorher bereit sein.
- [settingsmenu.rst](https://github.com/opnsense/docs/blob/ea0d9dd5b2c448e8676f3c55bf7725dab2acab9b/source/manual/settingsmenu.rst):
  System-/Tunables-Einstellungen; bestehende Firewallkonfiguration bleibt Sache des Betreibers.
- [software_included.rst](https://github.com/opnsense/docs/blob/ea0d9dd5b2c448e8676f3c55bf7725dab2acab9b/source/manual/software_included.rst):
  Komponenten/Paketumgebung; ein fremdes KMOD braucht bei jedem Kernelwechsel erneute ABI-Prüfung.

GPL-Komponenten dürfen als Binary nur mit erfüllten entsprechenden Quellcodepflichten verteilt
werden. Proprietäre Originaldateien bleiben lokal beim Gerätebesitzer; ein Build-/Hashmanifest
überträgt keine Rechte an diesen Dateien.
