# Diagnose

Host-/NPU-Logs und Gegenstellencaptures sichern. Aktive Initialisierung
bei unklarem Ringzustand nicht wiederholen.

## Modul oder Interfaces fehlen

preflight.sh meldet Kernelrelease/build, OPNsense-Serie, Modulhash,
Architektur und PCI-Bindung. Konkurrierendes mvxgs über kontrollierten
Bootweg entfernen, nicht während noch möglicher NPU-DMA wechseln.

agnic-control.sh diagnose und tests/network/collect.sh sammeln
dev.agnic.0, Interfaces, Zähler und Bootmeldungen. mgmt_ready=0:
Endpoint/Facility und NPU-Handshake prüfen. datapath_ready=0 bei
erfolgreichem Management: Queue-/Buffer-/ifnet-Initialisierung prüfen.
Ungültiger SMBIOS-UUID benötigt eigenen stabilen MAC-Präfix.

## RX funktioniert, TX kommt nicht an

tx_packets ist Enqueue; tx_cons belegt NPU-Verbrauch. Erst PP2-/
Switchzähler und Empfängercapture beweisen Frontport-Egress.

1. Ringindices und Drops vor/nach bekannter Paketanzahl aufnehmen;
   Wraparound berücksichtigen.
2. NPU-GIU-/PP2-Zähler und dp_dsa_rx-Anfangsdiagnosen korrelieren.
3. Live-DSA-Device gegen Buildprofil und empfangene Tags prüfen.
4. CPU-Portmap, CPU-DSA-Modus und Frontportmap lesen; Issuewerte
   0x03fe / 0x017f / 0x0001 sind Messhinweise.
5. usfp, UMSD_NPU, NetAgent und Wrapper auf fremde Schreiber prüfen.

Erfolgreiche TX-Ringe nicht als bestandenen Netzwerkpfad ausweisen.

## VLAN / MTU

802.1Q-TCI/PCP/DEI wird im DSA-Format erhalten. MTU-1500-VLAN
benötigt 1584 Bytes mit 66-Byte-Präfix ohne FCS; konservative Grenze
1588. Jumbo-MTU und Checksum-/Tag-Insertion-Offloads sind nicht
freigegeben. Tatsächlichen Tag per Gegenstellencapture prüfen.

## Link unbekannt / NPU-Neustart

Ohne validen SWOP-/NW_AGENT-Responder bleibt Link unbekannt.
Speedcode 3 bedeutet nicht automatisch Gigabit. Gegenstelle und
Kabelwechsel für jedes Interface prüfen.

recovery_required=1, ungültige Indices, verlorene Capability oder
Timeout sperren den Pfad. Ein Neustart mit gleicher Capability
kann unerkannt bleiben: kein vollständiger Generation-/Liveness-
Vertrag. Host/NPU koordiniert per Konsole neu starten; keine
Respawn-/KLD-Reload-Schleife.

## NPU-Autostart

/tmp/xgs116-startup.log und einmalige Startmarkierungen prüfen.
Fehlendes Boardprofil, unbestätigter Slot, DSA-Mismatch,
Konfliktprozess, Basismodul oder Hashfehler stoppt den Start.
Der S99-Hook verwendet dp-autostart.sh --apply. Manueller Aufruf
ohne --apply ist ein Dry-Run. Nicht Sperren im laufenden Boot
löschen; Originalbootweg nach RECOVERY.md verwenden.
