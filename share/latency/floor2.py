#!/usr/bin/env python3
# Compositor floor without screencopy (fullscreen: it takes fullscreen from the Reims
# window, so run fs.sh after): a windowed shm client flips its colour and commits;
# wp_presentation says when that frame was presented (scanout). usage: floor2.py [N]
import os, sys, subprocess, time, statistics
N = int(sys.argv[1]) if len(sys.argv) > 1 else 100
d = os.path.expanduser("~/.cache/omvm-latency")
env = dict(os.environ, XDG_RUNTIME_DIR="/run/user/1000", WAYLAND_DISPLAY="wayland-1")
fw = subprocess.Popen([f"{d}/flipwin"], stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True, env=env, bufsize=1)
print(fw.stdout.readline().strip()); time.sleep(1.0)
lat = []
for i in range(N):
    time.sleep(0.05 + (i % 11) * 0.00077)
    fw.stdin.write("f\n"); fw.stdin.flush()
    t0 = int(fw.stdout.readline().split()[0])
    l = fw.stdout.readline().split()
    if l[0] == "presented": lat.append((int(l[1]) - t0) / 1e6)
fw.kill()
a = sorted(lat)
print(f"[floor2] shm commit -> presented (scanout): n={len(a)} median {statistics.median(a):.1f} p90 {a[int(len(a)*.9)]:.1f} min {a[0]:.1f} max {a[-1]:.1f} ms")
