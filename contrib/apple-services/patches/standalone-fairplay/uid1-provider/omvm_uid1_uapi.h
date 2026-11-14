/* SPDX-License-Identifier: GPL-2.0 WITH Linux-syscall-note */
#ifndef OMVM_UID1_UAPI_H
#define OMVM_UID1_UAPI_H

#include <linux/ioctl.h>
#include <linux/types.h>

#define OMVM_UID1_ABI_VERSION 1U
#define OMVM_UID1_DEVICE "/dev/omvm-uid1-provider"
#define OMVM_UID1_MAX_PAYLOAD 4096U
#define OMVM_UID1_BLOCK_SIZE 16U
#define OMVM_UID1_SEED_BUNDLE_SIZE 32U
#define OMVM_UID1_PURPOSE_899 0x899U
#define OMVM_UID1_PURPOSE_89C 0x89cU
/* Only observed operations zero (CBC encrypt) and one (CBC decrypt). */
#define OMVM_UID1_OPERATION_ENCRYPT 0U
#define OMVM_UID1_OPERATION_DECRYPT 1U

enum omvm_uid1_state {
	OMVM_UID1_UNTESTED = 0,
	OMVM_UID1_SELFTEST_PASSED = 1,
	OMVM_UID1_READY = 2,
	OMVM_UID1_POISONED = 3,
};

#define OMVM_UID1_STATUS_BUSY (1U << 0)
#define OMVM_UID1_STATUS_PINNED (1U << 1)
#define OMVM_UID1_STATUS_POWER_HELD (1U << 2)

/* Exact immutable bundle, purpose 0x899 first, then 0x89c. No arbitrary seed.
 * SHA256: 1c6a5cc41f941e0788e436148f280dd5a875caf57929811b802aadca9e253c8d
 * ioctl succeeds only after SELFTEST and real UID1 operations for both purposes.
 */
struct omvm_uid1_init {
	__u32 abi_version;
	__u32 reserved;
	__u8 seed_bundle[OMVM_UID1_SEED_BUNDLE_SIZE];
};

/* Size 4136, no pointers, same layout for 32/64-bit callers.
 * operation must be 0 or 1. length is 16..4096 and a multiple of 16.
 * iv_present must be 0 or 1. When absent, input IV must be all zero and output
 * IV remains zero. When present, input IV is used and updated CBC IV returned.
 * data[0:length] is transformed in place; bytes above length must be zero.
 * Output is copied only after complete success. No derived key is returned.
 */
struct omvm_uid1_transform {
	__u32 abi_version;
	__u32 purpose;
	__u32 operation;
	__u32 iv_present;
	__u32 length;
	__u32 reserved;
	__u8 iv[OMVM_UID1_BLOCK_SIZE];
	__u8 data[OMVM_UID1_MAX_PAYLOAD];
};

/* Size 64. STATUS reads cached metadata only: no MMIO/power/crypto operation.
 * last_errno is zero or negative Linux errno. hw_tag is raw tag/status metadata.
 * reserved fields are zero. Status works in POISONED state; all work is rejected.
 */
struct omvm_uid1_status {
	__u32 abi_version;
	__u32 state;
	__s32 last_errno;
	__u32 flags;
	__u32 hw_status;
	__u32 hw_tag;
	__u32 completed_ops;
	__u32 reserved0;
	__aligned_u64 reserved[4];
};

#define OMVM_UID1_IOC_MAGIC 0xb7
#define OMVM_UID1_IOC_SELFTEST _IO(OMVM_UID1_IOC_MAGIC, 0x00)
#define OMVM_UID1_IOC_INIT _IOW(OMVM_UID1_IOC_MAGIC, 0x01, struct omvm_uid1_init)
#define OMVM_UID1_IOC_TRANSFORM _IOWR(OMVM_UID1_IOC_MAGIC, 0x02, struct omvm_uid1_transform)
#define OMVM_UID1_IOC_STATUS _IOR(OMVM_UID1_IOC_MAGIC, 0x03, struct omvm_uid1_status)

/* Explicit powered read, serialized with all work; no AES command/DMA.
 * Unlike STATUS, CAPABILITY may acquire/release normal runtime power before a
 * session. Success means readiness was valid and shared-disable bit3 sampled.
 * dsb_available is exactly 0 (disabled) or 1 (clear); errors copy no output.
 * No key, raw disable register or caller identity is returned. Size 64.
 */
struct omvm_uid1_capability {
	__u32 abi_version;
	__u32 dsb_available;
	__u32 readiness;
	__u32 reserved0;
	__aligned_u64 reserved[6];
};

#define OMVM_UID1_DSB_CONTEXT_SIZE 32U
#define OMVM_UID1_DSB_KEY_FIELD_SIZE 16U
/* Exact observed unflagged selector3000, format2, AES128 CBC-decrypt only.
 * One 16-byte block; IV always present; hardware context/offsets fixed zero.
 * dsb_context and key_field are opaque native inputs, never plaintext key
 * material supplied to kernel software CBC and never exported as derived keys.
 * Reserved must be zero. READY is required. Hardware availability is sampled
 * again before each submission, irrespective of an earlier CAPABILITY result.
 * Success modifies ONLY iv and data; header/opaque input fields are untouched.
 * Failure before copyback modifies nothing. A partial user-copy fault may
 * expose part of a completed result, never an uncertain hardware result.
 * No automatic retry. Size 88, output span [56,88), no pointers.
 */
struct omvm_uid1_dsb_decrypt {
	__u32 abi_version;
	__u32 reserved;
	__u8 dsb_context[OMVM_UID1_DSB_CONTEXT_SIZE];
	__u8 key_field[OMVM_UID1_DSB_KEY_FIELD_SIZE];
	__u8 iv[OMVM_UID1_BLOCK_SIZE];
	__u8 data[OMVM_UID1_BLOCK_SIZE];
};

#define OMVM_UID1_IOC_CAPABILITY _IOR(OMVM_UID1_IOC_MAGIC, 0x04, struct omvm_uid1_capability)
#define OMVM_UID1_IOC_DSB_DECRYPT _IOWR(OMVM_UID1_IOC_MAGIC, 0x05, struct omvm_uid1_dsb_decrypt)

#endif /* OMVM_UID1_UAPI_H */
