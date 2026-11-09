#!/usr/bin/env python3
# Pointer-to-photon latency of a local-mode omvm VM.
# A uinput mouse moves the pointer across the Reims window; the guest's latprobe turns its
# full-screen window white/black on the mouse-moved event; pixpoll (a persistent
# wlr-screencopy client) reports the compositor frame that first shows the new colour.
# Prints: move -> guest event, move -> composited frame (screencopy), and, with
# --trace FILE (reims-vgpu's REIMS_VGPU_TRACE), the reims stages in between.
# --no-pixel skips the screencopy poller: continuous screencopy keeps Hyprland busy and
# delays input and composition itself, so stage timings (--trace) are cleaner without it.
# usage: lat.py [N] [label] [--trace FILE] [--vm NAME] [--no-pixel]
# Build the helpers first: share/latency/build.sh (into ~/.cache/omvm-latency).
import os, sys, time, struct, fcntl, queue, threading, subprocess, statistics, argparse
ap = argparse.ArgumentParser()
ap.add_argument("n", nargs="?", type=int, default=30); ap.add_argument("label", nargs="?", default="run")
ap.add_argument("--trace"); ap.add_argument("--vm", default="macos")
ap.add_argument("--pixpoll", default=os.path.expanduser("~/.cache/omvm-latency/pixpoll"))
ap.add_argument("--no-pixel", action="store_true")
A = ap.parse_args()
RAW = time.CLOCK_MONOTONIC_RAW
def raw(): return time.clock_gettime_ns(RAW)
xdg = "/run/user/1000"
env = dict(os.environ, XDG_RUNTIME_DIR=xdg, WAYLAND_DISPLAY="wayland-1")
sig = sorted(os.listdir(f"{xdg}/hypr"), key=lambda d: os.path.getmtime(f"{xdg}/hypr/{d}"))[-1]
import socket
def hypr(cmd):
    s = socket.socket(socket.AF_UNIX); s.connect(f"{xdg}/hypr/{sig}/.socket.sock"); s.sendall(cmd.encode()); s.recv(4096); s.close()
ufd = os.open("/dev/uinput", os.O_WRONLY | os.O_NONBLOCK)
fcntl.ioctl(ufd, 0x40045564, 1); fcntl.ioctl(ufd, 0x40045564, 2)
fcntl.ioctl(ufd, 0x40045565, 0x110)
fcntl.ioctl(ufd, 0x40045566, 0); fcntl.ioctl(ufd, 0x40045566, 1)
os.write(ufd, b"omvm-latency-mouse".ljust(80, b"\0") + struct.pack("<4H", 3, 0x1234, 0x5678, 1) + struct.pack("<i", 0) + b"\0" * (4 * 64 * 4))
fcntl.ioctl(ufd, 0x5501); time.sleep(1.0)
def uev(t, c, v): os.write(ufd, struct.pack("<qqHHi", 0, 0, t, c, v))
def move(dx): uev(2, 0, dx); uev(0, 0, 0)
# screencopy poller
pq = queue.Queue()
pp = subprocess.Popen(["sleep", "100000"] if A.no_pixel else [A.pixpoll, "400", "400"],
                      stdout=subprocess.PIPE, text=True, env=env)
def preader():
    for l in pp.stdout:
        f = l.split()
        if f[0] != "first": pq.put((int(f[0]), int(f[2])))
threading.Thread(target=preader, daemon=True).start()
# guest probe
gq = queue.Queue()
gp = subprocess.Popen(["bash", "-c", f"set -a; . ~/.config/omvm/gui.env; set +a; exec omvm ssh {A.vm} bin/latprobe"],
                      stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True, bufsize=1)
def greader():
    for l in gp.stdout: gq.put((raw(), l.split()))
threading.Thread(target=greader, daemon=True).start()
while gq.get()[1][0] != "ready": pass
time.sleep(1.0)
best = None   # guest wall clock -> host raw ns, from the lowest-RTT ping
for _ in range(40):
    t0 = raw(); gp.stdin.write("p\n"); gp.stdin.flush()
    while True:
        t1, f = gq.get()
        if f[0] == "t": break
    if best is None or t1 - t0 < best[0]: best = (t1 - t0, float(f[1]) * 1e9 - (t0 + t1) / 2)
    time.sleep(0.01)
rtt, off = best
print(f"clock: min rtt {rtt/1e6:.2f} ms")
hypr("dispatch hl.dsp.cursor.move({x=300,y=600})"); time.sleep(0.2); move(-3000); time.sleep(0.5)
moves, ev, ph = [], [], []
for i in range(A.n):
    for dx, want in ((3000, 1), (-3000, 0)):
        time.sleep(0.25 + (i % 7) * 0.0011 * 7)   # spread over the refresh period
        while not gq.empty(): gq.get()
        while not pq.empty(): pq.get()
        t0 = raw(); move(dx); moves.append(t0)
        tp = None
        while True:
            try: t, red = pq.get(timeout=0.05 if A.no_pixel else 1.0)
            except queue.Empty: break
            if (red > 128) == (want == 1): tp = t; break
        tg = None
        while True:
            try: _, f = gq.get(timeout=0.3)
            except queue.Empty: break
            if f[0] == "m" and int(f[3]) == want: tg = float(f[1]) * 1e9 - off; break
        ev.append((tg - t0) / 1e6 if tg else None); ph.append((tp - t0) / 1e6 if tp else None)
        if tp is None and not A.no_pixel: print("no flip", want, flush=True)
gp.stdin.write("q\n"); gp.stdin.flush(); pp.kill(); fcntl.ioctl(ufd, 0x5502)
def s(a):
    a = sorted(x for x in a if x is not None)
    return f"n={len(a)} median {statistics.median(a):.1f} p90 {a[int(len(a)*0.9)]:.1f} max {a[-1]:.1f} ms" if a else "n=0"
print(f"[{A.label}] move -> guest event:        {s(ev)}")
print(f"[{A.label}] move -> composited frame:   {s(ph)}")
if A.trace:
    time.sleep(0.6)
    evs = []
    for l in open(A.trace):
        f = l.split()
        if len(f) >= 3 and f[0].isdigit(): evs.append((int(f[0]), f[2], f[3:]))
    evs.sort()
    kinds = sorted({k for _, k, _ in evs})
    stages = {}
    for t0, g, p in zip(moves, ev, ph):
        if g is None: continue
        tg = t0 + g * 1e6; tp = t0 + (p if p is not None else g + 60) * 1e6
        for k in kinds:  # the first of each kind after the guest event and before the frame
            hit = next((t for t, kk, _ in evs if kk == k and tg <= t <= tp), None)
            if hit: stages.setdefault(k, []).append((hit - t0) / 1e6)
    for k, a in sorted(stages.items(), key=lambda kv: statistics.median(kv[1])):
        print(f"[{A.label}]   move -> first {k:<14} {s(a)}")
