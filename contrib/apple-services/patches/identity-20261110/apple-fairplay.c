/* SPDX-License-Identifier: GPL-2.0-or-later */
/* Local ADI transport experiment; not a complete FairPlay implementation. */
#include "qemu/osdep.h"
#include <sys/un.h>
#include "qemu/module.h"
#include "qemu/main-loop.h"
#include "qemu/timer.h"
#include "qemu/sockets.h"
#include "qemu/iov.h"
#include "qapi/error.h"
#include "migration/vmstate.h"
#include "hw/core/qdev-properties.h"
#include "hw/virtio/virtio.h"
#include "hw/virtio/virtio-pci.h"
#include "hw/pci/pci_device.h"
#include "standard-headers/linux/virtio_ids.h"

#define TYPE_APPLE_FAIRPLAY "apple-fairplay"
#define TYPE_APPLE_FAIRPLAY_PCI "apple-fairplay-pci"
#define FP_MAX (1024 * 1024)
OBJECT_DECLARE_SIMPLE_TYPE(AppleFairPlay, APPLE_FAIRPLAY)
OBJECT_DECLARE_SIMPLE_TYPE(AppleFairPlayPCI, APPLE_FAIRPLAY_PCI)

struct AppleFairPlay {
    VirtIODevice parent_obj;
    VirtQueue *vq[4];
    VirtQueueElement *elem;
    VirtQueue *active_vq;
    char *socket_path;
    int fd;
    QEMUTimer *timer;
    uint8_t *tx, *rx;
    size_t tx_len, tx_off, rx_len, capacity;
    bool connected, failed;
};

struct AppleFairPlayPCI {
    VirtIOPCIProxy parent_obj;
    AppleFairPlay vdev;
};

static void fp_handle(VirtIODevice *vdev, VirtQueue *vq);

static void fp_close(AppleFairPlay *s)
{
    if (s->fd >= 0) {
        qemu_set_fd_handler(s->fd, NULL, NULL, NULL);
        close(s->fd);
        s->fd = -1;
    }
    if (s->timer) {
        timer_del(s->timer);
    }
    if (s->tx) {
        memset(s->tx, 0, s->tx_len);
        g_clear_pointer(&s->tx, g_free);
    }
    if (s->rx) {
        memset(s->rx, 0, s->capacity + 17);
        g_clear_pointer(&s->rx, g_free);
    }
    s->tx_len = s->tx_off = s->rx_len = s->capacity = 0;
    s->connected = false;
}

static void fp_cancel(AppleFairPlay *s)
{
    fp_close(s);
    if (s->elem) {
        virtqueue_detach_element(s->active_vq, s->elem, 0);
        g_clear_pointer(&s->elem, g_free);
    }
}

static void fp_fail(AppleFairPlay *s, const char *reason)
{
    s->failed = true;
    /* No established guest error payload: request reset, never fake success. */
    virtio_error(VIRTIO_DEVICE(s), "apple-fairplay: %s", reason);
    fp_cancel(s);
}

static void fp_timeout(void *opaque)
{
    fp_fail(opaque, "relay deadline exceeded");
}

static void fp_read(void *opaque)
{
    AppleFairPlay *s = opaque;
    VirtIODevice *vdev = VIRTIO_DEVICE(s);
    ssize_t n;
    uint32_t length;
    VirtQueue *completed;

    for (;;) {
        n = recv(s->fd, s->rx + s->rx_len,
                 s->capacity + 17 - s->rx_len, 0);
        if (n < 0) {
            if (errno == EINTR) {
                continue;
            }
            if (errno == EAGAIN || errno == EWOULDBLOCK) {
                return;
            }
            fp_fail(s, "relay receive failed");
            return;
        }
        if (!n) {
            break;
        }
        s->rx_len += n;
        if (s->rx_len >= 16) {
            length = ldl_le_p(s->rx + 12);
            if (memcmp(s->rx, "OFR1", 4) ||
                ldl_le_p(s->rx + 4) || ldl_le_p(s->rx + 8) ||
                length > s->capacity || s->rx_len > length + 16) {
                fp_fail(s, "relay rejected request or returned invalid frame");
                return;
            }
        }
    }
    if (s->rx_len < 16 || s->rx_len != 16 + ldl_le_p(s->rx + 12)) {
        fp_fail(s, "truncated relay response");
        return;
    }
    length = ldl_le_p(s->rx + 12);
    iov_memset(s->elem->in_sg, s->elem->in_num, 0, 0, s->capacity);
    iov_from_buf(s->elem->in_sg, s->elem->in_num, 0, s->rx + 16, length);
    completed = s->active_vq;
    virtqueue_push(completed, s->elem, length);
    g_clear_pointer(&s->elem, g_free);
    fp_close(s);
    virtio_notify(vdev, completed);
    fp_handle(vdev, completed == s->vq[0] ? s->vq[3] : s->vq[0]);
    fp_handle(vdev, completed);
}

static void fp_write(void *opaque)
{
    AppleFairPlay *s = opaque;
    int error = 0;
    socklen_t error_len = sizeof(error);
    ssize_t n;

    if (!s->connected) {
        if (getsockopt(s->fd, SOL_SOCKET, SO_ERROR, &error, &error_len) || error) {
            fp_fail(s, "relay connect failed");
            return;
        }
        s->connected = true;
    }
    while (s->tx_off < s->tx_len) {
        n = send(s->fd, s->tx + s->tx_off, s->tx_len - s->tx_off,
                 MSG_NOSIGNAL);
        if (n < 0 && errno == EINTR) {
            continue;
        }
        if (n < 0 && (errno == EAGAIN || errno == EWOULDBLOCK)) {
            return;
        }
        if (n <= 0) {
            fp_fail(s, "relay send failed");
            return;
        }
        s->tx_off += n;
    }
    if (shutdown(s->fd, SHUT_WR)) {
        fp_fail(s, "relay half-close failed");
        return;
    }
    qemu_set_fd_handler(s->fd, fp_read, NULL, s);
}

static void fp_handle(VirtIODevice *vdev, VirtQueue *vq)
{
    AppleFairPlay *s = APPLE_FAIRPLAY(vdev);
    struct sockaddr_un address = { .sun_family = AF_UNIX };
    size_t input;
    int result;

    if (s->failed || !virtio_queue_ready(vq) || virtio_queue_empty(vq)) {
        return;
    }
    if (vq != s->vq[3] && vq != s->vq[0]) {
        fp_fail(s, vq == s->vq[1] ? "unsupported queue 1" : "unsupported queue 2");
        return;
    }
    if (s->elem) {
        return;
    }
    s->elem = virtqueue_pop(vq, sizeof(VirtQueueElement));
    if (!s->elem) {
        return;
    }
    s->active_vq = vq;
    input = iov_size(s->elem->out_sg, s->elem->out_num);
    s->capacity = iov_size(s->elem->in_sg, s->elem->in_num);
    if (!input || input > FP_MAX || !s->capacity || s->capacity > FP_MAX) {
        fp_fail(s, "invalid ADI descriptor lengths");
        return;
    }
    s->tx_len = input + 16;
    s->tx = g_malloc(s->tx_len);
    s->rx = g_malloc0(s->capacity + 17);
    memcpy(s->tx, "OFP2", 4);
    stl_le_p(s->tx + 4, input);
    stl_le_p(s->tx + 8, s->capacity);
    stl_le_p(s->tx + 12, vq == s->vq[0] ? 0 : 3);
    iov_to_buf(s->elem->out_sg, s->elem->out_num, 0, s->tx + 16, input);
    memcpy(address.sun_path, s->socket_path, strlen(s->socket_path) + 1);
    s->fd = socket(AF_UNIX, SOCK_STREAM | SOCK_NONBLOCK | SOCK_CLOEXEC, 0);
    if (s->fd < 0) {
        fp_fail(s, "socket creation failed");
        return;
    }
    result = connect(s->fd, (struct sockaddr *)&address, sizeof(address));
    if (result && errno != EINPROGRESS) {
        fp_fail(s, "relay unavailable");
        return;
    }
    s->connected = result == 0;
    timer_mod(s->timer, qemu_clock_get_ms(QEMU_CLOCK_REALTIME) + 15000);
    qemu_set_fd_handler(s->fd, NULL, fp_write, s);
}

static uint64_t fp_features(VirtIODevice *vdev, uint64_t features, Error **errp)
{
    /* Bit 0 enables queue 2 host requests. Not supported by this experiment. */
    return features & ~((1ULL << 40) | (1ULL << 30) | (1ULL << 29) |
                        (1ULL << 28) | (1ULL << 27) | (1ULL << 24) | 1ULL);
}

static void fp_reset(VirtIODevice *vdev)
{
    AppleFairPlay *s = APPLE_FAIRPLAY(vdev);
    fp_cancel(s);
    s->failed = false;
}

static void fp_realize(DeviceState *dev, Error **errp)
{
    AppleFairPlay *s = APPLE_FAIRPLAY(dev);
    struct sockaddr_un address;
    int i;

    s->fd = -1;
    if (!s->socket_path || !s->socket_path[0] ||
        strlen(s->socket_path) >= sizeof(address.sun_path)) {
        error_setg(errp, "apple-fairplay requires a valid relay-socket path");
        return;
    }
    /* Internal ID only; PCI identification is overridden below. */
    virtio_init(VIRTIO_DEVICE(dev), VIRTIO_ID_GPIO, 0);
    for (i = 0; i < 4; i++) {
        s->vq[i] = virtio_add_queue(VIRTIO_DEVICE(dev), 256, fp_handle);
    }
    s->timer = timer_new_ms(QEMU_CLOCK_REALTIME, fp_timeout, s);
}

static void fp_unrealize(DeviceState *dev)
{
    AppleFairPlay *s = APPLE_FAIRPLAY(dev);
    int i;

    fp_cancel(s);
    timer_free(s->timer);
    s->timer = NULL;
    for (i = 0; i < 4; i++) {
        virtio_del_queue(VIRTIO_DEVICE(dev), i);
    }
    virtio_cleanup(VIRTIO_DEVICE(dev));
}

static const Property fp_props[] = {
    DEFINE_PROP_STRING("relay-socket", AppleFairPlay, socket_path),
};

static const VMStateDescription fp_vmstate = {
    .name = TYPE_APPLE_FAIRPLAY,
    .unmigratable = 1,
};

static void fp_class_init(ObjectClass *klass, const void *data)
{
    DeviceClass *dc = DEVICE_CLASS(klass);
    VirtioDeviceClass *vdc = VIRTIO_DEVICE_CLASS(klass);
    device_class_set_props(dc, fp_props);
    dc->desc = "Experimental Apple ADI relay";
    /* Outstanding backend state cannot migrate. */
    dc->vmsd = &fp_vmstate;
    vdc->realize = fp_realize;
    vdc->unrealize = fp_unrealize;
    vdc->get_features = fp_features;
    vdc->reset = fp_reset;
}

static void fp_pci_realize(VirtIOPCIProxy *proxy, Error **errp)
{
    AppleFairPlayPCI *s = APPLE_FAIRPLAY_PCI(proxy);
    uint8_t *config = proxy->pci_dev.config;
    uint8_t caps[PCI_CONFIG_SPACE_SIZE] = { 0 };
    int off, previous;

    if (!qdev_realize(DEVICE(&s->vdev), BUS(&proxy->bus), errp)) {
        return;
    }
    pci_config_set_vendor_id(config, 0x106b);
    pci_config_set_device_id(config, 0x1a08);
    pci_set_word(config + PCI_SUBSYSTEM_ID, 0x1100);
    off = pci_add_capability(&proxy->pci_dev, PCI_CAP_ID_VNDR, 0, 14, errp);
    if (off < 0) {
        return;
    }
    config[off + 2] = 14;
    config[off + 3] = 9;
    pci_set_word(config + off + 4, 0x106b);
    config[off + 6] = 1;
    for (off = config[PCI_CAPABILITY_LIST]; off;
         off = config[off + PCI_CAP_LIST_NEXT]) {
        caps[off] = 1;
    }
    previous = PCI_CAPABILITY_LIST;
    for (off = PCI_CONFIG_HEADER_SIZE; off < PCI_CONFIG_SPACE_SIZE; off++) {
        if (caps[off]) {
            config[previous] = off;
            previous = off + PCI_CAP_LIST_NEXT;
        }
    }
    config[previous] = 0;
}

static void fp_pci_init(Object *obj)
{
    AppleFairPlayPCI *s = APPLE_FAIRPLAY_PCI(obj);
    VirtIOPCIProxy *proxy = VIRTIO_PCI(obj);
    proxy->class_code = PCI_CLASS_OTHERS;
    proxy->nvectors = 5;
    proxy->disable_legacy = ON_OFF_AUTO_ON;
    if (!object_property_find(obj, "built-in")) {
        object_property_add_bool(obj, "built-in", NULL, NULL);
    }
    object_property_set_bool(obj, "built-in", true, NULL);
    virtio_instance_init_common(obj, &s->vdev, sizeof(s->vdev),
                                TYPE_APPLE_FAIRPLAY);
}

static void fp_pci_class_init(ObjectClass *klass, const void *data)
{
    VirtioPCIClass *k = VIRTIO_PCI_CLASS(klass);
    PCIDeviceClass *pc = PCI_DEVICE_CLASS(klass);
    k->realize = fp_pci_realize;
    pc->vendor_id = 0x106b;
    pc->device_id = 0x1a08;
    pc->class_id = PCI_CLASS_OTHERS;
}

static const TypeInfo fp_info = {
    .name = TYPE_APPLE_FAIRPLAY,
    .parent = TYPE_VIRTIO_DEVICE,
    .instance_size = sizeof(AppleFairPlay),
    .class_init = fp_class_init,
};

static const VirtioPCIDeviceTypeInfo fp_pci_info = {
    .generic_name = TYPE_APPLE_FAIRPLAY_PCI,
    .parent = TYPE_VIRTIO_PCI,
    .instance_size = sizeof(AppleFairPlayPCI),
    .instance_init = fp_pci_init,
    .class_init = fp_pci_class_init,
};

static void fp_register(void)
{
    type_register_static(&fp_info);
    virtio_pci_types_register(&fp_pci_info);
}
type_init(fp_register);
