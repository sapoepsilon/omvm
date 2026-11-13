# Linux Apple Account helper lifecycle

The host needs its existing SEP identity signer, the pinned UID1 provider and
one persistent FairPlay service for each enrolled VM. A guest launch waits for
these services through libvirt's `prepare/begin` hook. The GUI and CLI therefore
use the same readiness gate, as do direct `virsh start` and the watchdog.
This integration does not turn on guest autostart or change its display.

## Retained development VM (2026-11-13)

The owner retained `macos-fresh` as **`kentra`** and retired the other four
Omarchy guests. The guest directory is now `~/vm-artifacts/vms/kentra`, with
the same disks, Apple/platform identity, libvirt UUID and SSH port 41375.
It remains on macOS 27.2.1/26B131 with Xcode 27.2/27B52; the beta attempt
returned to the original OS and further upgrade work is deferred.

The managed instance is `omvm-fairplay@kentra.service`; its state lives under
`/var/lib/omvm/apple-helpers/vms/kentra` and its socket is
`/run/omvm-fairplay-managed-kentra/relay.sock`. The manifest key and staged
identifier path were renamed together, preserving all identifier/checkpoint
bytes. No enrollment, new identity, provider reset or host reboot occurred.
An offline matched guest backup and private helper checkpoint precede the rename.
The restarted VM reached SSH, Xcode reported its version, and the native desktop
still showed the signed-in Apple Account. A new authenticated server request was
not separately tested during this rename.

Guest watchdog/autostart remain disabled. Saved `OMVM_VM=kentra` in
`~/.config/omvm/gui.env` selects it for the CLI and GUI even when stopped;
`OMAC_VM=kentra` and `OMAC_SOURCE=kentra` point application commands at the
retained guest. Explicit environment variables override these saved defaults.
The separate UTM VM named kentra on another Mac is unrelated.

Keep `/var/lib/omvm/identity/macos/`: despite its old basename, the active
shared SEP signer still uses its public key. Keep the shared QEMU data,
firmware, provider/cache assets and fresh restore provenance. The original
fresh-v22 rollback helper retains its historical `macos-fresh` instance name;
the old macos27-v22 helper has been retired.

## Observed recovery (2026-11-13)

The three persistent units were installed and enabled for `macos-fresh`
(now `kentra`). A clean
managed-helper stop/start followed by a cold guest boot preserved the guest UUID
and its native ADI provisioning file. The new helper serviced fresh queue-0/3
requests. After local login, the account overview remained signed in; stock akd
completed fresh SRP at 07:44:45 UTC, and AppleIDSettings accepted an authenticated,
uncached HTTP 200 device-list response at 07:45:40 UTC. No Apple password or MFA
was entered for this recovery test.

The host checkpoint remained a valid 64-byte envelope representing an absent
emulated native file. The guest has its own provisioning file; host checkpoint
growth is not a universal acceptance criterion. This test proves the observed
clean process-restart/account-service path, not every Apple service, interrupted
native-state recovery, or full host boot ordering. Other account-context errors,
iMessage/APNs and Contact Key Verification remain unresolved.

A matched offline VM snapshot and quiesced root-private helper checkpoint were
retained before the restart. The original fresh-v22 helper remains alive for rollback; the retired
macos27 control no longer runs.
Full Linux host reboot remains to be verified after coordinating other host work
and the encrypted-root unlock. Guest watchdog and autostart are still disabled.

The bounded synchronized-clock launch check is also installed. All 18 Linux-root
lifecycle tests pass; the installed script matches source and recognizes the
current synchronized clock. Deployment did not restart the helper or guest.

## Installation and migration

The on-demand per-VM startup change was deployed on 2026-11-13 during the
coordinated stopped-guest lab enrollment window. The UID1 provider and SEP
signer remain enabled at host boot. Both managed FairPlay instances, kentra
and omvm-lab, are static units started on demand by the serialized libvirt
gate, with separate VM-bound state. Both guests retain disabled watchdogs
and autostart. Lab cold boots have passed the gate; a full host reboot with
authenticated account access remains unverified. See [lab.md](lab.md).

Use the reviewed v23-or-later backend with durable-state support. Stage its
binary, each VM's existing 16-byte identifier and the complete offline Apple
asset cache in root-owned directories under `/var/lib/omvm`. All ancestors must
be root-owned and not group/world writable. Cache files are pinned individually;
the runtime refuses an unlisted file. Do not run a root helper from a user-writable
cache. Obtain Apple assets only from Apple or the owner's Mac; none are shipped
in this repository.

The root-owned, mode-0600 JSON manifest has this schema (replace placeholders
with verified paths/hashes; it contains no credentials or raw state):

```json
{
  "version": 1,
  "allow_uid": 1000,
  "provider": {
    "kernel": "7.2.11-15vmapple-1-ARCH",
    "module": {"path": "/var/lib/omvm/uid1-provider-v3-20261112/omvm-uid1-provider.ko", "sha256": "<verified hash>"},
    "diagnostic": {"path": "/var/lib/omvm/uid1-provider-v3-20261112/diagnostic", "sha256": "<verified hash>"},
    "seeds": {"path": "/var/lib/omvm/uid1-provider-v3-20261112/seeds.bin", "sha256": "<verified hash>"},
    "boot": {"path": "/boot/efi/m1n1/boot.bin", "sha256": "<reviewed boot hash>"},
    "update_m1n1": {"path": "/etc/default/update-m1n1", "sha256": "<reviewed config hash>"}
  },
  "backend": {"path": "/var/lib/omvm/fairplay-linux-v23/backend", "sha256": "<verified hash>"},
  "cache": {"path": "/var/lib/omvm/fairplay-assets", "files": {"<relative asset path>": "<verified hash>"}},
  "vms": {"example": {"identifier": {"path": "/var/lib/omvm/fairplay-linux-v23/example.identifier", "sha256": "<verified hash>"}}}
}
```

The current provider implementation is deliberately restricted to the reviewed
J314c board, exact kernel and module/diagnostic/seed hashes. A new kernel/provider
needs a new review; do not update a manifest merely to silence a mismatch.

Run from the reviewed repository checkout:

```sh
sudo python3 share/install-apple-helpers.py /var/lib/omvm/private-stage/apple-helpers.json
omvm helpers install-hook
```

The installer verifies the manifest, installs root-owned code/units and a narrow
sudo rule for the owning UID. It enables the shared SEP/UID1 host prerequisites
and removes per-VM helper boot links **without stopping running helpers**.
The existing libvirt gate automatically starts the selected VM helper under its
one-guest lock. Helpers remain running afterward for state continuity; eager
parallel initialization of every enrolled helper is avoided. Changed installed
files are retained in a root-private backup directory.
`install-hook` updates only the recognized existing omvm hook, preserving its
environment; it forwards the phase and original domain XML. It does not regenerate
a domain. Preserve any custom hook if this operation reports an unfamiliar shape.

Migration from an in-memory v22 helper needs a cleanly stopped guest and paired
disk/auxiliary/identity backup. Keep the old helper alive for rollback. Normal
startup refuses missing, corrupt, wrong-identity or uncertain state. Only for an
explicitly approved new state generation, while all macOS guests are stopped:

```sh
sudo /usr/local/libexec/omvm-apple-helpers enroll example
sudo systemctl start omvm-fairplay@example.service
```

This initializes an empty state envelope, not a copied account session. Existing
account recovery must be verified with the new helper. Change only the stopped
guest's `apple-fairplay-pci,relay-socket=` option to
`/run/omvm-fairplay-managed-example/relay.sock`. Keep the exact
`OMVM_IDENTITY_SIGNER=/run/omvm-identity/sep.sock` environment setting. These new
runtime paths do not collide with the preserved v22 sockets.

Start the guest normally, then use `omvm helpers status example`. READY proves
the expected root socket peers, initialized UID1 provider and live service; it
does not prove Apple Account sign-in, APNs, iMessage or Contact Key Verification.

## Startup and failure behavior

Per-VM helpers are static, on-demand units. Normal host boot starts SEP/UID1;
the next guest launch starts and checks its helper before admitting QEMU.
Do not enable per-VM helpers for `multi-user.target` or manually start a new
helper against another running guest. The explicit enrollment/recovery commands
above require all guests stopped. A helper being inactive before any guest has
launched is expected, not a reason to reset its checkpoint or provider.

- `omvm-uid1-provider.service` validates artifacts and cold-boot ownership. It
  loads the reviewed driver once, checks its public AES self-test, initializes
  the fixed UID1 purposes and requires READY. An already READY owner is reused.
  A poisoned/uncertain owner is never reset, unloaded or retried. A normal
  platform reset is the recovery boundary; kexec is excluded.
- `omvm-fairplay@NAME.service` requires that provider and the existing SEP signer,
  uses only Unix sockets/private networking, limits memory to 3 GiB and CPU to
  two cores, disables core dumps and stores state in a root-private directory.
  Systemd creates a fresh private runtime directory; readiness grants only the
  configured VM owner's socket access. Restart remains disabled until actual
  process-restart/account recovery is established.
- The libvirt gate parses the real domain configuration and checks exact helper
  options. All vmapple starts share a bounded root lock and one-guest reservation,
  including guests without configured helpers. It inspects `/proc`, never calls
  libvirt recursively. `release/end` clears the reservation after QEMU exits.
  A start interrupted while its libvirt daemon is alive fails closed rather than
  guessing that the slot is free; inspect that failed start before recovery.
- Before admitting a vmapple launch, the gate waits up to 30 seconds for
  `timedatectl` to report `NTPSynchronized=yes`. An unavailable or unsynchronized
  host clock rejects the launch before starting helpers or reserving the VM slot;
  check the network/time service and retry. This prevents a guest inheriting an
  invalid Asahi RTC after battery loss. Helper boot and VM release do not wait for
  network time, and this check never reinitializes a provider or changes the clock.
- Backend state uses an exclusive lock and atomic checkpoint. Dirty/interrupted
  files indicate uncertain native execution and stop startup. Do not delete those
  files or silently initialize empty state to make a service green.

Validate a guest restart, a stopped-guest helper restart, and a controlled normal
host reboot separately. For the host reboot, notify the owner's HC Omarchy pane,
save state, stop the guest cleanly and retain matched rollback artifacts. After
reconnect, verify service health and real account/service behavior. Enabling the
units alone does not establish reboot survival.

## Offline validation

`tests/test_apple_helpers.py` covers foreign callers, bad/misleading domain
options, unmanaged-guest exclusion, existing reservations, bounded contention,
root socket peers, hook XML/phase forwarding, poisoned-state refusal and READY
reuse. It makes no SEP/AES request and starts no VM or system service. Linux root
is needed for all filesystem/socket-owner checks; otherwise those cases skip.

```sh
sudo python3 -m unittest discover -s tests -p test_apple_helpers.py -v
bash -n bin/omvm
python3 -m py_compile share/apple-helpers.py share/install-apple-helpers.py share/apple-helpers-hook.py
systemd-analyze verify share/omvm-uid1-provider.service share/omvm-fairplay@.service
```
