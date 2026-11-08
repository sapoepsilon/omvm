#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-2.0-or-later
# omvm guest layer: make the guest pleasant to use over VNC.
# Runs inside the guest as the admin user (piped by bake-golden.sh).
main() {
    set -euo pipefail
    sudo -n pmset -a displaysleep 0 sleep 0
    # Setup Assistant: mark every first-login pane as seen.
    v="$(sw_vers -productVersion)"; b="$(sw_vers -buildVersion)"
    for k in DidSeeCloudSetup DidSeePrivacy DidSeeSiriSetup DidSeeScreenTime DidSeeAppearanceSetup \
             DidSeeTouchIDSetup DidSeeAccessibility DidSeeTrueTone DidSeeActivationLock DidSeeIntelligence \
             DidSeeTermsOfAddress DidSeeLockdownMode DidSeeWallpaper DidSeeApplePaySetup DidSeeiCloudLoginForStorageServices \
             SkipFirstLoginOptimization; do
        defaults write com.apple.SetupAssistant "$k" -bool true
    done
    defaults write com.apple.SetupAssistant LastSeenCloudProductVersion "$v"
    defaults write com.apple.SetupAssistant LastSeenBuddyBuildVersion "$b"
    # Keyboard Setup Assistant: pre-identify QEMU's USB keyboard (0627:0001) as ANSI.
    sudo -n defaults write /Library/Preferences/com.apple.keyboardtype keyboardtype -dict-add "1-1575-0" -int 40
    # No crash dialogs (WindowServer restarts are expected on a paravirtual GPU).
    defaults write com.apple.CrashReporter DialogType none
    sudo -n find /Library/Logs/DiagnosticReports "$HOME/Library/Logs/DiagnosticReports" \
        -maxdepth 1 -type f \( -name '*.ips' -o -name '*.diag' -o -name '*.spin' -o -name '*.hang' \) -delete 2>/dev/null || true
    echo "+ omvm 70-desktop: no display sleep, Setup/Keyboard Assistant skipped, crash dialogs off" |
        sudo -n tee -a /etc/vmapple-image-version >/dev/null
    echo "layer 70-desktop complete"
}
main "$@" < /dev/null
