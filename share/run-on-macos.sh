#!/usr/bin/env bash
# One-shot macOS step for the macOS-VM-on-Omarchy project. Run from native
# macOS on this MacBook:
#
#   (staged by `omvm macos-step`, which prints the exact command)
#
# It:
#  1. shrinks the macOS APFS container to (used + HEADROOM_GB) and creates an
#     exFAT partition VMXFER in the freed space (asks first);
#  2. restores a pristine macOS 26.4 Tahoe VM bundle with Virtualization.framework
#     (aquarat/apple-macos-arm64-vm-guest images/host/macos-restore.sh);
#  3. writes to VMXFER: the bundle (tar.gz), AVPBooter, a disk image of the
#     installed Xcode.app, host info, checksums;
#  4. reboots (back into Omarchy, since macOS was a one-time boot).
# Rerunnable: finished steps are skipped.
set -euo pipefail

REPO=https://github.com/aquarat/apple-macos-arm64-vm-guest.git
REPO_COMMIT=2ec3cb8745e81c368276852b0a2a8688875e5325
WORK="${WORK:-$HOME/vmwork}"
XFER=/Volumes/VMXFER
BUNDLE=tahoe-26.4-25E246-restore
HEADROOM_GB="${HEADROOM_GB:-100}"   # free space left inside macOS after the shrink
MIN_XFER_GB=60

die() { echo; echo "ERROR: $*" >&2; echo "Nothing was rebooted. Take a photo of this and keep it for troubleshooting." >&2; exit 1; }
say() { echo; echo "== $*"; }
test "$(uname -s)" = Darwin || die "run this from macOS"
test "$(uname -m)" = arm64 || die "needs Apple Silicon"
PY=/usr/bin/python3

say "macOS host: $(sw_vers -productVersion) ($(sw_vers -buildVersion))"
xcode-select -p >/dev/null 2>&1 || die "Command Line Tools missing: run 'xcode-select --install', then rerun"
"$PY" -c 'import plistlib' 2>/dev/null || die "python3 not usable; run 'xcode-select --install'"

say "sudo (password once; kept alive while this runs)"
sudo -v
while true; do sudo -n true; sleep 50; kill -0 "$$" 2>/dev/null || exit; done 2>/dev/null &

# ---------- 1. shared exFAT partition ----------
if ! test -d "$XFER"; then
    info="$(diskutil info -plist / )"
    container="$(printf '%s' "$info" | "$PY" -c 'import plistlib,sys;print(plistlib.loads(sys.stdin.buffer.read())["APFSContainerReference"])')"
    store="$(printf '%s' "$info" | "$PY" -c 'import plistlib,sys;d=plistlib.loads(sys.stdin.buffer.read());print(d["APFSPhysicalStores"][0]["APFSPhysicalStore"])')"
    read -r ceiling free < <(diskutil apfs list -plist | "$PY" -c '
import plistlib,sys
d=plistlib.loads(sys.stdin.buffer.read())
c=[c for c in d["Containers"] if c["ContainerReference"]==sys.argv[1]][0]
print(c["CapacityCeiling"], c["CapacityFree"])' "$container")
    gb=1000000000
    used_gb=$(( (ceiling - free) / gb ))
    total_gb=$(( ceiling / gb ))
    target_gb=$(( ( (used_gb + HEADROOM_GB) / 10 + 1 ) * 10 ))
    xfer_gb=$(( total_gb - target_gb ))
    echo "macOS container $container on $store: ${total_gb} GB total, ${used_gb} GB used"
    echo "plan: shrink macOS to ${target_gb} GB (${HEADROOM_GB} GB+ free inside), new exFAT VMXFER ≈ ${xfer_gb} GB"
    (( xfer_gb >= MIN_XFER_GB )) || die "only ${xfer_gb} GB would be freed; delete some files in macOS (or rerun with HEADROOM_GB=70)"
    case "$store" in disk0s*) ;; *) die "unexpected physical store $store (expected disk0sN)";; esac
    read -r -p "Shrink macOS to ${target_gb} GB and create VMXFER? Your files are kept. [y/N] " a
    case "$a" in y|Y|yes) ;; *) die "cancelled";; esac
    sudo diskutil apfs resizeContainer "$store" "${target_gb}g" ExFAT VMXFER 0 || die "resizeContainer failed"
    sleep 3
    test -d "$XFER" || diskutil mount VMXFER || die "VMXFER not mounted after resize"
else
    echo "VMXFER already exists; skipping the shrink"
fi
df -h "$XFER" | tail -1

# ---------- 2. restore the VM bundle ----------
free_gb=$(df -g "$HOME" | awk 'NR==2{print $4}')
say "free inside macOS: ${free_gb} GB (restore needs ~60)"
mkdir -p "$WORK"
test -d "$WORK/repo/.git" || git clone -q "$REPO" "$WORK/repo"
git -C "$WORK/repo" fetch -q origin
git -C "$WORK/repo" checkout -q "$REPO_COMMIT"
if ! test -f "$WORK/$BUNDLE/MANIFEST.sha256"; then
    (( free_gb >= 60 )) || die "need ~60 GB free inside macOS for the IPSW and restore"
    say "restoring macOS 26.4 VM (downloads ~18 GB from Apple, then restores; ~30-60 min)"
    "$WORK/repo/images/host/macos-restore.sh" tahoe "$WORK" || die "restore failed"
else
    echo "bundle already restored; skipping"
fi
ls "$WORK/$BUNDLE"/extras/

# ---------- 3. copy to VMXFER ----------
say "AVPBooter on this Mac: $(cd "$WORK/$BUNDLE/extras" && ls AVPBooter.vmapple2.*.bin)"
cp "$WORK/$BUNDLE"/extras/AVPBooter.vmapple2.*.bin "$XFER/"
sw_vers > "$XFER/host-sw_vers.txt"
system_profiler SPHardwareDataType > "$XFER/host-hardware.txt" 2>/dev/null || true

if ! test -f "$XFER/$BUNDLE.tar.gz.done"; then
    say "packing VM bundle to VMXFER (mostly-empty 160 GB disk compresses to ~25 GB; ~10-20 min)"
    rm -f "$XFER/$BUNDLE.tar.gz"
    ( cd "$WORK" && COPYFILE_DISABLE=1 tar --no-mac-metadata --no-xattrs --format pax -czf "$XFER/$BUNDLE.tar.gz" "$BUNDLE" ) || die "packing bundle failed"
    touch "$XFER/$BUNDLE.tar.gz.done"
fi

xcode="$(ls -d /Applications/Xcode*.app 2>/dev/null | head -1 || true)"
if test -n "$xcode"; then
    xver="$(/usr/libexec/PlistBuddy -c 'Print CFBundleShortVersionString' "$xcode/Contents/Info.plist")"
    xbuild="$(/usr/libexec/PlistBuddy -c 'Print ProductBuildVersion' "$xcode/Contents/version.plist" 2>/dev/null || echo '?')"
    echo "$xcode $xver ($xbuild)" > "$XFER/xcode-version.txt"
    say "found $xcode, version $xver ($xbuild)"
    case "$xver" in 26.*) ;; *) echo "WARNING: Xcode $xver may not run on a macOS 26.4 guest (want Xcode 26.x); copying anyway";; esac
    if ! test -f "$XFER/Xcode.dmg.done"; then
        say "making a disk image of Xcode.app on VMXFER (keeps code signatures intact; ~10-25 min)"
        rm -f "$XFER/Xcode.dmg"
        sudo hdiutil create -quiet -srcfolder "$xcode" -volname Xcode -format ULFO "$XFER/Xcode.dmg" || die "hdiutil create failed"
        touch "$XFER/Xcode.dmg.done"
    fi
else
    echo "NOTE: no /Applications/Xcode*.app found; Xcode will need a .xip later" | tee "$XFER/xcode-version.txt"
fi

say "checksums"
( cd "$XFER" && shasum -a 256 "$BUNDLE.tar.gz" AVPBooter.vmapple2.*.bin $(test -f Xcode.dmg && echo Xcode.dmg) > vmxfer.sha256 ) || die "checksum failed"
cat "$XFER/vmxfer.sha256"
ls -lh "$XFER"
diskutil unmount VMXFER >/dev/null 2>&1 || true

echo
echo "ALL DONE. Rebooting back into Omarchy in 30 seconds (Ctrl-C to stay in macOS)."
echo "In the Limine menu pick 'linux-aurora-vmapple', then run: omvm ingest && omvm setup --xcode"
sleep 30
sudo shutdown -r now
