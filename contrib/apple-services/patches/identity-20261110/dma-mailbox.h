/*
 * AVP configuration-register DMA mailbox.
 * SPDX-License-Identifier: GPL-2.0-or-later
 */
#ifndef HW_VMAPPLE_DMA_MAILBOX_H
#define HW_VMAPPLE_DMA_MAILBOX_H

#include "hw/core/sysbus.h"

#define TYPE_DMA_MAILBOX "vmapple.dma-mailbox"
OBJECT_DECLARE_SIMPLE_TYPE(DmaMailbox, DMA_MAILBOX)

struct DmaMailbox {
    SysBusDevice parent_obj;

    MemoryRegion iomem;
    uint64_t last_addr;
    /*
     * The host key is the 20 raw UDID bytes, not an opaque 32-byte blob:
     * IdentityService asserts _hostKey->getLength() and the kext then hex
     * expands exactly those bytes, so the length and content both matter.
     */
    uint8_t host_key[20];
    uint32_t host_key_len;
};

#endif