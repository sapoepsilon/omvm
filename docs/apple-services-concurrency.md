# Experimental two-VM Apple services

The two-VM implementation has passed source builds and offline contract tests.
It has **not been installed or verified with two live authenticated guests**.
The [one-VM Apple Account, iMessage and normal-reboot results](apple-services.md)
remain the historical tested baseline. Contact Key Verification remains deferred.
Successful capability probes and helper readiness are not service acceptance.

Offline validation on Linux ARM64 passed 84 Python tests as root with fake
hardware/services, all eight Go SAP/library and tool packages, and the focused
device/client race checks. Both binaries built with Go1.26.5; a fresh public-base
reconstruction matched all 12 changed files. No live acceptance follows from
these results alone.

This mode keeps one shared Linux SEP signer and UID1 provider, with a separate
FairPlay process, identifier and durable checkpoint for each VM. It does not
change the two-guest maximum, enroll an identity, reset account state or replace
the pinned kernel/module/seed inputs.

## Source and transaction boundary

Reconstruct public ipatool revision
`3e84853e2e5d60540a5022b64895d496910144eb` in this order:

1. Apply the unchanged
   [`ipatool-linux-experiment.patch`](../contrib/apple-services/patches/standalone-fairplay/ipatool-linux-experiment.patch).
2. Apply
   [`multi-client-serialization.patch`](../contrib/apple-services/patches/standalone-fairplay/multi-client-serialization.patch).

The [overlay guide](../contrib/apple-services/README.md) and
[incremental provenance](../contrib/apple-services/patches/standalone-fairplay/multi-client-provenance.json)
record patch order, hashes and build inputs. This is a userspace change; the
kernel driver and its UAPI remain unchanged.

Each Go device session holds its mutex and an exclusive `flock` on its
independently opened device descriptor for a complete synchronous transaction.
This includes readiness, controller operations, and the status/work/status
sequence for AES and DSB operations. Contention on `flock` waits at most two
seconds before submitting an ioctl. Unsupported locking and other lock errors
fail closed. Work ioctls are never retried, including after `EBUSY` or `EINTR`.
There is no timeout that releases the lock while a synchronous ioctl is still
running. Unlock failure discards the result and prevents further session work.
Process exit releases the advisory lock but does not establish hardware safety:
the next client must still validate the provider's READY and poison state.

All hardware clients must follow this protocol; an old client does not respect
another process's advisory lock. The existing SEP signer serves clients
sequentially through one worker. A fake two-client socket test verifies separate
replies and one active worker, without exercising SEP hardware. It establishes
no live latency or concurrent service guarantee.

## Opt-in and admission

The [root-owned helper manifest](apple-helpers.md#installation-and-migration)
accepts optional `"max_active_vms": 1` or `"max_active_vms": 2`. Omission keeps
the one-VM behavior. Only the integers `1` and `2` are valid; strings, booleans
and larger limits are rejected.

Two-VM mode requires both the pinned backend and the reviewed pinned diagnostic
to support `-print-capabilities`. On Linux ARM64 each must print:

```json
{"schema_version":1,"device_aes_arbitration":"transaction-flock-v1"}
```

These pure probes exit before opening the provider or reading assets, seeds,
identifiers or checkpoints. Other build targets report unavailable arbitration.
The validator checks artifact hashes before probing and checks that the
executables did not change during verification. The old diagnostic remains
usable in one-VM mode; it does not satisfy the two-VM requirement.

Every enrolled VM must have different **16-byte identifier contents**, not just
a different filename. Keep existing identifiers and VM-bound checkpoints;
copied identity or checkpoint material is not a way to add a second guest.
Only configured systemd FairPlay instances using the pinned executable and
verified socket peers are admitted. Legacy services, old executable inodes,
unmanaged hardware backends and services still stopping block startup.

All vmapple starts share the existing root lifecycle lock. In two-VM mode a
private reservation per VM counts pending starts alongside actual QEMU
processes, including unmanaged or unnamed guests. A reservation is counted
with an existing QEMU only when both its name and owning libvirt daemon's
PID/start time match. Duplicate names or uncertain ancestry cannot free a slot.
The gate counts again after readiness, before admission, and rejects a third
guest or pending start. Configured guests still require their exact domain
sockets, synchronized host clock and healthy helpers.

Reservations do not expire. Daemon death or PID reuse cannot prove an orphaned
launch child is gone. Only that reservation's owning `release/end` hook clears
it after the VM is absent. Otherwise, recovery requires explicit inspection
with all guests and pending starts stopped and the relevant libvirt daemon
stopped. A legacy `active.json` blocks two-VM mode; two-VM reservation files
block a return to one-VM mode until deliberately reconciled at that boundary.
Do not treat reservation cleanup as permission to delete checkpoint dirty or
interrupted-operation markers.

## Upgrade and rollback

Use a planned maintenance window. The installer does not stop guests or helpers
and does not perform the reservation migration for you.

1. Stop all macOS guests through their normal libvirt lifecycle, prevent
   watchdog/autostart or pending launches, and verify they are off. Cleanly stop
   all old per-VM FairPlay helpers, including any legacy helper. Retain matched
   disk, auxiliary storage, identity metadata, inactive domain XML and each
   durable checkpoint, plus the old manifest and installed code. Preserve the
   existing SEP identity and provider inputs.
2. Review the new artifacts against the incremental provenance. Stage the
   backend and diagnostic at new immutable, root-owned paths; do not overwrite
   files beneath running processes. Preserve the kernel, module, seeds, boot
   and identity pins. Update only the reviewed binary paths/hashes and the
   optional limit in a staged manifest. Do not reenroll existing guests.
3. Resolve any old reservation only after verifying all guests, pending launch
   children and their libvirt daemon are stopped. Run the
   [helper installer and hook installation](apple-helpers.md#installation-and-migration)
   with the reviewed manifest. It validates the binaries and configuration,
   preserves changed installed files, and leaves per-VM helpers on demand.
4. Start guests with normal libvirt cold boots. The gate starts each helper and
   preserves its existing checkpoint. Reuse the READY provider; do not unload,
   unbind, reset or reinitialize it. A poisoned provider still requires the
   separately controlled normal platform-reset recovery boundary, not kexec.
5. Verify real authenticated service activity in each guest and record the
   installed revisions, failures and timing privately. Two-helper readiness,
   guest SSH or a cached signed-in screen alone does not prove concurrent
   service use. Live two-VM authentication, messaging and restart recovery
   remain pending acceptance work.

Rollback also requires all guests and pending launches off and helpers cleanly
stopped. Restore a reviewed matching manifest/code/binary set and reconcile
reservations with libvirt stopped. If restoring VM or helper state, use the
matched disk/identity/checkpoint set; an old checkpoint paired with newer disks
is not a supported rollback. Do not delete dirty markers or initialize empty
state to force startup. Keep one-VM mode as the previously tested baseline,
without claiming that source-only tests validate a new installation.
