# Work log

- **2026-11-13 Preserved identity implementation prerequisites.** Added the earlier SEP development patch and QEMU build/register integration needed by the source overlay. The complete relevant SEP and QEMU source chains now reconstruct against pinned baselines. Rebased only AES diagnostic Makefile context, preserving its driver. Seven QEMU C syntax checks and eight Rust parser checks pass; existing identity-snapshot warnings and experimental runtime logging/policy behavior are documented. No runtime deployment or hardware operation was performed.

- **2026-11-13 Added Apple-services source and Linux helper lifecycle.** Preserved the experimental SEP identity provider, serialized libvirt readiness gate, per-VM durable FairPlay helper units, offline tests, and source-only upstream overlay. Added the application launcher and native/seamless display changes. Kept the existing identity payload defaults and environment overrides; removed the GUI's hardcoded streaming-host fallback. This source checkpoint does not establish full encrypted-data synchronization, Contact Key Verification, or authenticated host-reboot recovery. Validation: 32 offline tests passed with eight root-only skips; shell syntax, Python parsing and synthetic domain XML default/override checks passed. Platform-specific build limitations are documented with the source overlay.

This public log records source changes and reproducible validation. Private
machine/account histories and run evidence are not part of this source snapshot.
