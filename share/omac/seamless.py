#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""omac seamless: every macOS app window of the app VM as its own Wayland window.

One RFB (VNC) connection to the guest's QEMU VNC server keeps the whole guest
framebuffer; one child (`omac windows --watch`) keeps the guest's window list.
Each guest app window gets a host toplevel (app id org.omvm.omac, title = app
name) that paints the live crop of the framebuffer at that window's bounds, with
the guest's menu bar strip on top, and sends pointer, scroll and keyboard input
back over the same VNC connection at the mapped guest coordinates.

    seamless.py --port 5901 --omac /path/to/omac [--vm macapps] [--hz 30]
                [--no-menubar] [--control SOCKET] [--selftest] [--stats N]
    seamless.py ctl SOCKET '{"op":"list"}'      talk to a running instance

Run it through `omac seamless`, which boots the VM and finds the VNC port.
"""
import argparse
import ctypes
import faulthandler
import json
import os
import signal
import socket
import struct
import subprocess
import sys
import threading
import time

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Gdk", "4.0")
gi.require_version("Gsk", "4.0")
gi.require_version("Graphene", "1.0")
from gi.repository import Gdk, GLib, Graphene, Gsk, Gtk  # noqa: E402

APP_ID = "org.omvm.omac"
MENUBAR_FALLBACK = 24  # points; the real height comes from `omac windows --all`
MENU_MARGIN = 75  # transparent shadow margin around menus (layer 101) on macOS 27
CORNER = 10  # guest window corner radius, points

T0 = time.monotonic()
faulthandler.register(signal.SIGUSR1, all_threads=True)  # kill -USR1: Python stacks to stderr


def die_with_parent():
    """preexec_fn: children get SIGTERM when this process dies, even by SIGKILL."""
    ctypes.CDLL(None, use_errno=True).prctl(1, signal.SIGTERM)  # PR_SET_PDEATHSIG


def log(*a):
    print(f"[seamless {time.monotonic() - T0:8.3f}]", *a, file=sys.stderr, flush=True)


# ------------------------------------------------------------------ RFB client
class RFB:
    """Minimal RFB 3.8 client: no auth, 32-bit BGRX, Raw/CopyRect/DesktopSize/Cursor.

    A reader thread keeps `fb` (a bytearray, stride w*4) current and calls
    `on_update(rects)` once per FramebufferUpdate from that thread. Writes
    (pointer, key, update requests) are serialised by a lock.
    """

    ENC_RAW, ENC_COPYRECT, ENC_DESKTOPSIZE, ENC_CURSOR = 0, 1, -223, -239

    def __init__(self, host, port, on_update, on_cursor, on_resize, on_close):
        self.sock = socket.create_connection((host, port), timeout=10)
        self.sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        self.wlock = threading.Lock()
        self.fblock = threading.Lock()
        self.on_update, self.on_cursor = on_update, on_cursor
        self.on_resize, self.on_close = on_resize, on_close
        self.closed = False
        self.frames = 0
        self.bytes = 0
        self._handshake()
        self.sock.settimeout(None)

    def _recv(self, n):
        buf = bytearray(n)
        mv = memoryview(buf)
        got = 0
        while got < n:
            k = self.sock.recv_into(mv[got:], n - got)
            if k == 0:
                raise EOFError("VNC server closed the connection")
            got += k
        self.bytes += n
        return buf

    def _send(self, data):
        with self.wlock:
            if not self.closed:
                self.sock.sendall(data)

    def _handshake(self):
        ver = bytes(self._recv(12))
        if not ver.startswith(b"RFB 003."):
            raise RuntimeError(f"not a VNC server: {ver!r}")
        self.sock.sendall(b"RFB 003.008\n")
        n = self._recv(1)[0]
        if n == 0:
            ln = struct.unpack(">I", self._recv(4))[0]
            raise RuntimeError("VNC refused: " + self._recv(ln).decode(errors="replace"))
        types = list(self._recv(n))
        if 1 not in types:
            raise RuntimeError(f"VNC wants authentication {types}; seamless mode needs none (127.0.0.1 only)")
        self.sock.sendall(b"\x01")
        if struct.unpack(">I", self._recv(4))[0] != 0:
            raise RuntimeError("VNC security handshake failed")
        self.sock.sendall(b"\x01")  # shared: other viewers stay connected
        w, h = struct.unpack(">HH", self._recv(4))
        self._recv(16)
        ln = struct.unpack(">I", self._recv(4))[0]
        self.name = self._recv(ln).decode(errors="replace")
        self.w, self.h = w, h
        self.fb = bytearray(w * h * 4)
        # 32 bpp, depth 24, little endian, true colour, red<<16 green<<8 blue: bytes B G R X
        pf = struct.pack(">BBBBHHHBBB3x", 32, 24, 0, 1, 255, 255, 255, 16, 8, 0)
        self.sock.sendall(b"\x00\x00\x00\x00" + pf)
        encs = [self.ENC_COPYRECT, self.ENC_RAW, self.ENC_DESKTOPSIZE, self.ENC_CURSOR]
        self.sock.sendall(struct.pack(">BxH", 2, len(encs)) + b"".join(struct.pack(">i", e) for e in encs))
        self.request(False)

    def start(self):
        threading.Thread(target=self._loop, name="rfb", daemon=True).start()

    def request(self, incremental=True):
        self._send(struct.pack(">BBHHHH", 3, 1 if incremental else 0, 0, 0, self.w, self.h))

    def pointer(self, x, y, mask):
        x = max(0, min(self.w - 1, int(round(x))))
        y = max(0, min(self.h - 1, int(round(y))))
        self._send(struct.pack(">BBHH", 5, mask & 0xFF, x, y))

    def key(self, keysym, down):
        self._send(struct.pack(">BBxxI", 4, 1 if down else 0, keysym))

    def close(self):
        self.closed = True
        try:
            self.sock.shutdown(socket.SHUT_RDWR)
        except OSError:
            pass
        self.sock.close()

    def _loop(self):
        try:
            while True:
                t = self._recv(1)[0]
                if t == 0:
                    self._update()
                elif t == 1:  # SetColourMapEntries (not used with true colour)
                    _, _, n = struct.unpack(">BHH", self._recv(5))
                    self._recv(6 * n)
                elif t == 2:  # Bell
                    pass
                elif t == 3:  # ServerCutText
                    self._recv(3)
                    self._recv(struct.unpack(">I", self._recv(4))[0])
                else:
                    raise RuntimeError(f"unknown VNC message {t}")
        except Exception as e:  # noqa: BLE001 - any end of the stream ends the session
            if not self.closed:
                log("vnc:", e)
                self.on_close(str(e))

    def _update(self):
        self._recv(1)
        n = struct.unpack(">H", self._recv(2))[0]
        rects = []
        for _ in range(n):
            x, y, w, h, enc = struct.unpack(">HHHHi", self._recv(12))
            if enc == self.ENC_RAW:
                data = self._recv(w * h * 4)
                S, row = self.w * 4, w * 4
                with self.fblock:
                    if x == 0 and w == self.w:
                        self.fb[y * S:(y + h) * S] = data
                    else:
                        fb = self.fb
                        for r in range(h):
                            o = (y + r) * S + x * 4
                            fb[o:o + row] = data[r * row:(r + 1) * row]
                rects.append((x, y, w, h))
            elif enc == self.ENC_COPYRECT:
                sx, sy = struct.unpack(">HH", self._recv(4))
                S, row = self.w * 4, w * 4
                with self.fblock:
                    src = [bytes(self.fb[(sy + r) * S + sx * 4:(sy + r) * S + sx * 4 + row]) for r in range(h)]
                    for r in range(h):
                        o = (y + r) * S + x * 4
                        self.fb[o:o + row] = src[r]
                rects.append((x, y, w, h))
            elif enc == self.ENC_DESKTOPSIZE:
                with self.fblock:
                    self.w, self.h = w, h
                    self.fb = bytearray(w * h * 4)
                self.on_resize(w, h)
                rects.append((0, 0, w, h))
            elif enc == self.ENC_CURSOR:
                pix = bytes(self._recv(w * h * 4))
                mask = bytes(self._recv(((w + 7) // 8) * h))
                self.on_cursor(x, y, w, h, pix, mask)
            else:
                raise RuntimeError(f"unexpected encoding {enc}")
        self.frames += 1
        self.on_update(rects)
        self.request(True)

    def crop(self, x, y, w, h):
        """BGRX bytes of the rectangle (clamped to the framebuffer; outside is black)."""
        out = bytearray(w * h * 4)
        x0, y0 = max(0, x), max(0, y)
        with self.fblock:
            x1, y1 = min(self.w, x + w), min(self.h, y + h)
            if x1 <= x0 or y1 <= y0:
                return out
            S, row = self.w * 4, (x1 - x0) * 4
            fb = self.fb
            for gy in range(y0, y1):
                o = gy * S + x0 * 4
                d = ((gy - y) * w + (x0 - x)) * 4
                out[d:d + row] = fb[o:o + row]
        return out


# ------------------------------------------------------------------ key mapping
# GDK keyvals are X keysyms, which QEMU's VNC server maps to guest key codes.
# Like omvm's VNC viewer (docs/omac.md): Super -> Command, Alt -> Option,
# Ctrl -> Control, all sent as they are (QEMU maps Super_L/Meta_L to the HID GUI key).
KEYSYM_REMAP = {
    0xFFE7: 0xFFEB,  # Meta_L  -> Super_L (Command)
    0xFFE8: 0xFFEC,  # Meta_R  -> Super_R
    0xFE03: 0xFFEA,  # ISO_Level3_Shift (AltGr) -> Alt_R (right Option)
}
SHIFT_L, SUPER_L = 0xFFE1, 0xFFEB


def keysym_for(keyval):
    return KEYSYM_REMAP.get(keyval, keyval)


def intersects(a, b):
    ax, ay, aw, ah = a
    bx, by, bw, bh = b
    return ax < bx + bw and bx < ax + aw and ay < by + bh and by < ay + ah


# ------------------------------------------------------------------ painting
class Crop(Gtk.Widget):
    """Paints guest rectangles (the window and, above it, the menu bar strip) scaled
    to fit with letterboxing, and maps host widget coordinates back to the guest."""

    __gtype_name__ = "OmacCrop"

    def __init__(self, app, owner):
        super().__init__()
        self.app = app
        self.owner = owner  # HostWindow or Overlay: provides parts() and round_corners
        self.tex = []  # [(texture, canvas rect)]
        self.dirty = True
        self.draws = 0
        self.set_focusable(True)
        self.set_hexpand(True)
        self.set_vexpand(True)

    # canvas = the parts laid out unscaled; geometry = scale + offset in the widget
    def geometry(self):
        cw, ch = self.owner.canvas_size()
        W, H = max(1, self.get_width()), max(1, self.get_height())
        s = min(W / cw, H / ch) if cw > 0 and ch > 0 else 1.0
        return s, (W - cw * s) / 2, (H - ch * s) / 2

    def to_guest(self, hx, hy):
        s, ox, oy = self.geometry()
        cx, cy = (hx - ox) / s, (hy - oy) / s
        for gx, gy, w, h, cx0, cy0 in self.owner.parts():
            if cx0 <= cx < cx0 + w and cy0 <= cy < cy0 + h:
                return gx + (cx - cx0), gy + (cy - cy0)
        # outside every part (letterbox): clamp into the main part
        gx, gy, w, h, cx0, cy0 = self.owner.parts()[-1]
        return gx + min(max(cx - cx0, 0), w - 1), gy + min(max(cy - cy0, 0), h - 1)

    def do_size_allocate(self, w, h, baseline):
        # a custom parent must place its popovers (the guest's menus) itself
        for o in getattr(self.owner, "overlays", {}).values():
            o.place()
            o.pop.present()

    def do_snapshot(self, snap):
        rfb = self.app.rfb
        if rfb is None:
            return
        if self.dirty or not self.tex:
            self.tex = []
            for gx, gy, w, h, cx0, cy0 in self.owner.parts():
                gx, gy, w, h = int(gx), int(gy), int(w), int(h)
                if w <= 0 or h <= 0:
                    continue
                data = rfb.crop(gx, gy, w, h)
                tex = Gdk.MemoryTexture.new(w, h, Gdk.MemoryFormat.B8G8R8X8, GLib.Bytes.new(data), w * 4)
                self.tex.append((tex, (cx0, cy0, w, h)))
            self.dirty = False
        s, ox, oy = self.geometry()
        filt = Gsk.ScalingFilter.NEAREST if abs(s - 1) < 1e-3 else Gsk.ScalingFilter.LINEAR
        for i, (tex, (cx, cy, w, h)) in enumerate(self.tex):
            r = Graphene.Rect().init(ox + cx * s, oy + cy * s, w * s, h * s)
            rounded = self.owner.corner_radius(i)
            if rounded:
                rr = Gsk.RoundedRect()
                rad = Graphene.Size().init(rounded * s, rounded * s)
                zero = Graphene.Size().init(0, 0)
                top = rad if self.owner.round_top(i) else zero
                rr.init(r, top, top, rad, rad)
                snap.push_rounded_clip(rr)
            snap.append_scaled_texture(tex, filt, r)
            if rounded:
                snap.pop()
        self.draws += 1
        if self.draws == 1:
            first = getattr(self.owner, "first_paint", None)
            if first:
                first()


class Input:
    """GTK input controllers on a Crop -> guest VNC events. The handlers only unpack
    the GTK event and call the input_* methods, which --selftest and the control
    socket call too."""

    BUTTONS = {1: 1, 2: 2, 3: 4}  # GDK button -> RFB mask bit (left, middle, right)

    def __init__(self, app, crop):
        self.app, self.crop = app, crop
        self.mask = 0
        self.keys = set()
        self.sx = self.sy = 0.0
        self.last = (0, 0)
        m = Gtk.EventControllerMotion()
        m.connect("motion", lambda c, x, y: self.input_motion(x, y))
        m.connect("enter", lambda c, x, y: self.input_motion(x, y))
        crop.add_controller(m)
        g = Gtk.GestureClick(button=0)
        g.connect("pressed", lambda g, n, x, y: self.input_button(g.get_current_button(), True, x, y))
        g.connect("released", lambda g, n, x, y: self.input_button(g.get_current_button(), False, x, y))
        crop.add_controller(g)
        sc = Gtk.EventControllerScroll(flags=Gtk.EventControllerScrollFlags.BOTH_AXES)
        sc.connect("scroll", lambda c, dx, dy: self.input_scroll(dx, dy, c.get_unit()) or True)
        crop.add_controller(sc)

    def guest(self, hx, hy):
        gx, gy = self.crop.to_guest(hx, hy)
        self.last = (gx, gy)
        return gx, gy

    def input_motion(self, hx, hy):
        gx, gy = self.guest(hx, hy)
        self.app.rfb.pointer(gx, gy, self.mask)

    def input_button(self, button, pressed, hx, hy):
        bit = self.BUTTONS.get(button)
        if bit is None:
            return
        if pressed:
            self.crop.grab_focus()
        self.mask = (self.mask | bit) if pressed else (self.mask & ~bit)
        gx, gy = self.guest(hx, hy)
        self.app.rfb.pointer(gx, gy, self.mask)
        self.app.stat_input(pressed)

    def input_scroll(self, dx, dy, unit=Gdk.ScrollUnit.WHEEL):
        step = 1.0 if unit == Gdk.ScrollUnit.WHEEL else 20.0  # touchpad: ~20 px per click
        self.sx += dx / step
        self.sy += dy / step
        gx, gy = self.last
        for acc, neg, pos in (("sy", 8, 16), ("sx", 32, 64)):  # wheel up/down, left/right
            v = getattr(self, acc)
            while abs(v) >= 1:
                bit = pos if v > 0 else neg
                self.app.rfb.pointer(gx, gy, self.mask | bit)
                self.app.rfb.pointer(gx, gy, self.mask)
                v -= 1 if v > 0 else -1
            setattr(self, acc, v)

    def input_key(self, keyval, pressed):
        ks = keysym_for(keyval)
        if pressed:
            self.keys.add(ks)
        elif ks not in self.keys:
            return  # a release without our press (focus came in with the key down)
        else:
            self.keys.discard(ks)
        self.app.rfb.key(ks, pressed)
        self.app.stat_input(pressed)

    def release_all(self):
        for ks in list(self.keys):
            self.app.rfb.key(ks, False)
        self.keys.clear()
        if self.mask:
            self.mask = 0
            self.app.rfb.pointer(*self.last, 0)


def attach_keys(widget, inp):
    k = Gtk.EventControllerKey()
    k.set_propagation_phase(Gtk.PropagationPhase.CAPTURE)
    k.connect("key-pressed", lambda c, kv, code, st: inp.input_key(kv, True) or True)
    k.connect("key-released", lambda c, kv, code, st: inp.input_key(kv, False))
    widget.add_controller(k)


# ------------------------------------------------------------------ windows
class Overlay:
    """A guest menu/popover/sheet/prompt shown as a popover of its app's host window."""

    def __init__(self, app, host, info):
        self.app, self.host, self.info = app, host, info
        self.crop = Crop(app, self)
        self.input = Input(app, self.crop)
        self.pop = Gtk.Popover()
        self.pop.add_css_class("omac-overlay")
        self.pop.set_has_arrow(False)
        self.pop.set_autohide(False)
        self.pop.set_position(Gtk.PositionType.BOTTOM)
        self.pop.set_halign(Gtk.Align.START)
        self.pop.set_child(self.crop)
        self.pop.set_parent(host.crop)
        self.update(info)
        self.pop.popup()

    def rect(self):
        b = self.info["bounds"]
        x, y, w, h = b["x"], b["y"], b["w"], b["h"]
        if self.info.get("layer") == 101 and self.app.trim_menus and w > 2 * MENU_MARGIN and h > 2 * MENU_MARGIN:
            x, y, w, h = x + MENU_MARGIN, y + MENU_MARGIN, w - 2 * MENU_MARGIN, h - 2 * MENU_MARGIN
        return int(x), int(y), int(w), int(h)

    def canvas_size(self):
        _, _, w, h = self.rect()
        return w, h

    def parts(self):
        x, y, w, h = self.rect()
        return [(x, y, w, h, 0, 0)]

    def corner_radius(self, i):
        return CORNER if self.info.get("layer") == 101 and self.app.trim_menus else 0

    def round_top(self, i):
        return True

    def update(self, info):
        self.info = info
        self.place()
        self.crop.dirty = True
        self.crop.queue_draw()

    def place(self):
        x, y, w, h = self.rect()
        s = self.host.crop.geometry()[0]
        self.crop.set_size_request(max(1, int(w * s)), max(1, int(h * s)))
        hx, hy = self.host.guest_to_host(x, y)
        # anchor inside the parent, the rest as offset (xdg anchor rects must stay inside)
        W, H = max(1, self.host.crop.get_width()), max(1, self.host.crop.get_height())
        ax, ay = int(min(max(hx, 0), W - 1)), int(min(max(hy - 1, 0), H - 1))
        r = Gdk.Rectangle()
        r.x, r.y, r.width, r.height = ax, ay, 1, 1
        self.pop.set_pointing_to(r)
        self.pop.set_offset(int(hx) - ax, int(hy) - (ay + 1))

    def region(self):
        return self.rect()

    def destroy(self):
        self.input.release_all()
        self.pop.popdown()
        self.pop.unparent()


class HostWindow:
    def __init__(self, app, info):
        self.app, self.info = app, info
        self.id = info["id"]
        self.closing = False  # we close it (guest window gone): no Cmd+W
        # Popovers (xdg_popup) only once the compositor has mapped us: GDK waits for
        # a popup's first configure, which never comes for an unmapped parent.
        self.ready = False
        self.pending_overlays = None
        self.close_sent = 0.0
        self.overlays = {}
        self.win = Gtk.Window(title=info.get("owner") or "macOS")
        self.win.set_decorated(False)
        self.win.add_css_class("omac-window")
        self.crop = Crop(app, self)
        self.input = Input(app, self.crop)
        attach_keys(self.win, self.input)
        self.win.set_child(self.crop)
        cw, ch = self.canvas_size()
        self.win.set_default_size(cw, ch)
        self.win.connect("close-request", self.on_close_request)
        self.win.connect("notify::is-active", self.on_active)
        self.crop.connect("map", lambda *_: app.window_mapped(self))
        if app.cursor:
            self.crop.set_cursor(app.cursor)
        self.win.present()

    def menubar_h(self):
        return self.app.menubar_h if self.app.menubar else 0

    def bounds(self):
        b = self.info["bounds"]
        return int(b["x"]), int(b["y"]), int(b["w"]), int(b["h"])

    def canvas_size(self):
        _, _, w, h = self.bounds()
        return w, h + self.menubar_h()

    def parts(self):
        """(guest x, y, w, h, canvas x, y): the menu bar strip, then the window."""
        x, y, w, h = self.bounds()
        mb = self.menubar_h()
        p = []
        if mb:
            p.append((0, 0, min(w, self.app.rfb.w), mb, 0, 0))
        p.append((x, y, w, h, 0, mb))
        return p

    def corner_radius(self, i):
        return CORNER if i == len(self.parts()) - 1 and self.app.round_corners else 0

    def round_top(self, i):
        return True

    def guest_to_host(self, gx, gy):
        """Guest point -> host widget point; menu-bar menus follow the strip."""
        s, ox, oy = self.crop.geometry()
        x, y, w, h = self.bounds()
        mb = self.menubar_h()
        if mb and gy <= mb + 2:
            return ox + gx * s, oy + gy * s
        return ox + (gx - x) * s, oy + (gy - y + mb) * s

    def regions(self):
        r = [self.bounds()]
        if self.menubar_h():
            r.append((0, 0, self.app.rfb.w, self.menubar_h()))
        return r

    def update(self, info):
        old = self.info
        self.info = info
        if old["bounds"] != info["bounds"]:
            self.relayout()
            self.crop.dirty = True
            self.crop.queue_draw()

    def relayout(self):
        for o in self.overlays.values():
            o.place()

    def first_paint(self):
        def ready():
            if not self.closing:
                self.ready = True
                if self.pending_overlays is not None:
                    self.set_overlays(self.pending_overlays)
            return False
        GLib.timeout_add(200, ready)

    def set_overlays(self, infos):
        if not self.ready:
            self.pending_overlays = infos
            return
        seen = set()
        for info in infos:
            seen.add(info["id"])
            o = self.overlays.get(info["id"])
            if o is None:
                self.overlays[info["id"]] = Overlay(self.app, self, info)
                log(f"overlay {info['id']} ({info.get('owner')}, layer {info.get('layer')}) on window {self.id}")
            elif o.info["bounds"] != info["bounds"]:
                o.update(info)
        for oid in [k for k in self.overlays if k not in seen]:
            self.overlays.pop(oid).destroy()

    def damage(self, rects):
        if any(intersects(r, reg) for r in rects for reg in self.regions()):
            self.crop.dirty = True
            self.crop.queue_draw()
        for o in self.overlays.values():
            if any(intersects(r, o.region()) for r in rects):
                o.crop.dirty = True
                o.crop.queue_draw()

    def on_active(self, *_):
        if self.win.is_active():
            self.app.focus_guest(self)
        else:
            self.input.release_all()

    def on_close_request(self, *_):
        if not self.closing:
            self.app.close_guest(self)
        return False

    def destroy(self):
        self.closing = True
        for o in self.overlays.values():
            o.destroy()
        self.overlays.clear()
        self.input.release_all()
        self.win.destroy()


# ------------------------------------------------------------------ the app
class Seamless:
    def __init__(self, a):
        self.a = a
        self.menubar = not a.no_menubar
        self.menubar_h = MENUBAR_FALLBACK
        self.trim_menus = not a.no_trim
        self.round_corners = not a.no_round
        self.loop = GLib.MainLoop()
        self.rfb = None
        self.cursor = None
        self.windows = {}  # guest window id -> HostWindow
        self.closed_by_user = {}  # guest window id -> time the user closed it on the host
        self.snapshot = None
        self.watch = None
        self.shell = None
        self.exit_code = 0
        self.quitting = False
        self.n_input = 0
        self.t_last_frames = (time.monotonic(), 0)
        self.map_times = {}
        self.pending_damage = []
        self.damage_scheduled = False
        self.ctl_clients = []
        self.probe = None  # (time, window id): key sent, waiting for its pixels
        self.probes = []

    # ---- startup
    def run(self):
        GLib.set_prgname(APP_ID)
        GLib.set_application_name("macOS (omac)")
        Gtk.init()
        css = Gtk.CssProvider()
        css.load_from_string(
            "window.omac-window { background: transparent; }"
            " popover.omac-overlay, popover.omac-overlay > contents"
            " { padding: 0; margin: 0; border: none; border-radius: 0; box-shadow: none;"
            "   background: transparent; outline: none; }"
        )
        Gtk.StyleContext.add_provider_for_display(Gdk.Display.get_default(), css, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
        for sig in (signal.SIGTERM, signal.SIGINT, signal.SIGHUP):
            add_signal(sig, self.quit, f"signal {sig}")
        if self.menubar:
            self.menubar_h = self.probe_menubar()
        self.rfb = RFB(self.a.host, self.a.port, self.vnc_update, self.vnc_cursor, self.vnc_resize, self.vnc_closed)
        log(f"vnc {self.a.host}:{self.a.port} '{self.rfb.name}' {self.rfb.w}x{self.rfb.h}; menu bar {self.menubar_h if self.menubar else 0} pt")
        self.rfb.start()
        self.start_watch()
        self.start_shell()
        if self.a.control:
            self.start_control(self.a.control)
        if self.a.stats:
            GLib.timeout_add_seconds(self.a.stats, self.print_stats)
        if self.a.selftest:
            threading.Thread(target=self.selftest, daemon=True).start()
        self.loop.run()
        self.cleanup()
        return self.exit_code

    def omac(self, *args):
        return [self.a.omac, *args]

    def env(self):
        e = dict(os.environ)
        e["OMAC_VM"] = self.a.vm
        return e

    def probe_menubar(self):
        try:
            out = subprocess.run(self.omac("windows", "--all"), capture_output=True, text=True, timeout=30,
                                 env=self.env(), stdin=subprocess.DEVNULL).stdout
            for w in json.loads(out)["windows"]:
                if w.get("owner") == "Window Server" and w.get("title") == "Menubar":
                    return int(w["bounds"]["h"])
        except Exception as e:  # noqa: BLE001
            log("menu bar height unknown, using", MENUBAR_FALLBACK, e)
        return MENUBAR_FALLBACK

    def start_watch(self):
        cmd = self.omac("windows", "--watch", "--hz", str(self.a.hz))
        self.watch = subprocess.Popen(cmd, stdout=subprocess.PIPE, stdin=subprocess.DEVNULL, env=self.env(),
                                      preexec_fn=die_with_parent)
        ch = GLib.IOChannel.unix_new(self.watch.stdout.fileno())
        ch.set_encoding(None)
        ch.set_buffered(True)
        GLib.io_add_watch(ch, GLib.PRIORITY_DEFAULT, GLib.IOCondition.IN | GLib.IOCondition.HUP, self.watch_line)

    def start_shell(self):
        # one long-lived guest shell for `open -b` (focus sync): no SSH handshake per focus change
        self.shell = subprocess.Popen(self.omac("shell", "/bin/sh"), stdin=subprocess.PIPE, stdout=subprocess.DEVNULL,
                                      stderr=subprocess.DEVNULL, env=self.env(), text=True,
                                      preexec_fn=die_with_parent)

    # ---- guest window list
    def watch_line(self, ch, cond):
        try:
            status, line, _, _ = ch.read_line()
        except GLib.Error as e:
            log("watch:", e)
            status, line = GLib.IOStatus.EOF, None
        if status == GLib.IOStatus.EOF or not line:
            if cond & GLib.IOCondition.HUP or status == GLib.IOStatus.EOF:
                self.quit("the window watcher ended (VM stopped?)")
                return False
            return True
        try:
            snap = json.loads(line)
        except ValueError:
            return True
        self.apply(snap)
        return True

    @staticmethod
    def split_sheets(wins):
        """Sheets and dialogs drawn as separate layer-0 windows: a window in front of a
        bigger window of the same app and inside it becomes that window's overlay."""
        top, sheets = [], []
        for i, w in enumerate(wins):
            b = w["bounds"]
            parent = None
            for p in wins[i + 1:]:
                pb = p["bounds"]
                if (p["pid"] == w["pid"] and p is not w and pb["w"] * pb["h"] > b["w"] * b["h"]
                        and b["x"] >= pb["x"] - 2 and b["y"] >= pb["y"] - 2
                        and b["x"] + b["w"] <= pb["x"] + pb["w"] + 2 and b["y"] + b["h"] <= pb["y"] + pb["h"] + 2):
                    parent = p
                    break
            if parent is None:
                top.append(w)
            else:
                sheets.append(dict(w, parent=parent["id"]))
        # a sheet of a sheet belongs to the outermost window
        ids = {w["id"] for w in top}
        by_id = {w["id"]: w for w in sheets}
        for sh in sheets:
            while sh["parent"] not in ids and sh["parent"] in by_id:
                sh["parent"] = by_id[sh["parent"]]["parent"]
        return top, sheets

    def apply(self, snap):
        self.snapshot = snap
        now = time.monotonic()
        wins, sheets = self.split_sheets(snap.get("windows", []))
        ids = {w["id"] for w in wins}
        for wid in [k for k in self.windows if k not in ids]:
            log(f"window {wid} gone in the guest: closing its host window (host now={int(time.time() * 1000)})")
            self.windows.pop(wid).destroy()
            self.closed_by_user.pop(wid, None)
        for w in wins:
            hw = self.windows.get(w["id"])
            if hw:
                hw.update(w)
            elif w["id"] in self.closed_by_user and now - self.closed_by_user[w["id"]] < 3:
                continue  # Cmd+W sent; give the app a moment (a save sheet keeps it open)
            else:
                if w["id"] in self.closed_by_user:
                    log(f"window {w['id']} still open in the guest after close: showing it again")
                    self.closed_by_user.pop(w["id"])
                self.map_times[w["id"]] = (now, snap.get("t"))
                log(f"window {w['id']} {w.get('owner')} ({w.get('bundle')}) {w['bounds']}: new host window")
                self.windows[w["id"]] = HostWindow(self, w)
        # overlays go to the frontmost host window of the same pid; prompts to the frontmost window
        by_pid = {}
        for w in wins:
            if w["id"] in self.windows:
                by_pid.setdefault(w["pid"], self.windows[w["id"]])
        front = self.windows.get(wins[0]["id"]) if wins else None
        per = {hw.id: [] for hw in self.windows.values()}
        for sh in sheets:
            if sh["parent"] in per:
                per[sh["parent"]].append(sh)
        for o in snap.get("overlays") or []:
            hw = by_pid.get(o["pid"]) or front
            if hw:
                per[hw.id].append(o)
        for wid, infos in per.items():
            self.windows[wid].set_overlays(infos)

    def window_mapped(self, hw):
        t = self.map_times.pop(hw.id, None)
        if t:
            log(f"window {hw.id} mapped {1000 * (time.monotonic() - t[0]):.0f} ms after its watch line"
                f" (guest t={t[1]}, host now={int(time.time() * 1000)})")

    # ---- VNC callbacks (reader thread -> main loop)
    def vnc_update(self, rects):
        with self.rfb.fblock:
            self.pending_damage.extend(rects)
            if self.damage_scheduled:
                return
            self.damage_scheduled = True
        GLib.idle_add(self.flush_damage, priority=GLib.PRIORITY_HIGH_IDLE)

    def flush_damage(self):
        with self.rfb.fblock:
            rects, self.pending_damage = self.pending_damage, []
            self.damage_scheduled = False
        for hw in list(self.windows.values()):
            hw.damage(rects)
        if self.probe:
            t, wid = self.probe
            hw = self.windows.get(wid)
            if hw and any(intersects(r, hw.bounds()) for r in rects):
                self.probes.append(round(1000 * (time.monotonic() - t), 1))
                self.probe = None
        return False

    def vnc_cursor(self, hx, hy, w, h, pix, mask):
        GLib.idle_add(self.set_cursor, hx, hy, w, h, pix, mask)

    def set_cursor(self, hx, hy, w, h, pix, mask):
        if w == 0 or h == 0:
            return False
        out = bytearray(w * h * 4)
        mrow = (w + 7) // 8
        for y in range(h):
            for x in range(w):
                if mask[y * mrow + x // 8] & (0x80 >> (x % 8)):
                    o = (y * w + x) * 4
                    out[o:o + 3] = pix[o:o + 3]
                    out[o + 3] = 255
        tex = Gdk.MemoryTexture.new(w, h, Gdk.MemoryFormat.B8G8R8A8_PREMULTIPLIED, GLib.Bytes.new(out), w * 4)
        self.cursor = Gdk.Cursor.new_from_texture(tex, min(hx, w - 1), min(hy, h - 1), None)
        for hw in self.windows.values():
            hw.crop.set_cursor(self.cursor)
            for o in hw.overlays.values():
                o.crop.set_cursor(self.cursor)
        return False

    def vnc_resize(self, w, h):
        log(f"guest display is now {w}x{h}")

    def vnc_closed(self, why):
        GLib.idle_add(self.quit, f"vnc closed: {why}")

    # ---- focus and close (no guest permissions needed)
    def guest_cmd(self, cmd):
        if self.shell and self.shell.poll() is None:
            try:
                self.shell.stdin.write(cmd + "\n")
                self.shell.stdin.flush()
                return
            except (BrokenPipeError, OSError):
                pass
        log("guest shell gone; restarting it")
        self.start_shell()
        self.shell.stdin.write(cmd + "\n")
        self.shell.stdin.flush()

    def focus_guest(self, hw):
        wins = (self.snapshot or {}).get("windows", [])
        if not wins or wins[0]["id"] == hw.id or wins[0]["id"] in hw.overlays:
            return
        if wins[0]["pid"] != hw.info["pid"] and hw.info.get("bundle"):
            # another app is in front: activate this one (LaunchServices, no Automation grant)
            self.guest_cmd("open -b " + sh_quote(hw.info["bundle"]))
        else:
            self.click_titlebar(hw)

    def click_titlebar(self, hw):
        x, y, w, h = hw.bounds()
        gx, gy = x + w // 2, y + 4  # top edge of the title bar: draggable, no controls
        self.rfb.pointer(gx, gy, 0)
        self.rfb.pointer(gx, gy, 1)
        self.rfb.pointer(gx, gy, 0)

    def close_guest(self, hw):
        """The user closed the host window: click the guest window's title bar (brings it
        to front), then Cmd+W. Works for any app that closes windows with Cmd+W."""
        log(f"host window {hw.id} ({hw.info.get('owner')}) closed by the user: Cmd+W in the guest")
        self.closed_by_user[hw.id] = time.monotonic()
        self.windows.pop(hw.id, None)
        hw.closing = True
        hw.input.release_all()
        self.click_titlebar(hw)

        def cmd_w():
            self.rfb.key(SUPER_L, True)
            self.rfb.key(ord("w"), True)
            self.rfb.key(ord("w"), False)
            self.rfb.key(SUPER_L, False)
            return False
        GLib.timeout_add(150, cmd_w)

        def recheck():  # still there (a save sheet, an app without Cmd+W): show it again
            if self.snapshot and not self.quitting:
                self.apply(self.snapshot)
            return False
        GLib.timeout_add(3100, recheck)
        for o in hw.overlays.values():
            o.destroy()
        hw.overlays.clear()

    # ---- stats, control, selftest
    def stat_input(self, pressed):
        self.n_input += 1

    def cpu_seconds(self):
        with open(f"/proc/{os.getpid()}/stat") as f:
            fields = f.read().rsplit(")", 1)[1].split()
        return (int(fields[11]) + int(fields[12])) / os.sysconf("SC_CLK_TCK")

    def stats(self):
        now = time.monotonic()
        t0, f0 = self.t_last_frames
        frames = self.rfb.frames if self.rfb else 0
        cpu = self.cpu_seconds()
        prev_cpu = getattr(self, "_prev_cpu", (t0, cpu))
        dt = max(1e-3, now - t0)
        out = {
            "vnc_fps": round((frames - f0) / dt, 1),
            "cpu_pct": round(100 * (cpu - prev_cpu[1]) / max(1e-3, now - prev_cpu[0]), 1),
            "vnc_mb": round(self.rfb.bytes / 1e6, 1) if self.rfb else 0,
            "windows": {},
        }
        for hw in self.windows.values():
            d0 = getattr(hw, "_d0", 0)
            out["windows"][hw.id] = {"owner": hw.info.get("owner"), "paint_fps": round((hw.crop.draws - d0) / dt, 1),
                                     "host": [hw.crop.get_width(), hw.crop.get_height()],
                                     "overlays": list(hw.overlays)}
            hw._d0 = hw.crop.draws
        self.t_last_frames = (now, frames)
        self._prev_cpu = (now, cpu)
        return out

    def print_stats(self):
        log("stats", json.dumps(self.stats()))
        return True

    def find(self, req):
        wins = list(self.windows.values())
        if "id" in req:
            return self.windows.get(req["id"])
        if "owner" in req:
            wins = [w for w in wins if w.info.get("owner") == req["owner"]]
        return wins[0] if wins else None

    def control(self, req):
        op = req.get("op")
        if op == "list":
            return {"windows": [{"id": hw.id, "owner": hw.info.get("owner"), "bundle": hw.info.get("bundle"),
                                 "bounds": hw.info["bounds"], "host": [hw.crop.get_width(), hw.crop.get_height()],
                                 "geometry": hw.crop.geometry(), "overlays": [o.info for o in hw.overlays.values()]}
                                for hw in self.windows.values()], "menubar_h": self.menubar_h if self.menubar else 0}
        if op == "stats":
            return self.stats()
        if op == "drag":  # guest coordinates, raw: {"from": [x, y], "to": [x, y]} (test setup)
            (x0, y0), (x1, y1) = req["from"], req["to"]
            self.rfb.pointer(x0, y0, 0)
            self.rfb.pointer(x0, y0, 1)
            for i in range(1, 21):
                self.rfb.pointer(x0 + (x1 - x0) * i / 20, y0 + (y1 - y0) * i / 20, 1)
                time.sleep(0.02)
            self.rfb.pointer(x1, y1, 0)
            return {"ok": True}
        if op == "quit":
            GLib.idle_add(self.quit, "control: quit")
            return {"ok": True}
        hw = self.find(req)
        if hw is None:
            return {"error": "no such window"}
        if op == "click":  # host widget coordinates, through the GTK handlers' methods
            x, y = req["x"], req["y"]
            hw.input.input_motion(x, y)
            hw.input.input_button(req.get("button", 1), True, x, y)
            hw.input.input_button(req.get("button", 1), False, x, y)
            return {"ok": True, "guest": hw.input.last}
        if op == "scroll":
            hw.input.input_motion(req["x"], req["y"])
            hw.input.input_scroll(req.get("dx", 0), req.get("dy", 0))
            return {"ok": True, "guest": hw.input.last}
        if op == "type":
            for ch in req["text"]:
                kv = Gdk.unicode_to_keyval(ord(ch)) if ch != "\n" else 0xFF0D
                shift = ch.isupper() or ch in '~!@#$%^&*()_+{}|:"<>?'
                if shift:
                    hw.input.input_key(SHIFT_L, True)
                hw.input.input_key(kv, True)
                hw.input.input_key(kv, False)
                if shift:
                    hw.input.input_key(SHIFT_L, False)
            return {"ok": True}
        if op == "key":  # {"keyval": 0x77, "mods": [0xffeb]}
            for m in req.get("mods", []):
                hw.input.input_key(m, True)
            hw.input.input_key(req["keyval"], True)
            hw.input.input_key(req["keyval"], False)
            for m in reversed(req.get("mods", [])):
                hw.input.input_key(m, False)
            return {"ok": True}
        if op == "probe":  # key in, time until VNC sends pixels of that window (input-to-photon over VNC)
            self.probe = (time.monotonic(), hw.id)
            hw.input.input_key(req.get("keyval", 0x78), True)
            hw.input.input_key(req.get("keyval", 0x78), False)
            return {"ok": True}
        if op == "probes":
            return {"ms": self.probes}
        if op == "focus":
            self.focus_guest(hw)
            return {"ok": True}
        if op == "close":  # as if the user closed the host window
            hw.win.close()
            return {"ok": True}
        return {"error": f"unknown op {op}"}

    def start_control(self, path):
        try:
            os.unlink(path)
        except FileNotFoundError:
            pass
        srv = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        srv.bind(path)
        os.chmod(path, 0o600)
        srv.listen(4)
        self.ctl_srv, self.ctl_path = srv, path

        def accept(*_):
            c, _ = srv.accept()
            data = b""
            c.settimeout(2)
            try:
                while not data.endswith(b"\n"):
                    k = c.recv(65536)
                    if not k:
                        break
                    data += k
                res = self.control(json.loads(data))
            except Exception as e:  # noqa: BLE001
                res = {"error": str(e)}
            try:
                c.sendall((json.dumps(res) + "\n").encode())
            except OSError:
                pass
            c.close()
            return True
        GLib.io_add_watch(srv.fileno(), GLib.PRIORITY_DEFAULT, GLib.IOCondition.IN, accept)

    def call_main(self, req):
        """Run a control request on the main loop from another thread and wait for it."""
        ev, box = threading.Event(), {}

        def do():
            box["r"] = self.control(req)
            ev.set()
            return False
        GLib.idle_add(do)
        ev.wait(10)
        return box.get("r")

    def selftest(self):
        """Click into the first TextEdit window's document and type a line, through the
        same input methods the GTK handlers call. Prints one JSON result line on stdout."""
        deadline = time.monotonic() + 60
        hw = None
        while time.monotonic() < deadline and not self.quitting:
            r = self.call_main({"op": "list"})
            te = [w for w in (r or {}).get("windows", []) if w["owner"] == "TextEdit" and w["host"][0] > 0]
            if te:
                hw = te[0]
                break
            time.sleep(0.5)
        if not hw:
            print(json.dumps({"selftest": "fail", "why": "no TextEdit window on the host"}), flush=True)
            return
        time.sleep(1.0)
        W, H = hw["host"]
        text = self.a.selftest_text
        click = self.call_main({"op": "click", "id": hw["id"], "x": W / 2, "y": H * 0.6})
        time.sleep(0.4)
        typed = self.call_main({"op": "type", "id": hw["id"], "text": text})
        print(json.dumps({"selftest": "sent", "window": hw["id"], "host_click": [W / 2, H * 0.6],
                          "guest_click": click.get("guest"), "typed": text, "ok": typed}), flush=True)

    # ---- exit
    def quit(self, why="quit"):
        if not self.quitting:
            self.quitting = True
            log("exiting:", why)
            if why.startswith("vnc closed") or why.startswith("the window watcher"):
                self.exit_code = 3
            self.loop.quit()
        return False

    def cleanup(self):
        for hw in list(self.windows.values()):
            hw.destroy()
        self.windows.clear()
        if self.rfb:
            self.rfb.close()
        for p in (self.watch, self.shell):
            if p and p.poll() is None:
                p.terminate()
        for p in (self.watch, self.shell):
            if p:
                try:
                    p.wait(5)
                except subprocess.TimeoutExpired:
                    p.kill()
                    p.wait()
        if getattr(self, "ctl_path", None):
            try:
                os.unlink(self.ctl_path)
            except FileNotFoundError:
                pass
        log("clean exit")


def add_signal(sig, fn, arg):
    try:
        gi.require_version("GLibUnix", "2.0")
        from gi.repository import GLibUnix
        GLibUnix.signal_add(GLib.PRIORITY_HIGH, sig, fn, arg)
    except (ImportError, ValueError, AttributeError):
        GLib.unix_signal_add(GLib.PRIORITY_HIGH, sig, fn, arg)


def sh_quote(s):
    return "'" + s.replace("'", "'\\''") + "'"


def ctl(path, req):
    c = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    c.connect(path)
    c.sendall((req.strip() + "\n").encode())
    data = b""
    while True:
        k = c.recv(65536)
        if not k:
            break
        data += k
    sys.stdout.write(data.decode())
    return 0


def main():
    if len(sys.argv) >= 2 and sys.argv[1] == "ctl":
        if len(sys.argv) != 4:
            sys.exit("usage: seamless.py ctl SOCKET JSON")
        return ctl(sys.argv[2], sys.argv[3])
    p = argparse.ArgumentParser(description="omac seamless mode")
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, required=True, help="the guest's QEMU VNC port")
    p.add_argument("--omac", required=True, help="path of bin/omac (window watcher, guest shell)")
    p.add_argument("--vm", default=os.environ.get("OMAC_VM", "macapps"))
    p.add_argument("--hz", type=float, default=30)
    p.add_argument("--no-menubar", action="store_true", help="no guest menu bar strip on top of each window")
    p.add_argument("--no-trim", action="store_true", help="show menus with their transparent shadow margin")
    p.add_argument("--no-round", action="store_true", help="no rounded-corner mask")
    p.add_argument("--control", help="unix socket for control requests (seamless.py ctl SOCKET JSON)")
    p.add_argument("--stats", type=int, default=0, help="log fps/CPU every N seconds")
    p.add_argument("--selftest", action="store_true", help="click into TextEdit and type --selftest-text")
    p.add_argument("--selftest-text", default="omac seamless ok")
    a = p.parse_args()
    return Seamless(a).run()


if __name__ == "__main__":
    sys.exit(main())
