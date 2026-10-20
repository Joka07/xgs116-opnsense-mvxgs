# Offene Arbeiten vor Produktionsfreigabe

Die portable Implementierung ist eine testbare Entwicklungsbasis.
Folgendes benötigt Hardware bzw. private Originaldaten:

1. Zielimage und vollständiges uname -v bestätigen; Hostpaket binden
   und Modul auf passendem FreeBSD-Kernel laden.
2. NPU-Speicherbelegung, readonly/quieszenten Backupzustand,
   Vendor-Module und Bootkette erfassen; Originalbackup und zweite
   Kopie prüfen.
3. DSA-Device, neun physische Portnummern, CPU-/SFP-SerDes,
   NWA+0xf000-Slot und fremde Switchdienste vermessen. Buildwert 2
   ist keine Boardkonfiguration.
4. Dienststarter prüfen, individuelles Offline-Image bauen und
   inaktiven Slotinhalt erhalten. Flashen/Bootumschaltung erst nach
   ausdrücklicher Freigabe und geprüfter serieller Recovery.
5. Erstboot, beide Bootreihenfolgen, Warm-/Kaltstart und Stromausfall
   prüfen. Persistenter Hook ist implementiert; autonomer Start ist
   nicht auf Hardware nachgewiesen.
6. DMA/MSI-X, Ringfortschritt, Isolation während Boot, neun Links/MACs
   und bidirektionale Frames belegen. Bekannten TX-Ausfall anhand
   der echten Messdaten eingrenzen und ggf. weiter korrigieren.
7. VLAN10/20/30/99 bei voller MTU, IPv4/IPv6, DHCP, pf/NAT,
   Inter-VLAN, Parallelverkehr, 600-Mbit/s-WAN, Gigabit-Nutzdatenziel
   und 72 Stunden Dauerlast abnehmen.
8. Original-Recovery durchführen; Updateverfahren praktisch testen.

Bewusste Funktionsgrenzen:

- Hot-Unload nach veröffentlichten DMA-Ringen wird verweigert;
  belegter Quiesce-/Resetvertrag für freies Hot-Reattach fehlt.
- Kein automatischer NPU-Neustart oder garantierter transparenter
  Wiederanschluss. Dafür fehlt ein expliziter Generation-/Liveness-
  und DMA-Ownership-Vertrag.
- Keine automatisch sichere A/B-Rückkehr oder Bootvariablenänderung.
- Kein natives pkg-Repository-Plugin. Dokumentierte Syshooks und
  exakte Kernelbindung sind implementiert; andere Kernelrevisionen
  benötigen Portierungsarbeit.
- SFP-Kompatibilität, Gigabitleistung und vollständige Portfunktion
  bleiben ohne Messung unbestätigt.

Testmatrix: COMPATIBILITY.md, PERFORMANCE.md,
tests/network/README.md. Bis zur Abnahme bleibt der Status experimentell.
