#!/usr/bin/env bash
# After the macOS step: mount VMXFER (exFAT, read-only), verify, unpack the
# restore bundle sparsely into ~/vm-artifacts, stage AVPBooter and Xcode.dmg,
# and write ~/Work/macos-vm/vm.env (AVPBOOTER, GFX=none, ...).
set -euo pipefail

BUNDLE=tahoe-26.4-25E246-restore
ART="${OMVM_ART:-$HOME/vm-artifacts}"
REPO="${OMVM_REPO:?set OMVM_REPO}"
ENVF="${OMVM_ENVF:-$ART/vm.env}"
MNT="${MNT:-/mnt/vmxfer}"

die() { echo "error: $*" >&2; exit 1; }
dev="$(lsblk -rno PATH,LABEL | awk '$2=="VMXFER"{print $1; exit}')"
test -n "$dev" || die "no partition labelled VMXFER found"
sudo mkdir -p "$MNT"
mountpoint -q "$MNT" || sudo mount -t exfat -o ro,uid="$(id -u)",gid="$(id -g)" "$dev" "$MNT"
trap 'cd /; sudo umount "$MNT" 2>/dev/null || true' EXIT

echo "== host info"; cat "$MNT/host-sw_vers.txt" "$MNT/xcode-version.txt" 2>/dev/null || true
echo "== verifying transfer checksums"
(cd "$MNT" && sha256sum -c vmxfer.sha256)

mkdir -p "$ART"
if ! test -f "$ART/$BUNDLE/.ingested"; then
    rm -rf "$ART/$BUNDLE.partial"
    mkdir "$ART/$BUNDLE.partial"
    echo "== unpacking bundle"
    tar -xzS -f "$MNT/$BUNDLE.tar.gz" -C "$ART/$BUNDLE.partial"
    b="$ART/$BUNDLE.partial/$BUNDLE"
    echo "== checking bundle manifest"
    (cd "$b" && sha256sum -c --quiet MANIFEST.sha256)
    echo "== re-sparsifying disk image"
    fallocate --dig-holes "$b/guest/disk.img"
    chmod a-w "$b"/guest/*
    mv "$b" "$ART/$BUNDLE"
    rmdir "$ART/$BUNDLE.partial"
    touch "$ART/$BUNDLE/.ingested"
fi
du -sh --apparent-size "$ART/$BUNDLE"; du -sh "$ART/$BUNDLE"

mkdir -p "$REPO/artifacts/firmware"
cp "$MNT"/AVPBooter.vmapple2.*.bin "$REPO/artifacts/firmware/"
booter="$(ls "$REPO"/artifacts/firmware/AVPBooter.vmapple2.*.bin | head -1)"
if test -f "$MNT/Xcode.dmg"; then
    test -f "$ART/Xcode.dmg" || cp "$MNT/Xcode.dmg" "$ART/"
    cp "$MNT/xcode-version.txt" "$ART/" 2>/dev/null || true
fi

cat > "$ENVF" <<EOF
# source this before running repo scripts
export AVPBOOTER="$booter"
export GFX=none
export RUNNER_KEY="$HOME/.ssh/vmapple_runner"
export G="$ART"
EOF
echo "== wrote $ENVF"; cat "$ENVF"
ls -lh "$ART"
echo "ingest done"
