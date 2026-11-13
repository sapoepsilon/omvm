# Messages push-certificate investigation

## Current evidence — 2026-11-12

System Apple Account sign-in and owner-reported Xcode sign-in work in the
fresh macOS 27.2.1 (26B131) guest. Messages activation is a separate failure.

A bounded read-only collection at 2026-11-13 06:50 UTC identified this chain:

1. `apsd` uses the system keychain and asks CryptoTokenKit to generate a key.
2. Key generation returns `0xe00002e2` / `-536870174` (`kIOReturnNotPermitted`).
3. `SecKeyCreateRandomKey_ios` wraps this as `NSOSStatusErrorDomain -25308`
   (`errSecInteractionNotAllowed`, failed to generate a keypair).
4. The BAA identity provider cannot obtain its certificate.
5. `apsctl status` reports both production and development disconnected.
   Messages has previously logged that it is waiting for its push token.

Four repeated failures in the narrow collection have the same chain. All 24
recorded Linux FairPlay requests in the wider preceding window completed with
status zero and a written response. This does not establish successful push
attestation; the failing key-generation path is separate.

The guest reports `kern.hv_vmm_present=1` and `hw.model=VirtualMac2,1`.
The inspected `apsd` matches the guest binary by SHA256. Its BAA options builder
checks that VM sysctl; it does not establish that the guest was mistaken for
physical hardware. DeviceIdentity's software-key option defaults to enabled,
so merely adding that option is not an evidenced repair either.

No account retry, sign-out, keychain reset, certificate deletion, guest service
restart, binary patch or host reboot was performed for this investigation.
The sanitized private report contains static templates and typed error codes,
not account values, keys, tokens or authentication payloads.

## External controls and next experiment

Independent native-host reports show the same key-generation error in macOS
27 VMs, including a fresh 27.2.1 guest on a 27.2.1 macOS host. A macOS 26.6.2
control connects to APNs in those reports. This strongly suggests a guest OS
regression is relevant, but it does not exclude additional Linux integration
issues in this installation.

- [Apple Developer Forums: VM enrollment and APNs failures](https://developer.apple.com/forums/thread/840500)
- [First-hand Lume 27.2.1 reproduction](https://github.com/trycua/cua/issues/7413)
- [Parallels issue tracking](https://kb.parallels.com/en/131218)

A [first-hand community report](https://www.reddit.com/r/jamf/comments/1xikolc/macos_27_vms_has_anyone_found_a_workaround_for/)
says 27.3 beta fixes the VM push issue. Apple's
[27.3 beta release notes](https://developer.apple.com/documentation/macos-release-notes/macos-27_3-release-notes)
confirm that beta exists but do not list this fix. It is a test candidate, not
a verified solution. The current guest's normal software-update catalog
reports no new update. Preserve a complete offline rollback and the current
helper before any test of a different OS build; do not replace working
identity or keychain state speculatively.

## Beta experiment — 2026-11-13, deferred

The owner accepted the official 27.3 beta licence. The in-place installer for
26C5035r completed preparation and reported apply success at 16:26:40 UTC.
Messages blocked its initial restart. After the owner finished using the VM,
a normal guest restart at 16:43:27 UTC returned to 27.2.1/26B131. The updater
recorded a target/current boot-manifest mismatch and "Failed Backward - in
original OS after update was attempted", then cleaned staged assets. The beta
was not successfully installed and its APNs result has not been tested.

The exact missed update-boot cause is unproven. The NVRAM no-op in the log belongs
to the SFR firmware-only substage, so it is not sufficient to blame the main
handoff. The pinned QEMU source includes bdif writes; a missing write fix or
stale warm-reset state was not established. No firmware/NVRAM changes or further
installer retry were made. At the owner's request, leave the existing signed-in
VM running for development and revisit the experiment later. The paired offline
rollback remains preserved; Linux helpers were not restarted.

## Acceptance

Require a successful BAA certificate acquisition and production APNs connection,
then Messages registration and an authorized send/receive test. Test Contact
Key Verification only after Messages works, checking its iCloud Keychain and
account/device prerequisites without resetting encrypted account data. A
successful push connection alone does not complete either user-facing test.
