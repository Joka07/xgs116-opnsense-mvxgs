# Reproduzierbarer Build

Ziel: OPNsense 26.7 / FreeBSD 15.1-RELEASE-p1, amd64. Kernelquelle:
12334a596709d195acb73f0f069da82c570a3d84. Der Build ersetzt keine
ABI-Prüfung des tatsächlich gestarteten Zielkernels.

## Linux-Werkzeuge

Getestet: Debian 13 amd64, Python 3.12.14, Clang/LLD 19.1.7,
AArch64 GCC 14.2.0, GNU Make 4.4.1. Vier Compilerprozesse passen zur
Cloud mit fünf CPUs. Mindestens 5 GiB freien Platz einplanen.

build/setup-linux.py lädt und entpackt 61 exakt versionierte Debian-
Pakete in eine private Toolchain. APT prüft Debian-Signaturen, das
Skript anschließend die festgehaltenen SHA-256-Werte. Es führt keine
Installationshaken aus und verändert keine Systemverzeichnisse.
Voraussetzung: Debian-13-Laufzeitbibliotheken, Git, Python, dpkg-deb,
APT und der offizielle Debian-Archivschlüsselring.

~~~sh
python3 build/setup-linux.py --prefix /workspace/toolchain
. /workspace/toolchain/activate.sh
~~~

Vorhandene fremde Ablagen werden abgelehnt; der verwaltete Prefix
ist wiederverwendbar. Fehlt ein historisches Paket im Mirror, bricht
der Bootstrap ab. Keine Signatur-/Hashprüfung umgehen.
Pins: build/debian-toolchain.lock.json. Native Voraussetzungen:
LLVM/Clang, bmake, gawk, AArch64-GCC/Binutils mit statischer libc,
Autoconf, Automake, Libtool, m4, pkg-config und e2fsprogs.

## Kernelquelle und Modul

~~~sh
git init /workspace/build-inputs/opnsense-src
git -C /workspace/build-inputs/opnsense-src remote add origin https://github.com/opnsense/src.git
git -C /workspace/build-inputs/opnsense-src fetch --depth 1 origin 12334a596709d195acb73f0f069da82c570a3d84
git -C /workspace/build-inputs/opnsense-src checkout --detach FETCH_HEAD
python3 build/build-driver.py \
  --src-tree /workspace/build-inputs/opnsense-src \
  --output-dir artifacts/driver --jobs 4
~~~

Bei vorhandenem Checkout nur Revision und Sauberkeit prüfen; keine
fremden Änderungen überschreiben. Der Wrapper prüft Kernelinputs,
verwendet originale bsd.kmod.mk-Regeln, baut frisch außerhalb der
Quellen und prüft FreeBSD-amd64-ELF und Modulmetadaten.
Unter Linux sind gawk und XARGS_J=-I erforderlich: mawk hing beim
originalen kmod_syms.awk; GNU xargs unterstützt BSD -J nicht.

Ergebnis: if_agnic.ko, SHA256SUMS, build-manifest.json und build.log.
Der Crossbuild wurde ausgeführt; Laden ist unter Linux unmöglich.
Nativ auf dem passenden FreeBSD-Buildhost:

~~~sh
cd driver/if_agnic
make SYSDIR=/path/to/exact-opnsense-src/sys
~~~

Bei besonderen Kernelkonfigurationen passende generierte
Kerneloptionsheader verwenden. Ähnliche Versionsnummern beweisen
keine ABI-Kompatibilität.

## NPU-Forwarder

MUSDK ist auf 278748af6e197672551ba220c8720d9ae0a8461e festgelegt.
Der Wrapper verändert keinen vorhandenen MUSDK-Checkout. Er wendet
den Patch auf eine frische Commitkopie an und baut nur Bibliothek
und benötigten Forwarder.

~~~sh
python3 npu/build/build.py \
  --work /workspace/build/xgs116-npu \
  --musdk-source /workspace/upstream/musdk-marvell \
  --dsa-device 2 --swop-version 1 \
  --sysroot /workspace/toolchain/root --jobs 4
~~~

Ohne --musdk-source wird MUSDK geklont. --sysroot ist für die lokale
relocierte Toolchain nötig; normal installierte Crosscompiler
verwenden ihren eigenen Sysroot.

**Die 2 ist eine Cloud-Buildprobe, keine gemessene Gerätenummer.**
Am Gerät bestimmen und den Wert entsprechend ersetzen. Capability
v2 wird mit --swop-version 2 gebaut; das Nachrichtenformat bleibt v1.
Keines dieser Profile wird als identisch zum historisch getesteten
Payload mit MD5 35c35a3c19311efd2b529a7693e76cd4 ausgegeben.

ARTIFACTS nennt das Ergebnisverzeichnis: dp_fwd, Debugbinary,
Konfiguration, Start-/Switchskripte, SHA256SUMS, BUILD-INFO.json.
Der Wrapper prüft statisches AArch64-ELF, 64-Bit-MUSDK-DMA und
kompilierte SWOP/SFF-Handler. Die Host-DMA-Grenze bleibt 36 Bit.

Legacy-MUSDK erzeugt mit GCC 14 Warnungen. Der globale -Werror-
Schalter wird nur in der isolierten Kopie aufgehoben; Warnungen
bleiben in den Logs. Compiler-/Linkfehler brechen den Build ab.
Statisches Linken vermeidet die alte NPU-glibc als Abhängigkeit,
ersetzt aber keinen Laufzeittest gegen NPU-Kernel/CMA/UIO.

## Pakete und Quellcode

Hostpakete brauchen das echte vollständige uname -v des Zielsystems:

~~~sh
python3 packaging/build-host-package.py \
  --module artifacts/driver/if_agnic.ko \
  --kernel-ident "$TARGET_KERNEL_IDENT" \
  --output /tmp/xgs116-host.tar.gz
~~~

Keinen Identitätsstring erfinden. Die Metadaten sind eine
Herkunftsangabe des Packagers, keine unabhängige Prüfung beliebiger
Eingabeobjekte. Buildmanifest/Log behalten. Dies ist ein transparentes
Installationsarchiv, kein natives pkg-Repository-Plugin.

~~~sh
python3 packaging/build-source.py \
  --musdk-source /workspace/upstream/musdk-marvell \
  --output /tmp/xgs116-corresponding-source.tar.gz
~~~

Enthalten sind alle Integrationsquellen/Tests/Lizenzen und das
vollständige Original-MUSDK-Archiv am festen Commit. Der NPU-Wrapper
kann daraus mit --musdk-archive und --musdk-archive-sha256 aus
SOURCE.json ohne MUSDK-Gitcheckout bauen. Binaries nur gemeinsam
mit diesem korrespondierenden Quellpaket weitergeben.

## Tests

~~~sh
python3 tests/run-host.py
~~~

e2fsprogs aktivieren, damit die echten ext4-Tests ausgeführt werden.
Ein Skip ist kein bestandener Test. C-Vertragstests verwenden
UBSan; DMA/MSI-X-Hardware wird nicht simuliert.
