#!/bin/bash
# SPDX-License-Identifier: GPL-2.0-or-later
# Build an iOS app in the macOS guest, sign it, install it on the passed-through
# iPhone and launch it. Runs IN the guest (omvm ssh macos ...). See docs/xcode-device.md.
#
#   ios-run-on-device.sh PROJECT.xcodeproj SCHEME [DEVICE]
#
# DEVICE defaults to the first connected physical iOS device (devicectl).
# Signing, first that works:
#   1. Xcode automatic signing (xcodebuild -allowProvisioningUpdates). With
#      ASC_KEY_PATH/ASC_KEY_ID/ASC_ISSUER_ID set it passes an App Store Connect API
#      key, so Xcode can create the certificate/profile and register the device
#      without an Apple Account sign-in (impossible in this VM: no anisette).
#   2. Unsigned build + codesign with a local "Apple Development" identity and a
#      matching provisioning profile in ~/Library/Developer/Xcode/UserData/
#      Provisioning Profiles (an explicit one for the bundle id, else the team
#      wildcard "iOS Team Provisioning Profile: *").
# TEAM (default: from the profile) and LOGIN_PW (keychain unlock, default "password")
# can be overridden in the environment.
set -euo pipefail

proj=${1:?usage: ios-run-on-device.sh PROJECT.xcodeproj SCHEME [DEVICE]}
scheme=${2:?usage: ios-run-on-device.sh PROJECT.xcodeproj SCHEME [DEVICE]}
dev=${3:-}
dd=${DERIVED_DATA:-$HOME/dev/dd-$scheme}
profdir="$HOME/Library/Developer/Xcode/UserData/Provisioning Profiles"
tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT

if [ -z "$dev" ]; then
  xcrun devicectl list devices --json-output "$tmp/devs.json" >/dev/null
  dev=$(plutil -extract result.devices json -o - "$tmp/devs.json" | python3 -c '
import json, sys
for d in json.load(sys.stdin):
    hp, cp = d.get("hardwareProperties", {}), d.get("connectionProperties", {})
    if hp.get("reality") == "physical" and hp.get("platform") == "iOS" and cp.get("tunnelState") == "connected":
        print(hp["udid"]); break')
fi
[ -n "$dev" ] || { echo "no connected iOS device (omvm usb attach iphone on the host?)" >&2; exit 1; }
echo "device: $dev"

security unlock-keychain -p "${LOGIN_PW:-password}" "$HOME/Library/Keychains/login.keychain-db" 2>/dev/null || true

app=""
asc=()
if [ -n "${ASC_KEY_PATH:-}" ]; then
  asc=(-authenticationKeyPath "$ASC_KEY_PATH" -authenticationKeyID "$ASC_KEY_ID" -authenticationKeyIssuerID "$ASC_ISSUER_ID")
fi
team_arg=()
[ -n "${TEAM:-}" ] && team_arg=(DEVELOPMENT_TEAM="$TEAM")

echo "== 1. xcodebuild, automatic signing"
if xcodebuild -project "$proj" -scheme "$scheme" -configuration Debug \
     -destination "id=$dev" -derivedDataPath "$dd" ${team_arg[@]+"${team_arg[@]}"} \
     -allowProvisioningUpdates -allowProvisioningDeviceRegistration ${asc[@]+"${asc[@]}"} \
     build >"$tmp/auto.log" 2>&1; then
  app=$(ls -d "$dd"/Build/Products/Debug-iphoneos/*.app | head -1)
else
  grep -E "error:" "$tmp/auto.log" | sort -u | head -5
  echo "== 2. unsigned build + codesign with a local identity and profile"
  xcodebuild -project "$proj" -scheme "$scheme" -configuration Debug \
    -destination "generic/platform=iOS" -derivedDataPath "$dd" \
    CODE_SIGNING_ALLOWED=NO build >"$tmp/unsigned.log" 2>&1 \
    || { tail -20 "$tmp/unsigned.log"; exit 1; }
  app=$(ls -d "$dd"/Build/Products/Debug-iphoneos/*.app | head -1)
  bid=$(/usr/libexec/PlistBuddy -c 'Print :CFBundleIdentifier' "$app/Info.plist")
  # pick a profile: explicit app id first, then the team wildcard; must list $dev
  # and contain a certificate we hold the private key for
  ids=$(security find-identity -p codesigning | awk '/Apple Development/ {print $2}')
  [ -n "$ids" ] || { echo "no 'Apple Development' identity in the keychain (import the .p12 first)" >&2; exit 1; }
  best=""; best_rank=9; sign_id=""
  for p in "$profdir"/*.mobileprovision; do
    [ -e "$p" ] || continue
    security cms -D -i "$p" >"$tmp/p.plist" 2>/dev/null || continue
    grep -q "$dev" "$tmp/p.plist" || continue
    appid=$(/usr/libexec/PlistBuddy -c 'Print :Entitlements:application-identifier' "$tmp/p.plist")
    teamid=${appid%%.*}; pat=${appid#*.}
    if [ "$pat" = "$bid" ]; then rank=0; elif [ "$pat" = "*" ]; then rank=1; else continue; fi
    i=0
    while /usr/libexec/PlistBuddy -c "Print :DeveloperCertificates:$i" "$tmp/p.plist" >"$tmp/c.der" 2>/dev/null; do
      sha=$(openssl x509 -inform der -in "$tmp/c.der" -noout -fingerprint -sha1 | sed 's/.*=//; s/://g')
      if echo "$ids" | grep -qi "$sha" && [ "$rank" -lt "$best_rank" ]; then
        best=$p; best_rank=$rank; sign_id=$sha; team=$teamid
      fi
      i=$((i + 1))
    done
  done
  [ -n "$best" ] || { echo "no provisioning profile for $bid that lists $dev and matches a local identity" >&2; exit 1; }
  echo "profile: $(security cms -D -i "$best" | plutil -extract Name raw -o - -)"
  security cms -D -i "$best" >"$tmp/p.plist"
  plutil -extract Entitlements xml1 -o "$tmp/ent.plist" "$tmp/p.plist"
  plutil -replace application-identifier -string "$team.$bid" "$tmp/ent.plist"
  plutil -replace keychain-access-groups -json "[\"$team.$bid\"]" "$tmp/ent.plist" 2>/dev/null || true
  cp "$best" "$app/embedded.mobileprovision"
  find "$app" -depth \( -name '*.framework' -o -name '*.dylib' -o -name '*.appex' \) \
    -exec codesign -f -s "$sign_id" {} \;
  codesign -f -s "$sign_id" --entitlements "$tmp/ent.plist" --generate-entitlement-der "$app"
fi

codesign -dvv "$app" 2>&1 | grep -E "^(Identifier|Authority=Apple Development|TeamIdentifier)"
echo "== install"
xcrun devicectl device install app --device "$dev" "$app" | tail -3
bid=$(/usr/libexec/PlistBuddy -c 'Print :CFBundleIdentifier' "$app/Info.plist")
echo "== launch $bid"
xcrun devicectl device process launch --device "$dev" --terminate-existing "$bid" | tail -2
