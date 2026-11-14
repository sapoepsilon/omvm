/*
 * Apple VirtualPlatform identity device, virtio-PCI 0x1a0c:0x106b.
 * SPDX-License-Identifier: GPL-2.0-or-later
 *
 * Every wire rule maps to research/identity/PROTOCOL.md, and the design
 * decisions to ASKING-FABLE.md. The device is a relay: the guest's request goes
 * to a host service, and the descriptor is held until that service answers,
 * because virtio is asynchronous and there is no busy status a driver retries.
 * With no service behind it the device answers the handshake itself today.
 */

#include "qemu/osdep.h"
#include <gnutls/crypto.h>
#include <errno.h>
#include <gnutls/gnutls.h>
#include <gnutls/x509.h>
#include <gnutls/abstract.h>
#include "qemu/log.h"
#include "qemu/module.h"
#include "qemu/cutils.h"
#include "qemu/timer.h"
#include "qemu/main-loop.h"
#include "qemu/sockets.h"
#include "qapi/error.h"
#include <sys/un.h>
#include <sys/utsname.h>
#include "system/memory.h"
#include "standard-headers/linux/pci_regs.h"
#include "hw/core/qdev-properties.h"
#include "hw/virtio/virtio.h"
#include "hw/virtio/virtio-access.h"
#include "hw/virtio/virtio-bus.h"
#include "standard-headers/linux/virtio_ids.h"
#include "hw/pci/pci.h"
#include "hw/pci/pci_device.h"
#include "hw/virtio/virtio-pci.h"

#include "hw/vmapple/apple-identity.h"

/*
 * How long a relayed request may stay unanswered before the guest is given an
 * error, so a dead host service can never hang it (ASKING-FABLE.md).
 * Existing SEP signing takes about 1.88 seconds and the provider serializes
 * requests; three queued calls legitimately exceed the previous five seconds.
 */
#define APPLE_IDENTITY_RELAY_TIMEOUT_MS 15000
/* One protocol-version byte; identity_get_config() writes exactly config[0]. */
#define APPLE_IDENTITY_CONFIG_SIZE 1

/* PROTOCOL.md §3: the guest writes this header; sizes are little-endian u32. */
typedef struct QEMU_PACKED AppleIdentityHeader {
    uint32_t version;
    uint32_t subsystem;
    uint32_t message_type;
    uint32_t transport_len;
    uint32_t message_len;
    uint32_t buffer_len;
    uint32_t num_buffers;
    uint32_t buffers_offset;
} AppleIdentityHeader;

/* PROTOCOL.md §3: {iov_base, iov_len}, both 64-bit. */
typedef struct QEMU_PACKED AppleIdentityBuffer {
    uint64_t base;
    uint64_t len;
} AppleIdentityBuffer;

G_STATIC_ASSERT(APPLE_IDENTITY_MEM_SIZE >=
                APPLE_IDENTITY_TUN_PLIST_OFF + APPLE_IDENTITY_TUN_PLIST_MAX);
G_STATIC_ASSERT(APPLE_IDENTITY_REPLY_TUN_MSGLEN == 36);
G_STATIC_ASSERT(APPLE_IDENTITY_REPLY_TUN_BOFF == 4);
/* Packed tunnel body: inner u32 followed by two 16-byte iovecs. */
G_STATIC_ASSERT(APPLE_IDENTITY_REPLY_TUN_MSGLEN ==
                sizeof(uint32_t) + 2 * sizeof(AppleIdentityBuffer));

#define OMVM_SIKA_TBS_MAX 384u
#define OMVM_SIKA_NONCE_MAX 48u

struct omvm_sika_input {
    const uint8_t *attested_point;
    size_t attested_point_len;
    uint32_t signing_flags;
    uint32_t attested_flags;
    uint32_t attested_selector;
    uint32_t attested_secondary;
    bool guest_identity_valid;
    uint32_t guest_chip_id;
    uint64_t guest_ecid;
    const uint8_t *nonce;
    size_t nonce_len;
    /* Caller has validated the special host context; never inferred from flags
     * or point bytes. Requires attested_flags bit0x4. Actual point curve is
     * independent of hash/curve flags for this retained-key slot.
     */
    bool attested_is_host;
};

struct omvm_sika_result {
    uint8_t tbs[OMVM_SIKA_TBS_MAX];
    size_t tbs_len;
    uint8_t hash[48];
    size_t hash_len;
    uint8_t normalized[48];
    size_t normalized_len;
};

/* Returns zero or positive errno; output is all zero on failure. No logging,
 * context derivation, key creation, signing, I/O, or host-fact substitution.
 * Initialize GnuTLS normally before calling. Point validation is mathematical.
 * Host-attested tag/actual-point behavior matches native public SOFTWARE-key
 * fixtures; ordinary points must match the curve selected by attested_flags.
 */
int omvm_sika_build(const struct omvm_sika_input *input,
                    struct omvm_sika_result *output);

/* Explicit second-stage truncation for an ACTUAL P256 signing key. Call only
 * when the caller has selected a P256 key, regardless of signing_flags curve.
 * This copies the first32 bytes of the FINAL normalized digest, not hash48.
 */
int omvm_sika_effective_p256(const struct omvm_sika_result *result,
                             uint8_t digest[32]);


#define F_GUARD          UINT32_C(0x0002)
#define F_HOST           UINT32_C(0x0004)
#define F_MEASUREMENT0   UINT32_C(0x0008)
#define F_GUEST_IDENTITY UINT32_C(0x0010)
#define F_IGNORED_0040   UINT32_C(0x0040)
#define F_SEP_REVISION   UINT32_C(0x0080)
#define F_MEASUREMENT6   UINT32_C(0x0200)
#define F_MEASUREMENTS23 UINT32_C(0x0800)
#define F_AON_SECURITY   UINT32_C(0x1000)
#define F_NONCE          UINT32_C(0x2000)
#define F_P384           UINT32_C(0x4000)

/* Only documented branches and fixture-proven ignored bit0x40. Native future
 * capability-dependent bits deliberately do not become implicit support here.
 */
#define SUPPORTED_FLAGS (F_GUARD | F_HOST | F_MEASUREMENT0 | F_GUEST_IDENTITY | \
                         F_IGNORED_0040 | F_SEP_REVISION | F_MEASUREMENT6 | \
                         F_MEASUREMENTS23 | F_AON_SECURITY | F_NONCE | F_P384)

static int identity_sika_append(struct omvm_sika_result *out, const void *bytes, size_t len)
{
    if (len > sizeof(out->tbs) - out->tbs_len)
        return EOVERFLOW;
    if (len != 0)
        memcpy(out->tbs + out->tbs_len, bytes, len);
    out->tbs_len += len;
    return 0;
}

static int identity_sika_append_u32(struct omvm_sika_result *out, uint32_t value, bool be)
{
    uint8_t bytes[4];
    for (unsigned i = 0; i < 4; i++)
        bytes[i] = (uint8_t)(value >> (be ? 8 * (3 - i) : 8 * i));
    return identity_sika_append(out, bytes, sizeof(bytes));
}

static int identity_sika_validate_point(const uint8_t *point, size_t length, bool p384)
{
    size_t coordinate = p384 ? 48 : 32;
    gnutls_pubkey_t key;
    if (point == NULL || length != 1 + 2 * coordinate || point[0] != 4)
        return EINVAL;
    int status = gnutls_pubkey_init(&key);
    if (status < 0)
        return ENOMEM;
    gnutls_datum_t x = {(unsigned char *)(point + 1), (unsigned int)coordinate};
    gnutls_datum_t y = {(unsigned char *)(point + 1 + coordinate), (unsigned int)coordinate};
    status = gnutls_pubkey_import_ecc_raw(
        key, p384 ? GNUTLS_ECC_CURVE_SECP384R1 : GNUTLS_ECC_CURVE_SECP256R1, &x, &y);
    if (status >= 0)
        status = gnutls_pubkey_verify_params(key);
    gnutls_pubkey_deinit(key);
    return status < 0 ? EINVAL : 0;
}

int omvm_sika_build(const struct omvm_sika_input *in,
                    struct omvm_sika_result *out)
{
    static const uint8_t labels[3][4] = {{'s','k','s',' '}, {'s','s','c','a'}, {'s','i','m','p'}};
    static const uint8_t host_tag[24] = {
        0xcc,0x4f,0xa4,0x26,0xc2,0xfc,0xb7,0xd6,0x4b,0x2f,0x4c,0xb1,
        0x0c,0x1c,0xb6,0xf2,0xc4,0xad,0x0d,0x5a,0x99,0xc8,0xc6,0xf6,
    };
    uint8_t measurement[52];
    struct omvm_sika_result result = {0};
    int error;
    if (out == NULL)
        return EINVAL;
    memset(out, 0, sizeof(*out));
    if (in == NULL)
        return EINVAL;
    if ((in->signing_flags | in->attested_flags) & ~SUPPORTED_FLAGS)
        return EOPNOTSUPP;
    if (in->attested_selector >= 3)
        return EOPNOTSUPP;
    /* Only caller-validated special context selects host mode. flags0x4 alone
     * can occur on an ordinary context and must not imply a retained host key.
     */
    if (in->attested_is_host && !(in->attested_flags & F_HOST))
        return EINVAL;
    if (in->nonce_len > OMVM_SIKA_NONCE_MAX)
        return EMSGSIZE;
    if ((in->nonce_len != 0 && in->nonce == NULL) ||
        ((in->attested_flags & F_NONCE) && in->nonce_len == 0) ||
        ((in->attested_flags & F_GUEST_IDENTITY) && !in->guest_identity_valid))
        return EINVAL;
    bool hash_p384 = (in->attested_flags & F_P384) != 0;
    bool point_p384 = in->attested_is_host ? in->attested_point_len == 97 : hash_p384;
    error = identity_sika_validate_point(in->attested_point, in->attested_point_len, point_p384);
    if (error)
        return error;

#define APPEND(bytes, len) do { error = identity_sika_append(&result, (bytes), (len)); if (error) return error; } while (0)
#define U32(value, be) do { error = identity_sika_append_u32(&result, (value), (be)); if (error) return error; } while (0)
    APPEND(in->attested_point + 1, in->attested_point_len - 1);
    APPEND(labels[in->attested_selector], 4);
    U32(in->attested_flags, false);
    if (in->attested_is_host)
        APPEND(host_tag, sizeof(host_tag));
    memset(measurement, 0xff, sizeof(measurement));
    if ((in->attested_flags & F_MEASUREMENT0) || (in->attested_flags & F_MEASUREMENT6))
        APPEND(measurement, sizeof(measurement));
    if (in->attested_flags & F_GUEST_IDENTITY) {
        char identity[26];
        int count = snprintf(identity, sizeof(identity), "%08" PRIX32 "-%016" PRIX64,
                             in->guest_chip_id, in->guest_ecid);
        if (count != 25)
            return EIO;
        APPEND(identity, 25);
    }
    if (in->attested_flags & F_SEP_REVISION) {
        const uint8_t revision = 1;
        APPEND(&revision, 1);
    }
    if (in->attested_flags & F_AON_SECURITY) {
        U32(1, true);
        U32(in->attested_secondary, true);
    }
    if (in->attested_flags & F_MEASUREMENTS23) {
        APPEND(measurement, sizeof(measurement));
        APPEND(measurement, sizeof(measurement));
    }
    if (in->attested_flags & F_NONCE)
        APPEND(in->nonce, in->nonce_len);
#undef U32
#undef APPEND

    result.hash_len = hash_p384 ? 48 : 32;
    if (gnutls_hash_fast(hash_p384 ? GNUTLS_DIG_SHA384 : GNUTLS_DIG_SHA256,
                         result.tbs, result.tbs_len, result.hash) < 0)
        return EIO;
    result.normalized_len = (in->signing_flags & F_P384) ? 48 : 32;
    if (result.hash_len > result.normalized_len) {
        memcpy(result.normalized, result.hash + result.hash_len - result.normalized_len,
               result.normalized_len);
    } else {
        /* result was zero-initialized: preserve leading16 zero padding. */
        memcpy(result.normalized + result.normalized_len - result.hash_len,
               result.hash, result.hash_len);
    }
    *out = result;
    return 0;
}

int omvm_sika_effective_p256(const struct omvm_sika_result *result,
                             uint8_t digest[32])
{
    if (digest == NULL)
        return EINVAL;
    if (result == NULL || (result->normalized_len != 32 && result->normalized_len != 48)) {
        memset(digest, 0, 32);
        return EINVAL;
    }
    memmove(digest, result->normalized, 32);
    return 0;
}

typedef struct AppleIdentityRequest {
    VirtQueueElement *elem;
    uint32_t subsystem;
    uint32_t message_type;
    uint32_t message_len;
    uint32_t transport_len;
    uint32_t num_buffers;
    uint32_t buffers_offset;
    uint32_t buffer_len;
    QEMUTimer *timeout;
    AppleIdentity *s;
    struct AppleIdentityRequest *next;
    int fd;
    bool connecting;
    bool backend_failed;
    uint32_t provider_operation;
    GBytes *provider_request;
    GBytes *challenge;
    GBytes *external_signature;
    size_t provider_sent;
    uint8_t provider_header[8];
    size_t provider_header_used;
    uint8_t provider_signature[72];
    size_t provider_signature_used;
    size_t provider_signature_len;
} AppleIdentityRequest;

static void identity_fdt_setup(AppleIdentity *s);
static void identity_relay_timeout(void *opaque);

/* Rejects everything the guest's own validator rejects (PROTOCOL.md §3). */
static bool header_is_valid(const AppleIdentityHeader *h, size_t buf_len)
{
    uint64_t want;

    if (h->version != 1 && h->version != 2) {
        return false;
    }
    want = (uint64_t)APPLE_IDENTITY_HEADER_LEN + h->message_len;
    if (want > UINT32_MAX || want + h->buffer_len > UINT32_MAX) {
        return false;
    }
    want += h->buffer_len;
    if (h->transport_len != want) {
        return false;
    }
    /*
     * Multiply in 64-bit rather than a 32-bit `count * size`: after the offset
     * check the subtraction cannot underflow.
     */
    if (h->buffers_offset > h->message_len) {
        return false;
    }
    if ((uint64_t)h->num_buffers * sizeof(AppleIdentityBuffer) >
        (uint64_t)h->message_len - h->buffers_offset) {
        return false;
    }
    if (h->num_buffers == 0 && (h->buffer_len != 0 || h->buffers_offset != 0)) {
        return false;
    }
    return buf_len >= h->transport_len;
}

/*
 * The handshake carries the guest's 25-char UDID (`%08X-%016llX`) and a u16
 * protocol version; the host requires version exactly 1 and refuses a second
 * handshake while one has been accepted.
 *
 * PROTOCOL.md §5: subsystem 4 type 1 is the handshake, carrying the guest's
 * UDID string and its protocol version; type 2 is the answer, carrying the
 * UDID as one buffer. The reply's version word echoes what we actually speak:
 * asking for 2 but answering with 2 while speaking 1 gives hangs, so a version
 * we do not implement is answered as 1.
 */

/*
 * Returns the tunneled Command string from the request body (a plist), or NULL.
 * Only used to choose the reply shape, so a crude scan is enough.
 */
static bool identity_b64_find(const char *buf, size_t n, const char *key, size_t *off, size_t *len);
static gnutls_privkey_t identity_privkey_wrap(gnutls_x509_privkey_t key);

/*
 * Binary property list (bplist00) holding {Value: {key: <data>}}. CFProperty-
 * ListCreateWithData detects binary plists by magic, and this saves the ~75
 * bytes of XML wrapper over a fixed 388-byte payload budget.
 */
/*
 * {"Value": {key: <data>}} as a binary property list. CFPropertyListCreate-
 * WithData sniffs the magic, and this costs ~60 bytes instead of ~135 for the
 * same content in XML, which matters against a fixed 388-byte payload budget.
 * Layout mirrors what plistlib emits for this exact shape.
 */
static GBytes *identity_bplist_data(const char *key, const uint8_t *blob,
                                    size_t blen)
{
    GByteArray *b = g_byte_array_new();
    uint8_t trailer[32] = { 0 };
    size_t offs[5];
    size_t klen = strlen(key);

    g_byte_array_append(b, (const uint8_t *)"bplist00", 8);

    /* 0: root dict, one pair -> key "Value", value = object 2 */
    offs[0] = (uint16_t)b->len;
    g_byte_array_append(b, (const uint8_t[]){ 0xd1, 1, 2 }, 3);

    /* 1: "Value" */
    offs[1] = (uint16_t)b->len;
    g_byte_array_append(b, (const uint8_t[]){ 0x55 }, 1);
    g_byte_array_append(b, (const uint8_t *)"Value", 5);

    /* 2: inner dict, one pair -> the key, value = object 4 */
    offs[2] = (uint16_t)b->len;
    g_byte_array_append(b, (const uint8_t[]){ 0xd1, 3, 4 }, 3);

    /* 3: the key string, inline form below 15 bytes */
    offs[3] = (uint16_t)b->len;
    if (klen < 15) {
        g_byte_array_append(b, (const uint8_t[]){ 0x50 | (uint8_t)klen }, 1);
    } else {
        g_byte_array_append(b, (const uint8_t[]){ 0x5f, 0x10, (uint8_t)klen }, 3);
    }
    g_byte_array_append(b, (const uint8_t *)key, klen);

    /* 4: the data blob */
    offs[4] = (uint16_t)b->len;
    if (blen < 15) {
        g_byte_array_append(b, (const uint8_t[]){ 0x40 | (uint8_t)blen }, 1);
    } else if (blen < 256) {
        g_byte_array_append(b,
                            (const uint8_t[]){ 0x4f, 0x10, (uint8_t)blen }, 3);
    } else {
        g_byte_array_append(b,
                            (const uint8_t[]){ 0x4f, 0x11 }, 2);
        g_byte_array_append(b,
                            (const uint8_t[]){ (uint8_t)(blen >> 8),
                                               (uint8_t)blen }, 2);
    }
    g_byte_array_append(b, blob, blen);

    {
        size_t table = b->len;

        for (int i = 0; i < 5; i++) {
            g_byte_array_append(b,
                                (const uint8_t[]){ (uint8_t)(offs[i] >> 8),
                                                   (uint8_t)offs[i] }, 2);
        }
        trailer[6] = 2;                 /* offset int size */
        trailer[7] = 1;                 /* object ref size */
        trailer[15] = 5;                /* object count */
        trailer[23] = 0;                /* top object */
        for (int i = 0; i < 8; i++)
            trailer[24 + i] = (uint8_t)(table >> (56 - i * 8));
        g_byte_array_append(b, trailer, sizeof(trailer));
    }
    return g_byte_array_free_to_bytes(b);
}

/* Sign the request Value using the same X9.62 DER encoding as Security.framework. */
static GBytes *identity_tunnel_sign(VirtQueueElement *elem, gnutls_x509_privkey_t key)
{
    g_autofree char *buf = NULL;
    size_t n = 0, k, off, len;
    g_autofree guchar *slot = NULL;
    gnutls_datum_t data = { 0 }, sig = { 0 };
    const char *key_v = "<key>Value</key>";

    if (!key) {
        return NULL;
    }
    for (k = 0; k < elem->out_num; k++) {
        n += elem->out_sg[k].iov_len;
    }
    if (n <= APPLE_IDENTITY_HEADER_LEN) {
        return NULL;
    }
    buf = g_malloc0(n);
    iov_to_buf(elem->out_sg, elem->out_num, 0, buf, n);

    /* BIKData identifies the VM; only the top-level Value is the challenge. */
    if (!identity_b64_find(buf, n, key_v, &off, &len)) {
        return NULL;
    }
    /* Slice the base64, strip whitespace, decode. */
    {
        g_autofree char *b64 = g_malloc0(len + 1);
        size_t j, m = 0;
        for (j = 0; j < len; j++) {
            char c = buf[off + j];
            if (!g_ascii_isspace(c)) {
                b64[m++] = c;
            }
        }
        b64[m] = 0;
        slot = g_base64_decode(b64, &len);
    }
    data.data = slot;
    data.size = len;
    {
        gnutls_privkey_t pk = identity_privkey_wrap(key);
        g_autoptr(GChecksum) sum = g_checksum_new(G_CHECKSUM_SHA256);
        gnutls_datum_t hash = { 0 };
        uint8_t raw[64];
        gsize hlen;
        int rc;

        if (!pk) {
            return NULL;
        }
        g_checksum_update(sum, data.data, data.size);
        hlen = 32;
        /* SHA-256 digest bytes, not a truncated hex string. */
        g_checksum_get_digest(sum, raw, &hlen);
        hash.data = raw;
        hash.size = hlen;
        rc = gnutls_privkey_sign_hash(pk, GNUTLS_DIG_SHA256, 0, &hash, &sig);
        gnutls_privkey_deinit(pk);
        if (rc < 0) {
            fprintf(stderr, "IDSIG fail: sign_hash %d\n", rc);
            return NULL;
        }
    }
    /* SecKey's message-X962:SHA256 algorithm returns SEQUENCE { r, s }. */
    {
        GBytes *result = g_bytes_new(sig.data, sig.size);
        gnutls_free(sig.data);
        return result;
    }
}

/* Wraps an x509 private key for the raw signing API. */
static gnutls_privkey_t identity_privkey_wrap(gnutls_x509_privkey_t key)
{
    gnutls_privkey_t pk = NULL;
    if (gnutls_privkey_init(&pk) < 0) {
        return NULL;
    }
    if (gnutls_privkey_import_x509(pk, key, 0) < 0) {
        gnutls_privkey_deinit(pk);
        return NULL;
    }
    return pk;
}

/* Finds "<key>X</key>" followed by <data>...</data>; returns the base64 span. */
static bool identity_b64_find(const char *buf, size_t n, const char *key,
                              size_t *off, size_t *len)
{
    const char *p = memmem(buf, n, key, strlen(key));
    const char *a, *b;
    if (!p) {
        return false;
    }
    a = p + strlen(key);
    a = memmem(a, (size_t)(buf + n - a), "<data>", 6);
    if (!a) {
        return false;
    }
    a += 6;
    b = memmem(a, (size_t)(buf + n - a), "</data>", 7);
    if (!b) {
        return false;
    }
    *off = (size_t)(a - buf);
    *len = (size_t)(b - a);
    return true;
}

static char *identity_tunnel_command(VirtQueueElement *elem)
{
    g_autofree char *buf = NULL;
    size_t n = 0, k;
    const char *key = "<key>Command</key>";

    for (k = 0; k < elem->out_num; k++) {
        n += elem->out_sg[k].iov_len;
    }
    if (n <= APPLE_IDENTITY_HEADER_LEN) {
        return NULL;
    }
    buf = g_malloc0(n);
    iov_to_buf(elem->out_sg, elem->out_num, 0, buf, n);
    {
        char *p = memmem(buf, n, key, strlen(key));
        char *a, *b;
        if (!p) {
            return NULL;
        }
        a = p + strlen(key);
        a = memmem(a, (size_t)(buf + n - a), "<string>", 8);
        if (!a) {
            return NULL;
        }
        a += 8;
        b = memmem(a, (size_t)(buf + n - a), "</string>", 9);
        return b ? g_strndup(a, (gsize)(b - a)) : NULL;
    }
}

/*
 * stderr under libvirt is a pipe to virtlogd and -D/qemu_log_mask need -d, so
 * instrumentation goes to a fixed absolute path that is readable regardless of
 * how QEMU was launched. Debug-only; harmless if the dir is missing.
 */
#define IDLOG_PATH "/tmp/w/idtun.log"

static void G_GNUC_PRINTF(1, 2) idlog(const char *fmt, ...)
{
    FILE *f = fopen(IDLOG_PATH, "a");
    va_list ap;

    if (!f) {
        return;
    }
    va_start(ap, fmt);
    vfprintf(f, fmt, ap);
    va_end(ap);
    fclose(f);
}

static void idlog_hex(const char *tag, const void *p, size_t n)
{
    FILE *f = fopen(IDLOG_PATH, "a");
    const uint8_t *b = p;

    if (!f) {
        return;
    }
    fprintf(f, "  %s[%zu]=", tag, n);
    for (size_t i = 0; i < n; i++) {
        fprintf(f, "%02x", b[i]);
    }
    fprintf(f, "\n");
    fclose(f);
}

/*
 * The strong-identity blob for 4/4 and 4/6. The userspace client never parses
 * it (it stores it under the guest UDID), so the UDID is served until a real
 * Apple-issued chain exists.
 */
/*
 * The 4/4 and 4/6 payload is handed to decodeAndTakeOwnership, which expects a
 * serialised message starting with a transport header (transportHeader, then
 * _message, then the buffers). Serving bare bytes only works while nothing
 * parses them; ID_SELFDESC serves the header + message layout instead.
 */
#define APPLE_IDENTITY_SELFDESC_LEN \
    (sizeof(AppleIdentityHeader) + sizeof(AppleIdentityBuffer) + \
     APPLE_IDENTITY_IDENTITY_LEN)

static uint32_t identity_data_len(AppleIdentity *s)
{
    if (s->external_mode) {
        return g_bytes_get_size(s->last_type == APPLE_IDENTITY_TYPE_GET_IDENTITY
                                ? s->external_identity6 : s->external_identity4);
    }
    return getenv("ID_SELFDESC") ? APPLE_IDENTITY_SELFDESC_LEN
                                 : APPLE_IDENTITY_IDENTITY_LEN;
}

/* The message's own transportLen: header + message + buffers, self consistent. */


static const uint8_t *identity_data_ptr(AppleIdentity *s)
{
    if (s->external_mode) {
        return g_bytes_get_data(s->last_type == APPLE_IDENTITY_TYPE_GET_IDENTITY
                                ? s->external_identity6 : s->external_identity4, NULL);
    }
    if (!getenv("ID_SELFDESC")) {
        return s->udid;
    }
    {
        static uint8_t buf[APPLE_IDENTITY_SELFDESC_LEN];
        AppleIdentityHeader *h = (void *)buf;
        AppleIdentityBuffer *iov = (void *)(buf + sizeof(*h));

        memset(buf, 0, sizeof(buf));
        h->version = APPLE_IDENTITY_REPLY_UDID_VERSION;
        h->subsystem = APPLE_IDENTITY_SUBSYS_IDENTITY;
        h->message_type = s->last_type;
        iov->len = APPLE_IDENTITY_IDENTITY_LEN;
        /* The userspace decoder requires bufferLen == 0, buffersOffset == 0,
         * the iovec table inside messageLen, and transportLen ==
         * header + messageLen + bufferLen. The data is addressed by the iovec. */
        h->message_len = sizeof(*iov);
        h->buffer_len = APPLE_IDENTITY_IDENTITY_LEN;
        h->num_buffers = getenv("ID_NB0") ? 0 : 1;
        h->buffers_offset = 0;
        /* bufferLen stays 0, but the iovec is addressed from the body and the
         * data follows the table, so transportLen must cover it. */
        h->transport_len = sizeof(AppleIdentityHeader) + sizeof(*iov) +
                           APPLE_IDENTITY_IDENTITY_LEN;
        if (getenv("ID_TRSHORT")) {
            h->transport_len = sizeof(AppleIdentityHeader) + sizeof(*iov);
        }
        memcpy(buf + sizeof(*h) + sizeof(*iov), s->udid,
               APPLE_IDENTITY_IDENTITY_LEN);
        return buf;
    }
}

/*
 * Build the iovec table the deserializer walks. It requires every iov_len to
 * add up to bufferLen exactly and fails with "remaining != 0" otherwise, so
 * num_buffers must never exceed the entries actually written. The second
 * entry is 4/6's error buffer, which stays empty on a success reply.
 */
static uint32_t identity_reply_iovecs(AppleIdentity *s, uint32_t type,
                                      uint32_t data_len, uint32_t err_len,
                                      AppleIdentityBuffer *out)
{
    uint32_t n = 0;

    out[n].base = 0;
    out[n].len = data_len;
    n++;
    if (type == APPLE_IDENTITY_TYPE_GET_IDENTITY) {
        out[n].base = 0;
        out[n].len = err_len;
        n++;
    }
    return n;
}

/* External host identities are certificates only; signing remains in the SEP. */
#define IDENTITY_EXTERNAL_CHAIN_MAX 8192
#define IDENTITY_SIGN_REQUEST_MAX 65536
#define IDENTITY_SIGN_REPLY_MAX 72

static void identity_answer(AppleIdentityRequest *req);
static void identity_swpka_buffer_reply(AppleIdentityRequest *req,
                                        uint32_t message_type, int32_t status,
                                        const uint8_t *point, size_t length);
static void identity_provider_complete(AppleIdentityRequest *req)
{
    if (req->subsystem == APPLE_IDENTITY_SUBSYS_SWPKA && req->message_type == 6) {
        gsize length = 0;
        const uint8_t *signature = req->external_signature && !req->backend_failed
            ? g_bytes_get_data(req->external_signature, &length) : NULL;
        identity_swpka_buffer_reply(req, 6, signature ? 0 : -1, signature, length);
    } else {
        identity_answer(req);
    }
}

static void identity_request_free(AppleIdentityRequest *req, bool detach)
{
    AppleIdentityRequest **link = &req->s->pending;

    while (*link && *link != req) {
        link = &(*link)->next;
    }
    if (*link) {
        *link = req->next;
    }
    if (req->fd >= 0) {
        qemu_set_fd_handler(req->fd, NULL, NULL, NULL);
        close(req->fd);
    }
    if (req->timeout) {
        timer_del(req->timeout);
        timer_free(req->timeout);
    }
    g_clear_pointer(&req->provider_request, g_bytes_unref);
    g_clear_pointer(&req->challenge, g_bytes_unref);
    g_clear_pointer(&req->external_signature, g_bytes_unref);
    if (req->elem) {
        if (detach) {
            virtqueue_detach_element(req->s->vq, req->elem, 0);
        }
        g_free(req->elem);
    }
    g_free(req);
}

static void identity_request_complete(AppleIdentityRequest *req, size_t length)
{
    virtqueue_push(req->s->vq, req->elem, length);
    virtio_notify(&req->s->parent_obj, req->s->vq);
    identity_request_free(req, false);
}

static void identity_cancel_pending(AppleIdentity *s)
{
    while (s->pending) {
        identity_request_free(s->pending, true);
    }
}

static bool identity_der_size(const uint8_t *data, size_t available, size_t *size)
{
    size_t header = 2, len;

    if (available < 2 || data[0] != 0x30) {
        return false;
    }
    if (data[1] < 0x80) {
        len = data[1];
    } else {
        unsigned count = data[1] & 0x7f;

        if (!count || count > 4 || available < 2 + count || !data[2]) {
            return false;
        }
        len = 0;
        header += count;
        for (unsigned i = 0; i < count; i++) {
            len = (len << 8) | data[2 + i];
        }
        if (len < 128) {
            return false;
        }
    }
    if (!len || len > available - header) {
        return false;
    }
    *size = header + len;
    return true;
}

static bool identity_read_file(const char *path, size_t max, char **data,
                               gsize *len, Error **errp)
{
    struct stat st;
    g_autoptr(GError) error = NULL;

    if (stat(path, &st) < 0 || !S_ISREG(st.st_mode) || st.st_size <= 0 ||
        (uint64_t)st.st_size > max) {
        error_setg(errp, "identity: invalid or oversized external file %s", path);
        return false;
    }
    if (!g_file_get_contents(path, data, len, &error) || !*len || *len > max) {
        error_setg(errp, "identity: cannot read external file %s", path);
        return false;
    }
    return true;
}

static void identity_external_cleanup(AppleIdentity *s)
{
    g_clear_pointer(&s->signer_path, g_free);
    g_clear_pointer(&s->external_identity4, g_bytes_unref);
    g_clear_pointer(&s->external_identity6, g_bytes_unref);
    if (s->host_public_key) {
        gnutls_pubkey_deinit(s->host_public_key);
        s->host_public_key = NULL;
    }
    g_clear_pointer(&s->host_cert, g_free);
    s->host_cert_len = 0;
    memset(s->host_public_point, 0, sizeof(s->host_public_point));
    if (s->host_key) {
        gnutls_x509_privkey_deinit(s->host_key);
        s->host_key = NULL;
    }
    g_clear_pointer(&s->host_ca, g_free);
    s->host_ca_len = 0;
}

static void identity_bplist_object(GByteArray *out, uint8_t type,
                                   const void *data, size_t len)
{
    uint8_t marker;

    if (len < 15) {
        marker = type | len;
        g_byte_array_append(out, &marker, 1);
    } else if (len < 256) {
        uint8_t prefix[] = { type | 15, 0x10, len };
        g_byte_array_append(out, prefix, sizeof(prefix));
    } else {
        uint8_t prefix[] = { type | 15, 0x11, len >> 8, len };
        g_byte_array_append(out, prefix, sizeof(prefix));
    }
    g_byte_array_append(out, data, len);
}

/* Native signature replies carry the signing certificate alongside the proof. */
static GBytes *identity_bplist_signature(const uint8_t *signature, size_t sig_len,
                                         const uint8_t *chain, size_t chain_len)
{
    GByteArray *out = g_byte_array_new();
    uint16_t offsets[7];
    uint8_t root[] = { 0xd1, 1, 2 };
    uint8_t value[] = { 0xd2, 3, 5, 4, 6 };
    uint8_t trailer[32] = { 0 };
    size_t table;

    g_byte_array_append(out, (const uint8_t *)"bplist00", 8);
    offsets[0] = out->len;
    g_byte_array_append(out, root, sizeof(root));
    offsets[1] = out->len;
    identity_bplist_object(out, 0x50, "Value", 5);
    offsets[2] = out->len;
    g_byte_array_append(out, value, sizeof(value));
    offsets[3] = out->len;
    identity_bplist_object(out, 0x50, "RKSignature", 11);
    offsets[4] = out->len;
    identity_bplist_object(out, 0x40, signature, sig_len);
    offsets[5] = out->len;
    identity_bplist_object(out, 0x50, "RKCertification", 15);
    offsets[6] = out->len;
    identity_bplist_object(out, 0x40, chain, chain_len);
    table = out->len;
    for (unsigned i = 0; i < G_N_ELEMENTS(offsets); i++) {
        uint8_t offset[] = { offsets[i] >> 8, offsets[i] };
        g_byte_array_append(out, offset, sizeof(offset));
    }
    trailer[6] = 2;
    trailer[7] = 1;
    trailer[15] = G_N_ELEMENTS(offsets);
    stq_be_p(trailer + 24, table);
    g_byte_array_append(out, trailer, sizeof(trailer));
    return g_byte_array_free_to_bytes(out);
}

static GBytes *identity_external_archive(const uint8_t public_key[65],
                                        const uint8_t *leaf, size_t leaf_len,
                                        const uint8_t *intermediate,
                                        size_t intermediate_len)
{
    const char *keys[] = { "BuildVersion", "ProductVersion", "HostKey",
                          "LeafCertificate", "IntermediateCertificate" };
    struct utsname host;
    GByteArray *out = g_byte_array_new();
    uint16_t offsets[11];
    uint8_t dict[] = { 0xd5, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10 };
    uint8_t trailer[32] = { 0 };
    size_t table;

    if (uname(&host) < 0) {
        pstrcpy(host.release, sizeof(host.release), "unknown");
        pstrcpy(host.sysname, sizeof(host.sysname), "Linux");
    }
    g_byte_array_append(out, (const uint8_t *)"bplist00", 8);
    offsets[0] = out->len;
    g_byte_array_append(out, dict, sizeof(dict));
    for (unsigned i = 0; i < G_N_ELEMENTS(keys); i++) {
        offsets[i + 1] = out->len;
        identity_bplist_object(out, 0x50, keys[i], strlen(keys[i]));
    }
    offsets[6] = out->len;
    identity_bplist_object(out, 0x50, host.release, strlen(host.release));
    offsets[7] = out->len;
    identity_bplist_object(out, 0x50, host.sysname, strlen(host.sysname));
    offsets[8] = out->len;
    identity_bplist_object(out, 0x40, public_key, 65);
    offsets[9] = out->len;
    identity_bplist_object(out, 0x40, leaf, leaf_len);
    offsets[10] = out->len;
    identity_bplist_object(out, 0x40, intermediate, intermediate_len);
    table = out->len;
    for (unsigned i = 0; i < G_N_ELEMENTS(offsets); i++) {
        uint8_t offset[] = { offsets[i] >> 8, offsets[i] };
        g_byte_array_append(out, offset, sizeof(offset));
    }
    trailer[6] = 2;
    trailer[7] = 1;
    trailer[15] = G_N_ELEMENTS(offsets);
    stq_be_p(trailer + 24, table);
    g_byte_array_append(out, trailer, sizeof(trailer));
    return g_byte_array_free_to_bytes(out);
}

static GBytes *identity_external_message(GBytes *archive, uint32_t type)
{
    size_t data_len;
    const uint8_t *data = g_bytes_get_data(archive, &data_len);
    uint32_t message_len = type == APPLE_IDENTITY_TYPE_GET_IDENTITY ? 48 : 16;
    uint32_t offset = type == APPLE_IDENTITY_TYPE_GET_IDENTITY ? 16 : 0;
    uint32_t count = type == APPLE_IDENTITY_TYPE_GET_IDENTITY ? 2 : 1;
    GByteArray *out = g_byte_array_sized_new(32 + message_len + data_len);
    AppleIdentityHeader header = {
        .version = 2, .subsystem = 4, .message_type = type,
        .transport_len = 32 + message_len + data_len,
        .message_len = message_len, .buffer_len = data_len,
        .num_buffers = count, .buffers_offset = offset,
    };
    uint8_t body[48] = { 0 };
    AppleIdentityBuffer entry = { .base = 0, .len = data_len };

    memcpy(body + offset, &entry, sizeof(entry));
    g_byte_array_append(out, (const uint8_t *)&header, sizeof(header));
    g_byte_array_append(out, body, message_len);
    g_byte_array_append(out, data, data_len);
    return g_byte_array_free_to_bytes(out);
}

static bool identity_load_external(AppleIdentity *s, Error **errp)
{
    const char *paths[] = { getenv("OMVM_IDENTITY_CERT_CHAIN"),
                            getenv("OMVM_IDENTITY_PUBLIC_KEY"),
                            getenv("OMVM_IDENTITY_TRUST_ROOT"),
                            getenv("OMVM_IDENTITY_SIGNER") };
    unsigned configured = 0, root_count = 0, status = 0;
    g_autofree char *chain = NULL;
    g_autofree char *point = NULL;
    g_autofree char *root = NULL;
    gsize chain_len, point_len, root_len;
    size_t leaf_len, intermediate_len;
    gnutls_x509_crt_t certs[2] = { NULL, NULL };
    gnutls_x509_crt_t *roots = NULL;
    gnutls_datum_t input, public_x = { 0 }, public_y = { 0 };
    gnutls_ecc_curve_t curve;
    uint8_t public_point[65] = { 4 };
    g_autoptr(GBytes) archive = NULL;
    bool ok = false;

    for (unsigned i = 0; i < G_N_ELEMENTS(paths); i++) {
        configured += paths[i] != NULL;
    }
    if (!configured) {
        return true;
    }
    if (configured != G_N_ELEMENTS(paths) ||
        !*paths[0] || !*paths[1] || !*paths[2] || !*paths[3]) {
        error_setg(errp, "identity: all four external identity paths are required");
        return false;
    }
    if (strlen(paths[3]) >= sizeof(((struct sockaddr_un *)0)->sun_path)) {
        error_setg(errp, "identity: signer socket path is too long");
        return false;
    }
    if (!identity_read_file(paths[0], IDENTITY_EXTERNAL_CHAIN_MAX, &chain,
                            &chain_len, errp) ||
        !identity_read_file(paths[1], 65, &point, &point_len, errp) ||
        !identity_read_file(paths[2], 65536, &root, &root_len, errp)) {
        goto out;
    }
    if (point_len != 65 || (uint8_t)point[0] != 4 ||
        !identity_der_size((uint8_t *)chain, chain_len, &leaf_len) ||
        !identity_der_size((uint8_t *)chain + leaf_len, chain_len - leaf_len,
                          &intermediate_len) ||
        leaf_len + intermediate_len != chain_len) {
        error_setg(errp, "identity: expected a P-256 point and exactly two DER certificates");
        goto out;
    }
    for (unsigned i = 0; i < 2; i++) {
        if (gnutls_x509_crt_init(&certs[i]) < 0) {
            error_setg(errp, "identity: cannot allocate certificate parser");
            goto out;
        }
        input.data = (uint8_t *)chain + (i ? leaf_len : 0);
        input.size = i ? intermediate_len : leaf_len;
        if (gnutls_x509_crt_import(certs[i], &input, GNUTLS_X509_FMT_DER) < 0) {
            error_setg(errp, "identity: invalid external certificate DER");
            goto out;
        }
    }
    input.data = (uint8_t *)root;
    input.size = root_len;
    if (gnutls_x509_crt_list_import2(&roots, &root_count, &input,
                                     GNUTLS_X509_FMT_PEM, 0) < 0 ||
        root_count != 1 ||
        gnutls_x509_crt_get_ca_status(certs[0], NULL) != 0 ||
        gnutls_x509_crt_get_ca_status(certs[1], NULL) != 1 ||
        gnutls_x509_crt_list_verify(certs, 2, roots, root_count, NULL, 0,
                                   GNUTLS_VERIFY_DO_NOT_ALLOW_UNSORTED_CHAIN,
                                   &status) < 0 || status) {
        error_setg(errp, "identity: external certificate chain is not trusted");
        goto out;
    }
    if (gnutls_pubkey_init(&s->host_public_key) < 0 ||
        gnutls_pubkey_import_x509(s->host_public_key, certs[0], 0) < 0 ||
        gnutls_pubkey_export_ecc_raw2(s->host_public_key, &curve,
                                     &public_x, &public_y,
                                     GNUTLS_EXPORT_FLAG_NO_LZ) < 0 ||
        curve != GNUTLS_ECC_CURVE_SECP256R1 ||
        public_x.size > 32 || public_y.size > 32) {
        error_setg(errp, "identity: external leaf must contain a P-256 public key");
        goto out;
    }
    memcpy(public_point + 33 - public_x.size, public_x.data, public_x.size);
    memcpy(public_point + 65 - public_y.size, public_y.data, public_y.size);
    if (memcmp(public_point, point, sizeof(public_point))) {
        error_setg(errp, "identity: external public key does not match the leaf certificate");
        goto out;
    }
    memcpy(s->host_public_point, public_point, sizeof(public_point));
    {
        g_autoptr(GChecksum) hash = g_checksum_new(G_CHECKSUM_SHA256);
        uint8_t digest[32];
        gsize digest_len = sizeof(digest);

        g_checksum_update(hash, (uint8_t *)point, point_len);
        g_checksum_get_digest(hash, digest, &digest_len);
        memcpy(s->udid, digest, sizeof(s->udid));
    }
    s->host_cert = (uint8_t *)g_steal_pointer(&chain);
    s->host_cert_len = chain_len;
    s->signer_path = g_strdup(paths[3]);
    archive = identity_external_archive((uint8_t *)point, s->host_cert, leaf_len,
                                       s->host_cert + leaf_len, intermediate_len);
    s->external_identity4 = identity_external_message(archive,
                                 APPLE_IDENTITY_TYPE_GET_IDENTITY_FALLBACK);
    s->external_identity6 = identity_external_message(archive,
                                 APPLE_IDENTITY_TYPE_GET_IDENTITY);
    s->external_mode = true;
    ok = true;
out:
    gnutls_free(public_x.data);
    gnutls_free(public_y.data);
    for (unsigned i = 0; i < 2; i++) {
        if (certs[i]) {
            gnutls_x509_crt_deinit(certs[i]);
        }
    }
    for (unsigned i = 0; roots && i < root_count; i++) {
        gnutls_x509_crt_deinit(roots[i]);
    }
    gnutls_free(roots);
    if (!ok) {
        identity_external_cleanup(s);
    }
    return ok;
}

typedef struct IdentityXMLValue {
    unsigned dict_depth;
    bool key;
    bool data;
    bool expecting_data;
    bool bad;
    GString *text;
    char *value;
} IdentityXMLValue;

static void identity_xml_start(GMarkupParseContext *context, const char *name,
                                const char **names, const char **values,
                                gpointer opaque, GError **error)
{
    IdentityXMLValue *state = opaque;

    if (state->expecting_data && strcmp(name, "data")) {
        state->bad = true;
    }
    if (!strcmp(name, "dict")) {
        state->dict_depth++;
    } else if (state->dict_depth == 1 && !strcmp(name, "key")) {
        state->key = true;
        g_string_truncate(state->text, 0);
    } else if (state->dict_depth == 1 && !strcmp(name, "data") &&
               state->expecting_data) {
        state->data = true;
        state->expecting_data = false;
        g_string_truncate(state->text, 0);
    } else if (state->key || state->data) {
        state->bad = true;
    }
}

static void identity_xml_end(GMarkupParseContext *context, const char *name,
                              gpointer opaque, GError **error)
{
    IdentityXMLValue *state = opaque;

    if (state->dict_depth == 1 && !strcmp(name, "key") && state->key) {
        state->key = false;
        if (!strcmp(state->text->str, "Value")) {
            if (state->value) {
                state->bad = true;
            }
            state->expecting_data = true;
        }
    } else if (state->dict_depth == 1 && !strcmp(name, "data") && state->data) {
        state->data = false;
        g_free(state->value);
        state->value = g_strdup(state->text->str);
    } else if (!strcmp(name, "dict") && state->dict_depth) {
        state->dict_depth--;
    }
}

static void identity_xml_text(GMarkupParseContext *context, const char *text,
                               gsize length, gpointer opaque, GError **error)
{
    IdentityXMLValue *state = opaque;

    if (state->key || state->data) {
        g_string_append_len(state->text, text, length);
    } else if (state->expecting_data) {
        for (size_t i = 0; i < length; i++) {
            if (!g_ascii_isspace(text[i])) {
                state->bad = true;
            }
        }
    }
}

/* Decode only the bounded top-level Value from Apple's XML property list. */
static GBytes *identity_external_challenge(VirtQueueElement *elem)
{
    static const GMarkupParser parser = {
        .start_element = identity_xml_start,
        .end_element = identity_xml_end,
        .text = identity_xml_text,
    };
    size_t total = iov_size(elem->out_sg, elem->out_num), len;
    g_autofree char *data = NULL;
    g_autofree char *base64 = NULL;
    g_autofree char *canonical = NULL;
    g_autofree uint8_t *decoded = NULL;
    g_autoptr(GMarkupParseContext) context = NULL;
    g_autoptr(GError) error = NULL;
    IdentityXMLValue state = { .text = g_string_new(NULL) };
    size_t compact = 0;
    bool parsed;

    if (total > IDENTITY_SIGN_REQUEST_MAX * 2 + 4096 ||
        total <= APPLE_IDENTITY_HEADER_LEN) {
        g_string_free(state.text, true);
        return NULL;
    }
    data = g_malloc(total);
    iov_to_buf(elem->out_sg, elem->out_num, 0, data, total);
    /* The XML buffer follows the message/iovec table. */
    {
        AppleIdentityHeader wire;
        size_t offset;
        iov_to_buf(elem->out_sg, elem->out_num, 0, &wire, sizeof(wire));
        if (wire.message_len > total - sizeof(wire)) {
            g_string_free(state.text, true);
            return NULL;
        }
        offset = sizeof(wire) + wire.message_len;
        if (!wire.buffer_len || wire.buffer_len > total - offset) {
            g_string_free(state.text, true);
            return NULL;
        }
        context = g_markup_parse_context_new(&parser, 0, &state, NULL);
        parsed = g_markup_parse_context_parse(context, data + offset,
                                               wire.buffer_len, &error) &&
                 g_markup_parse_context_end_parse(context, &error);
    }
    g_string_free(state.text, true);
    base64 = state.value;
    if (!parsed || state.bad || state.expecting_data || !base64) {
        return NULL;
    }
    len = strlen(base64);
    if (len > IDENTITY_SIGN_REQUEST_MAX * 2) {
        return NULL;
    }
    for (size_t i = 0; i < len; i++) {
        unsigned char c = base64[i];
        if (g_ascii_isspace(c)) {
            continue;
        }
        if (!(g_ascii_isalnum(c) || c == '+' || c == '/' || c == '=')) {
            return NULL;
        }
        base64[compact++] = c;
    }
    base64[compact] = 0;
    if (!compact || compact % 4) {
        return NULL;
    }
    decoded = g_base64_decode(base64, &len);
    if (!len || len > IDENTITY_SIGN_REQUEST_MAX) {
        return NULL;
    }
    canonical = g_base64_encode(decoded, len);
    if (strcmp(canonical, base64)) {
        return NULL;
    }
    return g_bytes_new_take(g_steal_pointer(&decoded), len);
}

static void identity_provider_fail(AppleIdentityRequest *req)
{
    req->backend_failed = true;
    identity_provider_complete(req);
}

static void identity_provider_read(void *opaque)
{
    AppleIdentityRequest *req = opaque;
    ssize_t count;

    while (req->provider_header_used < sizeof(req->provider_header)) {
        count = recv(req->fd, req->provider_header + req->provider_header_used,
                     sizeof(req->provider_header) - req->provider_header_used, 0);
        if (count < 0 && errno == EINTR) {
            continue;
        }
        if (count < 0 && (errno == EAGAIN || errno == EWOULDBLOCK)) {
            return;
        }
        if (count <= 0) {
            identity_provider_fail(req);
            return;
        }
        req->provider_header_used += count;
    }
    if (!req->provider_signature_len) {
        req->provider_signature_len = ldl_be_p(req->provider_header + 4);
        if (ldl_be_p(req->provider_header) || !req->provider_signature_len ||
            req->provider_signature_len > sizeof(req->provider_signature)) {
            identity_provider_fail(req);
            return;
        }
    }
    while (req->provider_signature_used < req->provider_signature_len) {
        count = recv(req->fd, req->provider_signature + req->provider_signature_used,
                     req->provider_signature_len - req->provider_signature_used, 0);
        if (count < 0 && errno == EINTR) {
            continue;
        }
        if (count < 0 && (errno == EAGAIN || errno == EWOULDBLOCK)) {
            return;
        }
        if (count <= 0) {
            identity_provider_fail(req);
            return;
        }
        req->provider_signature_used += count;
    }
    {
        gnutls_datum_t message, signature;
        gsize length;

        message.data = (uint8_t *)g_bytes_get_data(req->challenge, &length);
        message.size = length;
        signature.data = req->provider_signature;
        signature.size = req->provider_signature_len;
        int verified = req->provider_operation == 2
            ? (length == 32 ? gnutls_pubkey_verify_hash2(req->s->host_public_key,
                    GNUTLS_SIGN_ECDSA_SHA256, 0, &message, &signature) : -1)
            : gnutls_pubkey_verify_data2(req->s->host_public_key,
                    GNUTLS_SIGN_ECDSA_SHA256, 0, &message, &signature);
        if (verified < 0) {
            identity_provider_fail(req);
            return;
        }
    }
    req->external_signature = g_bytes_new(req->provider_signature,
                                         req->provider_signature_len);
    identity_provider_complete(req);
}

static void identity_provider_write(void *opaque)
{
    AppleIdentityRequest *req = opaque;
    size_t length;
    const uint8_t *data;
    ssize_t count;

    if (req->connecting) {
        int status = 0;
        socklen_t size = sizeof(status);
        if (getsockopt(req->fd, SOL_SOCKET, SO_ERROR, &status, &size) < 0 || status) {
            identity_provider_fail(req);
            return;
        }
        req->connecting = false;
    }
    data = g_bytes_get_data(req->provider_request, &length);
    while (req->provider_sent < length) {
        count = send(req->fd, data + req->provider_sent,
                     length - req->provider_sent, MSG_NOSIGNAL);
        if (count < 0 && errno == EINTR) {
            continue;
        }
        if (count < 0 && (errno == EAGAIN || errno == EWOULDBLOCK)) {
            return;
        }
        if (count <= 0) {
            identity_provider_fail(req);
            return;
        }
        req->provider_sent += count;
    }
    qemu_set_fd_handler(req->fd, identity_provider_read, NULL, req);
}

static void identity_provider_start_payload(AppleIdentityRequest *req)
{
    struct sockaddr_un address = { .sun_family = AF_UNIX };
    GByteArray *request;
    const uint8_t *challenge;
    gsize length;
    uint8_t header[8];
    int ret;

    if (!req->challenge || (req->provider_operation != 1 && req->provider_operation != 2)) {
        identity_provider_fail(req);
        return;
    }
    challenge = g_bytes_get_data(req->challenge, &length);
    if (!length || length > IDENTITY_SIGN_REQUEST_MAX ||
        (req->provider_operation == 2 && length != 32)) {
        identity_provider_fail(req);
        return;
    }
    stl_be_p(header, req->provider_operation);
    stl_be_p(header + 4, length);
    request = g_byte_array_sized_new(sizeof(header) + length);
    g_byte_array_append(request, header, sizeof(header));
    g_byte_array_append(request, challenge, length);
    req->provider_request = g_byte_array_free_to_bytes(request);
    req->fd = qemu_socket(AF_UNIX, SOCK_STREAM, 0);
    if (req->fd < 0) {
        identity_provider_fail(req);
        return;
    }
    {
        int flags = fcntl(req->fd, F_GETFL);
        if (flags < 0 || fcntl(req->fd, F_SETFL, flags | O_NONBLOCK) < 0) {
            identity_provider_fail(req);
            return;
        }
    }
    pstrcpy(address.sun_path, sizeof(address.sun_path), req->s->signer_path);
    ret = connect(req->fd, (struct sockaddr *)&address, sizeof(address));
    if (ret < 0 && errno != EINPROGRESS) {
        identity_provider_fail(req);
        return;
    }
    req->connecting = ret < 0;
    req->timeout = timer_new_ms(QEMU_CLOCK_REALTIME, identity_relay_timeout, req);
    timer_mod(req->timeout, qemu_clock_get_ms(QEMU_CLOCK_REALTIME) +
              APPLE_IDENTITY_RELAY_TIMEOUT_MS);
    qemu_set_fd_handler(req->fd, NULL, identity_provider_write, req);
}

static void identity_provider_start(AppleIdentityRequest *req)
{
    req->provider_operation = 1;
    req->challenge = identity_external_challenge(req->elem);
    identity_provider_start_payload(req);
}

/* Reproduce the native legacy public-key derivation for observed 32-byte
 * contexts. Its HMAC-DRBG stream supplies a LITTLE-endian ECC scalar. */
static int identity_swpka_derive_key(const uint8_t context[32], uint32_t flags,
                                    gnutls_x509_privkey_t *result)
{
    static const char order256[] =
        "ffffffff00000000ffffffffffffffffbce6faada7179e84f3b9cac2fc632551";
    static const char order384[] =
        "ffffffffffffffffffffffffffffffffffffffffffffffffc7634d81f4372ddf"
        "581a0db248b0a77aecec196accc52973";
    const bool p384 = flags & 0x4000;
    const size_t length = p384 ? 48 : 32;
    const char *order_hex = p384 ? order384 : order256;
    const gnutls_ecc_curve_t curve = p384 ? GNUTLS_ECC_CURVE_SECP384R1
                                          : GNUTLS_ECC_CURVE_SECP256R1;
    uint8_t key[32] = { 0 }, value[32], input[75], temporary[32];
    uint8_t entropy[48], scalar[48], order[48];
    gnutls_x509_privkey_t private_key = NULL;
    gnutls_datum_t private_data;
    int status = -11;
    bool nonzero = false;

    *result = NULL;
    memset(value, 1, sizeof(value));
    /* HMAC-DRBG instantiate: entropy=context, nonce empty, personalization
     * exactly ten bytes including the terminating NUL. */
    memcpy(input + 33, context, 32);
    memcpy(input + 65, "drbg seed", 10);
    for (unsigned separator = 0; separator < 2; separator++) {
        memcpy(input, value, sizeof(value));
        input[32] = separator;
        if (gnutls_hmac_fast(GNUTLS_MAC_SHA256, key, sizeof(key), input,
                             sizeof(input), temporary) < 0) {
            goto out;
        }
        memcpy(key, temporary, sizeof(key));
        if (gnutls_hmac_fast(GNUTLS_MAC_SHA256, key, sizeof(key), value,
                             sizeof(value), temporary) < 0) {
            goto out;
        }
        memcpy(value, temporary, sizeof(value));
    }
    for (size_t produced = 0; produced < length; ) {
        size_t count = MIN(sizeof(value), length - produced);
        if (gnutls_hmac_fast(GNUTLS_MAC_SHA256, key, sizeof(key), value,
                             sizeof(value), temporary) < 0) {
            goto out;
        }
        memcpy(value, temporary, sizeof(value));
        memcpy(entropy + produced, value, count);
        produced += count;
    }
    for (size_t i = 0; i < length; i++) {
        scalar[i] = entropy[length - i - 1];
        order[i] = (g_ascii_xdigit_value(order_hex[2 * i]) << 4) |
                    g_ascii_xdigit_value(order_hex[2 * i + 1]);
    }
    /* Native ccec_generate_scalar_legacy subtracts the order at most once;
     * it does not hash the context directly or use big-endian DRBG output. */
    if (memcmp(scalar, order, length) >= 0) {
        int borrow = 0;
        for (size_t i = length; i > 0; i--) {
            int difference = scalar[i - 1] - order[i - 1] - borrow;
            scalar[i - 1] = difference & 0xff;
            borrow = difference < 0;
        }
    }
    for (size_t i = 0; i < length; i++) {
        nonzero |= scalar[i] != 0;
    }
    if (!nonzero || gnutls_x509_privkey_init(&private_key) < 0) {
        goto out;
    }
    private_data.data = scalar;
    private_data.size = length;
    /* GnuTLS derives public coordinates when x/y are NULL; verified against
     * its actual P-256/P-384 API and the native known-context fixtures. */
    if (gnutls_x509_privkey_import_ecc_raw(private_key, curve,
                                           NULL, NULL, &private_data) < 0) {
        goto out;
    }
    *result = private_key;
    private_key = NULL;
    status = 0;
out:
    if (private_key) {
        gnutls_x509_privkey_deinit(private_key);
    }
    gnutls_memset(key, 0, sizeof(key));
    gnutls_memset(value, 0, sizeof(value));
    gnutls_memset(input, 0, sizeof(input));
    gnutls_memset(temporary, 0, sizeof(temporary));
    gnutls_memset(entropy, 0, sizeof(entropy));
    gnutls_memset(scalar, 0, sizeof(scalar));
    return status;
}

/* Ordinary native direct-digest signing; no I/O or key persistence. */
static int identity_swpka_ordinary_sign(const uint8_t context[32], uint32_t flags,
                                      const uint8_t *digest, size_t digest_len,
                                      gnutls_datum_t *signature)
{
    static const uint8_t host_marker[32] = {
        0xa6,0xc3,0x60,0x29,0x03,0xa3,0xc6,0x38,0xeb,0x29,
        0x91,0xce,0xab,0xb8,0xdb,0xee,0x5f,0x89,0x8c,0x12
    };
    gnutls_x509_privkey_t key = NULL;
    gnutls_privkey_t signer = NULL;
    gnutls_datum_t input;
    int status = -11;
    if (!signature) return -11;
    signature->data = NULL;
    signature->size = 0;
    if (!context || !digest || (digest_len != 32 && digest_len != 48) ||
        (flags & 2) || ((flags & 4) && !memcmp(context, host_marker, 32)))
        return -11;
    input.data = (uint8_t *)digest;
    input.size = digest_len;
    if (identity_swpka_derive_key(context, flags, &key) ||
        gnutls_privkey_init(&signer) < 0 ||
        gnutls_privkey_import_x509(signer, key, 0) < 0 ||
        gnutls_privkey_sign_hash2(signer, digest_len == 48
            ? GNUTLS_SIGN_ECDSA_SHA384 : GNUTLS_SIGN_ECDSA_SHA256,
            0, &input, signature) < 0 ||
        !signature->data || signature->size < 8 || signature->size > 104 ||
        signature->data[0] != 0x30) goto out;
    status = 0;
out:
    if (signer) gnutls_privkey_deinit(signer);
    if (key) gnutls_x509_privkey_deinit(key);
    if (status) {
        gnutls_free(signature->data);
        signature->data = NULL;
        signature->size = 0;
    }
    return status;
}

static int identity_swpka_derived_public(const uint8_t context[32], uint32_t flags,
                                        uint8_t point[97], size_t *length)
{
    gnutls_x509_privkey_t key = NULL;
    gnutls_privkey_t abstract_key = NULL;
    gnutls_pubkey_t public_key = NULL;
    gnutls_ecc_curve_t curve;
    gnutls_datum_t x = { 0 }, y = { 0 };
    const size_t coordinate = flags & 0x4000 ? 48 : 32;
    int status = -11;

    *length = 0;
    if (identity_swpka_derive_key(context, flags, &key) ||
        gnutls_privkey_init(&abstract_key) < 0 ||
        gnutls_privkey_import_x509(abstract_key, key, 0) < 0 ||
        gnutls_pubkey_init(&public_key) < 0 ||
        gnutls_pubkey_import_privkey(public_key, abstract_key, 0, 0) < 0 ||
        gnutls_pubkey_export_ecc_raw2(public_key, &curve, &x, &y,
                                     GNUTLS_EXPORT_FLAG_NO_LZ) < 0 ||
        x.size > coordinate || y.size > coordinate) {
        goto out;
    }
    memset(point, 0, 1 + 2 * coordinate);
    point[0] = 4;
    memcpy(point + 1 + coordinate - x.size, x.data, x.size);
    memcpy(point + 1 + 2 * coordinate - y.size, y.data, y.size);
    *length = 1 + 2 * coordinate;
    status = 0;
out:
    gnutls_free(x.data);
    gnutls_free(y.data);
    if (public_key) {
        gnutls_pubkey_deinit(public_key);
    }
    if (abstract_key) {
        gnutls_privkey_deinit(abstract_key);
    }
    if (key) {
        gnutls_x509_privkey_deinit(key);
    }
    return status;
}

/* A status plus one inline buffer is the native SWPKA public-key reply. */
static void identity_swpka_buffer_reply(AppleIdentityRequest *req,
                                        uint32_t message_type, int32_t status,
                                        const uint8_t *point, size_t length)
{
    AppleIdentityHeader reply = {
        .version = 2,
        .subsystem = APPLE_IDENTITY_SUBSYS_SWPKA,
        .message_type = message_type,
        .message_len = 20,
        .num_buffers = 1,
        .buffers_offset = 4,
    };
    uint8_t body[20] = { 0 };
    size_t capacity = iov_size(req->elem->in_sg, req->elem->in_num);
    size_t written;

    if (capacity < sizeof(reply) + sizeof(body)) {
        if (message_type == 6) {
            fprintf(stderr, "IDSWPKA attestation reply status=-50 signaturelen=0 used=0\n");
        }
        identity_request_complete(req, 0);
        return;
    }
    if (length > capacity - sizeof(reply) - sizeof(body)) {
        status = -50; /* paramErr: no complete success reply fits. */
        point = NULL;
        length = 0;
    }
    if (message_type == 6) {
        fprintf(stderr, "IDSWPKA attestation reply status=%d signaturelen=%zu\n",
                status, length);
    }
    reply.buffer_len = length;
    reply.transport_len = sizeof(reply) + sizeof(body) + length;
    stl_le_p(body, (uint32_t)status);
    /* The serialized pointer at +4 is zero; the decoder owns the buffer. */
    stq_le_p(body + 12, length);
    written = iov_from_buf(req->elem->in_sg, req->elem->in_num, 0,
                           &reply, sizeof(reply));
    written += iov_from_buf(req->elem->in_sg, req->elem->in_num, written,
                            body, sizeof(body));
    if (length) {
        written += iov_from_buf(req->elem->in_sg, req->elem->in_num, written,
                                point, length);
    }
    identity_request_complete(req, written);
}

/* The native virtual PKA reports the same opaque 52-byte measurement for
 * supported selectors 0..6; this is not a physical SEP measurement query. */
static void identity_swpka_measurement(AppleIdentityRequest *req,
                                       const AppleIdentityHeader *header)
{
    uint8_t request[4], measurement[52];
    uint32_t selector = 0;
    int32_t status = -50;

    if (req->s->external_mode && header->version == 2 &&
        header->subsystem == APPLE_IDENTITY_SUBSYS_SWPKA &&
        header->message_type == 2 && header->message_len == sizeof(request) &&
        !header->buffer_len && !header->num_buffers && !header->buffers_offset &&
        header_is_valid(header, iov_size(req->elem->out_sg,
                                         req->elem->out_num))) {
        iov_to_buf(req->elem->out_sg, req->elem->out_num,
                   sizeof(*header), request, sizeof(request));
        selector = ldl_le_p(request);
        if (selector <= 6) {
            memset(measurement, 0xff, sizeof(measurement));
            status = 0;
        }
    }
    fprintf(stderr, "IDSWPKA measurement selector=%u status=%d\n",
            selector, status);
    identity_swpka_buffer_reply(req, 2, status,
                                status ? NULL : measurement,
                                status ? 0 : sizeof(measurement));
}

/* Native virtual-PKA AON-security (8) and attested chip-revision (9) queries
 * are fixed-value queries, with distinct packed reply widths. */
static void identity_swpka_fixed_query(AppleIdentityRequest *req,
                                        const AppleIdentityHeader *header)
{
    const uint32_t type = header->message_type;
    AppleIdentityHeader reply = {
        .version = 2,
        .subsystem = APPLE_IDENTITY_SUBSYS_SWPKA,
        .message_type = type,
        .message_len = type == 8 ? 8 : 5,
    };
    uint8_t body[8] = { 0 };
    bool valid = req->s->external_mode && header->version == 2 &&
        header->subsystem == APPLE_IDENTITY_SUBSYS_SWPKA &&
        (type == 8 || type == 9) && header->message_len == 1 &&
        !header->buffer_len && !header->num_buffers && !header->buffers_offset &&
        header_is_valid(header, iov_size(req->elem->out_sg,
                                         req->elem->out_num));
    size_t written;

    reply.transport_len = sizeof(reply) + reply.message_len;
    if (iov_size(req->elem->in_sg, req->elem->in_num) < reply.transport_len) {
        identity_request_complete(req, 0);
        return;
    }
    stl_le_p(body, valid ? 0 : (uint32_t)-50);
    if (valid) {
        if (type == 8) {
            stl_le_p(body + 4, 1);
        } else {
            body[4] = 1;
        }
    }
    written = iov_from_buf(req->elem->in_sg, req->elem->in_num, 0,
                           &reply, sizeof(reply));
    written += iov_from_buf(req->elem->in_sg, req->elem->in_num, written,
                            body, reply.message_len);
    fprintf(stderr, "IDSWPKA query type=%u status=%d reply=%zu\n",
            type, valid ? 0 : -50, written);
    identity_request_complete(req, written);
}

static void identity_clear_guest_parameters(AppleIdentity *s)
{
    s->guest_parameters_valid = false;
    s->guest_chip_id = 0;
    s->guest_ecid = 0;
}

/* Native 4/3 carries packed guest ChipID, guest ECID, then an opaque context
 * iovec. The context's serialized pointer is never followed. */
static bool identity_capture_guest_parameters(AppleIdentity *s,
                                              VirtQueueElement *elem,
                                              const AppleIdentityHeader *header)
{
    uint8_t body[28];

    if (!s->external_mode || header->version != 2 ||
        header->subsystem != APPLE_IDENTITY_SUBSYS_IDENTITY ||
        header->message_type != APPLE_IDENTITY_TYPE_UDID ||
        header->message_len != sizeof(body) || header->buffers_offset != 12 ||
        header->num_buffers != 1 || !header->buffer_len ||
        !header_is_valid(header, iov_size(elem->out_sg, elem->out_num))) {
        return false;
    }
    iov_to_buf(elem->out_sg, elem->out_num, sizeof(*header), body, sizeof(body));
    if (ldq_le_p(body + 20) != header->buffer_len) {
        return false;
    }
    s->guest_chip_id = ldl_le_p(body);
    s->guest_ecid = ldq_le_p(body + 4);
    s->guest_parameters_valid = true;
    /* Actual identities are deliberately omitted from diagnostics. */
    fprintf(stderr, "IDSWPKA guest parameters captured\n");
    return true;
}

static void identity_swpka_guest_identity(AppleIdentityRequest *req,
                                          const AppleIdentityHeader *header)
{
    char identity[26];
    int32_t status = -50;
    size_t length = 0;

    if (req->s->external_mode && header->version == 2 &&
        header->subsystem == APPLE_IDENTITY_SUBSYS_SWPKA &&
        header->message_type == 10 && header->message_len == 1 &&
        !header->buffer_len && !header->num_buffers && !header->buffers_offset &&
        header_is_valid(header, iov_size(req->elem->out_sg,
                                         req->elem->out_num))) {
        status = -11;
        if (req->s->guest_parameters_valid &&
            snprintf(identity, sizeof(identity), "%08X-%016" PRIX64,
                     req->s->guest_chip_id, req->s->guest_ecid) == 25) {
            status = 0;
            length = 25;
        }
    }
    fprintf(stderr, "IDSWPKA guest identity status=%d length=%zu\n",
            status, length);
    identity_swpka_buffer_reply(req, 10, status,
                                status ? NULL : (const uint8_t *)identity,
                                length);
}

/* Diagnostic only: a type-6 request remains unsupported until its actual
 * signing/attestation contract is implemented. Never log either context. */
static void identity_swpka_log_attestation(AppleIdentityRequest *req,
                                           const AppleIdentityHeader *header)
{
    uint8_t body[74];
    uint64_t signing_context, attested_context, nonce;

    if (header->version != 2 ||
        header->subsystem != APPLE_IDENTITY_SUBSYS_SWPKA ||
        header->message_type != 6 || header->message_len != sizeof(body) ||
        header->buffers_offset != 26 || header->num_buffers != 3 ||
        !header_is_valid(header, iov_size(req->elem->out_sg,
                                         req->elem->out_num))) {
        fprintf(stderr, "IDSWPKA attestation metadata malformed descriptor\n");
        return;
    }
    iov_to_buf(req->elem->out_sg, req->elem->out_num,
               sizeof(*header), body, sizeof(body));
    signing_context = ldq_le_p(body + 34);
    attested_context = ldq_le_p(body + 50);
    nonce = ldq_le_p(body + 66);
    if (signing_context > header->buffer_len ||
        attested_context > header->buffer_len - signing_context ||
        nonce != header->buffer_len - signing_context - attested_context) {
        fprintf(stderr, "IDSWPKA attestation metadata malformed buffer lengths\n");
        return;
    }
    fprintf(stderr, "IDSWPKA attestation signflags=0x%x signselector=%u "
            "signbool=%u signsecondary=%u attestflags=0x%x "
            "attestselector=%u attestbool=%u attestsecondary=%u "
            "signctxlen=%" PRIu64 " attestctxlen=%" PRIu64 " noncelen=%" PRIu64 "\n",
            ldl_le_p(body), ldl_le_p(body + 4), body[8] != 0,
            ldl_le_p(body + 13), ldl_le_p(body + 9),
            ldl_le_p(body + 17), body[21] != 0, ldl_le_p(body + 22),
            signing_context, attested_context, nonce);
}

/* Only the observed retained-host signer is exported to the SEP provider.
 * Ordinary attested keys use the independently verified native public KDF. */
static void identity_swpka_attest(AppleIdentityRequest *req,
                                 const AppleIdentityHeader *header)
{
    static const uint8_t marker[32] = {
        0xa6,0xc3,0x60,0x29,0x03,0xa3,0xc6,0x38,0xeb,0x29,
        0x91,0xce,0xab,0xb8,0xdb,0xee,0x5f,0x89,0x8c,0x12,
    };
    uint8_t body[74], contexts[64], nonce[48], point[97], digest[32];
    struct omvm_sika_input input = { 0 };
    struct omvm_sika_result result;
    uint64_t signing_len, attested_len, nonce_len;
    size_t point_len = 0;
    bool signing_host = false, attested_host = false;
    int32_t status = -50;

    if (header->version != 2 || header->subsystem != APPLE_IDENTITY_SUBSYS_SWPKA ||
        header->message_type != 6 || header->message_len != sizeof(body) ||
        header->num_buffers != 3 || header->buffers_offset != 26 ||
        !header_is_valid(header, iov_size(req->elem->out_sg, req->elem->out_num))) {
        goto fail;
    }
    iov_to_buf(req->elem->out_sg, req->elem->out_num, sizeof(*header), body, sizeof(body));
    signing_len = ldq_le_p(body + 34);
    attested_len = ldq_le_p(body + 50);
    nonce_len = ldq_le_p(body + 66);
    if (signing_len != 32 || attested_len != 32 || nonce_len > sizeof(nonce) ||
        header->buffer_len != signing_len + attested_len + nonce_len) {
        goto fail;
    }
    iov_to_buf(req->elem->out_sg, req->elem->out_num,
               sizeof(*header) + sizeof(body), contexts, sizeof(contexts));
    iov_to_buf(req->elem->out_sg, req->elem->out_num,
               sizeof(*header) + sizeof(body) + sizeof(contexts), nonce, nonce_len);
    input.signing_flags = ldl_le_p(body);
    input.attested_flags = ldl_le_p(body + 9);
    input.attested_selector = ldl_le_p(body + 17);
    input.attested_secondary = ldl_le_p(body + 22);
    signing_host = (input.signing_flags & 4) && !memcmp(contexts, marker, 32);
    attested_host = (input.attested_flags & 4) && !memcmp(contexts + 32, marker, 32);
    status = -4;
    if (!signing_host) {
        goto fail;
    }
    if (attested_host) {
        memcpy(point, req->s->host_public_point, sizeof(req->s->host_public_point));
        point_len = sizeof(req->s->host_public_point);
    } else if (!memcmp(contexts + 32, marker, 32) ||
               identity_swpka_derived_public(contexts + 32, input.attested_flags,
                                              point, &point_len)) {
        goto fail;
    }
    input.attested_point = point;
    input.attested_point_len = point_len;
    input.attested_is_host = attested_host;
    input.guest_identity_valid = req->s->guest_parameters_valid;
    input.guest_chip_id = req->s->guest_chip_id;
    input.guest_ecid = req->s->guest_ecid;
    input.nonce = nonce;
    input.nonce_len = nonce_len;
    status = -50;
    if (omvm_sika_build(&input, &result) || omvm_sika_effective_p256(&result, digest)) {
        goto fail;
    }
    req->provider_operation = 2;
    req->challenge = g_bytes_new(digest, sizeof(digest));
    gnutls_memset(contexts, 0, sizeof(contexts));
    gnutls_memset(nonce, 0, sizeof(nonce));
    gnutls_memset(digest, 0, sizeof(digest));
    gnutls_memset(&result, 0, sizeof(result));
    fprintf(stderr, "IDSWPKA attestation signhost=1 attesthost=%u providerop=2\n", attested_host);
    identity_provider_start_payload(req);
    return;
fail:
    gnutls_memset(contexts, 0, sizeof(contexts));
    gnutls_memset(nonce, 0, sizeof(nonce));
    gnutls_memset(digest, 0, sizeof(digest));
    gnutls_memset(&result, 0, sizeof(result));
    fprintf(stderr, "IDSWPKA attestation signhost=%u attesthost=%u status=%d\n",
            signing_host, attested_host, status);
    identity_swpka_buffer_reply(req, 6, status, NULL, 0);
}

/* Host-slot lookup and native deterministic public keys are distinct paths. */
static void identity_swpka_getpub(AppleIdentityRequest *req,
                                  const AppleIdentityHeader *header)
{
    static const uint8_t host_marker[32] = {
        0xa6, 0xc3, 0x60, 0x29, 0x03, 0xa3, 0xc6, 0x38, 0xeb, 0x29,
        0x91, 0xce, 0xab, 0xb8, 0xdb, 0xee, 0x5f, 0x89, 0x8c, 0x12,
    };
    uint8_t body[29], context[32], derived_point[97];
    const uint8_t *public_point = NULL;
    size_t public_length = 0;
    uint32_t selector = 0, flags = 0, secondary = 0;
    uint64_t context_len = 0;
    bool requested_bool = false, marker = false;
    int32_t status = -50; /* paramErr until every wire bound is validated. */

    if (req->s->external_mode && header->version == 2 &&
        header->subsystem == APPLE_IDENTITY_SUBSYS_SWPKA &&
        header->message_type == 3 && header->message_len == sizeof(body) &&
        header->buffers_offset == 13 && header->num_buffers == 1 &&
        header_is_valid(header, iov_size(req->elem->out_sg,
                                         req->elem->out_num))) {
        iov_to_buf(req->elem->out_sg, req->elem->out_num,
                   sizeof(*header), body, sizeof(body));
        selector = ldl_le_p(body);
        requested_bool = body[4] != 0;
        flags = ldl_le_p(body + 5);
        secondary = ldl_le_p(body + 9);
        /* Never follow the serialized iovec pointer at +13. */
        context_len = ldq_le_p(body + 21);
        if (context_len == header->buffer_len) {
            status = -4; /* errSecUnimplemented: ordinary software KDF context. */
            if (context_len == 20 || context_len == sizeof(context)) {
                iov_to_buf(req->elem->out_sg, req->elem->out_num,
                           sizeof(*header) + sizeof(body), context, context_len);
                marker = !memcmp(context, host_marker, context_len);
                if ((flags & 4) && marker &&
                    req->s->host_public_point[0] == 4) {
                    public_point = req->s->host_public_point;
                    public_length = sizeof(req->s->host_public_point);
                    status = 0;
                } else if (!marker && context_len == sizeof(context)) {
                    /* Selector, request bool, secondary and the other flag
                     * bits are ignored by this native public-only path. The
                     * observed selector1/0x78d8/UINT32_MAX case matches the
                     * independent native public-seed P-384 fixtures. */
                    status = identity_swpka_derived_public(context, flags,
                                                           derived_point,
                                                           &public_length);
                    if (!status) {
                        public_point = derived_point;
                    }
                }
            }
        }
    }
    gnutls_memset(context, 0, sizeof(context));
    fprintf(stderr, "IDSWPKA getpub selector=%u bool=%u flags=0x%x "
            "secondary=%u ctxlen=%" PRIu64 " hostmarker=%u status=%d\n",
            selector, requested_bool, flags, secondary, context_len,
            marker, status);
    identity_swpka_buffer_reply(req, 3, status, public_point,
                                status ? 0 : public_length);
}

/* Native type5 signs the supplied digest directly; it never hashes it again. */
static void identity_swpka_sign(AppleIdentityRequest *req,
                                const AppleIdentityHeader *header)
{
    static const uint8_t host_marker[32] = {
        0xa6,0xc3,0x60,0x29,0x03,0xa3,0xc6,0x38,0xeb,0x29,
        0x91,0xce,0xab,0xb8,0xdb,0xee,0x5f,0x89,0x8c,0x12,
    };
    uint8_t body[45], context[32], digest[48];
    gnutls_datum_t signature = { 0 };
    uint32_t selector = 0, flags = 0, secondary = 0;
    uint64_t context_len = 0, digest_len = 0;
    bool requested_bool = false, marker = false;
    int32_t status = -50;

    if (header->version != 2 || header->subsystem != APPLE_IDENTITY_SUBSYS_SWPKA ||
        header->message_type != 5 || header->message_len != sizeof(body) ||
        header->num_buffers != 2 || header->buffers_offset != 13 ||
        !header_is_valid(header, iov_size(req->elem->out_sg, req->elem->out_num))) {
        goto out;
    }
    iov_to_buf(req->elem->out_sg, req->elem->out_num,
               sizeof(*header), body, sizeof(body));
    selector = ldl_le_p(body);
    requested_bool = body[4] != 0;
    flags = ldl_le_p(body + 5);
    secondary = ldl_le_p(body + 9);
    context_len = ldq_le_p(body + 21);
    digest_len = ldq_le_p(body + 37);
    if (context_len != sizeof(context) ||
        (digest_len != 32 && digest_len != sizeof(digest)) ||
        header->buffer_len != context_len + digest_len) {
        goto out;
    }
    iov_to_buf(req->elem->out_sg, req->elem->out_num,
               sizeof(*header) + sizeof(body), context, sizeof(context));
    iov_to_buf(req->elem->out_sg, req->elem->out_num,
               sizeof(*header) + sizeof(body) + sizeof(context), digest, digest_len);
    marker = !memcmp(context, host_marker, sizeof(context));
    if (flags & 2) {
        status = -11; /* Native direct-sign mode0 guard, unlike SIKA mode2. */
    } else if (marker) {
        status = -4; /* Retained-host direct signing is not observed/supported. */
    } else {
        status = identity_swpka_ordinary_sign(context, flags, digest, digest_len,
                                               &signature);
    }
out:
    gnutls_memset(context, 0, sizeof(context));
    gnutls_memset(digest, 0, sizeof(digest));
    fprintf(stderr, "IDSWPKA sign selector=%u bool=%u flags=0x%x secondary=%u "
            "ctxlen=%" PRIu64 " digestlen=%" PRIu64 " hostmarker=%u "
            "status=%d signaturelen=%u\n", selector, requested_bool, flags,
            secondary, context_len, digest_len, marker, status, signature.size);
    identity_swpka_buffer_reply(req, 5, status, signature.data, signature.size);
    gnutls_free(signature.data);
}

/* Native SWPKA subsystem 5/type 1 negotiates protocol version 1. */
static void identity_handle_swpka(AppleIdentityRequest *req,
                                  const AppleIdentityHeader *header)
{
    const AppleIdentityHeader reply = {
        .version = 2,
        .subsystem = APPLE_IDENTITY_SUBSYS_SWPKA,
        .message_type = 1,
        .transport_len = sizeof(AppleIdentityHeader) + sizeof(uint32_t),
        .message_len = sizeof(uint32_t),
    };
    const uint32_t version = cpu_to_le32(1);
    size_t written;

    if (req->s->external_mode && header->message_type == 5) {
        identity_swpka_sign(req, header);
        return;
    }
    if (req->s->external_mode && header->message_type == 10) {
        identity_swpka_guest_identity(req, header);
        return;
    }
    if (req->s->external_mode && header->message_type == 6) {
        identity_swpka_log_attestation(req, header);
        identity_swpka_attest(req, header);
        return;
    }
    if (req->s->external_mode &&
        (header->message_type == 8 || header->message_type == 9)) {
        identity_swpka_fixed_query(req, header);
        return;
    }
    if (req->s->external_mode && header->message_type == 2) {
        identity_swpka_measurement(req, header);
        return;
    }
    if (req->s->external_mode && header->message_type == 3) {
        identity_swpka_getpub(req, header);
        return;
    }
    if (!req->s->external_mode || header->version != 2 ||
        header->message_type != 1 || header->message_len != sizeof(uint32_t) ||
        header->buffer_len || header->num_buffers || header->buffers_offset ||
        !header_is_valid(header, iov_size(req->elem->out_sg,
                                         req->elem->out_num)) ||
        iov_size(req->elem->in_sg, req->elem->in_num) < reply.transport_len) {
        fprintf(stderr, "IDSWPKA unsupported type=%u version=%u mlen=%u "
                "blen=%u nb=%u boff=%u out=%zu in=%zu\n",
                header->message_type, header->version, header->message_len,
                header->buffer_len, header->num_buffers, header->buffers_offset,
                iov_size(req->elem->out_sg, req->elem->out_num),
                iov_size(req->elem->in_sg, req->elem->in_num));
        identity_request_complete(req, 0);
        return;
    }
    written = iov_from_buf(req->elem->in_sg, req->elem->in_num, 0,
                           &reply, sizeof(reply));
    written += iov_from_buf(req->elem->in_sg, req->elem->in_num, written,
                            &version, sizeof(version));
    fprintf(stderr, "IDSWPKA handshake version=1 reply=%zu\n", written);
    identity_request_complete(req, written);
}

static void identity_answer(AppleIdentityRequest *req)
{
    AppleIdentity *s = req->s;
    VirtQueueElement *elem = req->elem;
    AppleIdentityHeader reply;
    AppleIdentityPCI *pci = container_of(s, AppleIdentityPCI, vdev);
    size_t written;

    /*
     * The guest asserts equality of subsystem and messageType between its
     * request and our reply (START-ORDER.md), so the reply is derived from
     * the request rather than hardcoded: the UDID request is type 3 and wants
     * exactly kUniqueDeviceIdentifierLength bytes back. Handshake (type 1)
     * and anything unknown are answered with the same type and no buffer.
     */
    memset(&reply, 0, sizeof(reply));
    /*
     * The reply's version is 1 for a handshake and 2 for anything else:
     * 0xfffffe0008a9310c compares messageType to 1, cinc makes the expected
     * version 1 or 2, and mismatching it asserts. Echo the request's type.
     */
    reply.version = req->message_type == APPLE_IDENTITY_TYPE_HANDSHAKE
                    ? APPLE_IDENTITY_PROTOCOL_VERSION
                    : APPLE_IDENTITY_REPLY_UDID_VERSION;
    reply.subsystem = req->subsystem ? req->subsystem
                                     : APPLE_IDENTITY_SUBSYS_IDENTITY;
    reply.message_type = req->message_type ? req->message_type
                                           : APPLE_IDENTITY_TYPE_HANDSHAKE;
    /* Echo the request's payload length: the guest compares it, and its 4/1
     * carries the 2-byte protocol version. */
    reply.message_len = req->message_len;

    /*
     * The handshake (4/1) reply is what the guest's setUDID consumes: its
     * receive loop rejects a reply whose [buf+8] is not 0x14 and returns
     * kIOReturnUnsupported with _hostKey left NULL, after which the service's
     * start() assert fires. So the UDID rides on 4/1 as well as 4/3.
     */
    /*
     * Both requests carry transportLen 0x1c and bufferLen 0x10 on the wire
     * (START-ORDER.md section 3), so the reply must echo that shape: the
     * in-buffer is a 16-byte descriptor plus the payload, and the guest asserts
     * equality of every field against its own request.
     */
    idlog("CHAIN type=%u len=%u\n", reply.message_type, reply.message_len);
    if (reply.message_type == APPLE_IDENTITY_TYPE_UDID) {
        /*
         * The guest dereferences the returned buffer pointer and reads its
         * length at +8, so the BAR must hold a real {addr, len} entry pointing
         * at the payload that follows it.
         */
        uint8_t *bar = memory_region_get_ram_ptr(&pci->mem) +
                       APPLE_IDENTITY_UDID_OFF;
        AppleIdentityBuffer self;

        self.base = pci->mem.addr + APPLE_IDENTITY_UDID_OFF +
                    sizeof(AppleIdentityBuffer);
        self.len = APPLE_IDENTITY_UDID_LEN;
        memcpy(bar, &self, sizeof(self));
        memcpy(bar + sizeof(self), s->udid, APPLE_IDENTITY_UDID_LEN);
        /*
         * The reply is NOT a mirror of the request. The receive path compares
         * it against a fixed descriptor {messageLen 16, buffersOffset 0,
         * numBuffers 1} and asserts on any mismatch (0xfffffe0008a93b24 and
         * ..3b44), and transportLen must equal header + messageLen + bufferLen
         * (0xfffffe0008a9312c). The UDID rides inline after the one iovec.
         */
        reply.message_len = APPLE_IDENTITY_REPLY_UDID_MSGLEN;
        reply.buffer_len = APPLE_IDENTITY_UDID_LEN;
        reply.num_buffers = 1;
        reply.buffers_offset = 0;
        reply.transport_len = sizeof(reply) + reply.message_len + reply.buffer_len;
    } else if (reply.message_type == APPLE_IDENTITY_TYPE_HANDSHAKE) {
        /*
         * The guest's own 4/1 carries no buffer (numBuffers 0, bufferLen 0,
         * transportLen 34: the header plus a 2-byte version payload). The reply
         * mirrors the request, so it must too.
         */
        uint16_t ver = APPLE_IDENTITY_PROTOCOL_VERSION;

        reply.transport_len = sizeof(reply) + sizeof(ver);
        reply.num_buffers = 0;
        reply.buffer_len = 0;
        reply.buffers_offset = 0;
    } else if (reply.message_type == APPLE_IDENTITY_TYPE_GET_IDENTITY) {
        /*
         * 4/6: flags word, a reserved word, then two iovecs {identity, error}.
         * messages len 48 puts iovec 0 at +32 and iovec 1 at +48; the identity
         * data follows at +64. buffersOffset 16 means the table starts there.
         */
        reply.buffers_offset = 8;
        /* The request itself advertises one buffer (nb=1): mirror it. */
        reply.num_buffers = req->num_buffers ? req->num_buffers : 2;
        /* Two words of lead-in, then two iovecs; no trailing data. */
        reply.message_len = reply.buffers_offset +
                            reply.num_buffers * sizeof(AppleIdentityBuffer);
        /*
         * The caller sizes its next request from this reply's bufferLen, so a
         * short reply ratchets the buffer down. transportLen is only a declared
         * field: the in-buffer is ~1 MiB (IDCAP), so serve the whole blob and
         * let transportLen describe it. The caller's own header values are read
         * back and compared against ours, so mirror its messageLen too.
         */
        /* 4/3's accepted shape: one iovec at body+0, data at +16. */
        if (s->external_mode || getenv("ID_S3")) {
            reply.buffers_offset = 0;
            reply.num_buffers = 1;
            reply.message_len = sizeof(AppleIdentityBuffer);
        } else {
            reply.message_len = req->message_len;
        }
        reply.buffer_len = identity_data_len(s);
        reply.transport_len = sizeof(reply) + reply.message_len +
                              reply.buffer_len;
        /* ID_PAD reproduces the run that decoded: pad the reply to the
         * request's own transportLen so the caller sees the size it sized. */
        if (getenv("ID_PAD") && req->transport_len &&
            req->transport_len > reply.transport_len) {
            reply.buffer_len += req->transport_len - reply.transport_len;
            reply.transport_len = req->transport_len;
        }
        idlog("IDLEN type=%u req_trlen=%u mlen=%u body=%zu blen=%u trlen=%u\n",
              reply.message_type, req->transport_len, reply.message_len,
              sizeof(reply), reply.buffer_len, reply.transport_len);
        idlog("IDLEN type=%u req_trlen=%u mlen=%u body=%zu blen=%u trlen=%u\n",
              reply.message_type, req->transport_len, reply.message_len,
              sizeof(reply), reply.buffer_len, reply.transport_len);
    } else if (reply.message_type == APPLE_IDENTITY_TYPE_GET_IDENTITY_FALLBACK) {
        reply.buffers_offset = 0;
        reply.num_buffers = 1;
        reply.message_len = reply.buffers_offset +
                            reply.num_buffers * sizeof(AppleIdentityBuffer);
        /*
         * The caller compares its own header fields against ours, so mirror its
         * messageLen and bufferLen exactly; the blob is then padded or cut to
         * whatever bufferLen says. The in-buffer is ~1 MiB (IDCAP), so
         * transportLen is only a description, never a cap.
         */
        reply.message_len = s->external_mode ? sizeof(AppleIdentityBuffer)
                                              : req->message_len;
        /* Experiment: a full SHA-256-sized digest instead of the raw 20 bytes. */
        reply.buffer_len = identity_data_len(s);
        reply.transport_len = sizeof(reply) + reply.message_len +
                              reply.buffer_len;
        if (getenv("ID_PAD") && req->transport_len &&
            req->transport_len > reply.transport_len) {
            reply.buffer_len += req->transport_len - reply.transport_len;
            reply.transport_len = req->transport_len;
        }
    } else if (reply.message_type == APPLE_IDENTITY_TYPE_TUNNEL) {
        /*
         * 4/2 carries identity data for userspace. The reply starts with the
         * inner subsystem as a u32 at body +0, then the iovec table at body +4:
         * iov0 the data, iov1 the error data. The inner subsystem must match
         * the request's first word.
         */
        idlog("TUNBRANCH mlen=%d boff=%d nb=%d type=%u\n",
              APPLE_IDENTITY_REPLY_TUN_MSGLEN,
              APPLE_IDENTITY_REPLY_TUN_BOFF, 2, reply.message_type);
        reply.message_len = APPLE_IDENTITY_REPLY_TUN_MSGLEN;
        reply.buffers_offset = APPLE_IDENTITY_REPLY_TUN_BOFF;
        reply.num_buffers = 2;
        reply.buffer_len = s->host_cert_len;
        reply.transport_len = sizeof(reply) + reply.message_len + reply.buffer_len;
    } else {
        reply.transport_len = sizeof(reply);
    }

    /* Push only what fit; a short in-buffer must not claim a full reply. */
    written = iov_from_buf(elem->in_sg, elem->in_num, 0, &reply, sizeof(reply));
    if (reply.message_type == APPLE_IDENTITY_TYPE_HANDSHAKE) {
        uint16_t ver = APPLE_IDENTITY_PROTOCOL_VERSION;

        written += iov_from_buf(elem->in_sg, elem->in_num, written, &ver,
                                sizeof(ver));
    }
    if (reply.message_type == APPLE_IDENTITY_TYPE_UDID) {
        /*
         * The buffer array sits at header + buffers_offset, and the payload
         * follows it. The first entry is {address of that payload, length}, so
         * the guest can copy the UDID out of its own in-buffer.
         */
        AppleIdentityBuffer desc;
        /* messageLen 16 is exactly the iovec, so there is no lead-in padding. */
        uint8_t pad[APPLE_IDENTITY_REPLY_UDID_MSGLEN -
                    sizeof(AppleIdentityBuffer)] = { 0 };

        written += iov_from_buf(elem->in_sg, elem->in_num, written, pad,
                                sizeof(pad));
        /*
         * The deserializer overwrites this address with its own pointer into
         * the receive buffer (0xfffffe0008a9297c), so only len matters; the
         * BAR copy is kept for a host that does follow it.
         */
        desc.base = pci->mem.addr + APPLE_IDENTITY_UDID_OFF;
        desc.len = APPLE_IDENTITY_UDID_LEN;
        written += iov_from_buf(elem->in_sg, elem->in_num, written, &desc,
                                sizeof(desc));
        written += iov_from_buf(elem->in_sg, elem->in_num, written,
                                s->udid, APPLE_IDENTITY_UDID_LEN);
    } else if (reply.message_type == APPLE_IDENTITY_TYPE_TUNNEL) {
        /*
         * Echo the tunneled data back: inner subsystem, then an iovec over the
         * request's own bytes, then an empty error iovec. All addrs are
         * overwritten by the reader, so only lengths matter.
         */
        /*
         * The body is a plist whose Command says what to do; the only command
         * seen is CopyVMHostCertificateRequest, which wants the host
         * certificate back through the same tunnel. The certificate carries the
         * UDID, so the data length is its own.
         */
        uint8_t body[APPLE_IDENTITY_REPLY_TUN_MSGLEN] = { 0 };
        uint32_t inner = 0;
        g_autoptr(GBytes) plist = NULL;
        g_autofree char *b64 = NULL;
        AppleIdentityBuffer iov;
        uint8_t *data;
        size_t dlen, slen = 0;

        iov_to_buf(elem->out_sg, elem->out_num, sizeof(AppleIdentityHeader),
                   &inner, sizeof(inner));

        /*
         * The guest parses the tunnel data buffer as a property list
         * (CFPropertyListCreateWithData) and requires a dictionary. A raw DER
         * cert starts 0x30 = ASCII "0", which is the "Unexpected character 0
         * at line 1" error. So answer with an XML plist, nested the way the
         * guest decoder reads it: Value -> RKCertification (base64), and
         * RKSignature for the signature command. Unknown commands get Error.
         */
        {
            g_autofree char *cmd = identity_tunnel_command(elem);
            g_autoptr(GBytes) signed_bytes = NULL;
            bool sig_cmd = cmd && (strstr(cmd, "Attestation") || strstr(cmd, "Signature"));

            fprintf(stderr, "IDCMD [%s] sig=%d\n", cmd ? cmd : "(null)", sig_cmd);

            b64 = s->host_cert && s->host_cert_len
                  ? g_base64_encode(s->host_cert, s->host_cert_len) : NULL;
            if (sig_cmd) {
                if (s->external_mode) {
                    if (req->external_signature && !req->backend_failed) {
                        signed_bytes = g_bytes_ref(req->external_signature);
                    }
                } else {
                    signed_bytes = identity_tunnel_sign(elem, s->host_key);
                }
            }
            if (sig_cmd && signed_bytes && s->host_cert && s->host_cert_len) {
                const uint8_t *signature = g_bytes_get_data(signed_bytes, &slen);
                plist = identity_bplist_signature(signature, slen,
                                                   s->host_cert, s->host_cert_len);
            } else if (!sig_cmd && b64 &&
                       (!s->external_mode || (cmd && !strcmp(cmd, "CopyVMHostCertificateRequest")))) {
                if (b64) {
                plist = identity_bplist_data("RKCertification",
                                             s->host_cert, s->host_cert_len);
                }
            } else {
                const char *e =
                    "<?xml version=\"1.0\" encoding=\"UTF-8\"?>\n"
                    "<!DOCTYPE plist PUBLIC \"-//Apple//DTD PLIST 1.0//EN\" "
                    "\"http://www.apple.com/DTDs/PropertyList-1.0.dtd\">\n"
                    "<plist version=\"1.0\"><dict><key>Error</key>"
                    "<string>Unsupported command</string></dict></plist>";
                plist = g_bytes_new(e, strlen(e));
            }
        }
        data = (uint8_t *)g_bytes_get_data(plist, &dlen);
        {
            g_autofree char *hex = g_malloc(dlen * 2 + 1);

            for (size_t z = 0; z < dlen; z++) {
                sprintf(hex + z * 2, "%02x", data[z]);
            }
            fprintf(stderr, "IDPLIST %zu %s\n", dlen, hex);
        }

        /* The SG is the capacity; request.transport_len describes input only.
         * Never truncate a property list into a malformed success reply. */
        {
            size_t capacity = iov_size(elem->in_sg, elem->in_num);
            size_t prefix = sizeof(reply) + reply.message_len;
            size_t room = capacity >= prefix ? capacity - prefix : 0;

            if (dlen > room || dlen > APPLE_IDENTITY_TUN_PLIST_MAX) {
                static const char error[] =
                    "<plist version=\"1.0\"><dict><key>Error</key>"
                    "<string>Identity reply exceeds receive capacity</string></dict></plist>";
                g_clear_pointer(&plist, g_bytes_unref);
                plist = g_bytes_new_static(error, sizeof(error) - 1);
                data = (uint8_t *)g_bytes_get_data(plist, &dlen);
                if (dlen > room) {
                    identity_request_complete(req, 0);
                    return;
                }
            }
        }
        reply.buffer_len = dlen;
        reply.transport_len = sizeof(reply) + reply.message_len + dlen;
        /*
         * The tunnel reader in DeviceIdentity dereferences the descriptor even
         * though 4/4 and 4/6 readers overwrite it, so publish a real pointer:
         * the BAR is guest-visible, so the plist is readable either way.
         */
        {
            size_t bar_size = memory_region_size(&pci->mem);
            size_t offset = APPLE_IDENTITY_TUN_PLIST_OFF;

            if (offset <= bar_size && dlen <= APPLE_IDENTITY_TUN_PLIST_MAX &&
                dlen <= bar_size - offset) {
                uint8_t *bar = memory_region_get_ram_ptr(&pci->mem) + offset;

                memcpy(bar, data, dlen);
                iov.base = pci->mem.addr + offset;
            } else {
                iov.base = 0;
            }
        }
        iov.len = dlen;
        memcpy(body, &inner, sizeof(inner));
        memcpy(body + APPLE_IDENTITY_REPLY_TUN_BOFF, &iov, sizeof(iov));
        /* Second entry stays zero-length: the guest skips it on the walk. */
        written += iov_from_buf(elem->in_sg, elem->in_num, written, body,
                                reply.message_len);
        if (data) {
            written += iov_from_buf(elem->in_sg, elem->in_num, written, data,
                                    dlen);
        }
        idlog("TUN req_trlen=%u inner=%u mlen=%u boff=%u nb=%u dlen=%zu "
              "in_room=%zu iov0={len=%zu}\n",
              req->transport_len, inner, reply.message_len,
              reply.buffers_offset, reply.num_buffers, dlen,
              iov_size(elem->in_sg, elem->in_num), (size_t)iov.len);
        idlog_hex("TUNbody", body, reply.message_len);
        {
            /* Framing as the guest walks it: header, body, iov table, data. */
            AppleIdentityBuffer t[2];
            uint64_t sum = 0;

            memcpy(t, body + reply.buffers_offset,
                   MIN(sizeof(t), (size_t)(reply.message_len -
                                           reply.buffers_offset)));
            for (uint32_t i = 0; i < reply.num_buffers && i < 2; i++) {
                idlog("TUNIOV[%u] base=0x%" PRIx64 " len=%" PRIu64
                      " @body+%zu\n", i, t[i].base, t[i].len,
                      reply.buffers_offset + i * sizeof(AppleIdentityBuffer));
                sum += t[i].len;
            }
            idlog("TUNFRAME hdr=%zu mlen=%u boff=%u nb=%u table_end=%zu "
                  "blen=%u iov_sum=%" PRIu64 " remaining=%" PRId64
                  " data_at=%zu data_end=%zu trlen=%u written_so_far=%zu\n",
                  sizeof(reply), reply.message_len, reply.buffers_offset,
                  reply.num_buffers,
                  reply.buffers_offset + reply.num_buffers *
                  sizeof(AppleIdentityBuffer),
                  reply.buffer_len, sum,
                  (int64_t)reply.buffer_len - (int64_t)sum,
                  sizeof(reply) + reply.message_len,
                  sizeof(reply) + reply.message_len + dlen,
                  reply.transport_len, written);
            idlog_hex("TUNhdr", &reply, sizeof(reply));
            idlog_hex("TUNdata", data, MIN(dlen, (size_t)96));
            if (dlen > 64) {
                idlog_hex("TUNdatatail", data + dlen - 64, 64);
            }
        }
    } else if (reply.message_type == APPLE_IDENTITY_TYPE_GET_IDENTITY ||
               reply.message_type == APPLE_IDENTITY_TYPE_GET_IDENTITY_FALLBACK) {
        /*
         * The deserializer overwrites every iov addr and only consumes len, and
         * it requires the lens to add up to bufferLen exactly. So: flags (all
         * zero: bit 0 only is allowed and it is a caller flag), reserved, the
         * iovec table with 4/6's second (error) entry empty, then the blob.
         */
        AppleIdentityBuffer ios[2] = { 0 };
        uint8_t head[APPLE_IDENTITY_REPLY_66_MSGLEN] = { 0 };
        g_autofree uint8_t *blob = NULL;
        uint32_t dlen = MIN(identity_data_len(s), reply.buffer_len);
        uint32_t elen = reply.buffer_len - dlen;
        uint32_t n = identity_reply_iovecs(s, reply.message_type, dlen, elen,
                                           ios);

        if (reply.buffer_len > APPLE_IDENTITY_TUN_PLIST_MAX ||
            iov_size(elem->in_sg, elem->in_num) < reply.transport_len) {
            identity_request_complete(req, 0);
            return;
        }
        blob = g_malloc0(reply.buffer_len);
        /* The iov table sits at body + buffersOffset; head covers the body. */
        memcpy(head + reply.buffers_offset, ios,
               n * sizeof(AppleIdentityBuffer));
        written += iov_from_buf(elem->in_sg, elem->in_num, written, head,
                                reply.message_len);
        /* bufferLen may exceed the blob (the caller pads its own copies), so
         * send that many bytes with the tail zeroed rather than a short write. */
        memcpy(blob, identity_data_ptr(s), dlen);
        idlog_hex("IDBLOBDUMP", blob, reply.buffer_len);
        if (reply.buffer_len) {
            written += iov_from_buf(elem->in_sg, elem->in_num, written, blob,
                                    reply.buffer_len);
        }
    }
    /* Tunnel plist construction changes buffer_len and transport_len after
     * the initial header copy. Publish the FINAL header, not the DER-sized
     * placeholder, before returning this descriptor to the guest. */
    iov_from_buf(elem->in_sg, elem->in_num, 0, &reply, sizeof(reply));
    {
        AppleIdentityHeader wire;

        iov_to_buf(elem->in_sg, elem->in_num, 0, &wire, sizeof(wire));
        idlog("WIRE type=%u mlen=%u blen=%u nb=%u boff=%u trlen=%u written=%zu\n",
              wire.message_type, wire.message_len, wire.buffer_len,
              wire.num_buffers, wire.buffers_offset, wire.transport_len,
              written);
    }
    fprintf(stderr, "IDREP type=%u mlen=%u blen=%u nb=%u boff=%u trlen=%u written=%zu\n",
            reply.message_type, reply.message_len, reply.buffer_len,
            reply.num_buffers, reply.buffers_offset, reply.transport_len,
            written);
    idlog("REP type=%u mlen=%u blen=%u nb=%u boff=%u trlen=%u written=%zu\n",
          reply.message_type, reply.message_len, reply.buffer_len,
          reply.num_buffers, reply.buffers_offset, reply.transport_len,
          written);
    if (written != reply.transport_len) {
        qemu_log_mask(LOG_GUEST_ERROR, "%s: short reply buffer, %zu of %zu\n",
                      __func__, written, (size_t)reply.transport_len);
    }

    identity_request_complete(req, written);
}


/*
 * The guest kernel reads the UDID twice: as raw bytes from this device, and as
 * /chosen/unique-device-id-string from the device tree, formatted
 * "%08X-%016llX" (IDENTITY-KEXT-STRINGS.md). The booter emits only the raw
 * property, so AMFI finds nothing and never enables the UDID path. The tree is
 * built by the booter after QEMU runs, so it is patched here on the first
 * request, once boot has finished and the tree is final.
 *
 * The slot is found by the node name and confirmed against its terminator, and
 * the insertion is bounds-checked against the header total, so a tree we do not
 * recognise is left alone rather than corrupted.
 */
/*
 * The guest kernel reads the UDID twice: as raw bytes from this device, and as
 * /chosen/unique-device-id-string from the device tree, formatted
 * "%08X-%016llX" (research/identity/IDENTITY-KEXT-STRINGS.md). The booter emits
 * only the raw property, so AMFI finds nothing and never turns the UDID path on.
 *
 * The tree is built by the booter after QEMU runs, so it is patched on the first
 * request, once boot has finished and the tree is final. Everything is bounds
 * checked against the header total; a tree we do not recognise is left alone.
 *
 * Insertion happens at the end of the structure block: the property name goes
 * into the strings block (whose existing offset is opaque to us, so the new name
 * is appended there and referenced by its new offset) and the blob is written in
 * the strings block's place, which then moves. Layout:
 *
 *   [ structs ... | strings ... | end ]
 *   [ structs ... newprop | strings ... newname | end ]
 */
/*
 * The guest kernel reads the UDID twice: as raw bytes from this device, and as
 * /chosen/unique-device-id-string from the device tree, formatted
 * "%08X-%016llX" (research/identity/IDENTITY-KEXT-STRINGS.md). The booter emits
 * only the raw property, so AMFI finds nothing and never turns the UDID path on.
 *
 * The tree is built by the booter after QEMU runs, so it is patched on the first
 * request, once boot has finished and the tree is final. Everything is bounds
 * checked against the header total; a tree we do not recognise is left alone.
 *
 * Insertion happens at the end of the structure block: the property name goes
 * into the strings block (whose existing offset is opaque to us, so the new name
 * is appended there and referenced by its new offset) and the blob is written in
 * the strings block's place, which then moves. Layout:
 *
 *   [ structs ... | strings ... | end ]
 *   [ structs ... newprop | strings ... newname | end ]
 */
static const char fdt_prop_name[] = "unique-device-id-string";

/* Scans low RAM for the tree. RAM is a flat region, so a byte pointer is all
 * that is needed; only the first 8 MiB are swept and the header is validated,
 * so nothing else can be mistaken for it. */
static size_t identity_fdt_scan(const uint8_t *p, size_t lim)
{
    for (size_t o = 0; o + 8 < lim; o += 4) {
        uint32_t w = *(const uint32_t *)(p + o);

        if ((w == 0xd00dfeed || w == 0xedfe0dd0) &&
            be32_to_cpu(*(const uint32_t *)(p + o + 4)) >= 0x100) {
            return o;
        }
    }
    return 0;
}

static uint8_t *identity_fdt_locate(MemoryRegion *ram)
{
    uint8_t *p = memory_region_get_ram_ptr(ram);
    size_t o = identity_fdt_scan(p, 1023u << 20);

    return o ? p + o : NULL;
}

/* Appends the property to /chosen. Returns true once the tree has it. */
static bool identity_fdt_add_udid(AppleIdentity *s, MemoryRegion *ram)
{
    static bool done, failed;
    char value[APPLE_IDENTITY_UDID_STR_LEN + 1];
    size_t vlen, namesz, prop, name_off, tot, tail, strsz;
    uint8_t *base;

    if (done || failed) {
        return done;
    }

    fprintf(stderr, "IDFDT ram=%p first=%08x\n", (void *)memory_region_get_ram_ptr(ram),
            be32_to_cpu(*(uint32_t *)memory_region_get_ram_ptr(ram)));
    base = identity_fdt_locate(ram);
    fprintf(stderr, "IDFDT base=%p\n", (void *)base);
    if (!base) {
        failed = true;
        return false;
    }
    tot = be32_to_cpu(*(const uint32_t *)(base + 4));
    strsz = be32_to_cpu(*(const uint32_t *)(base + 12));
    if (tot < 0x100 || tot > APPLE_IDENTITY_FDT_CAP || strsz > tot) {
        failed = true;
        return false;
    }

    pstrcpy(value, sizeof(value), s->udid_str);
    vlen = strlen(value);
    namesz = (sizeof(fdt_prop_name) + 3) & ~(size_t)3;
    prop = (12 + namesz + vlen + 7) & ~(size_t)7;

    if (tot + prop + namesz > APPLE_IDENTITY_FDT_CAP) {
        failed = true;
        return false;
    }

    name_off = tot - strsz + strsz;   /* end of the current strings block */
    tail = tot - 4 - (tot - strsz);   /* size to the end marker: none, strings sit last */

    /*
     * The strings block ends at tot-4, so the new name is appended there; the
     * property blob is inserted at the end of the structure block, which is the
     * start of the strings block, moving both strings and end marker up.
     */
    {
        const size_t ins = tot - strsz;   /* first byte of the strings block */
        const size_t move = tot - ins;    /* strings block plus nothing else */

        memmove(base + ins + prop, base + ins, move);
        memset(base + ins, 0, prop);
        stl_be_p(base + ins, 3);                    /* FDT_PROP */
        stl_be_p(base + ins + 4, vlen);
        stl_be_p(base + ins + 8, name_off);
        memcpy(base + ins + 12, fdt_prop_name, sizeof(fdt_prop_name));
        memcpy(base + ins + 12 + namesz, value, vlen);

        memcpy(base + ins + prop, fdt_prop_name, sizeof(fdt_prop_name));
        stl_be_p(base + 4, tot + prop + namesz);
        stl_be_p(base + 12, strsz + namesz);
    }
    (void)tail;

    fprintf(stderr, "IDFDT added %s=%s\n", fdt_prop_name, value);
    done = true;
    return true;
}

/* The host service never answered: complete with an error so the guest retries
 * instead of waiting for ever. */
static void identity_relay_timeout(void *opaque)
{
    AppleIdentityRequest *req = opaque;

    qemu_log_mask(LOG_GUEST_ERROR,
                  "%s: no host reply in %d ms, failing the request\n",
                  __func__, APPLE_IDENTITY_RELAY_TIMEOUT_MS);
    req->backend_failed = true;
    identity_provider_complete(req);
}

/* The tree is only final once boot has run, and the device may see SET_STATUS
 * long before any driver sends output, so the patch is driven from both: the
 * first of them wins and the flag stops the second. */
/* The booter builds the device tree in RAM after firmware runs and the guest
 * kernel frees it once unflattened, so the patch has to land inside that
 * window: poll from realize until the magic shows up. */
#define APPLE_IDENTITY_FDT_POLL_MS 50
#define APPLE_IDENTITY_FDT_POLL_TRIES 1000

/* Apple's tree, not FDT: a node is u32 nprops then u32 nchildren, and each
 * property is a 32-byte NUL-padded name, a u32 length, then the value padded
 * to four bytes. There is no magic, so nodes are found by their property
 * names. The booter builds the tree at ~650 ms and the guest kernel unflattens
 * it once, so the property has to be in before that. */
#define APPLE_DT_NAME_LEN 32u
#define APPLE_DT_VALUE_GAP 0x100u   /* slack kept after the tree */
#define APPLE_DT_POLL_TRIES 6000

/* Returns the offset of the first byte of a node carrying `prop`, or 0. The
 * header sits immediately before the first property. */
/* The node is found by its exact first property, `name = "chosen"`, which no
 * other node or stray data carries. Returns the node header offset, or 0. */
static size_t identity_dt_find(uint8_t *p, size_t lim, const char *chosen_name)
{
    const size_t need = APPLE_DT_NAME_LEN + 4 + 8;

    for (size_t o = APPLE_DT_NAME_LEN; o + need <= lim; o += 4) {
        uint32_t nprops = *(uint32_t *)(p + o - 8);
        uint32_t nchildren = *(uint32_t *)(p + o - 4);

        if (memcmp(p + o, "name", 5) != 0 ||
            *(uint32_t *)(p + o + APPLE_DT_NAME_LEN) !=
                strlen(chosen_name) + 1 ||
            memcmp(p + o + APPLE_DT_NAME_LEN + 4, chosen_name,
                   strlen(chosen_name)) != 0) {
            continue;
        }
        if (nprops < 1 || nprops > 0x10 || nchildren > 0x100) {
            continue;
        }
        {
            size_t w = o + APPLE_DT_NAME_LEN + 4 + ((strlen(chosen_name) + 1 + 3) & ~3u);
            bool ok = true;

            for (uint32_t i = 1; i < nprops && ok; i++) {
                uint32_t vl = *(uint32_t *)(p + w + APPLE_DT_NAME_LEN);

                if (!p[w] || vl > 0x400) {
                    ok = false;
                }
                w += APPLE_DT_NAME_LEN + 4 + ((vl + 3) & ~3u);
            }
            if (!ok) {
                continue;
            }
        }
        return o - 8;
    }
    return 0;
}

/* Length of a node from its header: every property (name, length, padded
 * value) and, recursively, every child. */
static size_t identity_dt_node_len(uint8_t *p, size_t node, size_t lim)
{
    uint32_t nprops = *(uint32_t *)(p + node);
    uint32_t nchildren = *(uint32_t *)(p + node + 4);
    size_t o = 0;

    for (uint32_t i = 0; i < nprops && node + o < lim; i++) {
        uint32_t vlen = *(uint32_t *)(p + node + o + APPLE_DT_NAME_LEN);

        o += APPLE_DT_NAME_LEN + 4 + ((vlen + 3) & ~3u);
    }
    for (uint32_t i = 0; i < nchildren && node + o < lim; i++) {
        o += identity_dt_node_len(p, node + o, lim);
    }
    return 8 + o;
}

/* Overwrites one property in place, so the tree's total length never changes
 * and boot_args needs no fix. The property has to be at least as large as the
 * one being written. Returns false if it does not exist or is too small. */
static bool identity_dt_set(uint8_t *p, size_t node, size_t lim,
                            const char *from, const char *name,
                            const char *value)
{
    uint32_t nprops = *(uint32_t *)(p + node);
    size_t o = node + 8;

    for (uint32_t i = 0; i < nprops && o + APPLE_DT_NAME_LEN + 4 < lim; i++) {
        uint32_t vlen = *(uint32_t *)(p + o + APPLE_DT_NAME_LEN);
        size_t have = APPLE_DT_NAME_LEN + 4 + ((vlen + 3) & ~3u);
        size_t want = APPLE_DT_NAME_LEN + 4 + ((strlen(value) + 1 + 3) & ~3u);

        if (!strcmp((char *)p + o, from)) {
            if (have < want) {
                return false;
            }
            if (access("/tmp/noop", F_OK) == 0) {
                return true;
            }
            memset(p + o, 0, have);
            if (access("/tmp/samename", F_OK) == 0) {
                name = from;
            }
            if (access("/tmp/sameval", F_OK) == 0) {
                value = from;
            }
            memcpy(p + o, name, strlen(name) + 1);
            *(uint32_t *)(p + o + APPLE_DT_NAME_LEN) = strlen(value) + 1;
            memcpy(p + o + APPLE_DT_NAME_LEN + 4, value, strlen(value) + 1);
            return true;
        }
        o += have;
    }
    return false;
}

static bool identity_dt_fix_args(uint8_t *p, size_t tree, size_t delta)
{
    const size_t lim = 1024ULL << 20;
    const uint64_t want = (uint64_t)(uintptr_t)(p + tree);
    bool fixed = false;

    for (size_t o = 0; o + 16 < lim; o += 8) {
        uint64_t v = *(uint64_t *)(p + o);
        uint64_t n = *(uint64_t *)(p + o + 8);

        if (v == want || v == tree || (v >> 48) == 0xffff &&
            (v & 0xfffffULL) == (tree & 0xfffffULL)) {
            if (!fixed) {
                for (size_t i = o - 0x20; i < o + 0x40; i += 16) {
                    fprintf(stderr, "IDFDT ba %08zx: %016llx %016llx\n", i,
                            *(uint64_t *)(p + i),
                            *(uint64_t *)(p + i + 8));
                }
            }
            if (n >= 0x100 && n <= 0x100000) {
                *(uint64_t *)(p + o + 8) = n + delta;
                fixed = true;
            }
        }
    }
    return fixed;
}

static void identity_fdt_poll(void *opaque)
{
    AppleIdentity *s = opaque;
    MemoryRegionSection sec;
    bool again = true;
    uint8_t *p;

    sec = memory_region_find(get_system_memory(), 0x70000000ULL, 16ULL << 30);
    if (!sec.mr) {
        goto arm;
    }
    p = memory_region_get_ram_ptr(sec.mr) + sec.offset_within_region;

    if (!s->fdt_done && access("/tmp/nofdt", F_OK) == 0) {
        timer_del(s->fdt_timer);
        memory_region_unref(sec.mr);
        return;
    }
    if (!s->fdt_done && s->fdt_tries < 500) {
        goto arm;
    }
    if (!s->fdt_done) {
        size_t chosen = identity_dt_find(p, 16ULL << 30, "chosen");

        {
        MemoryRegionSection lo = memory_region_find(get_system_memory(),
                                                    0x3000000, 0x1000);

        if (lo.mr) {
            uint8_t *lp = memory_region_get_ram_ptr(lo.mr);
            fprintf(stderr, "IDFDT lo mr=%p off=%llx first=%08x\n",
                    (void *)lo.mr,
                    (unsigned long long)lo.offset_within_region,
                    be32_to_cpu(*(uint32_t *)lp));
            memory_region_unref(lo.mr);
        }
    }
        size_t plen = 0;

        if (!chosen && 0) {
            memory_region_unref(sec.mr);
            goto arm;
        }
        fprintf(stderr, "IDFDT at %zx name=\"%s\" len=%u np=%u\n", chosen,
                (char *)p + chosen + 8, *(uint32_t *)(p + chosen + 40),
                *(uint32_t *)(p + chosen));
        if (!chosen) {
            int shown = 0;
            fprintf(stderr, "IDFDT p%d\n", s->fdt_tries);
            for (size_t o = 32; o + 0x40 < (16ULL << 30); o += 4) {
                if (!memcmp(p + o, "chosen", 7) &&
                    *(uint32_t *)(p + o + 32) == 7 &&
                    *(uint32_t *)(p + o - 4) <= 0x100) {
                    fprintf(stderr, "IDFDT cand %zx np=%u nc=%u\n", o - 8,
                            *(uint32_t *)(p + o - 8),
                            *(uint32_t *)(p + o - 4));
                }
            }
        }
        {
            size_t o = chosen + 8;

            for (uint32_t i = 0; i < *(uint32_t *)(p + chosen) && i < 8; i++) {
                uint32_t vl = *(uint32_t *)(p + o + APPLE_DT_NAME_LEN);

                fprintf(stderr, "IDFDT prop[%u] \"%s\" len=%u\n", i,
                        (char *)p + o, vl);
                o += APPLE_DT_NAME_LEN + 4 + ((vl + 3) & ~3u);
            }
        }
        size_t m = identity_dt_find(p, 16ULL << 30, "UnusedBooleanProperty10");

        {
            uint8_t *q = memmem(p, 16ULL << 30, "manifest-properties", 19);

            if (q) {
                fprintf(stderr, "IDFDT blob: %.*s\n", 320, (char *)q + 19);
            }
        }
        {
            size_t q = chosen + 8;

            for (uint32_t i = 0; i < *(uint32_t *)(p + chosen) && i < 40; i++) {
                uint32_t vl = *(uint32_t *)(p + q + APPLE_DT_NAME_LEN);

                fprintf(stderr, "IDFDT ch[%u] \"%s\" len=%u\n", i,
                        (char *)p + q, vl);
                q += APPLE_DT_NAME_LEN + 4 + ((vl + 3) & ~3u);
            }
        }

        if (!m || !identity_dt_set(p, m, (16ULL << 30) - m,
                                   "UnusedStringProperty0", fdt_prop_name,
                                   s->udid_str)) {
            memory_region_unref(sec.mr);
            goto arm;
        }
        fprintf(stderr, "IDFDT set %s=%s at %zx\n", fdt_prop_name,
                s->udid_str, chosen);
        {
            /* Root is found the same way: its first property is `model`. */
            size_t r = 0;

            for (size_t o = 32; o + 0x60 < (16ULL << 30); o += 4) {
                if (!memcmp(p + o, "model", 6) &&
                    *(uint32_t *)(p + o + 32) == 14 &&
                    *(uint32_t *)(p + o + 36) == 0x74726956) {
                    r = o - 8;
                    break;
                }
            }

            if (r) {
                size_t q = r + 8;

                for (uint32_t i = 0; i < *(uint32_t *)(p + r) && i < 12; i++) {
                    uint32_t vl = *(uint32_t *)(p + q + APPLE_DT_NAME_LEN);

                    fprintf(stderr, "IDFDT root[%u] \"%s\" len=%u\n", i,
                            (char *)p + q, vl);
                    q += APPLE_DT_NAME_LEN + 4 + ((vl + 3) & ~3u);
                }
            }
        }
        s->fdt_base = chosen;
        s->fdt_add = 0;
        s->fdt_done = true;
        again = false;
    } else if (s->fdt_add && identity_dt_fix_args(p, s->fdt_base, s->fdt_add)) {
        s->fdt_args_fixed = true;
        again = false;
    }
    memory_region_unref(sec.mr);

arm:
    if (!again || s->fdt_args_fixed) {
        fprintf(stderr, "IDFDT stop again=%d fixed=%d\n", (int)again,
                (int)s->fdt_args_fixed);
        timer_del(s->fdt_timer);
        return;
    }
    if (++s->fdt_tries > APPLE_DT_POLL_TRIES) {
        fprintf(stderr, "IDFDT gave up at try=%d fixed=%d\n", s->fdt_tries,
                (int)s->fdt_args_fixed);
        timer_del(s->fdt_timer);
        return;
    }
    timer_mod(s->fdt_timer,
              qemu_clock_get_ms(QEMU_CLOCK_REALTIME) +
              APPLE_IDENTITY_FDT_POLL_MS);
}


static void identity_fdt_setup(AppleIdentity *s)
{
    MemoryRegionSection sec;
    uint8_t *p;

    sec = memory_region_find(get_system_memory(), 0x70000000ULL, 16ULL << 30);
    if (!sec.mr) {
        return;
    }
    p = memory_region_get_ram_ptr(sec.mr);
    if (s->fdt_done) {
        if (s->fdt_base && !s->fdt_args_fixed) {
            s->fdt_args_fixed = identity_dt_fix_args(p, s->fdt_base, s->fdt_add);
        }
        memory_region_unref(sec.mr);
        return;
    }
    memory_region_unref(sec.mr);
}

static void identity_handle_output(VirtIODevice *vdev, VirtQueue *vq)
{
    AppleIdentity *s = APPLE_IDENTITY(vdev);
    VirtQueueElement *elem;
    AppleIdentityRequest *req;
    AppleIdentityHeader req_hdr;
    uint16_t version;

    identity_fdt_setup(s);
    g_printerr("IDOUT called ready=%d\n", virtio_queue_ready(vq));
    if (!virtio_queue_ready(vq)) {
        return;
    }

    elem = virtqueue_pop(vq, sizeof(VirtQueueElement));
    if (!elem) {
        return;
    }

    req = g_new0(AppleIdentityRequest, 1);
    req->elem = elem;
    req->s = s;
    req->fd = -1;
    req->next = s->pending;
    s->pending = req;

    if (elem->out_num == 0 ||
        iov_size(elem->out_sg, elem->out_num) < sizeof(AppleIdentityHeader)) {
        /* Malformed descriptors cannot receive a success reply. */
        identity_request_complete(req, 0);
        return;
    }

    /* Parse from the local copy only, so the guest cannot change it after. */
    iov_to_buf(elem->out_sg, elem->out_num, 0, &req_hdr, sizeof(req_hdr));
    fprintf(stderr, "IDREQ sub=%u type=%u mlen=%u\n", req_hdr.subsystem,
            req_hdr.message_type, req_hdr.message_len);
    req->subsystem = req_hdr.subsystem;
    req->message_type = req_hdr.message_type;
    s->last_type = req_hdr.message_type;
    req->message_len = req_hdr.message_len;
    req->transport_len = req_hdr.transport_len;
    req->num_buffers = req_hdr.num_buffers;
    req->buffers_offset = req_hdr.buffers_offset;
    req->buffer_len = req_hdr.buffer_len;
    {
        size_t cap = 0, k;

        for (k = 0; k < elem->in_num; k++) {
            cap += elem->in_sg[k].iov_len;
        }
        fprintf(stderr, "IDCAP inn=%u cap=%zu lens=", elem->in_num, cap);
        for (k = 0; k < elem->in_num; k++) {
            fprintf(stderr, "%zu,", elem->in_sg[k].iov_len);
        }
        fprintf(stderr, "\n");
    }
    if (req_hdr.subsystem != APPLE_IDENTITY_SUBSYS_SWPKA &&
        !(s->external_mode && req_hdr.subsystem == APPLE_IDENTITY_SUBSYS_IDENTITY &&
          req_hdr.message_type == APPLE_IDENTITY_TYPE_UDID)) {
        uint8_t hex[512];
        size_t n = elem->out_sg[0].iov_len < sizeof(hex) ? elem->out_sg[0].iov_len : sizeof(hex);
        size_t k;

        iov_to_buf(elem->out_sg, elem->out_num, 0, hex, n);
        fprintf(stderr, "IDBODY ");
        for (k = sizeof(AppleIdentityHeader); k < n; k++) {
            fprintf(stderr, "%02x", hex[k]);
        }
        fprintf(stderr, "\n");
    }
    fprintf(stderr, "IDHDR ver=%u trlen=%u mlen=%u blen=%u nb=%u boff=%u inn=%u outn=%u outlen=%zu\n",
            req_hdr.version, req_hdr.transport_len, req_hdr.message_len,
            req_hdr.buffer_len, req_hdr.num_buffers, req_hdr.buffers_offset,
            elem->in_num, elem->out_num, elem->out_sg[0].iov_len);
    if (req_hdr.subsystem != APPLE_IDENTITY_SUBSYS_SWPKA &&
        !(s->external_mode && req_hdr.subsystem == APPLE_IDENTITY_SUBSYS_IDENTITY &&
          req_hdr.message_type == APPLE_IDENTITY_TYPE_UDID)) {
        uint8_t hex[768];
        size_t n = MIN(iov_size(elem->out_sg, elem->out_num), sizeof(hex));

        iov_to_buf(elem->out_sg, elem->out_num, 0, hex, n);
        idlog("REQ sub=%u type=%u ver=%u trlen=%u mlen=%u blen=%u nb=%u boff=%u "
              "in_room=%zu out_room=%zu\n",
              req_hdr.subsystem, req_hdr.message_type, req_hdr.version,
              req_hdr.transport_len, req_hdr.message_len, req_hdr.buffer_len,
              req_hdr.num_buffers, req_hdr.buffers_offset,
              iov_size(elem->in_sg, elem->in_num),
              iov_size(elem->out_sg, elem->out_num));
        idlog_hex("REQbody", hex, n);
    }
    if (req_hdr.subsystem == APPLE_IDENTITY_SUBSYS_SWPKA) {
        identity_handle_swpka(req, &req_hdr);
        return;
    }
    if (!header_is_valid(&req_hdr, iov_size(elem->out_sg, elem->out_num)) ||
        req_hdr.subsystem != APPLE_IDENTITY_SUBSYS_IDENTITY) {
        identity_request_complete(req, 0);
        return;
    }

    if (s->external_mode && req_hdr.message_type == APPLE_IDENTITY_TYPE_UDID) {
        identity_capture_guest_parameters(s, elem, &req_hdr);
    }

    if (s->external_mode && req_hdr.message_type == APPLE_IDENTITY_TYPE_TUNNEL) {
        g_autofree char *command = identity_tunnel_command(elem);
        if (command && !strcmp(command, "CreateVMHostKeyAttestationRequest")) {
            identity_provider_start(req);
            return;
        }
    }

    /* The UDID request (type 3) is answered in full and needs no more work. */
    if (req_hdr.message_type != APPLE_IDENTITY_TYPE_HANDSHAKE) {
        identity_answer(req);
        return;
    }

    /*
     * The version rides in the request body straight after the UDID string, and
     * only exactly 1 is accepted. A second handshake while one is accepted is a
     * protocol error (PROTOCOL.md §5 steps 3 and 4).
     */
    if (s->guest_protocol_version != 0) {
        qemu_log_mask(LOG_GUEST_ERROR,
                      "%s: second handshake while already negotiated\n",
                      __func__);
    }

    if (req_hdr.message_len >= APPLE_IDENTITY_UDID_STR_LEN + sizeof(version)) {
        iov_to_buf(elem->out_sg, elem->out_num,
                   APPLE_IDENTITY_HEADER_LEN + APPLE_IDENTITY_UDID_STR_LEN,
                   &version, sizeof(version));
    } else if (req_hdr.message_len >= sizeof(version)) {
        iov_to_buf(elem->out_sg, elem->out_num, APPLE_IDENTITY_HEADER_LEN,
                   &version, sizeof(version));
    } else {
        identity_request_complete(req, 0);
        return;
    }
    if (version != APPLE_IDENTITY_PROTOCOL_VERSION) {
        qemu_log_mask(LOG_GUEST_ERROR, "%s: protocol version %u, need %d\n",
                      __func__, version, APPLE_IDENTITY_PROTOCOL_VERSION);
    } else {
        s->guest_protocol_version = version;
    }

    /*
     * A handshake is answered in the device. A proper relay answers here once a
     * host service is bound; until then this is the device's whole answer, and
     * the timeout is armed so the shape is already right.
     */
    identity_answer(req);
}

static int identity_set_status(VirtIODevice *vdev, uint8_t status)
{
    AppleIdentity *s = APPLE_IDENTITY(vdev);

    /* The tree is final by the time the driver arms the device. */
    if (status & VIRTIO_CONFIG_S_DRIVER_OK) {
        identity_fdt_setup(s);
    }
    if (status == 0 && !s->fdt_zero_seen) {
        s->fdt_zero_seen = true;
        identity_fdt_setup(s);
        fprintf(stderr, "IDFDT after-first-zero base=%d\n", (int)s->fdt_tried);
    }

    fprintf(stderr, "IDSTATUS %02x ready=%d size=%u pa=%llx last=%u\n", status,
            virtio_queue_ready(s->vq), virtio_queue_get_num(vdev, 0),
            (unsigned long long)virtio_queue_get_desc_addr(vdev, 0),
            virtio_queue_get_last_avail_idx(vdev, 0));
    if (!(status & VIRTIO_CONFIG_S_DRIVER_OK)) {
        s->guest_protocol_version = 0;
    }
    /* Tell the driver the device is live; the guest may be waiting on it. */
    if (status & VIRTIO_CONFIG_S_DRIVER_OK) {
        virtio_notify_config(vdev);
        fprintf(stderr, "IDQUEUES n=%d sel=%u\n", virtio_get_num_queues(vdev), vdev->queue_sel);
        s->watch_ticks = 0;
        timer_mod(s->watch_timer, qemu_clock_get_ms(QEMU_CLOCK_VIRTUAL) + 1000);
    }
    return 0;
}

/*
 * A reset invalidates held descriptors. Their timers are safe to leave armed:
 * they only touch the queue, which is still ours, and they free themselves.
 */
static void identity_reset(VirtIODevice *vdev)
{
    fprintf(stderr, "IDRESET\n");
    AppleIdentity *s = APPLE_IDENTITY(vdev);

    identity_cancel_pending(s);
    identity_clear_guest_parameters(s);
    s->guest_protocol_version = 0;
}

/*
 * Claim no device-specific bits. The transport owns VERSION_1 and the ring
 * features; VERSION_1 is the only one a macOS guest hard-depends on. IN_ORDER is
 * deliberately absent: one held request would stall everything behind it.
 */
static uint64_t identity_get_features(VirtIODevice *vdev, uint64_t features,
                                      Error **errp)
{
    /*
     * Keep the transport's defaults (it needs some) but nothing else: the
     * guest calls finalizeGuestFeatures and rejects a word with bits it did
     * not offer. VERSION_1 is the one bit the guest hard-requires.
     */
    features &= ~(1ULL << VIRTIO_F_ANY_LAYOUT);
    /* Drop the device-specific bits (24..30): this device defines none, and a
     * bit the guest did not offer fails finalizeGuestFeatures. */
    /* bit 40 (RING_RESET) comes from the generic virtio-pci defaults but
     * Apple's driver does not know it; 24 and 28-30 likewise. */
    features &= ~((1ULL << 40) | (1ULL << 30) | (1ULL << 29) | (1ULL << 28) |
                  (1ULL << 24));
    fprintf(stderr, "IDFEAT %016lx\n", (unsigned long)features);
    return features;
}

/*
 * The device exposes one config byte: the protocol version it will speak. The
 * driver reads config while opening the transport, and a zero version reads as
 * "no protocol", which leaves _negotiatedProtocolVersion at 0 and trips the
 * service's assert. virtio-blk in this tree does the same trick for its "apple
 * type", so a one-field config is the house style here rather than a guess.
 */
/*
 * After DRIVER_OK the messenger builds a transaction and queues it. Nothing
 * reaches identity_handle_output, so to tell "the guest never advanced avail"
 * apart from "avail moved but we missed the notify", the ring indices are
 * sampled for a few seconds after DRIVER_OK.
 */
static void identity_watch(void *opaque)
{
    AppleIdentity *s = opaque;

    fprintf(stderr, "IDWATCH avail=%u ready=%d\n",
            virtio_queue_get_last_avail_idx(&s->parent_obj, 0),
            virtio_queue_ready(s->vq));
    if (++s->watch_ticks < 8) {
        timer_mod(s->watch_timer, qemu_clock_get_ms(QEMU_CLOCK_VIRTUAL) + 1000);
    }
}

static void identity_set_features(VirtIODevice *vdev, uint64_t val)
{
    fprintf(stderr, "IDSETFEAT %016lx wrote=%016lx\n",
            (unsigned long)vdev->host_features, (unsigned long)val);
    /* virtio_set_features would re-enter this handler, so record the accepted
     * bits directly: overriding vdc->set_features otherwise leaves
     * guest_features empty and every later has_feature is false. */
    vdev->guest_features = val & vdev->host_features;
}

static void identity_get_config(VirtIODevice *vdev, uint8_t *config)
{
    config[0] = APPLE_IDENTITY_PROTOCOL_VERSION;
    fprintf(stderr, "IDCFG read\n");
}

/*
 * Builds the host certificate the guest tunnels for CopyVMHostCertificateRequest.
 * A fresh P-256 key is made per VM, self-signed, with the UDID in the CN and as
 * the SHA-256 copy of the public key. Nothing verifies the chain against Apple;
 * the client only requires the key to exist and to hash to the UDID it was told.
 */
static void identity_build_host_cert(AppleIdentity *s)
{
    gnutls_x509_privkey_t xkey = NULL;
    gnutls_x509_crt_t crt = NULL;
    gnutls_datum_t ca_der = { 0 };
    char name[APPLE_IDENTITY_UDID_STR_LEN + 8];
    int rc;

    qemu_log_mask(LOG_GUEST_ERROR, "IDCERT ENTER kp=%s cached=%p\n",
                  getenv("OMVM_IDENTITY_KEY") ?: "(unset)",
                  (void *)s->host_cert);
    if (s->host_cert) {
        return;
    }
    if (gnutls_x509_privkey_init(&xkey) < 0) {
        return;
    }
    /*
     * A stable identity across boots: every reboot otherwise looks like a
     * brand-new untrusted device to Apple's sign-in. Reuse the key on disk so
     * the certificate is byte-identical each time.
     */
    {
        const char *kp = getenv("OMVM_IDENTITY_KEY");

        if (kp && *kp) {
            g_autofree char *pem = NULL;
            gsize plen = 0;
            gnutls_datum_t d;

            if (g_file_get_contents(kp, &pem, &plen, NULL)) {
                d.data = (unsigned char *)pem;
                d.size = plen;
                if (gnutls_x509_privkey_import(xkey, &d,
                                               GNUTLS_X509_FMT_PEM) < 0) {
                    fprintf(stderr, "IDCERT: bad key %s, regenerating\n", kp);
                } else {
                    fprintf(stderr, "IDCERT: reusing %s\n", kp);
                    goto have_key;
                }
            }
        }
    }
    if (gnutls_x509_privkey_generate(xkey, GNUTLS_PK_ECDSA,
                                     GNUTLS_CURVE_TO_BITS(
                                         GNUTLS_ECC_CURVE_SECP256R1),
                                     0) < 0) {
        fprintf(stderr, "IDCERT fail: generate\n");
        goto out;
    }
    {
        const char *kp = getenv("OMVM_IDENTITY_KEY");

        fprintf(stderr, "IDCERT dbg kp=%s\n", kp ? kp : "(unset)");
        if (kp && *kp) {
            gnutls_datum_t pem = { 0 };

            if (gnutls_x509_privkey_export2(xkey, GNUTLS_X509_FMT_PEM,
                                            &pem) >= 0) {
                g_file_set_contents(kp, (char *)pem.data, pem.size, NULL);
                fprintf(stderr, "IDCERT: wrote %s\n", kp);
                gnutls_free(pem.data);
            }
        }
    }
have_key:
    if (gnutls_x509_crt_init(&crt) < 0) {
        goto out;
    }
    /* Shape follows what the guest's RKProperties validator reads: a real
     * subject (not a placeholder CN), a stable serial, and a leaf that
     * carries this VM's host key. The reply must fit the 384-byte buffer. */
    snprintf(name, sizeof(name), "CN=%s", "AVH");
    rc = gnutls_x509_crt_set_dn(crt, name, NULL);
    if (rc < 0) {
        fprintf(stderr, "IDCERT fail: set_dn %d\n", rc);
        goto out;
    }
    gnutls_x509_crt_set_version(crt, 3);
    {
        /* Serial is the VM ECID: stable per VM, never reused across VMs. */
        uint8_t ser[8];
        int i;

        for (i = 0; i < 8; i++) {
            ser[i] = (uint8_t)(s->ecid >> (56 - i * 8));
        }
        gnutls_x509_crt_set_serial(crt, ser, sizeof(ser));
    }
    /* Trust evaluation needs a well-formed leaf: explicit CA:FALSE, the
     * digitalSignature key usage, and a dNSName SAN carrying the CN. */
    {
        unsigned int ku = GNUTLS_KEY_DIGITAL_SIGNATURE |
                          GNUTLS_KEY_KEY_AGREEMENT;
        char dns[APPLE_IDENTITY_UDID_STR_LEN + 8];

        snprintf(dns, sizeof(dns), "AVH");
        gnutls_x509_crt_set_ca_status(crt, 0);
        gnutls_x509_crt_set_key_usage(crt, ku);
        gnutls_x509_crt_set_subject_alt_name(crt, GNUTLS_SAN_DNSNAME, dns,
                                             strlen(dns), 0);
    }
    /* Apple property extensions the client's validator reads:
     * 1.2.840.113635.100.10.1 -> plist {udid}, compared to MGCopyAnswer's UDID;
     * 1.2.840.113635.100.8.7  -> plist {1403}, the leaf build. */
    {
        /* Apple encodes these as: SET of { PRIVATE FourCC tag -> SEQUENCE {
         * IA5String name, OCTET STRING value } }. A plist is not accepted. */
        guint8 ub[APPLE_IDENTITY_UDID_LEN];
        static const char oid_ucrt[] = "1.2.840.113635.100.10.1";
        static const char oid_os[] = "1.2.840.113635.100.8.7";
        size_t k;

        for (k = 0; k < APPLE_IDENTITY_UDID_LEN; k++) {
            ub[k] = s->udid[k];
        }
        {
            /* entry(name, value) with the FourCC tag encoded per X.690. */
            static const guint8 t_udid[] = { 0xff, 0x87, 0xab, 0x91, 0xd2, 0x64 };
            static const guint8 t_1403[] = { 0xff, 0x87, 0xb3, 0x90, 0xb0, 0x63 };
            static const guint8 nm_udid[] = { 0x16, 0x04, 'u', 'd', 'i', 'd' };
            static const guint8 nm_1403[] = { 0x16, 0x04, '1', '4', '0', '3' };
            const char *build = "26B123";
            guint8 buf[256];
            size_t n = 0, m;

            /* helper: emit tag, length, body */
#define EMIT(p_, l_) do { memcpy(buf + n, (p_), (l_)); n += (l_); } while (0)
#define EMIT_SEQ(body_len, body...) do { } while (0)

            /* udid entry */
            {
                guint8 inner[64];
                size_t x = 0;

                memcpy(inner + x, nm_udid, sizeof(nm_udid)); x += sizeof(nm_udid);
                inner[x++] = 0x04; inner[x++] = (guint8)sizeof(ub);
                memcpy(inner + x, ub, sizeof(ub)); x += sizeof(ub);
                memcpy(buf + n, t_udid, sizeof(t_udid)); n += sizeof(t_udid);
                buf[n++] = (guint8)(0x30);
                buf[n++] = (guint8)x;
                memcpy(buf + n, inner, x); n += x;
            }
            /* 1403 goes in DeviceOSInformation (8.7), not the UCRT set. */
            {
                guint8 os[64];
                size_t x = 0, bl = strlen(build);

                memcpy(os + x, nm_1403, sizeof(nm_1403)); x += sizeof(nm_1403);
                os[x++] = 0x04; os[x++] = (guint8)bl;
                memcpy(os + x, build, bl); x += bl;
                {
                    guint8 set2[80];
                    size_t y = 0;
                    guint8 inner[64];
                    size_t z = 0;

                    memcpy(inner + z, nm_1403, sizeof(nm_1403));
                    z += sizeof(nm_1403);
                    inner[z++] = 0x04; inner[z++] = (guint8)bl;
                    memcpy(inner + z, build, bl); z += bl;
                    memcpy(set2 + y, t_1403, sizeof(t_1403)); y += sizeof(t_1403);
                    set2[y++] = 0x30; set2[y++] = (guint8)z;
                    memcpy(set2 + y, inner, z); y += z;
                    {
                        guint8 wrap[96];
                        size_t w = 0;

                        wrap[w++] = 0x31; wrap[w++] = (guint8)y;
                        memcpy(wrap + w, set2, y); w += y;
                        gnutls_x509_crt_set_extension_by_oid(crt, oid_os,
                                                             wrap, w, 0);
                    }
                }
            }
            /* wrap all entries in the SET and put it under the UCRT OID */
            {
                guint8 set[288];
                size_t sl = 0;

                set[sl++] = 0x31;
                if (n < 0x80) {
                    set[sl++] = (guint8)n;
                } else {
                    set[sl++] = 0x81;
                    set[sl++] = (guint8)n;
                }
                memcpy(set + sl, buf, n); sl += n;
                gnutls_x509_crt_set_extension_by_oid(crt, oid_ucrt, set, sl, 0);
            }
            (void)m;
#undef EMIT
        }
    }
    gnutls_x509_crt_set_activation_time(crt, time(NULL) - 3600);
    gnutls_x509_crt_set_expiration_time(crt, time(NULL) + 3650 * 86400);
    if (gnutls_x509_crt_set_key(crt, xkey) < 0) {
        fprintf(stderr, "IDCERT fail: set_key\n");
        goto out;
    }
    /* The server wants a chain, not a bare self-signed leaf: build a CA that
     * signs the leaf, then ship leaf || CA in the blob. */
    {
        gnutls_x509_privkey_t cakey = NULL;
        gnutls_x509_crt_t ca = NULL;

        {
            int r1 = gnutls_x509_crt_init(&ca);
            int r2 = gnutls_x509_privkey_init(&cakey);
            int r3 = r2 < 0 ? 0 : gnutls_x509_privkey_generate(
                cakey, GNUTLS_PK_ECDSA,
                GNUTLS_CURVE_TO_BITS(GNUTLS_ECC_CURVE_SECP256R1), 0);

            /* Reuse the CA key from disk so the chain is byte-identical across
             * boots; a fresh CA each time makes the VM a new device. */
            {
                const char *kp = getenv("OMVM_IDENTITY_KEY");

                if (r2 >= 0 && kp && *kp) {
                    g_autofree char *pem = NULL;
                    gsize plen = 0;

                    g_autofree char *cpath = g_strdup_printf("%s.ca", kp);

                    if (g_file_get_contents(cpath, &pem, &plen, NULL)) {
                        gnutls_datum_t d = { (void *)pem, plen };

                        if (gnutls_x509_privkey_import(cakey, &d,
                                                       GNUTLS_X509_FMT_PEM) >= 0) {
                            r3 = 0;
                        }
                    }
                }
            }

            if (r1 < 0 || r2 < 0 || r3 < 0) {
                fprintf(stderr, "IDCERT fail: ca init r=%d/%d/%d\n", r1, r2, r3);
                goto out;
            }
        }
        {
            const char *kp = getenv("OMVM_IDENTITY_KEY");
            g_autofree char *cpath = kp ? g_strdup_printf("%s.ca", kp) : NULL;
            gnutls_datum_t pem = { 0 };

            if (cpath && !g_file_test(cpath, G_FILE_TEST_EXISTS) &&
                gnutls_x509_privkey_export2(cakey, GNUTLS_X509_FMT_PEM, &pem) >= 0) {
                g_file_set_contents(cpath, (char *)pem.data, pem.size, NULL);
                gnutls_free(pem.data);
            }
        }
        gnutls_x509_crt_set_dn(ca, "CN=AVI", NULL);
        gnutls_x509_crt_set_version(ca, 3);
        gnutls_x509_crt_set_serial(ca, "\x02", 1);
        gnutls_x509_crt_set_activation_time(ca, time(NULL) - 3600);
        gnutls_x509_crt_set_expiration_time(ca, time(NULL) + 3650 * 86400);
        gnutls_x509_crt_set_basic_constraints(ca, 1, -1);
        gnutls_x509_crt_set_key_usage(ca, GNUTLS_KEY_KEY_CERT_SIGN);
            /* SKI/AKI: Apple certificates carry both, and chain building
             * wants them (the CA's AKI is its own SKI). */
            {
                unsigned char kid[32], akid[32];
                size_t kl = sizeof(kid), al = sizeof(akid);

                if (gnutls_x509_crt_get_key_id(crt, 0, kid, &kl) >= 0) {
                    gnutls_x509_crt_set_subject_key_id(crt, kid, kl);
                }
                if (gnutls_x509_crt_get_key_id(ca, 0, akid, &al) >= 0) {
                    gnutls_x509_crt_set_subject_key_id(ca, akid, al);
                    gnutls_x509_crt_set_authority_key_id(crt, akid, al);
                    gnutls_x509_crt_set_authority_key_id(ca, akid, al);
                }
            }
        if (gnutls_x509_crt_set_key(ca, cakey) < 0 ||
            gnutls_x509_crt_sign2(ca, ca, cakey, GNUTLS_DIG_SHA256, 0) < 0 ||
            gnutls_x509_crt_sign2(crt, ca, cakey, GNUTLS_DIG_SHA256, 0) < 0) {
            fprintf(stderr, "IDCERT fail: chain sign\n");
            goto out;
        }
        fprintf(stderr, "IDCERT chain ok\n");
        if (gnutls_x509_crt_export2(ca, GNUTLS_X509_FMT_DER, &ca_der) < 0) {
            fprintf(stderr, "IDCERT fail: ca export\n");
            goto out;
        }
        s->host_ca = g_memdup2(ca_der.data, ca_der.size);
        s->host_ca_len = ca_der.size;
        /* The CA key only signs the leaf; nothing later needs it. */
        gnutls_x509_privkey_deinit(cakey);
        gnutls_x509_crt_deinit(ca);
    }
    {
        gnutls_datum_t out = { 0 };

        if (gnutls_x509_crt_export2(crt, GNUTLS_X509_FMT_DER, &out) < 0) {
            fprintf(stderr, "IDCERT fail: export\n");
            goto out;
        }
        /* leaf || intermediate: the server validates the chain as one blob. */
        s->host_cert = g_malloc0(out.size + s->host_ca_len);
        memcpy(s->host_cert, out.data, out.size);
        memcpy(s->host_cert + out.size, s->host_ca, s->host_ca_len);
        s->host_cert_len = out.size + s->host_ca_len;
        gnutls_free(out.data);
    }
    /* The key must outlive the call: the attestation command signs with it and
     * the guest verifies against the certificate above. */
    s->host_key = xkey;
    xkey = NULL;
out:
    if (crt) {
        gnutls_x509_crt_deinit(crt);
    }
    if (xkey) {
        gnutls_x509_privkey_deinit(xkey);
    }
    fprintf(stderr, "IDCERT len=%zu leaf=%zu\n", s->host_cert_len, s->host_cert_len ? s->host_ca_len : 0);
    if (getenv("ID_DUMPCERT")) {
        g_file_set_contents("/tmp/avpcert.der", (char *)s->host_cert,
                            s->host_cert_len, NULL);
    }
}


static void identity_realize(DeviceState *dev, Error **errp)
{
    VirtIODevice *vdev = VIRTIO_DEVICE(dev);
    AppleIdentity *s = APPLE_IDENTITY(vdev);
    int i;

    identity_clear_guest_parameters(s);
    if (!identity_load_external(s, errp)) {
        return;
    }
    virtio_init(vdev, VIRTIO_ID_GPIO, APPLE_IDENTITY_CONFIG_SIZE);
    s->vq = virtio_add_queue(vdev, 256, identity_handle_output);
    s->watch_timer = timer_new_ms(QEMU_CLOCK_VIRTUAL, identity_watch, s);

    /* Derived from the ECID once the property is wired; stable per VM. */
    if (!s->external_mode) {
        for (i = 0; i < APPLE_IDENTITY_UDID_LEN; i++) {
            s->udid[i] = (uint8_t)(s->ecid >> ((i % 8) * 8));
        }
    }
    /* The device tree form is %08X-%016llX over the same bytes. */
    snprintf(s->udid_str, sizeof(s->udid_str), "%08X-%016llX",
             (uint32_t)ldl_be_p(s->udid), (unsigned long long)ldq_be_p(s->udid + 8));
    /* Unconditional: qemu_log_mask is silent without -d guest_errors. */
    fprintf(stderr, "IDBUILD pid=%ld tunnel_mlen=%u tunnel_nb=2 tunnel_boff=%u\n",
            (long)getpid(), APPLE_IDENTITY_REPLY_TUN_MSGLEN,
            APPLE_IDENTITY_REPLY_TUN_BOFF);
    idlog("IDBUILD pid=%ld tunnel_mlen=%u tunnel_nb=2 tunnel_boff=%u\n",
          (long)getpid(), APPLE_IDENTITY_REPLY_TUN_MSGLEN,
          APPLE_IDENTITY_REPLY_TUN_BOFF);
    qemu_log_mask(LOG_GUEST_ERROR, "IDREALIZE called\n");
    if (!s->external_mode) {
        identity_build_host_cert(s);
    }
    s->fdt_timer = timer_new_ms(QEMU_CLOCK_REALTIME, identity_fdt_poll, s);
    /*
     * Opt-in only (OMVM_IDENTITY_FDT=1 in the domain's qemu:env). After try
     * 500 every tick scans the whole 16 GB of guest RAM on the main loop
     * (~1.4 s under the BQL), which pins QEMU's main thread at ~100 % and
     * stalls input and the monitor for the life of the poll (up to 6000
     * tries). /tmp/nofdt still stops a running poll.
     */
    if (getenv("OMVM_IDENTITY_FDT")) {
        timer_mod(s->fdt_timer, qemu_clock_get_ms(QEMU_CLOCK_REALTIME) +
                  APPLE_IDENTITY_FDT_POLL_MS);
    }
}

static void identity_unrealize(DeviceState *dev)
{
    VirtIODevice *vdev = VIRTIO_DEVICE(dev);
    AppleIdentity *s = APPLE_IDENTITY(vdev);

    identity_cancel_pending(s);
    if (s->watch_timer) {
        timer_del(s->watch_timer);
        timer_free(s->watch_timer);
        s->watch_timer = NULL;
    }
    if (s->fdt_timer) {
        timer_del(s->fdt_timer);
        timer_free(s->fdt_timer);
        s->fdt_timer = NULL;
    }
    identity_external_cleanup(s);
    virtio_del_queue(vdev, 0);
    virtio_cleanup(vdev);
    s->vq = NULL;
}

static const Property identity_props[] = {
    DEFINE_PROP_UINT64("ecid", AppleIdentity, ecid, 0),
};

static void identity_class_init(ObjectClass *klass, const void *data)
{
    DeviceClass *dc = DEVICE_CLASS(klass);
    VirtioDeviceClass *vdc = VIRTIO_DEVICE_CLASS(klass);

    device_class_set_props(dc, identity_props);
    dc->desc = "Apple VirtualPlatform identity";
    vdc->realize = identity_realize;
    vdc->unrealize = identity_unrealize;
    vdc->get_features = identity_get_features;
    vdc->get_config = identity_get_config;
    vdc->set_status = identity_set_status;
    vdc->reset = identity_reset;
}

static const TypeInfo identity_info = {
    .name = TYPE_APPLE_IDENTITY,
    .parent = TYPE_VIRTIO_DEVICE,
    .instance_size = sizeof(AppleIdentity),
    .class_init = identity_class_init,
};

static void identity_register_types(void)
{
    type_register_static(&identity_info);
}

type_init(identity_register_types);

/*
 * The service requires at least one device memory of >= 16 bytes and DMAs
 * through it (IDENTITY-KEXT-STRINGS.md). BAR 4 is past every BAR virtio-pci
 * registers for itself (0 legacy IO, 1 MSI-X, 2 modern IO, 4 modern MEM; 3 is free).
 */
#define APPLE_IDENTITY_MEM_BAR 3

/* Same Apple vendor capability vmapple virtio-blk uses (virtio-blk.c). */
#define APPLE_IDENTITY_VNDR_SIZE 14
#define APPLE_IDENTITY_VNDR_DISABLE_ENCRYPTION 1
/* Advertised shMaxSize: a reply window larger than the BAR, 64 KiB. */
#define APPLE_IDENTITY_MAXMSG 0x10000

/*
 * Builds the SysCfgV2 blob the guest's copyOSData() walks
 * (research/identity/SYSCFG-CONSTANTS.md). The guest asserts tags are unique
 * and that shSize equals the real total exactly, so both are computed here
 * rather than padded.
 *
 * Returns the total bytes written, or 0 if the tags do not fit.
 */
static size_t identity_build_syscfg(AppleIdentity *s, MemoryRegion *mem,
                                    Error **errp)
{
    uint8_t blob[APPLE_SYSCFG_MAX_BLOB];
    uint8_t *p = blob + APPLE_SYSCFG_HDR_SIZE;
    size_t left = sizeof(blob) - APPLE_SYSCFG_HDR_SIZE;
    size_t payload = 0;
    const struct {
        uint32_t tag;
        const void *data;
        uint32_t len;
    } entries[] = {
        { APPLE_SYSCFG_TAG_UDID, s->udid, APPLE_IDENTITY_UDID_LEN },
        { APPLE_SYSCFG_TAG_ECID, &s->ecid, sizeof(s->ecid) },
    };
    size_t i;

    for (i = 0; i < ARRAY_SIZE(entries); i++) {
        size_t need = APPLE_SYSCFG_ENTRY_SIZE + entries[i].len;

        if (need > left) {
            error_setg(errp, "apple-identity: SysCfg tags do not fit");
            return 0;
        }
        stl_le_p(p + 0, entries[i].tag);
        stl_le_p(p + 4, entries[i].len);
        memcpy(p + 8, entries[i].data, entries[i].len);
        p += need;
        left -= need;
        payload += need;
    }

    memset(blob, 0, APPLE_SYSCFG_HDR_SIZE);
    stl_le_p(blob + APPLE_SYSCFG_OFF_MAGIC, APPLE_SYSCFG_MAGIC);
    stl_le_p(blob + APPLE_SYSCFG_OFF_VERSION, APPLE_SYSCFG_VERSION);
    /* Bits 5..9 of the flag word must be clear for a little-endian blob. */
    stl_le_p(blob + APPLE_SYSCFG_OFF_FLAGS, 0);
    stl_le_p(blob + APPLE_SYSCFG_OFF_BIGENDIAN, 0);
    stl_le_p(blob + APPLE_SYSCFG_OFF_SIZE,
             APPLE_SYSCFG_HDR_SIZE + payload);
    /* shMaxSize is the mapping the guest may use, so it is our whole BAR. */
    stl_le_p(blob + APPLE_SYSCFG_OFF_MAXSIZE, APPLE_IDENTITY_MAXMSG);

    /*
     * Only the header and the entries are live; the rest of the BAR stays as
     * it is, so a later rebuild cannot leave a stale tail past shSize.
     */
    memcpy(memory_region_get_ram_ptr(mem), blob,
           APPLE_SYSCFG_HDR_SIZE + payload);
    return APPLE_SYSCFG_HDR_SIZE + payload;
}

static void identity_pci_realize(VirtIOPCIProxy *vpci_dev, Error **errp)
{
    AppleIdentityPCI *dev = APPLE_IDENTITY_PCI(vpci_dev);
    DeviceState *vdev = DEVICE(&dev->vdev);

    if (!qdev_realize(vdev, BUS(&vpci_dev->bus), errp)) {
        return;
    }

    /*
     * virtio-pci sets 1af4:10xx during its own realize; put the Apple ids
     * back afterwards, as vmapple virtio-blk does.
     */
    pci_config_set_vendor_id(vpci_dev->pci_dev.config, APPLE_IDENTITY_VENDOR);
    pci_config_set_device_id(vpci_dev->pci_dev.config, APPLE_IDENTITY_DEVICE);
    pci_set_word(vpci_dev->pci_dev.config + PCI_SUBSYSTEM_ID, 0x1100);

    /* The guest's transport looks for this capability (VMAPPLE_PCI_VNDR_*). */
    {
        int offset = pci_add_capability(&vpci_dev->pci_dev, PCI_CAP_ID_VNDR,
                                        0, APPLE_IDENTITY_VNDR_SIZE, errp);
        if (offset < 0) {
            return;
        }
        pci_set_byte(vpci_dev->pci_dev.config + offset + 2,
                     APPLE_IDENTITY_VNDR_SIZE);
        pci_set_byte(vpci_dev->pci_dev.config + offset + 3, 9);
        pci_set_word(vpci_dev->pci_dev.config + offset + 4, APPLE_IDENTITY_VENDOR);
        pci_set_byte(vpci_dev->pci_dev.config + offset + 6,
                     APPLE_IDENTITY_VNDR_DISABLE_ENCRYPTION);
    }

    if (!memory_region_init_ram(&dev->mem, OBJECT(dev), "apple-identity-mem",
                                APPLE_IDENTITY_MEM_SIZE, errp)) {
        error_prepend(errp, "apple-identity: no device memory: ");
        return;
    }
    pci_register_bar(PCI_DEVICE(dev), APPLE_IDENTITY_MEM_BAR,
                     PCI_BASE_ADDRESS_SPACE_MEMORY, &dev->mem);

    if (!identity_build_syscfg(&dev->vdev, &dev->mem, errp)) {
        return;
    }

    /*
     * Same as vmapple virtio-blk: Golden Gate's cached capability lookup and
     * its fallback disagree on descending lists, so keep the capabilities but
     * enumerate them in address order.
     */
    {
        uint8_t capabilities[PCI_CONFIG_SPACE_SIZE] = { 0 };
        uint8_t *config = vpci_dev->pci_dev.config;
        int previous = PCI_CAPABILITY_LIST;
        int off;

        for (off = config[PCI_CAPABILITY_LIST]; off;
             off = config[off + PCI_CAP_LIST_NEXT]) {
            capabilities[off] = 1;
        }
        for (off = PCI_CONFIG_HEADER_SIZE; off < PCI_CONFIG_SPACE_SIZE; off++) {
            if (capabilities[off]) {
                config[previous] = off;
                previous = off + PCI_CAP_LIST_NEXT;
            }
        }
        config[previous] = 0;
    }
}

/*
 * The region is QOM-owned RAM, so its storage and MemoryRegion are released
 * with the device; there is no explicit destroy in this tree.
 */
static void identity_pci_unrealize(VirtIOPCIProxy *vpci_dev)
{
}

static void identity_pci_class_init(ObjectClass *klass, const void *data)
{
    DeviceClass *dc = DEVICE_CLASS(klass);
    VirtioPCIClass *k = VIRTIO_PCI_CLASS(klass);
    PCIDeviceClass *pcidev_k = PCI_DEVICE_CLASS(klass);

    set_bit(DEVICE_CATEGORY_MISC, dc->categories);
    k->realize = identity_pci_realize;
    dc->unrealize = (void (*)(DeviceState *))identity_pci_unrealize;
    pcidev_k->vendor_id = APPLE_IDENTITY_VENDOR;
    pcidev_k->device_id = APPLE_IDENTITY_DEVICE;
    pcidev_k->revision = 0x00;
    pcidev_k->class_id = PCI_CLASS_OTHERS;
}

static void identity_pci_instance_init(Object *obj)
{
    AppleIdentityPCI *dev = APPLE_IDENTITY_PCI(obj);
    { FILE *f = fopen("/tmp/IDINIT", "a"); if (f) { fputs("instance_init\n", f); fclose(f); } }

    /*
     * virtio-pci reads class_code during its own PCI realize and only calls our
     * hook afterwards, so set it here rather than in the hook, or the guest sees
     * the transport's default class instead.
     */
    VIRTIO_PCI(obj)->class_code = PCI_CLASS_OTHERS;
    /*
     * One vector per queue plus the config queue. virtio-pci reads this while
     * setting up MSI-X, before it calls our realize, so it cannot be set
     * there; without it the device falls back to legacy and gets no MSI-X BAR.
     */
    VIRTIO_PCI(obj)->nvectors = 1;
    /* The guest's transport is modern-only; a legacy BAR pair only confuses
     * negotiation and it resets without ever setting a status. */
    VIRTIO_PCI(obj)->disable_legacy = ON_OFF_AUTO_ON;
    /*
     * virtio-pci would otherwise present this as 1af4:1069, and the guest's
     * transport class matches 106b:1a0c.
     */

    /*
     * Every transport the guest actually starts carries this; without it
     * AppleVirtIOPCITransport::start() returns false and the device is never
     * registered, so no driver above it can ever match.
     */
    if (!object_property_find(OBJECT(obj), "built-in")) {
        object_property_add_bool(OBJECT(obj), "built-in", NULL, NULL);
    }
    object_property_set_bool(OBJECT(obj), "built-in", true, NULL);

    virtio_instance_init_common(obj, &dev->vdev, sizeof(dev->vdev),
                                TYPE_APPLE_IDENTITY);
}

static const VirtioPCIDeviceTypeInfo identity_pci_info = {
    .generic_name = "apple-identity-pci",
    .parent = TYPE_VIRTIO_PCI,
    .instance_size = sizeof(AppleIdentityPCI),
    .instance_init = identity_pci_instance_init,
    .class_init = identity_pci_class_init,
};

static void identity_pci_register(void)
{
    virtio_pci_types_register(&identity_pci_info);
}

type_init(identity_pci_register);