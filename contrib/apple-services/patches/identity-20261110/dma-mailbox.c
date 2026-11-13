/*
 * AVP configuration-register DMA mailbox, virtio-independent.
 * SPDX-License-Identifier: GPL-2.0-or-later
 *
 * Apple's platform expert fetches the VM host key by DMAing a request through a
 * configuration register at GPA 0x4ffff8 (see
 * research/identity/HOSTKEY-MAILBOX.md). The guest builds this request in its
 * own memory, writes its physical address to the register with one 64-bit
 * store, then polls the request for completion:
 *
 *   +0x00 u16 ver  (must be 1)
 *   +0x02 u8  dir
 *   +0x03 u8  done (guest clears it, host sets it)
 *   +0x04 u32 id   (1 = read the host key)
 *   +0x08 u64 buf  physical address of the reply buffer, below 4 GiB
 *   +0x10 u64 len  buffer length
 *
 * On done the guest reads +0x08 as the error code (0 = OK) and +0x10 as the
 * length. A request left incomplete for long enough makes the guest give up
 * with EINVAL and leave the host key NULL, which is what stops the identity
 * service from ever starting. So completion happens in the same store, while
 * the guest is still spinning.
 *
 * The mailbox is deliberately synchronous: there is no interrupt, no queue and
 * no state beyond the register.
 */

#include "qemu/osdep.h"
#include "qemu/log.h"
#include "qemu/module.h"
#include "hw/core/sysbus.h"
#include "system/memory.h"
#include "system/address-spaces.h"

#include "hw/vmapple/dma-mailbox.h"
#include "hw/vmapple/apple-identity.h"

/* Request field offsets, above. */
#define REQ_VERSION     0x00
#define REQ_DIR         0x02
#define REQ_DONE        0x03
#define REQ_ID          0x04
#define REQ_BUF         0x08
#define REQ_LEN         0x10
#define REQ_SIZE        0x20

/* Register 1 is the host key read. */
#define REG_HOST_KEY    1

/*
 * The guest asks for 0x1000 first and only grows on error 0xc, so this covers
 * every request it makes. Real Virtualization.framework has not been measured;
 * the guest only needs a non-empty value, and 32 bytes is comfortable.
 */
#define HOST_KEY_LEN    APPLE_IDENTITY_UDID_LEN

/* Fallback only; create_cfg() overrides it with the VM identity. */
static const uint8_t default_host_key[APPLE_IDENTITY_UDID_LEN] = {
    0x41, 0x56, 0x50, 0x48, 0x4f, 0x53, 0x54, 0x4b, 0x45, 0x59,
    0x30, 0x30, 0x30, 0x30, 0x31, 0x32, 0x33, 0x34, 0x35, 0x36,
};
static uint64_t mailbox_read(void *opaque, hwaddr off, unsigned size)
{
    /* The register itself is write-only; a read returns the last address. */
    DmaMailbox *s = DMA_MAILBOX(opaque);

    fprintf(stderr, "IDMAIL rd off=%llx\n", (unsigned long long)off);
    return s->last_addr;
}

/* Completes one request in guest memory. */
static void mailbox_complete(DmaMailbox *s, hwaddr req, unsigned size)
{
    uint8_t hdr[REQ_SIZE];
    uint16_t ver;
    uint32_t id, len;
    uint64_t buf;
    uint32_t err = 0;

    if (size < REQ_SIZE ||
        address_space_read(&address_space_memory, req, MEMTXATTRS_UNSPECIFIED,
                           hdr, sizeof(hdr)) != MEMTX_OK) {
        return;
    }

    ver = lduw_le_p(hdr + REQ_VERSION);
    id = ldl_le_p(hdr + REQ_ID);
    buf = ldq_le_p(hdr + REQ_BUF);
    len = ldl_le_p(hdr + REQ_LEN);

    if (ver != 1) {
        err = 1;
    } else if (id == REG_HOST_KEY) {
        if (buf == 0 || buf >= 0x100000000ULL) {
            err = 2;
        } else {
            uint32_t n = MIN(len, s->host_key_len ? s->host_key_len : HOST_KEY_LEN);

            if (address_space_write(&address_space_memory, buf, MEMTXATTRS_UNSPECIFIED,
                                    s->host_key, n) != MEMTX_OK) {
                err = 2;
            } else {
                len = n;
            }
        }
    } else {
        err = 3;
    }

    if (err) {
        len = 0;
    }

    /* +8 carries the error code on completion, not the buffer address. */
    stq_le_p(hdr + REQ_BUF, err);
    stl_le_p(hdr + REQ_LEN, len);
    hdr[REQ_DONE] = 1;

    address_space_write(&address_space_memory, req, MEMTXATTRS_UNSPECIFIED, hdr, sizeof(hdr));

    qemu_log_mask(LOG_UNIMP, "%s: id %u len 0x%x err %u\n", __func__, id, len,
                  err);
    fprintf(stderr, "IDMAILDONE req=%llx id=%u len=%u err=%u\n",
            (unsigned long long)req, id, len, err);
}

static void mailbox_write(void *opaque, hwaddr off, uint64_t val, unsigned size)
{
    DmaMailbox *s = DMA_MAILBOX(opaque);

    fprintf(stderr, "IDMAIL wr off=%llx val=%llx size=%u\n",
            (unsigned long long)off, (unsigned long long)val, size);
    s->last_addr = val;
    if (val) {
        mailbox_complete(s, val, REQ_SIZE);
    }
}

static const MemoryRegionOps mailbox_ops = {
    .read = mailbox_read,
    .write = mailbox_write,
    .endianness = DEVICE_LITTLE_ENDIAN,
    .valid = { .min_access_size = 4, .max_access_size = 8 },
    .impl = { .min_access_size = 4, .max_access_size = 8 },
};

static void mailbox_realize(DeviceState *dev, Error **errp)
{
    DmaMailbox *s = DMA_MAILBOX(dev);

    memcpy(s->host_key, default_host_key, sizeof(s->host_key));
    s->host_key_len = sizeof(s->host_key);
    memory_region_init_io(&s->iomem, OBJECT(dev), &mailbox_ops, s,
                          TYPE_DMA_MAILBOX, 0x8);
    sysbus_init_mmio(SYS_BUS_DEVICE(dev), &s->iomem);
}

static void mailbox_class_init(ObjectClass *klass, const void *data)
{
    DeviceClass *dc = DEVICE_CLASS(klass);

    dc->realize = mailbox_realize;
    dc->desc = "AVP configuration DMA mailbox";
}

static const TypeInfo mailbox_info = {
    .name = TYPE_DMA_MAILBOX,
    .parent = TYPE_SYS_BUS_DEVICE,
    .instance_size = sizeof(DmaMailbox),
    .class_init = mailbox_class_init,
};

static void mailbox_register_types(void)
{
    type_register_static(&mailbox_info);
}

type_init(mailbox_register_types);
