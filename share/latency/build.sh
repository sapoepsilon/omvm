#!/bin/bash
# Build the host helpers of the latency rig into ~/.cache/omvm-latency:
# pixpoll (a persistent wlr-screencopy pixel poller) and flipwin (a fullscreen shm
# window that flips colour per stdin line and reports wp_presentation times).
set -euo pipefail
here="$(cd "$(dirname "$0")" && pwd)"; out=~/.cache/omvm-latency; mkdir -p "$out"; cd "$out"
sc="$(ls ~/.cargo/registry/src/*/wayland-protocols-wlr-*/wlr-protocols/unstable/wlr-screencopy-unstable-v1.xml 2>/dev/null | head -1)"
sc="${OMVM_SCREENCOPY_XML:-${sc:-/usr/share/wlr-protocols/unstable/wlr-screencopy-unstable-v1.xml}}"
wp=/usr/share/wayland-protocols
wayland-scanner client-header "$sc" wlr-screencopy-unstable-v1-client-protocol.h
wayland-scanner private-code "$sc" screencopy.c
wayland-scanner client-header $wp/stable/xdg-shell/xdg-shell.xml xdg-shell-client-protocol.h
wayland-scanner private-code $wp/stable/xdg-shell/xdg-shell.xml xdg-shell.c
wayland-scanner client-header $wp/stable/presentation-time/presentation-time.xml presentation-time-client-protocol.h
wayland-scanner private-code $wp/stable/presentation-time/presentation-time.xml presentation-time.c
cc -O2 -I. -o pixpoll "$here/pixpoll.c" screencopy.c -lwayland-client
cc -O2 -I. -o flipwin "$here/flipwin.c" xdg-shell.c presentation-time.c -lwayland-client
echo "built $out/pixpoll $out/flipwin"
