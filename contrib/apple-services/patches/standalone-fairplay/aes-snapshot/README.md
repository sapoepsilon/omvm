# AES powered-state diagnostic patches

These research patches prepare a bounded status snapshot for the
T6001/J314c board family. They do not implement the UID1-derived FairPlay
AES transform.

Apply in numeric order to the inspected kernel source based on
`b798f2b0c767e3d780896cff2f57e19e412bf954`. Patch 2's Makefile context is
rebased to that clean base, without the unrelated earlier AES draft. Inspect
the integration hunks before applying to another tree.

1. `0001-dt-bindings-apple-t6000-aes.patch`: revision-3 resource binding.
2. `0002-soc-apple-add-powered-aes-snapshot.patch`: separately named driver,
   default-disabled configuration and administrator documentation.
3. `0003-arm64-dts-apple-describe-disabled-t6000-aes.patch`: shared resource
   node, disabled by default.
4. `0004-OPTIONAL-enable-j314c-powered-snapshot.patch`: explicit board opt-in.
   This is a separate activation decision, not a default configuration.

The driver samples the readiness word once and reads the shared disable word
only if every required readiness bit is set. It rejects all-ones values and
reports unavailable state explicitly. Its privileged debugfs file reads cached
metadata. It performs no AES writes, resets, interrupts, FIFO/DMA submissions,
key reads, key export or cryptographic operation. Normal PM and IOMMU attachment
still affect power and stream state; the result is a powered-probe observation,
not immutable boot state. A clear disable bit does not prove a working key.

## Build and integration limits

Build against the exact prepared kernel output tree and matching toolchain.
Validate the binding and default-disabled/opt-in DTBs against the target board;
resource addresses and interrupt routing must not be generalized to other
boards. A patch applying cleanly does not establish safe hardware operation.

The series was checked against the pinned kernel base. The separate SEP
prerequisite patch touches different files. Check Kconfig conflicts with any
other AES driver. Keep the node disabled until
a reviewed boot and rollback plan is ready. These source patches contain no
firmware dump, compiled DTB, module binary or machine identifier.
