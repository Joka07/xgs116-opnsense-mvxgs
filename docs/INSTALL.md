# Installation auf einer XGS 116

Experimenteller Stand: isolierter Testaufbau, serielle Zugänge zu
Host und NPU sowie bestandene Recoveryprobe sind erforderlich.
Erst nach Hardwareabnahme die Hauptfirewall ersetzen.

## Original und Ziel prüfen

Mit unveränderter Sophos-Umgebung NPU-Zugang, Speicheraufbau,
aktiven Slot, Module und Switchzustand erfassen. Vollständiges
Originalbackup und zweite Kopie außerhalb des Geräts anlegen:
NPU-SETUP.md.

Auf dem gestarteten OPNsense-Zielsystem festhalten:

~~~sh
uname -srmv
uname -K
freebsd-version -ku
opnsense-version
pciconf -l
~~~

Erwartet sind OPNsense 26.7, FreeBSD 15.1-RELEASE-p1, amd64 und
der dokumentierte Quellstand. Abweichungen brauchen einen passenden
Build bzw. Portierung; keine Versionsprüfung umgehen.

## NPU vorbereiten

Nach NPU-SETUP.md ein separates Image auf Basis der eigenen
gesicherten Originalumgebung erzeugen. Hardwareeinsatz erst nach
bestätigten Slots, Backup, serieller Recovery und ausdrücklicher
Freigabe des Schreibvorgangs planen. Die Werkzeuge schreiben keine
Partition/Bootvariable.

Endpoint und Vendor-Basismodule bleiben aus der eigenen Umgebung.
DSA-Device, Portmap, SWOP-Slot und Ausschluss konkurrierender
Switchdienste müssen am Gerät bestätigt sein.

## Hostpaket installieren

Mit BUILD.md Modul bauen und Paket an das echte uname -v binden.
Archivhash über vertrauenswürdigen Übertragungsweg vergleichen.
In ein neues leeres Verzeichnis auf dem Host auspacken:

~~~sh
cd xgs116-host
sh installer/preflight.sh .
sh installer/install-host.sh --bundle .
~~~

Der zweite Befehl ist ein Dry-Run. Geprüft werden Hashes, amd64-ELF,
exakte laufende/installierte Kernelversion, OPNsense-Serie und
genau ein 11ab:7080-Endpoint ohne konkurrierenden Treiber.
mvxgs aus current/ oder phases/ darf ihn nicht belegen.

Nach bestandener Prüfung:

~~~sh
sh installer/install-host.sh --bundle . --apply
~~~

Bestehende Dateien benötigen bewusst --replace-existing. Vor jeder
Ersetzung wird der gesamte vorherige Dateistand unter
/var/backups/xgs116-agnic/install.* gesichert. Der Installer lädt
kein Modul und verändert keine Interfacezuweisungen.

## Kontrollierter Start

NPU und Host koordiniert mit serieller Konsole starten. Der Early-
Syshook läuft vor der OPNsense-Netzwerkkonfiguration, prüft und lädt
einmalig und wartet begrenzt auf neun Interfaces und Readiness.
Die internen Attach-Wartezeiten kommen zu maximal 60 Sekunden
Hook-Polling hinzu. Fehler sperren weitere Versuche dieses Boots.

~~~sh
/usr/local/libexec/xgs116-agnic/agnic-control.sh check
/usr/local/libexec/xgs116-agnic/agnic-control.sh diagnose > /tmp/xgs116-diagnostics.txt
ifconfig -l
~~~

Initialisierung: dev.agnic.0.mgmt_ready=1, datapath_ready=1,
nports=9, recovery_required=0 und port1..port9. Dies beweist keine
Paketübertragung. Der Treiber erzeugt stabile MAC-Präfixe aus dem
SMBIOS-UUID; bei fehlender/duplizierter UUID einen eigenen gültigen
hw.agnic.mac_base-Tunable verwenden: driver/if_agnic/README.md.

Jeden Anschluss per Kabelwechsel und Gegenstellencapture zuordnen.
Link, Speed/Duplex, RX/TX und Isolation prüfen. Danach normale
OPNsense-Zuweisung bzw. eigenes Backup übernehmen. Die Integration
migriert keine Regeln, VLANs, Adressen oder Dienste.

COMPATIBILITY.md, PERFORMANCE.md und tests/network/README.md
enthalten die vollständige Abnahme inklusive NAT, VLAN-MTU,
Stromausfall und 72-Stunden-Test.

## Updates

Der Update-Syshook prüft die Kompatibilität; ein anderer Kernel
wird beim Start abgelehnt. Vor Updates serielle Erreichbarkeit und
Ersatzbetrieb sichern. Andere Kernelrevisionen werden nicht
automatisch unterstützt. Neubau und Hardware-Regression gehören
zum Updateverfahren. Rollback: RECOVERY.md.
