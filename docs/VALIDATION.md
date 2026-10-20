# Tatsächlich ausgeführte Prüfungen

Cloud-Lauf am 20. Oktober 2026. Debian 13 amd64; keine XGS-116-
Hardwareverbindung. Alle folgenden Hardwareaussagen bleiben ungetestet.

## Bestanden

- 54 portable Tests: 39 in tests/unit, 7 in tests/network und 8 in
  tests/performance; keine Skips im vollständigen Lauf.
- Tatsächliche C-Header/-Handler mit UBSan ausgeführt: Porttags,
  Framegrenzen/Overflow, MAC-Ableitung, SWOP-v1/v2 und Antwortprüfung.
- 6.912 DSA-Roundtrips über neun Ports, 802.1Q/802.1ad bei voller
  MTU, PCP/DEI/VID und unabhängiger bekannter VLAN-/DSA-Bytevektor.
- SWOP-Suite: 506 Prüfungen. Die absichtlich falsche Negativkontrolle
  meldet intern FAIL und wird als erwartete Kontrolle erkannt;
  Suite-Endergebnis ist PASS mit null Fehlern.
- Echte temporäre ext4-Dateisysteme mit mke2fs/debugfs/e2fsck:
  Original unverändert, Kernel erhalten, persistenter Start-Hook
  gesetzt, aktive Slotwahl/Hashmanipulation/Traversal/Symlinks
  abgelehnt. Geräte-/Kerneldaten darin sind Testfixtures.
- Hostinstallation und Rollback in isolierten Verzeichnissen,
  exakte Kernelprüfung über Kommandomocks, Paketmanipulation,
  Symlinkpfade und versehentliches Live-Root-Staging geprüft.
- Switchinitialisierung gegen einen dateibasierten Registermock:
  fehlgeschlagene Isolation verhindert Portfreigabe und PHY-Start;
  alle Maps werden vor Forwarding geprüft.
- 18 neue Shellskripte/Hooks syntaktisch geprüft; Pythonquellen
  ohne Erzeugung von Repository-Bytecode kompiliert.
- Toolchain-Bootstrap mit 61 signierten, SHA-256-gepinnten Paketen
  sowohl erneut im bestehenden als auch in einem frischen Prefix
  ausgeführt. Systemverzeichnisse unverändert.
- FreeBSD-Kernelmodul mit originalem bsd.kmod.mk gegen exakt
  12334a596709d195acb73f0f069da82c570a3d84 gebaut und gelinkt.
  Zweiter frischer Build erzeugte dasselbe if_agnic.ko.
- Beide NPU-Capabilityprofile als statisches AArch64-ELF gebaut;
  64-Bit-MUSDK-DMA, SWOP-/SFF-Handler und Artefakthashes geprüft.
- SWOP-v1 aus dem vollständigen Quellpaket ohne MUSDK-Gitcheckout
  mit einer frisch installierten Toolchain an einem anderen Prefix
  neu gebaut: stripped und Debugbinary bytegleich zum Build aus
  dem Referenzcheckout. Quell-/Sysrootpfade werden normalisiert.

Hostmodul SHA-256:

~~~text
a81d7f876ea64434fcc0f2671757e40f35aa0f8fa959c01c44684cac610b497a
~~~

Finale Forwarder SHA-256 (DSA-Device 2, nicht hardwarevalidiert):

~~~text
v1 f6693f21e5dab1566e02811951b50157a2631fe0b799b0e6bf53a30a2bc68d5e
v2 af80bea59ede73c4b46f5c62b2a435a6d077e0c2736eb56f012d5783ea800756
~~~

BUILD-INFO.json und SHA256SUMS in den endgültigen Artefaktordnern
enthalten die NPU-Profile und deren tatsächliche Quellhashes. Alle
Cloudproben verwenden explizit DSA-Device 2; das ist keine
Gerätevermessung. Paket-Bytegleichheit wird in der Testsuite geprüft.

## Nicht ausgeführt

Modul laden, DMA, MSI-X, PCIe-Handshake auf dem Ziel, NPU-Binary
ausführen, Vendor-Extraktion vom echten Gerät, Originalbackup,
Flashen/Slotumschaltung, SFP/RJ45-Link, echte RX/TX-/VLAN-/NAT-
Paketübertragung, Gigabit/WAN-/Inter-VLAN-Durchsatz, Neustarts,
Stromunterbrechung, 72 Stunden Last und Original-Recovery.

Keine Hoststatistik beweist Frontport-Egress. Kein bestandener
Cloudtest gibt diesen Stand als Hauptfirewall frei. Vollständige
Abnahme und verbleibende Funktionsgrenzen: REMAINING.md.
