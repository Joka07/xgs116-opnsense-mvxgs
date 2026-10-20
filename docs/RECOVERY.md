# Recovery

Vor jedem Kandidatenboot die serielle NPU-Konsole, U-Boot-Zugriff
und Originalboot praktisch testen. Eine zweite vollständige
Backupkopie außerhalb der Appliance aufbewahren. A/B-Slots beweisen
keinen automatischen Rollback.

## Host

An der seriellen/single-user-Konsole den Early-Hook
/usr/local/etc/rc.syshook.d/early/50-xgs116-agnic für den nächsten
Boot deaktivieren. Keine KLD-Unload-/Reload-Schleife: nach
veröffentlichten DMA-Adressen verweigert der Treiber Hot-Unload.

Bei nicht geladenem Modul mit dem ausgepackten Hostpaket:

~~~sh
sh host/rollback-host.sh /var/backups/xgs116-agnic/install.ABC123
sh host/rollback-host.sh /var/backups/xgs116-agnic/install.ABC123 --apply
~~~

Die echte Backupablage einsetzen. Original- und installierte Hashes
werden geprüft; veränderte Dateien werden abgelehnt. Nach Verschieben
des Hooks für Recovery dessen erwarteten Dateistand vor dem
automatischen Rollback wiederherstellen oder Originaldateien bewusst
manuell anhand der Backuphashes restaurieren. Andere
Firewallkonfigurationen werden nicht geändert.

## NPU

~~~sh
sh installer/rollback.sh --backup /private/xgs116-backup
~~~

Prüft das vollständige Backup und erstellt einen gerätespezifischen
Plan. Schreibt keine Partition/Bootvariable und gibt private
Bootvariablen nicht ins Test-/Chatlog aus.

An der bereits geprüften Konsole U-Boot unterbrechen. Originales
bootcmd und bootargs privat mit Livewerten vergleichen. Kernel/DTB
und root= müssen aus demselben Slot stammen. Einen einmaligen
Originalstart nur mit den geprüften Originalwerten im RAM ausführen,
kein automatisches saveenv. Konkrete Befehle hängen von den
gesicherten Variablen ab.

Originalkernel, Rootgerät, Module und Switch bestätigen. Dann den
Host kontrolliert neu starten, damit keine veralteten PCIe-/DMA-
Adressen weiterbenutzt werden. Anschließend Originalfunktion prüfen.

Auch eine Partitionsrestaurierung benötigt die gemessene Tabelle,
vollständige Hashprüfung und gesonderte Freigabe des Schreibziels.
Keine pauschalen dd-/mke2fs-Kommandos. /dev/mtd0 und Bootloader
sind kein Test-/Installationsschreibziel.

Serieller Rückweg, Kandidatenboot, Original-Recovery und
Stromausfallstart wurden hier nicht praktisch ausgeführt.
