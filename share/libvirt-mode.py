#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Show or switch the display mode of an omvm libvirt domain (omvm mode).

    libvirt-mode.py get   < domain.xml            prints local or remote
    libvirt-mode.py local RES REFRESH WAYLAND_DISPLAY XDG_RUNTIME_DIR ICD [STATS] < domain.xml > new.xml
    libvirt-mode.py remote < domain.xml > new.xml
    libvirt-mode.py sound < domain.xml > new.xml   (only the sound upgrade below)

remote: QEMU's VNC server (libvirt <graphics type='vnc'>, 127.0.0.1, autoport)
        with reims-vgpu headless (REIMS_VGPU_WINDOW=0); Sunshine/Moonlight and
        VNC viewers show it. This is what `omvm virt` defines.
local:  no <graphics> (libvirt passes -display none), and reims-vgpu opens its
        own SDL3/Vulkan window on the host's Wayland screen (REIMS_VGPU_WINDOW=1):
        zero-copy, at the screen's refresh rate (REIMS_VGPU_WINDOW_REFRESH, and
        REIMS_VGPU_MAX_REFRESH_HZ raised from remote's 60). RES is apple-gfx's resolution
        property (WxH@PPI, or host). ICD is a Vulkan driver with Wayland WSI
        (the remote one, built with -Dplatforms=, has none); the remote ICD is
        kept in OMVM_REMOTE_VK_DRIVER_FILES and put back by remote.

Both modes (and `sound`) also upgrade the sound card of a domain defined before
2026-11-08 (virtio-snd on a discarding 'none' backend, output only) to the
user's PipeWire with output and input, and keep XDG_RUNTIME_DIR in both modes
so QEMU finds PipeWire's socket.

Only what one mode adds is touched, so local -> remote gives back the domain
`omvm virt` made (libvirt normalises the rest).
"""
import os
import sys
import xml.etree.ElementTree as ET

QEMU_NS = "http://libvirt.org/schemas/domain/qemu/1.0"
ET.register_namespace("qemu", QEMU_NS)
OMVM_NS = "https://github.com/sapoepsilon/omvm"
ET.register_namespace("omvm", OMVM_NS)
Q = "{%s}" % QEMU_NS
# Environment that local mode adds (and remote mode removes).
LOCAL_ENV = ("REIMS_VGPU_WINDOW_REFRESH", "REIMS_VGPU_WINDOW_BORDERLESS",
             "WAYLAND_DISPLAY", "REIMS_VGPU_STATS", "REIMS_VGPU_TRACE",
             "REIMS_VGPU_TRACE_GATE", "REIMS_VGPU_TUNE")
RES_PREFIX = "apple-gfx-mmio.resolution="
SAVED_ICD = "OMVM_REMOTE_VK_DRIVER_FILES"
# reims-vgpu's cap on the display modes and VBL it offers the guest (qemu-fleet's
# reims; steelbrain's ignores it and offers the window's rate). `omvm virt`
# writes 60 for the headless remote mode; local mode runs at the panel's rate.
MAX_REFRESH = "REIMS_VGPU_MAX_REFRESH_HZ"
REMOTE_MAX_REFRESH = "60"


def get_env(c, name):
    for e in c.findall(Q + "env"):
        if e.get("name") == name:
            return e.get("value")
    return None


def mode_of(dom):
    return "remote" if dom.find("devices/graphics[@type='vnc']") is not None else "local"


def cmdline(dom):
    c = dom.find(Q + "commandline")
    if c is None:
        c = ET.SubElement(dom, Q + "commandline")
    return c


def set_env(c, name, value):
    for e in c.findall(Q + "env"):
        if e.get("name") == name:
            e.set("value", value)
            return
    ET.SubElement(c, Q + "env", name=name, value=value)


def drop_env(c, name):
    for e in c.findall(Q + "env"):
        if e.get("name") == name:
            c.remove(e)


def drop_resolution(c):
    """Remove a '-global apple-gfx-mmio.resolution=...' pair."""
    args = c.findall(Q + "arg")
    for i, a in enumerate(args):
        if a.get("value", "").startswith(RES_PREFIX) and i and args[i - 1].get("value") == "-global":
            c.remove(args[i - 1])
            c.remove(a)
            return


def add_arg_pair(c, flag, value):
    # args must precede env elements in libvirt's schema
    envs = c.findall(Q + "env")
    idx = list(c).index(envs[0]) if envs else len(c)
    for off, v in enumerate((flag, value)):
        el = ET.Element(Q + "arg", value=v)
        c.insert(idx + off, el)


def upgrade_sound(dom, c):
    """virtio-snd on PipeWire, output + input (see libvirt-domain.py)."""
    import os
    name = dom.findtext("name") or "macos"
    for a in c.findall(Q + "arg"):
        v = a.get("value", "")
        if v.startswith("none,id=snd0"):
            a.set("value", "pipewire,id=snd0,out.stream-name=%s,in.stream-name=%s" % (name, name))
        elif v.startswith("virtio-sound-pci,") and "streams=1" in v:
            a.set("value", v.replace("streams=1", "streams=2"))
    if get_env(c, "XDG_RUNTIME_DIR") is None:
        set_env(c, "XDG_RUNTIME_DIR", os.environ.get("XDG_RUNTIME_DIR", "/run/user/%d" % os.getuid()))


def main():
    what = sys.argv[1] if len(sys.argv) > 1 else "get"
    dom = ET.fromstring(sys.stdin.read())
    if what == "get":
        print(mode_of(dom))
        return
    devices = dom.find("devices")
    c = cmdline(dom)
    upgrade_sound(dom, c)
    if what == "sound":
        write(dom)
        return
    for g in devices.findall("graphics"):
        devices.remove(g)
    drop_resolution(c)
    for name in LOCAL_ENV:
        drop_env(c, name)
    saved = get_env(c, SAVED_ICD)
    if saved is not None:
        set_env(c, "VK_DRIVER_FILES", saved)
        drop_env(c, SAVED_ICD)
    if what == "local":
        res, refresh, wl, xdg, icd = sys.argv[2:7]
        if icd and icd != get_env(c, "VK_DRIVER_FILES"):
            set_env(c, SAVED_ICD, get_env(c, "VK_DRIVER_FILES") or "")
            set_env(c, "VK_DRIVER_FILES", icd)
        add_arg_pair(c, "-global", RES_PREFIX + res)
        set_env(c, "REIMS_VGPU_WINDOW", "1")
        set_env(c, "REIMS_VGPU_WINDOW_REFRESH", refresh)
        set_env(c, MAX_REFRESH, refresh)
        set_env(c, "REIMS_VGPU_WINDOW_BORDERLESS", "1")
        set_env(c, "WAYLAND_DISPLAY", wl)
        set_env(c, "XDG_RUNTIME_DIR", xdg)
        # Latency tooling (docs/graphics.md "Pointer latency"): reims-vgpu writes its
        # trace only while the gate file exists, and reads run-time settings (the
        # window's present mode) from the tune file.
        cache = os.path.expanduser("~/.cache/reims-vgpu")
        set_env(c, "REIMS_VGPU_TRACE", f"{cache}/trace.log")
        set_env(c, "REIMS_VGPU_TRACE_GATE", f"{cache}/trace.on")
        set_env(c, "REIMS_VGPU_TUNE", f"{cache}/tune")
        if len(sys.argv) > 7 and sys.argv[7] == "1":   # frame rates, once a second, in the libvirt log
            set_env(c, "REIMS_VGPU_STATS", "1")
    elif what == "remote":
        g = ET.Element("graphics", type="vnc", autoport="yes", listen="127.0.0.1")
        ET.SubElement(g, "listen", type="address", address="127.0.0.1")
        # keep libvirt's device order: graphics right after the emulator
        emu = devices.find("emulator")
        devices.insert(list(devices).index(emu) + 1 if emu is not None else 0, g)
        set_env(c, "REIMS_VGPU_WINDOW", "0")
        set_env(c, MAX_REFRESH, REMOTE_MAX_REFRESH)
    else:
        sys.exit("usage: libvirt-mode.py get | local RES REFRESH WAYLAND_DISPLAY XDG_RUNTIME_DIR ICD [STATS] | remote | sound")
    write(dom)


def write(dom):
    out = ET.tostring(dom, encoding="unicode")
    # ElementTree prefixes omvm's metadata (omvm:omvm); give it back its default
    # namespace, as `omvm virt` wrote it, so a round trip leaves the XML as it was
    out = (out.replace(' xmlns:omvm="%s"' % OMVM_NS, "")
              .replace("<omvm:omvm>", '<omvm xmlns="%s">' % OMVM_NS)
              .replace("<omvm:", "<").replace("</omvm:", "</"))
    sys.stdout.write(out + "\n")


if __name__ == "__main__":
    main()
