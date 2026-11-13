# Independent service-test VM

## Scope and current phase — 2026-11-13

The retained `kentra` guest is the owner's development VM. The resumed service
goal uses a newly restored `omvm-lab` with its own factory machine identifier,
native default serial, network address, disk/auxiliary storage and managed
FairPlay checkpoint. Do not copy kentra's signed-in disk, account or identifier.

The official macOS 27.3 beta (26C5035r) IPSW download is in progress. No lab
domain or guest boot is yet established. The prior 27.3 in-place attempt in
what is now kentra returned to 27.2.1; it did not test APNs on the beta.
A direct fresh restore avoids that handoff, but compatibility with the current
Linux QEMU/27-era AVPBooter remains unverified. Preserve separate failed lab
artifacts if boot fails; do not change kentra's firmware or disks to compensate.

Initial restore may use native Virtualization.framework. Restore completion
must leave the new VM stopped, with no native Setup Assistant/account boot.
Guest execution, SEP signing and FairPlay use the Linux host after transfer.
This does not establish a Linux-only blank-disk installation pipeline.

## Gates before account sign-in

1. Check both hosts' capacity and power. Verify the new restore's ECID, serial
   and network address differ from kentra. Validate the stopped sparse transfer,
   full auxiliary storage, trimmed flash and profile as one matching set.
2. Define a separate session-libvirt domain with normal boot and its own paths.
   Keep kentra's saved launcher defaults and both guests' watchdog/autostart off.
3. Coordinate a clean kentra shutdown before the lab boots. The current provider
   allows one active guest even when there is enough RAM for both.
4. Complete stock local Setup Assistant, skipping Apple Account. Read the
   actual IOPlatformUUID through guest SSH. The name-derived libvirt UUID is
   not an established substitute for that FairPlay identifier.
5. With all guests stopped and their VM locks held, retain matched offline
   guest/helper backups before updating the managed manifest. The reviewed
   installer requires existing managed services stopped for a manifest change.
   Preserve the original fresh-v22 rollback helper and pinned UID1 provider.
6. Enroll the lab once with its own identifier and empty checkpoint. Never use
   enrollment to repair an existing or uncertain checkpoint. Attach only its
   own managed socket and cold-boot through the existing readiness hook.
7. Confirm unchanged guest identity, correct OS/build and clock, BAA certificate
   acquisition and production APNs connection. Capture bounded sanitized logs;
   preserve templates/codes rather than raw account or authentication payloads.

## Service and recovery acceptance

The earlier Messages failure occurs at CryptoTokenKit system-keychain key
generation (`e00002e2`, wrapped as `-25308`), before the push certificate and
token. A fresh lab or READY helper alone is not a repair. See [messages.md](messages.md).

After push works, verify Apple Account authentication, Messages activation and
an owner-authorized send/receive test as separate milestones. Contact Key
Verification follows Messages and its account/iCloud Keychain prerequisites.
Do not reset account devices, encrypted data or keychains speculatively.
The owner's separate Passwords/Keychain-sync investigation remains deferred.

Finally, retain paired backups and notify the owner's HC omarchy pane before a
normal Linux reboot. The shared host/provider reboot affects kentra too. Check
helper startup and real authenticated guest access after boot, then verify
kentra remains usable. Do not unload/reset the pinned provider or use kexec.
