# Linux SEP public attestation export

This incremental patch requires a Linux SEP development baseline with prior
SEP research changes. `baseline-sha256.json` records the exact required input
files. Apply `../../../prerequisites/linux-sep-prerequisites.patch` to the
pinned kernel base first; the prerequisite README records the exact revision.
Check every input hash before applying with
`git apply --check`, then `git apply`, from the matching source root.

It adds two CAP_SYS_ADMIN-only, bounded ioctls:

- `SEP_BIO_EXPORT_ATTESTATION` (`0x9050b10c`, 4176 bytes): committed UIK `(2,2)`
  attestation DER and the same target machine ref-key's 65-byte public point.
  An existing persisted reference can be loaded read-only if the cache is empty;
  the code never creates, replaces, commits, or persists a key. IPC framing and
  the operation's status/blob framing are removed. Encrypted DER is preserved.
- `SEP_BIO_SYSTEM_PUBLIC_KEY` (`0xd010b10d`, 4112 bytes): only SIK `(1,1)` or
  committed UIK `(2,2)`, returning verbatim opaque `oskgp` public data. Its request uses system
  keybag `-1`, without loading/unlocking an Identity bag. The existing
  profile-specific operation envelope (3 on Sepos13, 2 on Variant5) is retained;
  native userspace does not establish that kernel-side envelope field.

Both initialise every returned byte. Large output structs fix ABI sizes only;
handlers use an 80/16-byte header, heap-backed result, and 128-byte zero chunks,
so no 4 KiB output buffer is allocated on the kernel stack. The attested key
reference and its public point are copied together under the cache lock and
checked against the reference's embedded point. No payload is logged.

Userspace command (once the matching module is activated):

```sh
sudo python3 tools/aurora-sep/aurora-sep-export-attestation \
  --include-system-public-keys --output-dir /tmp/sep-host-reference
```

The new directory must not exist. It is mode 0700, with mode-0600
`attestation.der`, `public-key.x963`, `SIKPub.bin`, `UIKPub.bin`, and
`metadata.json`. The tool does not request certificate issuance or export a
private key. It preserves opaque public-data encodings.

## Integration limits

Validate the ABI sizes/offsets/numbers, userspace parser and file boundaries,
and the exact target kernel build before activation. The `oskgp` getter expects
standard SKS success-status/blob framing and fails closed if a reply differs.
Verify that framing before using exported files as RKProperties.

Do not hot-reload an attached SEP. This integration requires a matched build
and a controlled full host reboot for module replacement. Building a candidate
does not activate it. Never replace a machine reference key or alter identity
state to make a diagnostic pass. Exported machine data belongs outside source
control even when it contains public-key material.
