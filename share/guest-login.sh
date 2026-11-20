# SPDX-License-Identifier: GPL-2.0-or-later
# Guest side of omvm's automatic login. Runs INSIDE the macOS guest as the
# guest account (passwordless sudo) through `bash -s`; omvm puts two lines in
# front of this file (guest_login_script in bin/omvm):
#
#   LOGIN_USER=<account>          the account loginwindow logs in
#   KCPASSWORD_B64=<base64>       its password, kcpassword-encoded (share/kcpassword.py)
#
# It is appended to images/10-headless-clt.sh for the -v1 bake (`omvm setup`)
# and sent on its own by `omvm autologin NAME`. Idempotent. macOS's /bin/bash
# is 3.2: no bash 4 features. As in layer 10, the body runs with stdin from
# /dev/null, since bash -s reads this script from stdin as it goes.
omvm_guest_login() {
    set -euo pipefail
    local user="${LOGIN_USER:?}" kc="${KCPASSWORD_B64:?}" ver build sa k
    id -u "$user" >/dev/null || { echo "no account $user in the guest" >&2; exit 1; }

    # Automatic login: loginwindow logs autoLoginUser in with the password in
    # /etc/kcpassword (root-only, like System Settings writes it). The account
    # keeps its password, so sudo, the lock screen and the login keychain use it.
    printf '%s' "$kc" | base64 -D | sudo -n tee /etc/kcpassword >/dev/null
    sudo -n chown root:wheel /etc/kcpassword
    sudo -n chmod 600 /etc/kcpassword
    sudo -n defaults write /Library/Preferences/com.apple.loginwindow autoLoginUser -string "$user"

    # Post-login Setup Assistant panes (Apple Account, Siri, Screen Time,
    # "Update Mac Automatically", ...): mark them seen for this OS version so an
    # automatic login lands on the desktop. They come back after a macOS update
    # bumps the version; `omvm autologin NAME` writes them again.
    ver="$(sw_vers -productVersion)"
    build="$(sw_vers -buildVersion)"
    sa=com.apple.SetupAssistant
    for k in DidSeeAccessibility DidSeeActivationLock DidSeeAppStore DidSeeAppearanceSetup \
        DidSeeApplePaySetup DidSeeAvatarSetup DidSeeCloudDiagnostics DidSeeCloudSetup \
        DidSeeIntelligence DidSeeLockdownMode DidSeePrivacy DidSeeScreenTime DidSeeSiriSetup \
        DidSeeSoftwareUpdate DidSeeSyncSetup DidSeeSyncSetup2 DidSeeTermsOfAddress \
        DidSeeTouchIDSetup DidSeeTrueTonePrivacy DidSeeUpdateCompleted DidSeeWallpaper \
        DidSeeiCloudLoginForStorageServices SkipFirstLoginOptimization; do
        defaults write "$sa" "$k" -bool true
    done
    for k in LastSeenCloudProductVersion LastSeenSiriProductVersion LastSeenBuddyProductVersion \
        LastSeenDiagnosticsProductVersion LastSeenSoftwareUpdateProductVersion \
        LastPreLoginTasksPerformedVersion; do
        defaults write "$sa" "$k" -string "$ver"
    done
    for k in LastSeenBuddyBuildVersion LastPreLoginTasksPerformedBuild; do
        defaults write "$sa" "$k" -string "$build"
    done
    defaults write "$sa" LastPrivacyBundleVersion -string 2

    # The managed form of the same ("skip these panes"), which macOS 26 also
    # checks for the software-update pane. Without MDM this is best effort:
    # cfprefsd reads /Library/Managed Preferences, but a later profile sync may
    # clear it; the per-user keys above do not depend on it.
    local skip="Accessibility Appearance AppleID AppStore Biometric DeviceToDeviceMigration
        Diagnostics EnableLockdownMode FileVault iCloudDiagnostics iCloudStorage Intelligence
        Location LockdownMode Payment Privacy Restore ScreenSaver ScreenTime Siri SoftwareUpdate
        TermsOfAddress TOS TouchIDSetup UpdateCompleted Wallpaper Welcome"
    local mp="/Library/Managed Preferences" f
    sudo -n mkdir -p "$mp/$user"
    for f in "$mp/$sa.managed" "$mp/$user/$sa.managed"; do
        # shellcheck disable=SC2086  # one array element per word
        sudo -n defaults write "$f" SkipSetupItems -array $skip
        sudo -n defaults write "$f" SkipCloudSetup -bool true
        sudo -n defaults write "$f" SkipSiriSetup -bool true
        sudo -n defaults write "$f" SkipPrivacySetup -bool true
        sudo -n chmod 644 "$f.plist"
    done

    # Answer the "Update Mac Automatically" question for it: this guest is
    # pinned to the restore image omvm made it from, so macOS installs no
    # updates by itself (layer 10 sets the same keys for Ventura guests).
    for k in AutomaticallyInstallMacOSUpdates AutomaticDownload; do
        sudo -n defaults write /Library/Preferences/com.apple.SoftwareUpdate "$k" -bool false
    done

    echo "automatic login: $user (Setup Assistant panes for macOS $ver $build marked seen)"
}
omvm_guest_login < /dev/null
