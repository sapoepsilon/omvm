#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Two-way text clipboard between the Omarchy (Wayland) host and a macOS guest.

    omvm-clip.py SSH_PORT KEY [GUEST_USER]

Host -> guest: `wl-paste --watch` reports each host clipboard change; the text
is sent to the guest's `pbcopy` over SSH. Guest -> host: one long-lived SSH
session polls the guest's `pbpaste` and prints new text base64-encoded; it goes
to `wl-copy`. The last value seen on either side is
remembered, so a copy never bounces back. Text only.
"""
import base64, hashlib, os, subprocess, sys, threading, time

port, key = sys.argv[1], sys.argv[2]
user = sys.argv[3] if len(sys.argv) > 3 else os.environ.get("OMVM_GUEST_USER") or "aquarat"
SSH = ["ssh", "-i", key, "-o", "IdentitiesOnly=yes", "-o", "BatchMode=yes",
       "-o", "StrictHostKeyChecking=no", "-o", "UserKnownHostsFile=/dev/null",
       "-o", "LogLevel=ERROR", "-o", "ServerAliveInterval=15", "-p", port, f"{user}@127.0.0.1"]
last = {"h": None}
lock = threading.Lock()
digest = lambda b: hashlib.sha256(b).hexdigest()

# Runs in the guest over one SSH session: print the pasteboard text, base64 on
# one line, whenever it changes (pbpaste every 0.6 s; Apple's python3 has no AppKit).
GUEST = r'''export LANG=en_US.UTF-8; p=$(pbpaste | base64); while sleep 0.6; do c=$(pbpaste | base64); if [ "$c" != "$p" ]; then p=$c; printf '%s\n' "$c" | tr -d '\n'; echo; fi; done'''


def guest_to_host():
    while True:
        p = subprocess.Popen(SSH + [GUEST], stdout=subprocess.PIPE, text=True)
        for line in p.stdout:
            data = base64.b64decode(line.strip() or "")
            with lock:
                if digest(data) == last["h"]:
                    continue
                last["h"] = digest(data)
            subprocess.run(["wl-copy"], input=data)
        p.wait(); time.sleep(3)  # guest rebooting or not up yet: retry


def host_to_guest():
    # wl-paste --watch runs the command with the new contents on stdin at each change.
    while True:
        p = subprocess.Popen(["wl-paste", "--type", "text", "--watch", "sh", "-c", "base64 -w0; echo"],
                             stdout=subprocess.PIPE, text=True)
        for line in p.stdout:
            data = base64.b64decode(line.strip() or "")
            with lock:
                if digest(data) == last["h"]:
                    continue
                last["h"] = digest(data)
            subprocess.run(SSH + ["LANG=en_US.UTF-8 pbcopy"], input=data, timeout=15)
        p.wait(); time.sleep(3)


threading.Thread(target=guest_to_host, daemon=True).start()
host_to_guest()
