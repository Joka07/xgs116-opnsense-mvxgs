# NPU sichern und persistent vorbereiten

Der Forwarder braucht den eigenen NPU-Kernel und passende Endpoint-/
CMA-/UIO-Module. Diese Originale werden nicht verteilt. Die Werkzeuge
laufen auf einem Linux-Buildhost mit Python, OpenSSH und e2fsprogs.
Die interne NPU muss über eine eigene SSH-Konfiguration erreichbar
sein, gegebenenfalls über einen vom Betreiber eingerichteten Jump-
Host. Die Cloud hat keinen Zugang zur Appliance.

## Vollständiges Originalbackup

SSH-Hostkey über serielle Konsole prüfen; eigene known_hosts-Datei
und eigenen berechtigten Schlüssel verwenden. Keine fremden
mitgelieferten Schlüssel übernehmen.

~~~sh
sh installer/backup-npu.sh \
  --host root@NPU_ALIAS --identity /private/own-key \
  --known-hosts /private/known_hosts --out /private/xgs116-backup
~~~

Dies zeigt Inventar und Backupplan. Der aktive Slot wird aus Mount
und Kernelkommandozeile bestimmt. Unterstützt sind unzweideutige
eMMC-/ext4-Root-Dateisysteme, keine geratenen Partitionsnummern.

eMMC-/Flash-Mounts einschließlich /persistent müssen für ein
konsistentes Backup readonly/quieszent sein. Das Werkzeug remountet
nichts und bricht bei schreibenden Mounts ab. Zustand und Dienste
vorab an der Konsole prüfen.

~~~sh
sh installer/backup-npu.sh \
  --host root@NPU_ALIAS --identity /private/own-key \
  --known-hosts /private/known_hosts --out /private/xgs116-backup --apply
~~~

--apply schreibt nur lokale Backupdateien: gesamte eMMC, aktives
Rootfs, vorhandene eMMC-Bootbereiche, alle inventarisierten MTD-
Bereiche und Original-Bootumgebung. Die NPU wird nur gelesen.
Größen/Hashes werden gegen das Gerät geprüft; nur bei unverändertem
Schlussinventar entsteht ein vollständiges Manifest.

Ablage außerhalb des Gitcheckouts und ausreichend Platz für eMMC
plus aktives Rootfs vorsehen. Zweite Kopie auf anderem Datenträger
sichern. Backups, Bootumgebung und Module niemals veröffentlichen.

## Eigene Module extrahieren

~~~sh
sh installer/extract-vendor-files.sh \
  --backup /private/xgs116-backup --out /private/xgs116-modules
sh installer/extract-vendor-files.sh \
  --backup /private/xgs116-backup --out /private/xgs116-modules --apply
~~~

musdk_cma.ko, mv_dmax2_uio.ko und uio_pdrv_genirq.ko werden eindeutig
aus dem geprüften Originalimage zur NPU-Kernelversion gebunden.
Weitere Basismodule wie mv_armada_ep bleiben im Originalrootfs.
Umbenennen macht fremde Module nicht kompatibel.

## Board-/Protokollprofil

Auf dem isolierten NPU-System mit npu/switch-init/probe.sh lesen.
MDIO schreibt Lesekommandos, keine Switchkonfiguration. DSA-Device
aus Global1 Control2 mit beobachteten Ingress-DSA-Tags abgleichen.
CPU-/Frontportmap und SFP-Modul prüfen; XGS126-/Issue-Werte sind
Referenzen.

Vor Capability-Publikation das NWA-Fenster passiv sichern und bei
originalem Mailboxverkehr vergleichen. NWA+0xf000/BAR0+0x13000 muss
auf dieser Appliance als frei/reserviert bestätigt sein. Die
XGS126-Vermessung ist dafür kein Beweis.

Nach tatsächlicher Messung privat board.conf anlegen:

~~~text
board_confirmed=yes
swop_slot_confirmed=yes
dsa_device=<gemessene Zahl 0..31>
~~~

Diese Bestätigungen sind Betreiberanforderungen, keine vom Editor
ausgeführte Hardwareprüfung. Buildprofil, Board und Live-Device
müssen übereinstimmen. Das private Payloadverzeichnis muss vollständig
aus dem Build stammen: dp_fwd, dp-nmp-config.txt, build-profile.conf,
BUILD-INFO.json, SHA256SUMS, startup/ und switch-init/. Hashes
werden vor der Imageerstellung und beim Start geprüft.

Die Startfolge prüft Konfliktprozesse, Basismodule, eigene UIO-Module,
Switchidentität und Isolation. Sie startet dp_fwd einmal pro Boot,
ohne Kill-/Respawn-Schleife. Originaldienste und ihre Wrapper müssen
so deaktiviert sein, dass kein späterer Switchschreiber erscheint.

## Persistentes Offline-Image

installer/npu-boot-profile.example.json privat kopieren. Tatsächliche
Kernelversion, geprüfte serielle Recovery und gezielt deaktivierte
Original-Dienststartdateien eintragen. Nicht die Basismodul-/SSH-
Initialisierung abschalten. Ohne diese Angaben wird abgebrochen.

~~~sh
sh installer/prepare-npu.sh \
  --backup /private/xgs116-backup \
  --payload /private/reviewed-payload \
  --boot-profile /private/reviewed-boot-profile.json \
  --target-slot /dev/mmcblkXpY \
  --out /private/xgs116-candidate
~~~

Den Platzhalter durch eine inventarisierte, ausreichend große,
inaktive Partition desselben eMMC ersetzen. Bei mitgelieferten
privaten Modulen zusätzlich --vendor-manifest auf das eigene
Extraktionsmanifest setzen. Passende Originalmodule können an
ihrem bisherigen Ort bleiben.

Mit zusätzlichem --apply entsteht rootfs-xgs116.ext4 als separate
reguläre Datei. Kernel, DTB, SSH und Originaldateien bleiben erhalten.
Nur geprüfte Dienststarter werden vor dem rcS-S??*-Glob versteckt.
/opt/xgs116 und der einmalige S99-Start werden ergänzt. E2fsck und
Hashes prüfen das Ergebnis; Originalimage/Geräte bleiben unverändert.

Die persistente Bootintegration ist damit im Image implementiert.
Flashen, Slotumschaltung und Recovery sind noch nicht auf Hardware
validiert oder automatisiert. Aktiver Rootslot, /dev/mtd0 und
Bootvariablen werden niemals beschrieben. Keine automatische A/B-
Rückkehr bei Bootfehlern ist belegt. Die Hardwarephase braucht konkrete
Slot-/Konsolendaten und ausdrückliche Freigabe jedes irreversiblen
Schreibvorgangs.
