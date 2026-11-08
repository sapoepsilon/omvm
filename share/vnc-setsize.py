#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Ask a VNC server to resize its desktop (RFB SetDesktopSize, message 251),
as TigerVNC's vncviewer does when its window is resized:
    vnc-setsize.py PORT WIDTH HEIGHT [SECONDS]   (WIDTH 0: only print the size)
Prints the server's ExtendedDesktopSize replies seen within a few seconds."""
import socket, struct, sys, time

port, w, h = int(sys.argv[1]), int(sys.argv[2]), int(sys.argv[3])
s = socket.create_connection(("127.0.0.1", port))


def recv(n):
    b = b""
    while len(b) < n:
        c = s.recv(n - len(b))
        if not c:
            raise EOFError
        b += c
    return b


recv(12)
s.sendall(b"RFB 003.008\n")
n = recv(1)[0]
types = recv(n)
if 1 not in types:
    sys.exit(f"no 'None' security type: {list(types)}")
s.sendall(b"\x01")
if struct.unpack(">I", recv(4))[0] != 0:
    sys.exit("security failed")
s.sendall(b"\x01")  # shared
try:
    fw, fh = struct.unpack(">HH", recv(4))
except EOFError:
    sys.exit("the VM refused a second VNC connection: a viewer is connected in exclusive mode. "
             "Resize that viewer's window instead, or start it with -Shared=1")
recv(16)
recv(struct.unpack(">I", recv(4))[0])
print(f"server desktop {fw}x{fh}")
encs = [0, -223, -308]  # raw, DesktopSize, ExtendedDesktopSize
s.sendall(struct.pack(">BxH", 2, len(encs)) + b"".join(struct.pack(">i", e) for e in encs))
if w == 0:  # only report the current size
    sys.exit(0)
s.sendall(struct.pack(">BxHHBx", 251, w, h, 1) + struct.pack(">IHHHHI", 0, 0, 0, w, h, 0))
# Read the replies: framebuffer updates carrying ExtendedDesktopSize rects.
s.settimeout(1.0)
deadline = time.time() + float(sys.argv[4]) if len(sys.argv) > 4 else time.time() + 8
reasons = {0: "ok", 1: "by admin", 2: "out of resources", 3: "invalid layout", 4: "forwarded"}
try:
    while time.time() < deadline:
        t = recv(1)[0]
        if t != 0:
            continue
        recv(1)
        nrect = struct.unpack(">H", recv(2))[0]
        for _ in range(nrect):
            x, y, rw, rh, enc = struct.unpack(">HHHHi", recv(12))
            if enc == -308:
                ns = recv(4)[0]
                recv(16 * ns)
                print(f"ExtendedDesktopSize {rw}x{rh} x={x} reason={reasons.get(y, y)}")
            elif enc == -223:
                print(f"DesktopSize {rw}x{rh}")
            else:
                print(f"rect enc {enc}; stopping")
                raise EOFError
except (socket.timeout, EOFError):
    pass
s.close()
