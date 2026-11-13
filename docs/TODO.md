# TODO

## P1: Start Linux Apple Account helpers automatically

Requested 2026-11-12 after a new factory-restored VM completed Apple Account
sign-in using the Linux SEP and FairPlay providers. The owner wants launching a
VM to handle the helper setup automatically, including from the Omarchy GUI.
Status (2026-11-13): implemented and installed for macos-fresh. Managed helper
process restart plus a cold guest boot recovered authenticated Apple access.
Full Linux host reboot acceptance remains pending; see docs/apple-helpers.md.

The integration belongs in the Linux host installation and VM lifecycle. The
FairPlay adapter serves the guest through a Unix socket; it is not an account
password or a service that needs to be baked into the macOS disk image.

- [x] Package the pinned, verified adapter and provider configuration through a
  repeatable installation command. Obtain required Apple assets only from the
  owner's Mac or Apple; do not commit them or VM identities.
- [x] Order host startup: validate the supported kernel and provider ownership,
  perform the required self-test/initialization once, and require READY before
  starting dependent helpers. Never reload a provider pinned until platform reset.
- [x] Manage a persistent, isolated FairPlay service per VM, bound to that VM's
  actual stable identity. Reuse a healthy process across guest restarts. Retain
  root-private files, Unix-socket-only access and memory/CPU limits.
- [x] Make CLI, GUI, libvirt and watchdog startup paths wait for the same bounded
  SEP/FairPlay readiness check before guest authentication can begin. Keep the
  GUI a thin wrapper and report actionable errors instead of launching with a
  missing helper or falling back silently to a Mac relay.
- [x] Implement the supported identity-bound host ADI checkpoint contract and
  verify a clean helper-process restart plus cold guest/account-service recovery.
  The tested guest retains its own ADI provisioning file; its host checkpoint
  stayed valid with an absent native file. Keep Restart=no.
- [ ] Verify a normal Linux host reboot, automatic helper readiness and real
  authenticated account recovery after disk unlock. Crash-interrupted native
  mutations must continue to fail closed, without automatic state reset.
- [x] Coordinate shared hardware access. Preserve the current one-active-guest
  constraint until provider requests can be serialized safely without EBUSY.
- [ ] Add a concise status check distinguishing helper readiness, completed Apple
  Account sign-in and subsequent service errors. Never log credentials, MFA
  codes, tokens or raw authentication payloads.
- [ ] Validate a fresh-identity guest, a guest restart, a helper restart and a
  controlled Linux host restart, all without a native Mac signing/FairPlay relay.
  Verify the account overview and any recovery steps, rather than just open
  sockets or process health. Preserve the signed-in control and paired rollbacks.

Acceptance: after one-time host installation, the owner launches a supported VM
normally and enters credentials/MFA in stock macOS. Helper startup requires no
manual terminal work or native Mac service, and tested restart behavior is
documented. Native macOS factory restore remains a separate image-creation step.

## P2: Explain the stale or repeated verification prompt

- [ ] Correlate UI completion, first MFA success and follow-up service requests
  without collecting secrets. In the fresh test, secondary authentication,
  completed account authentication and primary iCloud account addition preceded
  a later IDMS check-in HTTP 401. The owner reported a second incorrect code was
  followed by dismissal and an already-signed-in account overview. This does not
  establish that the incorrect code was accepted. The exact cause of the repeated
  prompt remains unverified; avoid credential retries based only on stale UI.

## P2: Create and install a new VM entirely from Linux

Requested for feasibility assessment 2026-11-12. Status: unproven; no Linux-only
blank-disk install has been attempted. The successful fresh test used native
Virtualization.framework to restore a new VM before copying it to Linux. Local
account setup and Apple Account sign-in then occurred on Linux. The SEP/FairPlay
work proves the tested authentication path, not a replacement restore pipeline.

- [ ] Map the native restore inputs and outputs: factory hardware model, new
  machine identifier, auxiliary/NVRAM storage, disk layout, recovery boot and
  Apple personalization. Determine which steps actually require the SEP bridge.
- [ ] Download and verify the official IPSW on Linux. Establish a reproducible
  way to obtain all required Apple boot/provider assets from official downloads,
  rather than relying on a preinstalled Mac or another VM's restored disk.
- [ ] Evaluate booting Apple's recovery/restore environment with the existing
  virtual hardware and the restore protocol needed to install an empty disk.
  Physical-device DFU tools are not evidence of VM restore support.
- [ ] Validate a distinct new VM identity, full install, first boot, stock Apple
  Account sign-in and guest restart with no native macOS host step. Preserve the
  existing signed-in guests and do not mount or modify their live disks.

Acceptance: starting with Linux and official Apple downloads, create a new
personalized VM and complete installation/sign-in without a pre-restored image,
borrowed identity, or live native Mac service. Continue distinguishing this from
automatic helper startup for an already installed guest.

Sources checked: [Apple's VM installation API](https://developer.apple.com/documentation/virtualization/installing-macos-on-a-virtual-machine)
and the [current upstream KVM experiment](https://github.com/steelbrain/experiment-macOS-arm64-on-asahi-linux-arm64).
The latter uses Ambrosia boot firmware but explicitly requires an already
installed/restored guest; its boot success does not establish this install path.
