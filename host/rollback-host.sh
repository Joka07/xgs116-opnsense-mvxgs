#!/bin/sh
# SPDX-License-Identifier: MIT
# Offline host-file rollback only; no kldunload, reboot, or NPU writes.
set -eu
HERE=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
. "$HERE/common.sh"
[ "$#" -ge 1 ] || { echo 'Usage: rollback-host.sh BACKUP [--stage-root DIR] [--apply]' >&2; exit 2; }
BACKUP=$1; shift
DEST=/; APPLY=0; STAGING=0
while [ "$#" -gt 0 ]; do
    case "$1" in
    --apply) APPLY=1; shift;;
    --stage-root) [ "$#" -ge 2 ] || exit 2; DEST=$2; STAGING=1; shift 2; [ "$DEST" != / ] || exit 2;;
    *) exit 2;;
    esac
done
[ -d "$DEST" ] && [ ! -L "$DEST" ] || exit 1
DEST=$(CDPATH= cd -- "$DEST" && pwd -P)
[ "$STAGING" = 0 ] || [ "$DEST" != / ] || { xgs_error 'Staging destination resolves to the live root'; exit 1; }
[ -d "$BACKUP" ] && [ ! -L "$BACKUP" ] || exit 1
[ "$(cat "$BACKUP/destination")" = "$DEST" ] || { xgs_error 'Backup destination mismatch'; exit 1; }
for list in created-files replaced-files backup-SHA256SUMS installed-SHA256SUMS; do
    [ -f "$BACKUP/$list" ] && [ ! -L "$BACKUP/$list" ] || exit 1
done
awk 'seen[$0]++ {exit 1} {n++} END {if(n!=6) exit 1}' "$BACKUP/created-files" "$BACKUP/replaced-files" || exit 1
check_path() {
    check_base=$1; check_rel=$2
    while [ -n "$check_rel" ]; do
        part=${check_rel%%/*}; check_base="$check_base/$part"
        [ ! -L "$check_base" ] || { xgs_error "Refusing symlink: $check_base"; return 1; }
        case "$check_rel" in */*) check_rel=${check_rel#*/};; *) break;; esac
    done
}
for list in created-files replaced-files; do
    while IFS= read -r rel; do
        case "$rel" in
        boot/modules/if_agnic.ko|usr/local/etc/xgs116-agnic/module.meta|usr/local/libexec/xgs116-agnic/common.sh|usr/local/libexec/xgs116-agnic/agnic-control.sh|usr/local/etc/rc.syshook.d/early/50-xgs116-agnic|usr/local/etc/rc.syshook.d/update/50-xgs116-agnic) ;;
        *) xgs_error 'Unexpected backup path'; exit 1;;
        esac
        check_path "$DEST" "$rel"
        want=$(awk -v p="payload/$rel" '$2==p {print $1}' "$BACKUP/installed-SHA256SUMS")
        [ -f "$DEST/$rel" ] && [ "$(xgs_hash "$DEST/$rel")" = "$want" ] || {
            xgs_error "Installed file changed since this backup; refusing rollback: $rel"; exit 1;
        }
        if [ "$list" = replaced-files ]; then
            check_path "$BACKUP/files" "$rel"
            want=$(awk -v p="$rel" '$2==p {print $1}' "$BACKUP/backup-SHA256SUMS")
            [ -f "$BACKUP/files/$rel" ] && [ "$(xgs_hash "$BACKUP/files/$rel")" = "$want" ] || {
                xgs_error "Backup checksum mismatch: $rel"; exit 1;
            }
        fi
    done < "$BACKUP/$list"
done
if [ "$DEST" = / ]; then
    if kldstat -q -n if_agnic; then
        xgs_error 'Module is loaded. Use serial console recovery with its boot hook disabled; no automatic unload.'; exit 1
    fi
    [ "$APPLY" = 0 ] || [ "$(id -u)" = 0 ] || exit 1
fi
echo "Restore prior host files from $BACKUP to $DEST"
[ "$APPLY" = 1 ] || { echo 'DRY RUN: add --apply to restore files.'; exit 0; }
# Remove activation first; restore any previous activation only after dependencies.
rm -f "$DEST/usr/local/etc/rc.syshook.d/early/50-xgs116-agnic"
while IFS= read -r rel; do rm -f "$DEST/$rel"; done < "$BACKUP/created-files"
while IFS= read -r rel; do
    [ "$rel" = usr/local/etc/rc.syshook.d/early/50-xgs116-agnic ] && continue
    cp -p "$BACKUP/files/$rel" "$DEST/$rel"
done < "$BACKUP/replaced-files"
rel=usr/local/etc/rc.syshook.d/early/50-xgs116-agnic
if [ -f "$BACKUP/files/$rel" ]; then cp -p "$BACKUP/files/$rel" "$DEST/$rel"; fi
echo 'Host files restored; no driver or NPU was restarted.'
