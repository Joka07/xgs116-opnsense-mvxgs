#!/bin/sh
# SPDX-License-Identifier: MIT
# Installs only the host module and hooks; never loads it or changes NPU storage.
set -eu
HERE=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
. "$HERE/../host/common.sh"
BUNDLE=$(CDPATH= cd -- "$HERE/.." && pwd)
DEST=/
APPLY=0
REPLACE=0
STAGING=0
usage() { echo 'Usage: install-host.sh [--bundle DIR] [--stage-root DIR] [--apply] [--replace-existing]' >&2; exit 2; }
while [ "$#" -gt 0 ]; do
    case "$1" in
    --bundle) [ "$#" -ge 2 ] || usage; BUNDLE=$2; shift 2;;
    --stage-root) [ "$#" -ge 2 ] || usage; DEST=$2; STAGING=1; shift 2; [ "$DEST" != / ] || usage;;
    --apply) APPLY=1; shift;;
    --replace-existing) REPLACE=1; shift;;
    *) usage;;
    esac
done
[ -d "$DEST" ] && [ ! -L "$DEST" ] || { xgs_error 'Destination must be an existing real directory'; exit 1; }
DEST=$(CDPATH= cd -- "$DEST" && pwd -P)
[ "$STAGING" = 0 ] || [ "$DEST" != / ] || { xgs_error 'Staging destination resolves to the live root'; exit 1; }
[ -d "$BUNDLE/payload" ] && [ ! -L "$BUNDLE/payload" ] || { xgs_error 'Missing bundle payload'; exit 1; }
META="$BUNDLE/payload/usr/local/etc/xgs116-agnic/module.meta"
MODULE="$BUNDLE/payload/boot/modules/if_agnic.ko"
xgs_verify_module "$MODULE" "$META"
MANIFEST="$BUNDLE/SHA256SUMS"
[ -f "$MANIFEST" ] && [ ! -L "$MANIFEST" ] || { xgs_error 'Missing bundle SHA256SUMS'; exit 1; }
awk 'NF!=2 || seen[$2]++ {exit 1} {n++} END {if(n!=6)exit 1}' "$MANIFEST" || {
    xgs_error 'Invalid checksum manifest'; exit 1;
}
FILES='boot/modules/if_agnic.ko
usr/local/etc/xgs116-agnic/module.meta
usr/local/libexec/xgs116-agnic/common.sh
usr/local/libexec/xgs116-agnic/agnic-control.sh
usr/local/etc/rc.syshook.d/update/50-xgs116-agnic
usr/local/etc/rc.syshook.d/early/50-xgs116-agnic'
# Reject symlinks in every path component, including existing destination parents.
check_path() {
    xgs_check_base=$1; xgs_check_rel=$2
    while [ -n "$xgs_check_rel" ]; do
        xgs_part=${xgs_check_rel%%/*}
        xgs_check_base="$xgs_check_base/$xgs_part"
        [ ! -L "$xgs_check_base" ] || { xgs_error "Refusing symlink: $xgs_check_base"; return 1; }
        case "$xgs_check_rel" in */*) xgs_check_rel=${xgs_check_rel#*/};; *) break;; esac
    done
}
for rel in $FILES; do
    check_path "$BUNDLE/payload" "$rel"
    check_path "$DEST" "$rel"
    [ -f "$BUNDLE/payload/$rel" ] || { xgs_error "Missing payload file: $rel"; exit 1; }
    want=$(awk -v path="payload/$rel" '$2==path {print $1}' "$MANIFEST")
    [ -n "$want" ] && [ "$(xgs_hash "$BUNDLE/payload/$rel")" = "$want" ] || {
        xgs_error "Bundle integrity failure: $rel"; exit 1;
    }
    if [ -e "$DEST/$rel" ]; then
        [ -f "$DEST/$rel" ] || { xgs_error "Destination is not a regular file: $rel"; exit 1; }
        [ "$REPLACE" = 1 ] || { xgs_error "Existing file requires --replace-existing (backup will be kept): $rel"; exit 1; }
    fi
done
if [ "$DEST" = / ]; then
    xgs_platform "$META"
    xgs_pci
    [ "$APPLY" = 0 ] || [ "$(id -u)" = 0 ] || { xgs_error 'Root is required'; exit 1; }
else
    xgs_error 'Staging only: running kernel and PCI are not validated; staged files are not activated.'
fi
printf 'Destination: %s\n' "$DEST"
printf 'Install %s\n' $FILES
[ "$APPLY" = 1 ] || { echo 'DRY RUN: no files changed. Add --apply to install.'; exit 0; }
check_path "$DEST" var/backups/xgs116-agnic
mkdir -p "$DEST/var/backups/xgs116-agnic"
BACKUP=$(mktemp -d "$DEST/var/backups/xgs116-agnic/install.XXXXXX")
: > "$BACKUP/created-files"
: > "$BACKUP/replaced-files"
: > "$BACKUP/backup-SHA256SUMS"
# Capture the entire prior state before replacing any file.
for rel in $FILES; do
    if [ -f "$DEST/$rel" ]; then
        mkdir -p "$BACKUP/files/$(dirname "$rel")"
        cp -p "$DEST/$rel" "$BACKUP/files/$rel"
        printf '%s  %s\n' "$(xgs_hash "$BACKUP/files/$rel")" "$rel" >> "$BACKUP/backup-SHA256SUMS"
        printf '%s\n' "$rel" >> "$BACKUP/replaced-files"
    else
        printf '%s\n' "$rel" >> "$BACKUP/created-files"
    fi
done
rollback_failure() {
    rc=$?
    trap - EXIT HUP INT TERM
    if [ "$rc" != 0 ]; then
        xgs_error "Installation failed; restoring files from $BACKUP"
        while IFS= read -r rel; do rm -f "$DEST/$rel"; done < "$BACKUP/created-files"
        while IFS= read -r rel; do cp -p "$BACKUP/files/$rel" "$DEST/$rel"; done < "$BACKUP/replaced-files"
    fi
    exit "$rc"
}
trap rollback_failure EXIT
trap 'exit 1' HUP INT TERM
# The early startup hook is installed last; all dependencies are present first.
for rel in $FILES; do
    mkdir -p "$DEST/$(dirname "$rel")"
    case "$rel" in *.ko|*.meta) mode=0644;; *) mode=0755;; esac
    temp=$(mktemp "$DEST/$(dirname "$rel")/.xgs116-install.XXXXXX")
    install -m "$mode" "$BUNDLE/payload/$rel" "$temp"
    mv -f "$temp" "$DEST/$rel"
done
printf '%s\n' "$DEST" > "$BACKUP/destination"
cp "$MANIFEST" "$BACKUP/installed-SHA256SUMS"
echo "Installed; previous files retained in $BACKUP"
echo 'No module was loaded. Verify NPU preparation and serial recovery before the first controlled boot.'
