#!/usr/bin/env bash
# Stream a macOS VM to a phone/tablet with Moonlight, from Sunshine on the Linux host.
#
# How it works: a virtual (headless) Hyprland monitor "SUNVM" at the guest's
# resolution shows a dedicated full-screen TigerVNC viewer of the VM's QEMU VNC
# display. Sunshine captures only that monitor (wlr-screencopy), encodes with
# libx264 (Asahi has no hardware encoder) and injects the phone's touch, mouse
# and keyboard through uinput. Nothing is installed in the guest.
#
# Usage:
#   stream-host.sh setup              # once: package, ufw rules, web UI login
#   stream-host.sh start [VNCPORT]    # default 5931 (VM sb1)
#   stream-host.sh pin 1234           # finish pairing with the PIN Moonlight shows
#   stream-host.sh status | stop | log
set -euo pipefail

VNCPORT="${2:-${OMVM_STREAM_VNC:-5931}}"
OUT="${OMVM_STREAM_OUTPUT:-SUNVM}"
MODE="${OMVM_STREAM_MODE:-1440x1080@60}"   # the guest's display mode
WS="${OMVM_STREAM_WORKSPACE:-11}"
UNIT=omvm-sunshine
CONF_DIR="$HOME/.config/sunshine"
CONF="$CONF_DIR/sunshine.conf"
CRED="$CONF_DIR/omvm-webui-login"       # "user password", mode 600
STATE="${XDG_RUNTIME_DIR:-/run/user/$(id -u)}/omvm-stream"
LAN_NETS="${OMVM_STREAM_LAN:-192.168.0.0/16 10.0.0.0/8 172.16.0.0/12}"

die() { echo "stream-host: $*" >&2; exit 1; }
lua() { hyprctl eval "$1" >/dev/null; }

viewer_address() {
  [[ -f $STATE/viewer.pid ]] || return 1
  hyprctl clients -j | python3 -c '
import json,sys
pid=int(sys.argv[1])
print(next(c["address"] for c in json.load(sys.stdin) if c["pid"]==pid))' "$(cat "$STATE/viewer.pid")" 2>/dev/null
}

write_conf() {
  mkdir -p "$CONF_DIR"
  cat >"$CONF" <<EOF
# Written by omvm stream-host.sh: stream the VM viewer on Hyprland output $OUT
sunshine_name = omarchy-macos-vm
capture = wlr
output_name = $OUT
encoder = software
sw_preset = superfast
sw_tune = zerolatency
min_threads = 4
origin_web_ui_allowed = lan
upnp = disabled
# phone touches arrive as absolute mouse events (tested mapping); native touch
# would be bound to one monitor by Hyprland and land on the wrong one
native_pen_touch = disabled
EOF
}

cmd_setup() {
  pacman -Q sunshine >/dev/null 2>&1 || sudo pacman -S --needed --noconfirm sunshine
  if systemctl is-active -q ufw; then
    for net in $LAN_NETS; do
      sudo ufw allow from "$net" to any port 47984,47989,47990,48010 proto tcp comment sunshine
      sudo ufw allow from "$net" to any port 47998:48010 proto udp comment sunshine
    done
  fi
  if [[ ! -s $CRED ]]; then
    umask 077
    echo "sunshine $(head -c 12 /dev/urandom | base64 | tr -d '/+=')" >"$CRED"
    read -r u p <"$CRED"
    sunshine --creds "$u" "$p" >/dev/null 2>&1
  fi
  echo "web UI login (user password): $(cat "$CRED")"
}

cmd_start() {
  command -v sunshine >/dev/null || die "run: $0 setup"
  mkdir -p "$STATE"
  # 1. virtual monitor at the guest's resolution
  if ! hyprctl monitors -j | grep -q "\"name\": \"$OUT\""; then
    hyprctl output create headless "$OUT" >/dev/null
    sleep 0.5
  fi
  # Right of the real screen: Sunshine maps absolute input assuming the layout
  # starts at 0,0, so the virtual monitor must not get negative coordinates.
  lua "hl.monitor({ output = '$OUT', mode = '$MODE', position = 'auto-right', scale = 1 })"
  lua "hl.workspace_rule({ workspace = '$WS', monitor = '$OUT', default = true, persistent = true })" 2>/dev/null || true

  # 2. dedicated VNC viewer, full screen on that monitor
  if ! viewer_address >/dev/null; then
    setsid -f bash -c 'echo $$ >"$1"; exec vncviewer -Shared=1 -RemoteResize=0 -AlertOnFatalError=0 \
      -ReconnectOnError=1 -geometry "${3%@*}" "127.0.0.1:$2"' _ "$STATE/viewer.pid" "$VNCPORT" "$MODE" \
      >"$STATE/viewer.log" 2>&1
    for _ in $(seq 50); do viewer_address >/dev/null && break; sleep 0.2; done
  fi
  addr=$(viewer_address) || die "VNC viewer did not start (see $STATE/viewer.log)"
  lua "hl.dispatch(hl.dsp.window.move({ workspace = '$WS', follow = false, window = 'address:$addr' }))"
  lua "hl.dispatch(hl.dsp.window.fullscreen({ mode = 'fullscreen', action = 'set', window = 'address:$addr' }))"

  # 3. Sunshine on that monitor only
  write_conf
  if ! systemctl --user is-active -q "$UNIT"; then
    systemctl --user reset-failed "$UNIT" 2>/dev/null || true
    systemd-run --user --unit="$UNIT" --description="Sunshine for the macOS VM (omvm)" \
      -p Restart=on-failure --setenv=WAYLAND_DISPLAY="${WAYLAND_DISPLAY:-wayland-1}" \
      --setenv=HYPRLAND_INSTANCE_SIGNATURE="${HYPRLAND_INSTANCE_SIGNATURE:-}" \
      /usr/bin/sunshine "$CONF" >/dev/null
  fi
  ip=$(ip -4 route get 1.1.1.1 2>/dev/null | sed -n 's/.* src \([0-9.]*\).*/\1/p')
  echo "streaming VNC :$VNCPORT on $OUT. Moonlight: add host $ip ; web UI https://$ip:47990"
}

cmd_stop() {
  systemctl --user stop "$UNIT" 2>/dev/null || true
  if [[ -f $STATE/viewer.pid ]]; then kill "$(cat "$STATE/viewer.pid")" 2>/dev/null || true; rm -f "$STATE/viewer.pid"; fi
  hyprctl monitors -j | grep -q "\"name\": \"$OUT\"" && hyprctl output remove "$OUT" >/dev/null
  echo stopped
}

cmd_pin() { # PIN shown by Moonlight on the phone
  [[ -n ${1:-} ]] || die "usage: $0 pin 1234 [device-name]"
  read -r u p <"$CRED"
  local api=https://127.0.0.1:47990/api/pin id
  # this Sunshine wants the id of the pending pairing request: take the newest
  id=$(curl -sk -u "$u:$p" "$api" | python3 -c 'import json,sys; p=json.load(sys.stdin)["pairings"]; print(p[-1]["id"] if p else "")')
  [[ -n $id ]] || die "no pending pairing: start pairing in Moonlight first"
  curl -sk -u "$u:$p" -H 'Content-Type: application/json' \
    -d "{\"pairing_id\":\"$id\",\"pin\":\"$1\",\"name\":\"${2:-phone}\"}" "$api"; echo
}

cmd_status() {
  systemctl --user --no-pager status "$UNIT" 2>/dev/null | sed -n 1,3p || echo "sunshine: not running"
  hyprctl monitors | grep -A1 "Monitor $OUT" || echo "no $OUT monitor"
  viewer_address >/dev/null && echo "viewer: pid $(cat "$STATE/viewer.pid")" || echo "viewer: not running"
}

case "${1:-}" in
  setup) cmd_setup ;;
  start) cmd_start ;;
  stop) cmd_stop ;;
  pin) cmd_pin "${2:-}" "${3:-}" ;;
  status) cmd_status ;;
  log) journalctl --user -u "$UNIT" -n 100 --no-pager ;;
  *) sed -n '2,16p' "$0"; exit 1 ;;
esac
