# Xcode → real iPhone from the `macos` guest

Goal: build an app in the macOS 27.2 guest (Xcode 27.2) and run it on the owner's
iPhone, passed through with `omvm usb attach iphone` (docs/usb.md). State on
2026-11-09:

| Step | Status |
|---|---|
| Device prep (pair, Developer Mode, DDI, symbols) | **done**: devicectl `connected`, DDI services `isUsable: true` (cryptex DDI), `~/Library/Developer/Xcode/iOS DeviceSupport/iPhone18,1 27.2 (24B119)` complete (6.8 GB of symbols copied over the patched xHCI) |
| Build | **done**: SwiftUI test app builds for `generic/platform=iOS` with `CODE_SIGNING_ALLOWED=NO` in ~6 s |
| Upload to the phone | **works**: `devicectl device install app` reaches `installd` on the phone, which rejects an ad-hoc signature (`0xe8008014 The executable contains an invalid signature`) |
| Sign | **blocked on the owner**: no Apple Development identity in the guest |
| Install + launch | waits on signing; scripted (`share/ios-run-on-device.sh`) |

## Apple Account sign-in in Xcode: not viable

Xcode's Settings → Accounts uses AuthKit (`akd`), which needs anisette data from
`adid`. In this VM `akd` fails anisette provisioning every minute, for every client
(949 times in 2 days in `log show`):

```
adid  A13 / A5: 4294922240
akd   ADIGetIDMSRouting failed! Error: -45061
akd   No response body for start provisioning request!
akd   Provisioning failed. No Anisette for you today! Error: Error Domain=AKAnisetteError Code=-8007
FeatureAccessAgent  Unable to get Attestation data for request <private>! Error: ... Code=-8007
```

Apple's provisioning server returns nothing to `start provisioning` (no Secure Enclave
attestation on a Linux host, same root cause as the system Apple Account in
docs/fcp.md). Xcode's sign-in goes through the same `akd`, so it fails the same way;
nothing to type in.

## Signing routes

1. **Existing identity + team wildcard profile (works today, CLI).** The owner's
   "Apple Development" certificate is on uzi's Mac, and the Xcode-managed
   "iOS Team Provisioning Profile: \*" there lists this phone's UDID and that
   certificate (valid until 2027-10-06). The profile is already copied into the
   guest (`~/Library/Developer/Xcode/UserData/Provisioning Profiles/`), and the Apple
   WWDR G3 intermediate (`AppleWWDRCAG3.cer`, SHA-256 `DC:F2:18:78:…:60:1F`) is in
   the guest login keychain (the guest only had the expired 2023 one). Missing: the
   private key. The owner exports it as a .p12 and runs a one-go script that imports
   it into the guest keychain (`security import -T /usr/bin/codesign` +
   `set-key-partition-list`) and runs `share/ios-run-on-device.sh`.
   - `xcodebuild` automatic signing finds the profile but reports `No Accounts`; if
     that is fatal, the script falls back to an unsigned build + `codesign` with the
     profile's entitlements (`application-identifier` rewritten to TEAM.bundleid)
     and `embedded.mobileprovision`. That path was tested end to end with a
     throwaway self-signed identity and profile: the app is signed, uploaded, and
     rejected by the phone only for the untrusted profile signature (`0xe8008013`).
   - Xcode's Run button cannot use this profile with manual signing: `Provisioning
     profile "iOS Team Provisioning Profile: *" is Xcode managed, but signing
     settings require a manually managed profile.`
2. **Manual development profile (Xcode Run button).** On developer.apple.com create
   an "iOS App Development" profile for the wildcard App ID `*` with the Apple
   Development certificate and the phone (already registered), download it, copy it
   into the guest's `Provisioning Profiles` folder, and set the target to manual
   signing with that profile. Then Xcode's Run works with no account.
3. **App Store Connect API key (`xcodebuild` only, no sign-in).** JWT auth, no
   anisette:
   `xcodebuild … -allowProvisioningUpdates -allowProvisioningDeviceRegistration
   -authenticationKeyPath AuthKey_ID.p8 -authenticationKeyID ID
   -authenticationKeyIssuerID ISSUER`. Checked in the guest with a random throwaway
   key: Xcode signs a JWT and calls
   `appstoreconnect.apple.com/xcbuild/…/listTeams.action`, which answers 401 for
   the fake key, so a real Admin key should let Xcode create the cloud-managed
   certificate and profiles itself. `ios-run-on-device.sh` passes the key when
   `ASC_KEY_PATH`, `ASC_KEY_ID`, `ASC_ISSUER_ID` are set. Store the values with
   `bws-save` on uzi's Mac (Touch ID): `ASC_KEY_ID`, `ASC_ISSUER_ID`,
   `bws-save ASC_KEY_P8 < AuthKey_ID.p8`.

## Recipe

```sh
# guest: device state
omvm ssh macos xcrun devicectl list devices
omvm ssh macos xcrun devicectl device info ddiServices --device UDID
# guest: build without signing (toolchain check)
omvm ssh macos 'cd ~/dev/HelloVM && xcodebuild -project HelloVM.xcodeproj -scheme HelloVM \
  -destination generic/platform=iOS CODE_SIGNING_ALLOWED=NO build'
# guest: build + sign + install + launch (needs an identity in the keychain)
omvm ssh macos 'cd ~/dev/HelloVM && ~/bin/ios-run-on-device.sh HelloVM.xcodeproj HelloVM'
```

`share/ios-run-on-device.sh` goes to the guest as `~/bin/ios-run-on-device.sh`;
`share/ios-hello/` is the test project (no team set; the guest copy in `~/dev/HelloVM`
has the team). Over ssh the login keychain is locked; the script unlocks it with the
VM's password (`LOGIN_PW`, default `password`).

Owner steps for route 1 (on uzi's Mac):

- Open Keychain Access.
- Category "My Certificates".
- Right-click "Apple Development: …".
- Export as `.p12` to Desktop (`AppleDevelopment.p12`).
- Set an export password.
- Run `bash /tmp/omvm-ios-signing.sh`.
- Type that password.

The script streams the .p12 and password over ssh stdin into the guest (nothing on
omarchy), deletes the guest copy after import, then offers to delete the local one.
After a VM restart: `omvm usb attach iphone` on omarchy before running anything.

Notes:

- Running `osascript -e 'tell application "Xcode" …'` over ssh hangs (Automation
  consent prompt in the GUI session); avoid it.
- An unentitled process cannot ask `akd` for anisette (`Peer connection was rejected
  by the listener`, NSCocoaError 4099); the failure above is from `akd`'s own
  provisioning, not from that probe.
