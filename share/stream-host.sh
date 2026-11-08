#!/usr/bin/env bash
# Remote control of this Omarchy laptop, and of its macOS VMs, from Moonlight
# (phone, tablet, another computer) through Sunshine on the Linux host.
#
# How it works: when Moonlight connects, a virtual (headless) Hyprland monitor
# "REMOTE" is created at exactly the resolution and refresh rate the client
# asked for. Sunshine captures only that monitor (wlr-screencopy), encodes with
# libx264 (Asahi has no hardware encoder) and injects touch, mouse and keyboard
# through uinput. When the stream ends, the monitor is removed again.
#
# Moonlight apps:
#   Desktop         the Linux desktop on REMOTE. With the lid closed the built-in
#                   screen is switched off for the session, so every workspace
#                   moves to REMOTE.
#   macOS NAME      a full-screen TigerVNC viewer of that VM on REMOTE. The guest
#                   resizes itself to the client's resolution (QEMU patch 0003).
#
# Clamshell: `start` holds a lid-switch inhibitor, so closing the lid locks the
# session but does not suspend; unlock from Moonlight with your password.
#
# Usage:
#   stream-host.sh setup              # once: package, ufw rules, web UI login
#   stream-host.sh start              # Sunshine + lid inhibitor, as user services
#   stream-host.sh enable | disable   # also start at login
#   stream-host.sh pin 1234 [name]    # finish pairing with the PIN Moonlight shows
#   stream-host.sh display WxH[@Hz]   # resize the live REMOTE monitor
#   stream-host.sh status | stop | log
set -euo pipefail

SELF=$(readlink -f "$0")
OUT="${OMVM_STREAM_OUTPUT:-REMOTE}"
WS="${OMVM_STREAM_WORKSPACE:-11}"
UNIT=omvm-sunshine
LIDUNIT=omvm-remote-lid
CONF_DIR="$HOME/.config/sunshine"
CONF="$CONF_DIR/sunshine.conf"
APPS="$CONF_DIR/apps.json"
CRED="$CONF_DIR/omvm-webui-login"       # "user password", mode 600
STATE="${XDG_RUNTIME_DIR:-/run/user/$(id -u)}/omvm-stream"
LAN_NETS="${OMVM_STREAM_LAN:-192.168.0.0/16 10.0.0.0/8 172.16.0.0/12 100.64.0.0/10}"
UDIR="$HOME/.config/systemd/user"

die() { echo "stream-host: $*" >&2; exit 1; }
lua() { hyprctl eval "$1" >/dev/null; }
has_output() { hyprctl monitors all -j | jq -e --arg o "$1" 'any(.[]; .name == $o)' >/dev/null; }
internal() { omarchy-hyprland-monitor-laptop 2>/dev/null || echo eDP-1; }
lid_closed() { omarchy-hw-laptop-closed 2>/dev/null; }

# Running VMs as "name port" lines: QEMU processes listening for VNC.
vms() {
  ss -ltnpH 2>/dev/null | awk '/qemu-system/ {split($4,a,":"); p=a[2]; match($0,/pid=[0-9]+/); print substr($0,RSTART+4,RLENGTH-4), p}' |
  while read -r pid port; do
    [[ $port -ge 5900 && $port -lt 6000 ]] || continue
    cmd=$(tr '\0' ' ' </proc/"$pid"/cmdline)
    name=$(grep -oE 'guest=[A-Za-z0-9_.-]+' <<<"$cmd" | head -1 | cut -d= -f2)
    [[ -n $name ]] || name=$(grep -oE 'runs/[A-Za-z0-9_.-]+' <<<"$cmd" | head -1 | cut -d/ -f2)
    echo "${name:-vm$port} $port"
  done
}

write_conf() {
  mkdir -p "$CONF_DIR"
  cat >"$CONF" <<EOF
# Written by omvm stream-host.sh: stream the virtual Hyprland output $OUT
sunshine_name = $(hostname)
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

write_apps() {
  [[ -f $APPS && ! -f $APPS.pre-omvm ]] && cp "$APPS" "$APPS.pre-omvm"
  python3 - "$APPS" "$SELF" <<'PY' "$(vms)"
import json, sys
path, me, vms = sys.argv[1], sys.argv[2], sys.argv[3]
apps = [{"name": "Desktop", "image-path": "desktop.png",
         "prep-cmd": [{"do": f"{me} session-do desktop", "undo": f"{me} session-undo"}]}]
for line in filter(None, vms.splitlines()):
    name, port = line.split()
    apps.append({"name": f"macOS {name}", "image-path": "desktop.png",
                 "prep-cmd": [{"do": f"{me} session-do vm {port}", "undo": f"{me} session-undo"}]})
json.dump({"env": {"PATH": "$(PATH):$(HOME)/.local/bin"}, "apps": apps}, open(path, "w"), indent=2)
PY
}

# ---- per-session display (Sunshine prep-cmd; SUNSHINE_CLIENT_* come from Moonlight)
set_mode() { # WxH@Hz
  local w=${1%%x*} rest=${1#*x} h fps scale pos
  h=${rest%%@*}; fps=60; [[ $rest == *@* ]] && fps=${rest#*@}
  scale=${OMVM_STREAM_SCALE:-}
  if [[ -z $scale ]]; then scale=1; (( h >= 1800 )) && scale=2; fi
  # Sunshine maps absolute input from 0,0, so REMOTE must not sit at negative
  # coordinates: alone it is at 0x0, next to the built-in screen to its right.
  pos=auto-right; [[ -f $STATE/internal-off ]] && pos=0x0
  lua "hl.monitor({ output = '$OUT', mode = '${w}x${h}@${fps}', position = '$pos', scale = $scale })"
}

session_do() { # desktop | vm PORT
  mkdir -p "$STATE"
  local mode="${SUNSHINE_CLIENT_WIDTH:-1920}x${SUNSHINE_CLIENT_HEIGHT:-1080}@${SUNSHINE_CLIENT_FPS:-60}"
  has_output "$OUT" || { hyprctl output create headless "$OUT" >/dev/null; sleep 0.5; }
  if [[ $1 == desktop ]] && lid_closed && [[ ${OMVM_STREAM_KEEP_INTERNAL:-0} != 1 ]]; then
    # Clamshell: the built-in screen can't be seen, so take it away; Hyprland
    # moves its workspaces to REMOTE.
    touch "$STATE/internal-off"
    lua "hl.monitor({ output = '$(internal)', disabled = true })"
  fi
  set_mode "$mode"
  lua "hl.workspace_rule({ workspace = '$WS', monitor = '$OUT', default = true })" 2>/dev/null || true
  if [[ $1 == vm ]]; then
    setsid -f bash -c 'echo $$ >"$1"; exec vncviewer -Shared=1 -RemoteResize=1 -FullScreen=1 \
      -FullScreenMode=Selected -FullScreenSelectedMonitors=1 -AlertOnFatalError=0 -ReconnectOnError=1 \
      "127.0.0.1:$2"' _ "$STATE/viewer.pid" "$2" >"$STATE/viewer.log" 2>&1
    local addr=""
    for _ in $(seq 50); do
      addr=$(hyprctl clients -j | jq -r --argjson p "$(cat "$STATE/viewer.pid")" '.[] | select(.pid == $p) | .address' | head -1)
      [[ -n $addr ]] && break; sleep 0.2
    done
    if [[ -n $addr ]]; then
      lua "hl.dispatch(hl.dsp.window.move({ workspace = '$WS', follow = true, window = 'address:$addr' }))"
      lua "hl.dispatch(hl.dsp.window.fullscreen({ mode = 'fullscreen', action = 'set', window = 'address:$addr' }))"
    fi
  else
    hyprctl dispatch "hl.dsp.focus({ monitor = '$OUT' })" >/dev/null 2>&1 || true
  fi
  echo "$(date +%T) session $* at $mode" >>"$STATE/sessions.log"
}

session_undo() {
  if [[ -f $STATE/viewer.pid ]]; then kill "$(cat "$STATE/viewer.pid")" 2>/dev/null || true; rm -f "$STATE/viewer.pid"; fi
  if [[ -f $STATE/internal-off ]]; then
    rm -f "$STATE/internal-off"
    lua "hl.monitor({ output = '$(internal)', disabled = false, mode = 'preferred', position = 'auto' })" || true
    omarchy-hyprland-monitor-clamshell >/dev/null 2>&1 || true   # restores its usual scale
  fi
  has_output "$OUT" && hyprctl output remove "$OUT" >/dev/null || true
  echo "$(date +%T) session end" >>"$STATE/sessions.log"
}

# ---- services
write_units() {
  mkdir -p "$UDIR"
  cat >"$UDIR/$UNIT.service" <<EOF
[Unit]
Description=Sunshine remote desktop for Omarchy and its macOS VMs (omvm)
PartOf=graphical-session.target
After=graphical-session.target

[Service]
ExecStartPre=$SELF prepare
ExecStart=/usr/bin/sunshine $CONF
Restart=on-failure
RestartSec=3

[Install]
WantedBy=graphical-session.target
EOF
  cat >"$UDIR/$LIDUNIT.service" <<EOF
[Unit]
Description=Keep the laptop awake with the lid closed, for remote use (omvm)
PartOf=graphical-session.target
After=graphical-session.target

[Service]
ExecStart=/usr/bin/systemd-inhibit --what=handle-lid-switch --who=omvm --why="Remote access (Sunshine/SSH) in clamshell" --mode=block sleep infinity

[Install]
WantedBy=graphical-session.target
EOF
  systemctl --user daemon-reload
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

cmd_prepare() { write_conf; write_apps; }

cmd_start() {
  command -v sunshine >/dev/null || die "run: $0 setup"
  # the old transient unit and SUNVM monitor from earlier versions
  systemctl --user stop "$UNIT" 2>/dev/null || true
  has_output SUNVM && hyprctl output remove SUNVM >/dev/null || true
  write_units
  systemctl --user start "$LIDUNIT" "$UNIT"
  ip=$(ip -4 route get 1.1.1.1 2>/dev/null | sed -n 's/.* src \([0-9.]*\).*/\1/p')
  echo "Sunshine up. Moonlight: add host $ip ; web UI https://$ip:47990 ; lid close won't suspend."
  echo "apps: Desktop$(vms | awk '{printf ", macOS %s", $1}')"
}

cmd_stop() {
  systemctl --user stop "$UNIT" "$LIDUNIT" 2>/dev/null || true
  session_undo >/dev/null 2>&1 || true
  echo "stopped (lid close suspends again)"
}

cmd_pin() { # PIN shown by Moonlight on the phone
  [[ -n ${1:-} ]] || die "usage: $0 pin 1234 [device-name]"
  read -r u p <"$CRED"
  local api=https://127.0.0.1:47990/api/pin id
  id=$(curl -sk -u "$u:$p" "$api" | python3 -c 'import json,sys; p=json.load(sys.stdin)["pairings"]; print(p[-1]["id"] if p else "")')
  [[ -n $id ]] || die "no pending pairing: start pairing in Moonlight first"
  curl -sk -u "$u:$p" -H 'Content-Type: application/json' \
    -d "{\"pairing_id\":\"$id\",\"pin\":\"$1\",\"name\":\"${2:-phone}\"}" "$api"; echo
}

cmd_status() {
  for u in "$UNIT" "$LIDUNIT"; do printf '%-18s %s\n' "$u" "$(systemctl --user is-active "$u")"; done
  hyprctl monitors | grep -A1 "Monitor $OUT" || echo "no $OUT monitor (no stream running)"
  tail -3 "$STATE/sessions.log" 2>/dev/null || true
}

case "${1:-}" in
  setup) cmd_setup ;;
  start) cmd_start ;;
  stop) cmd_stop ;;
  enable) write_units; systemctl --user enable --now "$LIDUNIT" "$UNIT" ;;
  disable) systemctl --user disable --now "$UNIT" "$LIDUNIT" ;;
  prepare) cmd_prepare ;;
  session-do) shift; session_do "$@" ;;
  session-undo) session_undo ;;
  display) has_output "$OUT" || die "no stream running"; set_mode "${2:?WxH[@Hz]}" ;;
  pin) cmd_pin "${2:-}" "${3:-}" ;;
  status) cmd_status ;;
  log) journalctl --user -u "$UNIT" -n 100 --no-pager ;;
  *) sed -n '2,29p' "$0"; exit 1 ;;
esac
