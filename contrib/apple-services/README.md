# Apple services source overlay

This directory preserves experimental identity, FairPlay and restore source for
macOS guests on Apple Silicon Linux. It is an overlay for
[`aquarat/apple-macos-arm64-vm-guest`](https://github.com/aquarat/apple-macos-arm64-vm-guest),
not a complete replacement checkout or a ready-to-install hardware package.
Operational journals, account histories, host configurations and machine
artifacts are excluded.

The exact upstream base is
`2ec3cb8745e81c368276852b0a2a8688875e5325`. The source checkpoint is
`10df598139348b3441e7748b78b13ae28cfaf4e7`; that checkpoint's private repository
history is not required to reconstruct the included code. [provenance.json](provenance.json)
records every source/output hash, the dependency revisions and the documentation
changes made for publication.

## Reconstruct the source

Use a fresh checkout of the upstream repository at the exact base. Set `OVERLAY`
to the absolute path of this directory and `UPSTREAM` to that fresh checkout:

```sh
git -C "$UPSTREAM" checkout --detach 2ec3cb8745e81c368276852b0a2a8688875e5325
git -C "$UPSTREAM" apply --check "$OVERLAY/upstream-source-changes.patch"
git -C "$UPSTREAM" apply "$OVERLAY/upstream-source-changes.patch"
cp -a "$OVERLAY/patches/." "$UPSTREAM/patches/"
cp -a "$OVERLAY/scripts/." "$UPSTREAM/scripts/"
```

The patch preserves the changes to `images/host/macos-restore.sh` and
`scripts/provision-on-macos.sh`. The latter's unlicensed upstream implementation
is not copied wholesale. The scripts use the restore image's factory hardware
model by default, make legacy compatibility explicit, and extract auxiliary
flash while preserving the complete native file.

The copied implementation files reconstruct the source checkpoint exactly.
Five patch documents were generalized. The cumulative ipatool patch also has a
generalized README paragraph; every resulting implementation and test file
remains identical to the source checkpoint's patch output. The source overlay
does not recreate the omitted operational documents. Historical comments in
the exact source snapshots still name research notes outside this overlay;
those references are intentionally unavailable and are not build inputs.

## Components and dependencies

| Path | Purpose and integration boundary |
| --- | --- |
| `patches/identity-20261110/` | QEMU identity/mailbox snapshots, host-register changes, the FairPlay frontend and QMP fix. Some snapshots require an existing development baseline. |
| `patches/identity-20261110/linux-sep-export/` | Incremental public attestation export; requires the exact input file hashes and earlier SEP work. |
| `patches/standalone-fairplay/ipatool-linux-experiment.patch` | Complete cumulative Linux adapter through v23, device-provider client, durable-state implementation and tests. Applies to ipatool `3e84853e2e5d60540a5022b64895d496910144eb`. |
| `patches/standalone-fairplay/qemu-ofr2-completion.patch` | Queue-0 completion semantics required by the Linux adapter; applies to the included `apple-fairplay.c` frontend. |
| `patches/standalone-fairplay/uid1-provider/` | Board-specific kernel provider, fixed UAPI, build file and optional interrupt metadata patch. |
| `patches/standalone-fairplay/aes-snapshot/` | Earlier, default-disabled powered-state diagnostics and board opt-in source. |
| `scripts/debug/fairplay-relay.c` and `fairplay-relay-socket.py` | Historical macOS IOKit relay and private Unix transport. This backend requires macOS and restricted driver access; it is separate from the Linux adapter. |
| `scripts/extract-aux.py` | Read-only auxiliary-storage parser used by the restore patch. |

To reconstruct the Linux adapter, apply the cumulative patch to a clean
checkout of the pinned ipatool revision using `git apply --check` followed by
`git apply`. Build and protocol details are in the patch's
`tools/omvm-fairplay-linux/README.md`. The Linux runtime uses explicit Linux
SEP/device-AES providers and the OFR2-capable QEMU frontend. Its Apple asset
cache, per-VM identity and private provider inputs must be supplied separately;
none are included in this overlay.

The QEMU frontend/QMP checks use the Reims fork at
`760d1d0d29b07341409825eb55e760a52fd7d58f`. The remaining QEMU and kernel
development prerequisites are not completely bundled here. In particular,
`cfg-host-identity.patch` expects earlier register changes, and the SEP patch
requires the files described by its baseline manifest. Source preservation
does not imply that all components build from pristine upstream repositories.

## State and hardware limitations

V23 adds explicit, identity-bound ADI checkpoints with private-file validation,
atomic replacement, commit-before-reply and crash markers. It does not persist
every transient emulator or guest session. Missing, mismatched or uncertain
state fails closed; integration must not silently enroll or roll back state.
Complete guest/helper/host restart recovery still requires lifecycle testing.

The kernel provider targets the documented T6001/J314c resources. After a
hardware session it retains the module, power, DMA and IRQ ownership until a
full platform reset, vetoes system sleep and has no supported ordinary unload
or reset/abort path. Do not generalize it to another board or interpret source
checks as hardware activation approval. No installation, service activation,
VM start or hardware operation is part of applying this overlay.

The preserved macOS relay compiles with the macOS SDK and IOKit. Stock-policy
execution may reject its restricted entitlement. Its successful framing is
not evidence of successful account authentication.

## Licenses and excluded material

New project source is GPL-2.0-or-later under the repository [LICENSE](../../LICENSE).
Existing notices and per-file SPDX identifiers take precedence for derived
code: QEMU remains GPL-2.0-or-later, the kernel provider is GPL-2.0-only, the UAPI
retains its Linux syscall note, and the device-tree binding retains its dual
license. The ipatool changes use upstream's MIT license, whose copyright and
permission notice is preserved in [licenses/ipatool-MIT.txt](licenses/ipatool-MIT.txt).
No license is granted to excluded, unlicensed upstream implementations.

There are no Apple binaries, firmware, restore images, VM disks, identity
manifests, certificates, credentials, captured requests, private constants or
generated cryptographic keys in this directory. Obtain required Apple assets
through the applicable Apple or owner-provided source. Preserve all third-party
attribution when integrating the code.

## Packaging checks

The upstream delta applies to the pinned base, and all reconstructed code files
match their source bytes. Both cumulative ipatool patches apply to the pinned
dependency and differ only in the generalized README. Restored shell/Python
syntax checks and strict compilation of the OFR2-patched QEMU frontend pass.
The manifest records these checks. Kernel builds, Darwin compilation and
runtime/hardware tests were not repeated during packaging.
