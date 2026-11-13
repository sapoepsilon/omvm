# Local AVP host configuration experiment

This local experiment records native register meanings for a specific reference build. It is not an upstream QEMU contribution or a general account-provisioning guarantee.

## Native source evidence

Reference executable: macOS 27.2 build 26B123:
`Virtualization.framework/Versions/A/XPCServices/com.apple.Virtualization.VirtualMachine.xpc/Contents/MacOS/com.apple.Virtualization.VirtualMachine` (arm64e).

The `AvpConfigurationRegisters` constructor at `0x1000C5C38` loads optional `host_build` at `0x1000C64B0`–`0x1000C64F4`. The `std::string` data pointer and full byte length become x21/x22 at `0x1000C6540`/`0x1000C6544`. It copies min(length,32) bytes to internal offset 0x3EC and zero-pads only if shorter, then calls CC_SHA256_Init/Update/Final at `0x1000C6584`, `0x1000C6594`, `0x1000C65A0`. Update receives the original pointer and full length, without NUL, truncation or padding. The complete digest is stored at internal 0x3AC (`0x1000C65A4`–`0x1000C65AC`).

The MMIO read callback `0x1000CB6BC`, with its table at `0x1004019C8`, maps:

| Guest register bytes | Native meaning | Native object offset |
|---|---|---|
| 0x500–0x51F | guest serial | 0x2CC |
| 0x520–0x53F | guest region | 0x2EC |
| 0x540–0x55F | guest model | 0x30C |
| 0x560–0x57F | host build digest | 0x3AC |
| 0x584–0x5C3 | CPU name | 0x32C |
| 0x5C8–0x607 | variant name | 0x36C |
| 0x650–0x66F | physical host serial | 0x3CC |
| 0x670–0x68F | host build | 0x3EC |
| 0x6CC–0x6EB | host hardware platform | 0x40C |

The save/restore serializer at `0x1000C96FC` names internal 0x3AC `host_build_digest`. Host serial is read from optional `host_serial_number` at `0x1000C63F4` and copied/padded to 32 bytes at internal 0x3CC (`0x1000C6458`). These string/digest MMIO handlers have no platform-version condition. QEMU's existing `cfg.version=2` is retained. This does not prove every later guest boot stage consumes all optional fields under version 2.

## Incremental change

`cfg-host-identity.patch` requires a development `hw/vmapple/cfg.c` baseline with earlier serial/MLB changes already present; it is not a standalone patch for pristine upstream QEMU. The original `mlb` member actually occupies offset 0x560; the older comments were incorrect. An anonymous union keeps its legacy CLI behavior while naming the native digest field correctly.

Only the presence of `OMVM_IDENTITY_CERT_CHAIN` enables the new population. The host build is Linux `uname().release`, the same complete input used by the genuine identity archive's `BuildVersion`. The digest covers all release bytes; the build register contains its first 32 bytes. Physical host serial comes only from the read-only live Linux DT `serial-number` property. Trailing NUL padding is removed; empty, over-32-byte, embedded-NUL or nonprintable values fail startup. A full 32-byte serial/build requires no terminating NUL.

Guest serial, model, ECID and MAC fields retain their exact existing bytes. The staged MLB CLI and files are retained; external mode supplies the register's proven digest meaning. Legacy mode performs no new I/O or register writes. The unproven host hardware-platform field remains zero.

## Validation boundaries

Integration checks should cover full-input SHA256, truncation after hashing,
full-width serials, zero padding, malformed input without partial writes,
register offsets, preservation of unrelated guest bytes and legacy operation.
Use public synthetic values for tests. Real host identifiers must remain private.

The register layout and constructor addresses are specific to the reference
build. They do not establish successful account provisioning. Preserve stable
guest identity and verify the complete matched QEMU integration before use.
