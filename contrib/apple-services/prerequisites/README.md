# Identity source prerequisites

These patches preserve the missing development source beneath the incremental
identity/export patches. They change source only. They contain no machine data,
runtime configuration, compiled objects or activation commands.

## Linux SEP

Start with [`omacom/linux-aurora`](https://github.com/omacom/linux-aurora)
commit `b798f2b0c767e3d780896cff2f57e19e412bf954`. In that checkout, apply:

1. `linux-sep-prerequisites.patch` from this directory.
2. `../patches/identity-20261110/linux-sep-export/export-attestation.patch`.

Use `git apply --check` before each `git apply`. Between the two patches, the
five files in `../patches/identity-20261110/linux-sep-export/baseline-sha256.json`
must match that manifest. The combined result reconstructs all 14 relevant
source/tool files exactly.

The prerequisite covers DER Boolean encoding, the machine-reference-key
attestation ACL option, and coordinated keybag/xART recovery code in eight Rust
files. Preserve the per-file `GPL-2.0-only OR MIT` notices and attribution from
the kernel checkout.

This is a prototype source archive with runtime-sensitive behavior intact:

- `profile::T6000`, named `T6000/J316s` in `profile.rs`, changes the
  `xart_guard` default from 1 to 0. That changes the default protection for
  shared xART records on that profile; publishing this source does not validate
  or activate that policy.
- `refkey.rs` retains diagnostic `refkey_oa` and `refkey_oska` probes reached
  by `refkey_attest_sign` when the default-off `refkey_attest_acl` parameter is
  nonzero. The probe methods themselves have no logging privacy gate:
  `refkey_oa` prints up to 64 bytes of request DER, while successful
  `refkey_oska` prints up to 24 raw response bytes and the entire unwrapped
  response in hexadecimal. These runtime logs can contain private machine
  material and must not be published.

The source files contain no captured values. That source-publication check is
not a claim that running this prototype is private or suitable for production.
Review the diagnostic logging and guard policy before any deployment; this
archive deliberately preserves the existing implementation bytes.

The AES diagnostic patches `0001` through `0004` under
`../patches/standalone-fairplay/aes-snapshot/`, followed by the optional UID1 IRQ
patch, also apply to the pinned kernel base. Their file paths do not overlap the
SEP changes. Patch `0002` has only its Makefile integration context rebased to
that clean base, avoiding a dependency on an unrelated AES draft. The snapshot
driver source is unchanged. Board activation remains explicit and separate.

This preserves the identity source prerequisites. Building a macOS-capable
kernel still requires the existing omvm platform/KVM flow and its separately
obtained patches. The unlicensed PAC patch is not redistributed here; see the
repository [licensing notes](../../../LICENSING.md).

## QEMU

The recorded `760d1d0d29b07341409825eb55e760a52fd7d58f` revision is a local
integration result. Reconstruct its source from
[`steelbrain/qemu-reims-vgpu`](https://github.com/steelbrain/qemu-reims-vgpu)
commit `1b41f5f5db4d1067d023973b9bd74c7b341e0d28`, then apply the existing omvm
`patches/graphics/qemu/0001` through `0007` in order and
`patches/usb/0001-hw-usb-hcd-xhci-IOC-event-after-a-short-packet.patch`.
The exact filenames are recorded in [provenance.json](provenance.json). All 30
touched files were checked against the recorded local integration revision.
The source result is reproducible without reproducing Git author metadata.

Then apply, in order:

1. `qemu-identity-prerequisites.patch` from this directory.
2. `../patches/identity-20261110/cfg-host-identity.patch`.
3. `../patches/identity-20261110/qemu-aes-command-context.patch`.
4. `../patches/identity-20261110/virtio-qmp-backend-features.patch`.

Copy the preserved source snapshots into their QEMU destinations:

| Overlay source under `patches/identity-20261110/` | QEMU destination |
| --- | --- |
| `apple-identity.c` | `hw/vmapple/apple-identity.c` |
| `apple-identity.h` | `include/hw/vmapple/apple-identity.h` |
| `dma-mailbox.c` | `hw/vmapple/dma-mailbox.c` |
| `dma-mailbox.h` | `include/hw/vmapple/dma-mailbox.h` |
| `vmapple.c` | `hw/vmapple/vmapple.c` |
| `apple-fairplay.c` | `hw/vmapple/apple-fairplay.c` |

For the Linux backend, finish by applying
`../patches/standalone-fairplay/qemu-ofr2-completion.patch` in the QEMU checkout.
The prerequisite supplies the missing Kconfig/Meson wiring and earlier MLB
register support; the incremental host-register patch then applies exactly.
QEMU source remains GPL-2.0-or-later with existing notices preserved.

## Checks and limits

Both prerequisite patches apply to their exact baselines. The SEP chain matches
the recorded pre-export hashes and reconstructs the existing relevant files.
The complete QEMU source chain matches the preserved implementation before the
separate OFR2 extension. Seven QEMU C files pass syntax checks with the existing
configured compiler flags. Six also pass `-Werror`; the preserved identity
snapshot has existing zero-length-array initializer, parentheses, diagnostic
format and unused-variable warnings. The new prerequisite source was not used
to hide or fix those unrelated warnings.

All eight SEP prerequisite Rust files pass parser checks. No full fresh QEMU
configure/link, kernel type-check/build, guest run, hardware operation or reboot
was performed during packaging. Source reconstruction is distinct from those
integration checks.

Unrelated KVM/PAC changes, display/power experiments, unreferenced driver drafts,
scratch copies and local toolchain settings are excluded from this directory.
