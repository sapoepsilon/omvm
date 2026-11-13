# Independent service-test VM

## Scope and current phase — 2026-11-13

Latest owner clarification: **turn off kentra and turn on omvm-lab**. The clean
guest switch completed at 21:08 UTC: kentra cleanly shut off, lab running with
pinned SSH on 27.3/26C5035r and its native XWayland Reims window mapped.
Kentra contents, account, configuration and helper state remain protected. The source/skill handoff is complete. A dedicated visible GPT-6.1 Terra native
operator now works; local desktop login completed at 21:33:26 UTC. The private
`omvm-apple-services` skill records the acceptance ledger and verified
Mac-source import. Historical setup steps below are completed work, not a
request to repeat enrollment or execute archived slot-switch scripts.

The retained `kentra` guest is the owner's development VM. The resumed service
goal uses a newly restored `omvm-lab` with its own factory machine identifier,
native default serial, network address, disk/auxiliary storage and managed
FairPlay checkpoint. Do not copy kentra's signed-in disk, account or identifier.

The official macOS 27.3 beta (26C5035r) fresh restore completed on the native
Mac and stopped without a Setup Assistant boot. Its sparse disk/full auxiliary
storage/profile transfer passed verification. The 4 CPU/8 GiB lab then booted
on Omarchy with the existing pinned QEMU and 27.2-era AVPBooter. Stock local
Setup Assistant completed with Apple Account skipped. Pinned SSH verified the
actual build, completed setup, sub-second clock agreement and a guest
IOPlatformUUID distinct from kentra. On the next coordinated maintenance slot,
its own empty, UUID-bound FairPlay state was enrolled once. The on-demand
per-VM startup policy was installed, and the lab cold-booted through the normal
libvirt gate with unchanged actual UUID and sub-second clock agreement.

The first Linux boot successfully acquired two BAA certificates and signed a
nonce with the host VM identity. Production APNs reported connected, and
identityservicesd logged received push tokens. The bounded first-boot report
recorded no BAA failure. This is evidence that the earlier push-certificate
hurdle is cleared in this fresh 27.3 lab; Apple Account, Messages activation,
send/receive and Contact Key Verification remain untested here. Private,
sanitized evidence is retained under the lab's evidence/first-boot-20261113.

A new owner-authorized maintenance slot began after the development pane's
explicit release. Both guests were cleanly stopped; matched offline guest
backups, public SEP artifacts and a quiesced kentra helper checkpoint were
saved before enrollment. Kentra's checkpoint remained byte-identical after
its managed helper restarted. The original v22 rollback helper, shared SEP
service and pinned UID1 provider were preserved. This maintenance slot has
ended: the lab is cleanly stopped with its native X11 configuration retained,
and kentra restarted normally on unchanged27.2.1/26B131 with pinned SSH
verified again after the return worker exited. Both VM locks were released
and the development pane was notified. Native Sol control awaits the remote
CLI MCP session permission. A later lab slot must be coordinated anew.

The earlier return at 19:44 UTC reached SSH but shut down ten seconds later for
an undetermined reason. A normal restart was verified repeatedly and handed
back before this separately authorized slot. Do not infer a crash or attribute
that shutdown to a user or process without additional evidence.

Initial restore may use native Virtualization.framework. Restore completion
must leave the new VM stopped, with no native Setup Assistant/account boot.
Guest execution, SEP signing and FairPlay use the Linux host after transfer.
This does not establish a Linux-only blank-disk installation pipeline.

## Historical setup gates — completed, not a repeat checklist

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

## Current native control path

The owner explicitly requested OMVM’s native VM window instead of a VNC relay.
The lab was cleanly stopped, its current XML backed up, and only display
configuration restored to native Reims at 3024x1964@254. The managed helper,
actual identity and disks were preserved. Normal native boot reached pinned
SSH on 27.3/26C5035r. Live compositor inventory confirmed that this window
was Wayland. A separate Mesa build now supplies X11 plus Wayland WSI from
the same hash-verified patched source, leaving existing driver installations
unchanged. A clean lab restart with only its driver prefix, SDL3 X11 backend
and existing DISPLAY changed reached pinned SSH again; the compositor now
confirms an XWayland Reims window owned by the lab QEMU. The previous Wayland
XML is retained for display-only rollback. Kentra configuration is unchanged.

The dedicated Linux GPT-6.1 Terra CLI uses the installed public computer-only
CUA launcher and actual graphical-session environment. Its first custom launch
omitted the installed trusted-module path; matching the app-managed trusted
path resolved discovery without changing package code or access checks.
Screenshots, click/type/clear input, and a single local-login submission are
verified. Independent pinned SSH confirmed the console user and Finder/Dock.
The owner requested per-invocation --yolo and a visible terminal beside the VM
on workspace 5. Global approval settings remain unchanged. This supersedes
the earlier Sol permission wait and this chat's unavailable native surface.
Do not reopen Moonlight or VNC unless the owner changes this preference.

The temporary noVNC service, browser session and three SSH forwards are closed.
VNC testing established local login, but physical and textarea input lost
shifted characters. The built-in Accessibility Keyboard produced exact
nonsecret A@2.Z through mouse clicks; it remains enabled in the lab. No Apple
Account password was submitted during that retired VNC test. At 21:39:01 UTC,
Terra opened the empty stock Apple Account form. The owner subsequently
confirmed the lab account for sign-in; its password is held in the OS keyring
and a single private native-input attempt reached the trusted-device code
prompt at 21:44:28 UTC. Guest akd recorded successful SRP at 21:43:59 UTC.
The owner was asked to enter MFA directly; no code or retry has been submitted.
The first secondary-auth exchange completed before the later incorrect-code
alert. Correlated logs subsequently show account authenticated=true with
HTTP200, primary account addition at21:54:01UTC, and native signed-in overview
at22:03:09UTC. CDP encrypted-data recovery failed separately after finding no
escrow records; iCloud settings remained Loading at that observation. The owner added reliable
first-attempt sign-in as a requirement; explain/fix the extra prompts and prove
a clean flow rather than accepting a resend workaround.

Later2026-11-13 evidence: IDS com.apple.madrid registration and callback
succeeded at22:14:57UTC. The owner subsequently confirmed an outgoing send
worked and a fresh reply arrived inside the lab. This is an owner-observed
end-to-end messaging result; native screenshots have not independently shown
both delivery bubbles. Keychain trust, Contact Key Verification, reliable
first-attempt sign-in and post-host-reboot service recovery remain incomplete.

Native supervision now reviews actual screenshots/actions every3–5minutes.
Intermittent black/stale captures remain unresolved. A bounded diagnostic
recorded left-button down/up at QEMU; all input traces were restored disabled.
One local unlock succeeded at22:52UTC after correcting a private handoff schema
and allowing verified focus restoration within the same task. Two earlier
handoffs submitted no password. Read-only console state and a fresh desktop
image corroborate unlock; private input was deleted. No Apple reauthentication
or account reset was performed. A temporary display-awake assertion expires
automatically; persistent lock preferences are unchanged.

The trust failure predates the final local-password prompt: secure-channel
initialization fell back at21:49:39UTC, no viable recovery records appeared
at21:50:18UTC, then local-password approval began at21:50:55UTC. Later
noPreparedIdentity appears during device-name lookup and is not proof of a
failed identity-generation operation. A CloudKit cache sandbox denial is
confirmed, but later fetches succeed; do not repair Unix permissions or reset
encrypted data speculatively. Inspect normal trusted-device approval next.

## VNC route tested, then retired

The temporary lab test used QEMU's remote-display mode with VNC bound to
127.0.0.1:5991 and WebSocket VNC to 127.0.0.1:5992. Its own native-display XML
was preserved first; the conversion retained its identity, disks and Linux SEP
attachment. The later enrollment added only its own managed FairPlay socket.
Watchdog/autostart remain off and kentra's domain/defaults remain unchanged.

The custom QEMU bundle's keyboard maps were broken symlinks into an absent
build directory. The original directory was preserved, and regular maps from
the existing QEMU source were copied with a verified SHA256 manifest into the
existing data path. No QEMU binary or Apple firmware changed.

Official noVNC v1.6.0 (a8dfd6a3ea3c74244f5ebdaa5a7f1023007a7820) was served by a
transient user service on loopback 6088, with SSH forwards to loopback-only
operator endpoints. The service and forwards are now stopped. A separate GPT-6.1
Sol task uses the existing headless agent-browser CLI; its browser launch,
screenshot path and live lab desktop were verified. Local omvmlab login
completed through the VNC browser. The desktop-app
CUA browser host was unavailable, so its configuration and policies were left
unchanged. The VNC route is verified. After the helper-backed
cold boot,
production APNs connected again; current-boot logs recorded two BAA certificate
successes, one host VM nonce signature and zero BAA failures. Sanitized evidence
is retained under evidence/after-helpers-20261113.
No Moonlight or owner desktop takeover is required for this route.

QEMU's WebSocket endpoint accepts path `/`; noVNC's default `/websockify`
returns HTTP 404 here. Use `path=.` in the noVNC 1.6 client URL: its UI
prepends `./`, so entering `/` produces `//` rather than the required `/`.
Transport checks verified HTTP 101 at `/` and the RFB 3.8 banner through SSH.
