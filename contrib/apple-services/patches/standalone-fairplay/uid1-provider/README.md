# Experimental Linux UID1 provider

This manually loaded, board-specific research module implements the missing
device-key primitive for the standalone FairPlay experiment. It is not a
general crypto driver or a validated Apple Account sign-in solution.

The v3 interface includes an explicit powered DSB capability query and the
fixed selector 3000/AES128/CBC-decrypt/one-block operation. It is specific to
the T6001/J314c integration and must not be treated as a general Apple AES
provider. Its source and userspace tests do not establish account recovery.

## Build and ownership

Build against the exact target kernel's prepared output tree and original
toolchain, with normal MODPOST/BTF and no forced vermagic. For a matching
prepared tree, the normal external-module command is:

```sh
make -C "$KERNEL_BUILD" M="$PWD" LLVM="$LLVM_PREFIX" modules
```

The existing AES diagnostic must relinquish ownership before manual loading.
The provider has no automatic module alias, no boot installation and no
hardware operation in probe or cached STATUS. The default IRQ route uses the
device tree. The optional patch in this directory adds the reviewed board's
interrupt to the earlier snapshot DT series.

The default-off `j314c_irq_diagnostic=1` option is a board-specific diagnostic
for missing interrupt metadata. Only when both IRQ properties are absent does
it validate the exact board/controller/resources
and ask the existing AIC2 IRQ domain for the authentic four-cell specification.
It never guesses a Linux IRQ number or programs the controller directly. An
existing mapping is rejected; a newly requested mapping is deliberately retained
until reset because the API does not distinguish creation from concurrent reuse.
Controller, die and IRQ number must match the board firmware resource map.
Level-high is the standard Linux AIC2 declaration, not a recovered ADT polarity
bit. A present malformed or deferred DT interrupt never selects this path.

## Explicit operations

The root-owned mode-0600 misc device requires global root and CAP_SYS_RAWIO.
`omvm_uid1_uapi.h` defines the fixed pointer-free ABI; the ipatool patch includes
the matching Linux ARM64 client and explicit administrative diagnostic CLI.

1. SELFTEST executes the fixed public NIST SP 800-38A F.2.1 first-block vector
   in both hardware directions, checking ciphertext/plaintext and returned IV. It then
   checks the actual synchronous kernel CBC encrypt/decrypt API with the same
   public vector and verifies both updated IVs. These temporary test keys are
   never a fallback: INIT must replace both before READY.
2. INIT verifies a private 32-byte static program-constant bundle, ordered
   purpose 0x899 then 0x89c, by SHA-256
   `1c6a5cc41f941e0788e436148f280dd5a875caf57929811b802aadca9e253c8d`.
   Each actual UID1 one-block derivation installs its result into a separate
   kernel AES-128 CBC context. The bundle belongs outside this public repository.
3. TRANSFORM accepts only those two purposes, operations 0/1 (CBC encrypt/decrypt), 16–4096 bytes in
   complete blocks, and explicit IV presence. Payload crypto uses the genuinely
   derived kernel keys; no raw key or arbitrary parent/seed interface exists.
4. STATUS returns cached metadata. The adapter opens only an already READY
   provider and never initializes it implicitly.
5. CAPABILITY explicitly samples readiness and shared-disable bit 3 while the
   provider owns the powered resources. Before a hardware session its temporary
   runtime-PM reference is balanced; after a session the permanent reference is
   retained. It submits no commands or DMA, and rejects poisoned state.
6. DSB_DECRYPT accepts only the fixed 88-byte request: ABI/reserved, opaque 32-byte
   DSB fields, opaque 16-byte key-storage field, IV 16 and ciphertext 16. It fixes
   native context 0/format 2/decrypt, checks capability afresh before modifying
   DMA buffers or FIFO, and copies back only completed IV/data. It exports no
   selector, command-header or DMA-pointer interface. Only the separate adapter
   opt-in enables this path; normal adapter startup never performs administrative
   actions. No raw opaque inputs are logged or interpreted as software keys.

The driver uses normal 32-bit coherent DMA mappings with full-range checks,
one outstanding request, a fresh completion interrupt, exact tag and native
error masks. A submission is not completion. Readiness and completion waits
are bounded. Failed operations expose no payload. Uncertain hardware completion
permanently poisons the session; its DMA is never freed, unmapped or reported
as cancelled. Input or capability rejection before submission does not claim
that a hardware operation occurred.

## Diagnostic lifetime limitation

The first explicit hardware session permanently pins the module and retains
power, DMA storage and the IRQ action **even after success**. It vetoes system
sleep until a full platform reset. It does not implement reset/abort, ordinary
post-session unloading or production power management. Supplier/DT removal
and kexec are excluded from the controlled workflow. Normal driver bind/unbind controls
are suppressed, but this is not a guarantee against privileged supplier removal.

## Validation and provenance

The userspace patch includes fake-device client tests for syscall errors,
immutable fields, node identity, buffer ownership and serialized close. Review
command layout, range bounds, timeout/error/stale-tag rejection, failure
copyback, retained ownership and sleep veto against the exact kernel build
before any hardware operation. Synthetic tests do not establish hardware or
account-provisioning behavior.

The command contract targets AppleS8000AES and IOCryptoAcceleratorFamily from
macOS 27.0.1 / 26A434. Proprietary members, private constants, machine identities
and generated keys are not distributed here. The public known-answer vector is
from [NIST SP 800-38A, Appendix F.2.1](https://nvlpubs.nist.gov/nistpubs/Legacy/SP/nistspecialpublication800-38a.pdf).
