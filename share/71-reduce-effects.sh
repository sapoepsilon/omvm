#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-2.0-or-later
# omvm guest layer: fewer effects the paravirtual GPU (Reims) cannot draw.
# Runs inside the guest as the admin user (piped by bake-golden.sh), after 70-desktop.
#
# Tahoe's Liquid Glass, translucent Dock/menu bar and the video (Aerial)
# wallpaper are drawn with Metal features Reims does not translate yet (blur
# and backdrop passes, two-plane YUV textures). With them off the Dock is an
# opaque bar instead of red/blue blocks, and the empty wallpaper is black.
#
# com.apple.universalaccess (reduceTransparency, ...) is TCC-protected and
# cannot be written over SSH ("Could not write domain"), even by root, with
# SIP on. com.apple.Accessibility holds the same switches and is writable;
# they take effect at the next login.
main() {
    set -euo pipefail
    # Metal error mode 5 (= MTL_ERROR_MODE=nslog): Metal logs a validation failure
    # and goes on instead of aborting. Without it iconservicesagent crashes in a
    # loop on Reims (DiagnosticReports fill with iconservicesagent-*.ips) and app
    # icons never arrive. Every process reads it from its next launch (upstream
    # steelbrain/reims-vgpu README, guest step 3).
    sudo -n defaults write /Library/Preferences/.GlobalPreferences METAL_ERROR_MODE -int 5
    sudo -n chmod 644 /Library/Preferences/.GlobalPreferences.plist
    # Reduce Transparency, Reduce Motion, Increase Contrast.
    defaults write com.apple.Accessibility EnhancedBackgroundContrastEnabled -bool true
    defaults write com.apple.Accessibility ReduceMotionEnabled -bool true
    defaults write com.apple.Accessibility DarkenSystemColors -bool true
    # Dark mode: the undrawn wallpaper is black, so dark windows/menus read on it.
    defaults write -g AppleInterfaceStyle Dark
    # No widgets or click-wallpaper-to-reveal on the desktop (glass widgets misdraw).
    defaults write com.apple.WindowManager StandardHideWidgets -bool true
    defaults write com.apple.WindowManager StageManagerHideWidgets -bool true
    defaults write com.apple.WindowManager EnableStandardClickToShowDesktop -bool false
    # Dock: no magnification, no launch bounce, quick show.
    defaults write com.apple.dock magnification -bool false
    defaults write com.apple.dock launchanim -bool false
    defaults write com.apple.dock mineffect -string scale
    # Fewer window animations.
    defaults write -g NSAutomaticWindowAnimationsEnabled -bool false
    defaults write -g NSWindowResizeTime -float 0.001
    # Static solid wallpaper instead of the Aerial video (YUV video frames do not draw).
    python3 - <<'PY'
import os, plistlib
p = os.path.expanduser("~/Library/Application Support/com.apple.wallpaper/Store/Index.plist")
url = "file:///System/Library/Desktop%20Pictures/Solid%20Colors/Black.png"
choice = {"Configuration": plistlib.dumps({"type": "imageFile", "url": {"relative": url}}, fmt=plistlib.FMT_BINARY),
          "Files": [{"relative": url}], "Provider": "com.apple.wallpaper.choice.image"}
import datetime
now = datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None, microsecond=0)
linked = {"Type": "linked", "Linked": {"Content": {"Choices": [choice], "EncodedOptionValues": "$null", "Shuffle": "$null"},
                                       "LastSet": now, "LastUse": now}}
d = plistlib.load(open(p, "rb")) if os.path.exists(p) else {"Displays": {}, "Spaces": {}}
for k in ("AllSpacesAndDisplays", "SystemDefault"):
    d[k] = linked
os.makedirs(os.path.dirname(p), exist_ok=True)
plistlib.dump(d, open(p, "wb"), fmt=plistlib.FMT_BINARY)
PY
    echo "+ omvm 71-reduce-effects: METAL_ERROR_MODE=5, reduce transparency/motion, contrast, dark, no widgets, solid wallpaper" |
        sudo -n tee -a /etc/vmapple-image-version >/dev/null
    echo "layer 71-reduce-effects complete"
}
main "$@" < /dev/null
