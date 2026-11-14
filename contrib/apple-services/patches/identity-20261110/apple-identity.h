/*
 * Apple VirtualPlatform identity device, virtio-PCI 0x1a0c:0x106b.
 * SPDX-License-Identifier: GPL-2.0-or-later
 *
 * The guest side is AppleVirtualPlatformIdentityVirtioMessenger. See
 * research/identity/PROTOCOL.md for every offset below and how it was
 * recovered. This device answers the handshake and returns the VM's identity;
 * the host side of that identity is not implemented yet.
 */


#include <gnutls/gnutls.h>
#include <gnutls/abstract.h>
#ifndef HW_VMAPPLE_APPLE_IDENTITY_H
#define HW_VMAPPLE_APPLE_IDENTITY_H

#include "hw/virtio/virtio.h"
#include "hw/virtio/virtio-pci.h"
#include "qom/object.h"

#define APPLE_IDENTITY_VENDOR 0x106b
#define APPLE_IDENTITY_DEVICE 0x1a0c

#define APPLE_IDENTITY_SUBSYS_IDENTITY     4
#define APPLE_IDENTITY_SUBSYS_SWPKA        5

#define APPLE_IDENTITY_TYPE_HANDSHAKE 1
/* Type 1 is the handshake; the guest then sends type 3 asking for the UDID,
 * and asserts the reply's type equals its request's (START-ORDER.md). */
#define APPLE_IDENTITY_TYPE_UDID      3
/* Relayed for userspace: 4/6 asks for the identity blob, 4/4 is its fallback. */
#define APPLE_IDENTITY_TYPE_GET_IDENTITY 6
#define APPLE_IDENTITY_TYPE_GET_IDENTITY_FALLBACK 4

/*
 * Reply descriptors the client's deserializer compares against
 * (GetMessage at 0x100003288/0x100003298/0x1000032a8/0x1000032b8 of the
 * AppleVirtualPlatformIdentity XPC binary): {messageLen, buffersOffset,
 * numBuffers}. The iov lengths must also add up to exactly bufferLen, or the
 * walk fails with "remaining != 0" (0x100002cd4).
 */
#define APPLE_IDENTITY_REPLY_66_MSGLEN 48
#define APPLE_IDENTITY_REPLY_66_BOFF   16
#define APPLE_IDENTITY_REPLY_44_MSGLEN 16
#define APPLE_IDENTITY_REPLY_44_BOFF   0
/* 4/2 is the tunnel: messageLen 36, buffersOffset 4, numBuffers 2. */
#define APPLE_IDENTITY_TYPE_TUNNEL     2
#define APPLE_IDENTITY_REPLY_TUN_MSGLEN 36
#define APPLE_IDENTITY_REPLY_TUN_BOFF   4
#define APPLE_IDENTITY_REPLY_TUN_LEN    16
/* The identity blob is the 20 raw UDID bytes. */
#define APPLE_IDENTITY_IDENTITY_LEN    APPLE_IDENTITY_UDID_LEN

/*
 * The reply messageLen for 4/3: exactly one 16-byte iovec and nothing else.
 * The receive path asserts this value, so it is NOT the request's messageLen.
 */
#define APPLE_IDENTITY_REPLY_UDID_MSGLEN 16

/* Minimum payload for the relayed 4/4 and 4/6 bodies. */
#define APPLE_IDENTITY_MSG_MIN 8

/* A non-handshake reply carries version 2; only 4/1 uses the protocol version. */
#define APPLE_IDENTITY_REPLY_UDID_VERSION 2

/* Where the UDID is published in the device-memory BAR, past the SysCfg blob. */
#define APPLE_IDENTITY_UDID_OFF 0x800
/* Scratch for the 4/2 tunnel plist, so its descriptor has a real address. */
#define APPLE_IDENTITY_TUN_PLIST_OFF 0x1000
#define APPLE_IDENTITY_TUN_PLIST_MAX 0x2000
/* PCI BARs are powers of two; include the entire tunnel scratch window. */
#define APPLE_IDENTITY_MEM_SIZE 0x4000

/* Protocol 1 is the only version the guest accepts (PROTOCOL.md §1). */
#define APPLE_IDENTITY_PROTOCOL_VERSION 1

#define APPLE_IDENTITY_HEADER_LEN 0x20
/* The identity reply must be exactly this long (PROTOCOL.md §5). */
#define APPLE_IDENTITY_UDID_LEN 0x14
/* The guest's handshake carries a 25-character UDID string. */
#define APPLE_IDENTITY_UDID_STR_LEN 0x19
/* Upper bound for the patched device tree, used for every bounds check. */
#define APPLE_IDENTITY_FDT_CAP 0x20000
/* One config byte: the protocol version the device speaks. */
#define APPLE_IDENTITY_CONFIG_SIZE 1

/*
 * SysCfgV2 blob, recovered from the guest kext (research/identity/
 * SYSCFG-CONSTANTS.md). Leaf constants, so they live here rather than in the
 * blob builder, and carry their offsets so the builder cannot drift.
 */
#define APPLE_SYSCFG_MAGIC      0x53436667u     /* "SCfg" */
#define APPLE_SYSCFG_VERSION    0x17u
#define APPLE_SYSCFG_JUMBO_BIT  0x10u           /* bit 4 of a tag */
#define APPLE_SYSCFG_HDR_SIZE   0x188u          /* sizeof(SysCfgV2Header) */
#define APPLE_SYSCFG_ENTRY_SIZE 0x10u           /* sizeof(SysCfgV2Entry) */

/*
 * Offsets read straight from SysCfgV2Header::isValid (0xfffffe0008a9a414):
 * +0 magic (cmp), +4 version (cmp 0x17), +8 shSize, +0xc flags (bit test),
 * +0x10 shBigEndian, +0x14 shMaxSize. Entries start at the end of the header.
 */
#define APPLE_SYSCFG_OFF_MAGIC     0x00
#define APPLE_SYSCFG_OFF_VERSION   0x04
#define APPLE_SYSCFG_OFF_SIZE      0x08
#define APPLE_SYSCFG_OFF_FLAGS     0x0c
#define APPLE_SYSCFG_OFF_BIGENDIAN 0x10
#define APPLE_SYSCFG_OFF_MAXSIZE   0x14

/* SysCfg tags carried in the blob; values are the guest's own tag space. */
#define APPLE_SYSCFG_TAG_UDID 1
#define APPLE_SYSCFG_TAG_ECID 2
#define APPLE_SYSCFG_MAX_BLOB 0x1000

#define TYPE_APPLE_IDENTITY "apple.identity"
OBJECT_DECLARE_SIMPLE_TYPE(AppleIdentity, APPLE_IDENTITY)

#define TYPE_APPLE_IDENTITY_PCI "apple-identity-pci"
typedef struct AppleIdentityPCI AppleIdentityPCI;
DECLARE_INSTANCE_CHECKER(AppleIdentityPCI, APPLE_IDENTITY_PCI, TYPE_APPLE_IDENTITY_PCI)

struct AppleIdentity {
    VirtIODevice parent_obj;
    VirtQueue *vq;

    /* What the guest told us in its handshake; 0 until then. */
    uint16_t guest_protocol_version;
    /* Last request type, for the self-describing identity payload. */
    uint32_t last_type;

    /* Machine ECID, the stable per-VM value the identity derives from. */
    uint64_t ecid;

    /* Built from the ECID; stable for the life of the VM. */
    uint8_t udid[APPLE_IDENTITY_UDID_LEN];
    char udid_str[APPLE_IDENTITY_UDID_STR_LEN + 1];
    bool fdt_tried;
    bool fdt_done;
    bool fdt_args_fixed;
    size_t fdt_base;
    size_t fdt_add;
    bool fdt_zero_seen;
    QEMUTimer *watch_timer;
    QEMUTimer *fdt_timer;
    int fdt_tries;
    int watch_ticks;

    /*
     * The host certificate mobileactivationd asks for (CopyVMHostCertificate-
     * Request). Its public key's SHA-256 prefix is the UDID, so one key pair is
     * generated per VM and the certificate is DER. 0 length until built.
     */
    uint8_t *host_cert;
    size_t host_cert_len;
    gnutls_x509_privkey_t host_key;
    uint8_t *host_ca;
    size_t host_ca_len;
    bool external_mode;
    char *signer_path;
    gnutls_pubkey_t host_public_key;
    uint8_t host_public_point[65];
    uint32_t guest_chip_id;
    uint64_t guest_ecid;
    bool guest_parameters_valid;
    GBytes *external_identity4;
    GBytes *external_identity6;
    struct AppleIdentityRequest *pending;
};

struct AppleIdentityPCI {
    VirtIOPCIProxy parent_obj;
    AppleIdentity vdev;

    /*
     * The identity service maps provider device memory and DMAs through it
     * (IDENTITY-KEXT-STRINGS.md, "Device requirements"), so the device exposes
     * one BAR of its own on top of the virtio transports.
     */
    MemoryRegion mem;

    /* Where virtio-pci put its own BARs, so ours cannot collide. */
    int mem_bar;
};

#endif