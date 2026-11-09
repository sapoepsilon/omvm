#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Read or switch an iPhone/iPad's USB mode from the host, before passthrough.

An iPhone comes up in its charging mode. macOS reads the mode (vendor request
0xc0 0x45, 4 bytes, first byte 4 = charging, 6 = Mac mode) and switches it (0xc0
0x52, wIndex 4); the phone then drops off the bus and comes back in the new mode.
Passed through to a VM, the host never sees that drop and the phone answers every
later request with EPROTO. Done here on the host first, the phone re-enumerates
normally, comes up in Mac mode, and the guest finds nothing to switch.

    usb-apple-mode.py get BUS-PORT      print the mode bytes, e.g. "06 04 03 04"
    usb-apple-mode.py ensure BUS-PORT   switch to Mac mode unless already there
"""
import ctypes
import ctypes.util
import sys
import time

lib = ctypes.CDLL(ctypes.util.find_library("usb-1.0") or "libusb-1.0.so.0")
lib.libusb_get_device_list.restype = ctypes.c_ssize_t
lib.libusb_get_device_list.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p))]
lib.libusb_free_device_list.argtypes = [ctypes.POINTER(ctypes.c_void_p), ctypes.c_int]
lib.libusb_get_bus_number.argtypes = [ctypes.c_void_p]
lib.libusb_get_port_numbers.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_uint8), ctypes.c_int]
lib.libusb_open.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_void_p)]
lib.libusb_close.argtypes = [ctypes.c_void_p]
lib.libusb_control_transfer.argtypes = [ctypes.c_void_p, ctypes.c_uint8, ctypes.c_uint8, ctypes.c_uint16,
                                        ctypes.c_uint16, ctypes.c_char_p, ctypes.c_uint16, ctypes.c_uint]


def open_port(busport):
    bus, ports = busport.split("-", 1)
    want = (int(bus), tuple(int(p) for p in ports.split(".")))
    devs = ctypes.POINTER(ctypes.c_void_p)()
    n = lib.libusb_get_device_list(None, ctypes.byref(devs))
    try:
        for i in range(n):
            d = devs[i]
            buf = (ctypes.c_uint8 * 8)()
            k = lib.libusb_get_port_numbers(d, buf, 8)
            if (lib.libusb_get_bus_number(d), tuple(buf[:max(k, 0)])) == want:
                h = ctypes.c_void_p()
                rc = lib.libusb_open(d, ctypes.byref(h))
                if rc != 0:
                    sys.exit(f"usb-apple-mode: can't open {busport} (libusb {rc}; omvm usb attach installs the udev rule)")
                return h
    finally:
        lib.libusb_free_device_list(devs, 1)
    sys.exit(f"usb-apple-mode: no device at {busport}")


def get_mode(busport):
    h = open_port(busport)
    try:
        b = ctypes.create_string_buffer(4)
        rc = lib.libusb_control_transfer(h, 0xC0, 0x45, 0, 0, b, 4, 1000)
        return b.raw[:rc] if rc > 0 else None
    finally:
        lib.libusb_close(h)


def devnum(busport):
    try:
        return open(f"/sys/bus/usb/devices/{busport}/devnum").read().strip()
    except OSError:
        return None


def main():
    if len(sys.argv) != 3 or sys.argv[1] not in ("get", "ensure"):
        sys.exit(__doc__)
    verb, bp = sys.argv[1:]
    lib.libusb_init(None)
    mode = get_mode(bp)
    if mode is None:
        sys.exit(f"usb-apple-mode: {bp} did not answer the mode request (not an iPhone/iPad?)")
    if verb == "get" or mode[0] == 6:
        print(" ".join(f"{c:02x}" for c in mode))
        return
    before = devnum(bp)
    h = open_port(bp)
    b = ctypes.create_string_buffer(1)
    rc = lib.libusb_control_transfer(h, 0xC0, 0x52, 0, 4, b, 1, 1000)
    lib.libusb_close(h)
    if rc < 0:
        sys.exit(f"usb-apple-mode: mode switch failed (libusb {rc})")
    for _ in range(40):  # the phone drops off and comes back with a new device number
        time.sleep(0.25)
        now = devnum(bp)
        if now and now != before:
            break
    time.sleep(1)
    lib.libusb_exit(None)
    lib.libusb_init(None)
    mode = get_mode(bp)
    print(" ".join(f"{c:02x}" for c in mode) if mode else "?")
    if not mode or mode[0] != 6:
        sys.exit("usb-apple-mode: phone did not come back in Mac mode")


if __name__ == "__main__":
    main()
