# TODO

## P1: Start Linux Apple Account helpers automatically

Requested 2026-11-12 after a new factory-restored VM completed Apple Account
sign-in using the Linux SEP and FairPlay providers. The owner wants launching a
VM to handle the helper setup automatically, including from the Omarchy GUI.
Status: planned; the current experimental FairPlay services are manually staged.

The integration belongs in the Linux host installation and VM lifecycle. The
FairPlay adapter serves the guest through a Unix socket; it is not an account
password or a service that needs to be baked into the macOS disk image.

- [ ] Package the pinned, verified adapter and provider configuration through a
  repeatable installation command. Obtain required Apple assets only from the
  owner's Mac or Apple; do not commit them or VM identities.
- [ ] Order host startup: validate the supported kernel and provider ownership,
  perform the required self-test/initialization once, and require READY before
  starting dependent helpers. Never reload a provider pinned until platform reset.
- [ ] Manage a persistent, isolated FairPlay service per VM, bound to that VM's
  actual stable identity. Reuse a healthy process across guest restarts. Retain
  root-private files, Unix-socket-only access and memory/CPU limits.
- [ ] Make CLI, GUI, libvirt and watchdog startup paths wait for the same bounded
  SEP/FairPlay readiness check before guest authentication can begin. Keep the
  GUI a thin wrapper and report actionable errors instead of launching with a
  missing helper or falling back silently to a Mac relay.
- [ ] Resolve helper state lifetime across process/host restart using the actual
  backend contract, then verify account recovery. Current in-memory state must
  not be treated as durable; blindly enabling service auto-restart is insufficient.
- [ ] Coordinate shared hardware access. Preserve the current one-active-guest
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
