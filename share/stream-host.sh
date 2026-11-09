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
# One Moonlight host per VM: `-i NAME` runs a second Sunshine instance named
# after the VM (own config dir ~/.config/sunshine-NAME, own pairing, ports
# shifted to base 48989), so Moonlight lists the laptop and the VM as two
# machines. The laptop's instance then offers only Desktop; the VM's instance
# offers "macOS NAME" (follows the client) plus fixed per-device tiles
# (DEVICES below). In Moonlight add the VM host as ADDRESS:48989.
#
# Clamshell: `start` holds a lid-switch inhibitor, so closing the lid locks the
# session but does not suspend; unlock from Moonlight with your password.
#
# Usage:
#   stream-host.sh [-i VM] setup      # once: package, ufw rules, web UI login
#   stream-host.sh [-i VM] start      # Sunshine + lid inhibitor, as user services
#   stream-host.sh [-i VM] enable | disable   # also start at login (-i: and keep the VM running)
#   stream-host.sh pin 1234 [name]    # finish pairing (finds the instance that asked)
#   stream-host.sh keepalive VM       # start VM at boot (linger) + restart it if it dies
#   stream-host.sh [-i VM] display WxH[@Hz]   # resize the live REMOTE monitor
#   stream-host.sh [-i VM] status | stop | log
set -euo pipefail

SELF=$(readlink -f "$0")
INSTANCE="${OMVM_STREAM_INSTANCE:-}"
if [[ ${1:-} == -i || ${1:-} == --instance ]]; then INSTANCE=${2:?-i VM}; shift 2; fi
UNIT=omvm-sunshine
LIDUNIT=omvm-remote-lid
UDIR="$HOME/.config/systemd/user"
LAN_NETS="${OMVM_STREAM_LAN:-192.168.0.0/16 10.0.0.0/8 172.16.0.0/12 100.64.0.0/10}"
if [[ -z $INSTANCE ]]; then
  OUT="${OMVM_STREAM_OUTPUT:-REMOTE}"
  WS="${OMVM_STREAM_WORKSPACE:-11}"
  PORT=47989
  CONF_DIR="$HOME/.config/sunshine"
else
  [[ $INSTANCE =~ ^[A-Za-z0-9_.-]+$ ]] || { echo "stream-host: bad VM name '$INSTANCE'" >&2; exit 1; }
  OUT="${OMVM_STREAM_OUTPUT:-REMOTE-$INSTANCE}"
  WS="${OMVM_STREAM_WORKSPACE:-12}"
  PORT="${OMVM_STREAM_PORT:-48989}"
  UNIT="omvm-sunshine-$INSTANCE"
  CONF_DIR="$HOME/.config/sunshine-$INSTANCE"
fi
CONF="$CONF_DIR/sunshine.conf"
APPS="$CONF_DIR/apps.json"
CRED="$CONF_DIR/omvm-webui-login"       # "user password", mode 600
STATE="${XDG_RUNTIME_DIR:-/run/user/$(id -u)}/omvm-stream${INSTANCE:+-$INSTANCE}"
ME="$SELF${INSTANCE:+ -i $INSTANCE}"     # how prep-cmds call back into this script

# Fixed-size tiles of a VM instance: "tile name|guest WxH or client|fps cap|HiDPI".
# HiDPI 1 = the guest draws W/2 x H/2 points into W x H pixels (macOS has no 3x
# modes); auto = only when H >= 1800. The client's own stream resolution should
# match (Moonlight setting), else Sunshine scales the frame into it.
# fps caps keep libx264 (software, ~4-5 Mpx at 60 fps on M1 Max) from falling behind.
DEVICES=(
  "macOS – Pixel Fold|2076x2152|60|1"     # Pixel 9 Pro Fold inner screen -> 1038x1076 pt
  "macOS – Fold cover|1080x2424|60|1"     # Pixel 9 Pro Fold cover screen -> 540x1212 pt
  "macOS – iPhone|client|60|1"            # any iPhone: its requested size, at 2x
  "macOS – MacBook 14|3024x1964|50|1"     # MacBook Pro 14 -> 1512x982 pt
)

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

vm_port() { # NAME|PORT -> VNC port of that running VM
  if [[ $1 =~ ^[0-9]+$ ]]; then echo "$1"; return; fi
  vms | awk -v n="$1" '$1 == n {print $2; exit}'
}

write_conf() {
  mkdir -p "$CONF_DIR"
  cat >"$CONF" <<EOF
# Written by omvm stream-host.sh: stream the virtual Hyprland output $OUT
sunshine_name = ${INSTANCE:-$(hostname)}
capture = wlr
output_name = $OUT
encoder = software
sw_preset = ${OMVM_STREAM_PRESET:-ultrafast}
sw_tune = zerolatency
min_threads = ${OMVM_STREAM_THREADS:-8}
origin_web_ui_allowed = lan
upnp = disabled
# phone touches arrive as absolute mouse events (tested mapping); native touch
# would be bound to one monitor by Hyprland and land on the wrong one
native_pen_touch = disabled
EOF
  # a VM's own instance: shifted ports and its own files (pairings, cert, state)
  [[ -z $INSTANCE ]] || cat >>"$CONF" <<EOF
port = $PORT
file_apps = $APPS
file_state = $CONF_DIR/sunshine_state.json
credentials_file = $CONF_DIR/sunshine_state.json
pkey = $CONF_DIR/credentials/cakey.pem
cert = $CONF_DIR/credentials/cacert.pem
log_path = $CONF_DIR/sunshine.log
EOF
}

# VMs that have their own Sunshine instance (stream-host.sh -i NAME setup)
own_instance() { [[ -s $HOME/.config/sunshine-$1/omvm-webui-login ]]; }

write_apps() {
  [[ -f $APPS && ! -f $APPS.pre-omvm ]] && cp "$APPS" "$APPS.pre-omvm"
  local vmlist="" n p
  if [[ -z $INSTANCE ]]; then
    while read -r n p; do
      [[ -n $n ]] && ! own_instance "$n" && vmlist+="$n $p"$'\n'
    done < <(vms)
  fi
  python3 - "$APPS" "$ME" "$INSTANCE" "$vmlist" "${DEVICES[@]}" <<'PY'
import json, sys
path, me, inst, vms, devices = sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4], sys.argv[5:]
def app(name, do):
    return {"name": name, "image-path": "desktop.png",
            "prep-cmd": [{"do": f"{me} session-do {do}", "undo": f"{me} session-undo"}]}
if inst:   # the VM's own host: follow-the-client tile + one tile per device
    apps = [app(f"macOS {inst}", f"vm {inst}")]
    for d in devices:
        name, size, fps, hidpi = d.split("|")
        apps.append(app(name, f"vm {inst} {size}@{fps} {hidpi}"))
else:      # the laptop: its desktop, plus VMs that have no host of their own
    apps = [app("Desktop", "desktop")]
    for line in filter(None, vms.splitlines()):
        name, port = line.split()
        apps.append(app(f"macOS {name}", f"vm {port}"))
json.dump({"env": {"PATH": "$(PATH):$(HOME)/.local/bin"}, "apps": apps},
          open(path, "w"), indent=2, ensure_ascii=False)
PY
}

# ---- per-session display (Sunshine prep-cmd; SUNSHINE_CLIENT_* come from Moonlight)
GUEST_KEY="${OMVM_STREAM_GUEST_KEY:-$HOME/.ssh/vmapple_runner}"
# VNC port -> guest ssh port (QEMU hostfwd), e.g. "5900=42541 5931=40123".
# A VM without an entry just skips the guest-side steps (HiDPI).
GUEST_SSH="${OMVM_STREAM_GUEST_SSH:-5900=42541}"
guest_ssh_port() { local kv; for kv in $GUEST_SSH; do [[ ${kv%%=*} == "$1" ]] && echo "${kv#*=}"; done; return 0; }
gssh() { # VNCPORT CMD...
  local p; p=$(guest_ssh_port "$1"); shift
  [[ -n $p && -r $GUEST_KEY ]] || return 1
  ssh -i "$GUEST_KEY" -o IdentitiesOnly=yes -o BatchMode=yes -o ConnectTimeout=4 -o StrictHostKeyChecking=no \
      -o UserKnownHostsFile=/dev/null -o LogLevel=ERROR -p "$p" aquarat@127.0.0.1 "$@"
}
# The guest's pixel size: asked of macOS when we can (the VNC server reports a
# padded, sometimes stale size), else of the VNC server.
guest_size() {
  local m; m=$(gssh "$1" /usr/local/bin/omvm-hidpi 2>/dev/null || true)
  if [[ $m =~ /([0-9]+x[0-9]+)px$ ]]; then echo "${BASH_REMATCH[1]}"; return; fi
  python3 "$(dirname "$SELF")/vnc-setsize.py" "$1" 0 0 0 2>/dev/null | awk '/server desktop/ {print $3; exit}'
}
# Kill every stream viewer of PORT, including one leaked by an aborted
# session-do (it would keep resizing the guest to its own window size).
kill_viewers() { pkill -f "vncviewer -Shared=1 -RemoteResize=1 .*127[.]0[.]0[.]1:$1\$" 2>/dev/null || true; rm -f "$STATE/viewer.pid"; }

# HiDPI in the guest: once the guest is W x H pixels, switch to the Retina mode
# that draws W/2 x H/2 points into those pixels (full sharpness, normal-sized
# text). auto: only for tall streams (H >= 1800, the same rule as the REMOTE
# scale); smaller streams stay 1:1, or everything would be tiny. Device tiles
# force it on (1) or off (0).
# Needs share/omvm-hidpi.swift built into the guest at /usr/local/bin/omvm-hidpi.
# OMVM_STREAM_GUEST_HIDPI=0 turns it off.
guest_hidpi() { # VNCPORT W H [auto|0|1]
  [[ ${OMVM_STREAM_GUEST_HIDPI:-1} == 1 ]] || return 0
  local want=${4:-auto}
  [[ $want == auto ]] && { want=0; (( $3 >= 1800 )) && want=1; }
  (
    # wait until the guest itself is W x H pixels (the VNC server reports a
    # padded size, e.g. 2080 for 2076, so ask macOS)
    for _ in $(seq 40); do [[ $(gssh "$1" /usr/local/bin/omvm-hidpi 2>/dev/null) == */"$2x$3"px ]] && break; sleep 0.5; done
    sleep 1
    echo "$(date +%T) ${2}x${3} hidpi=$want: $(gssh "$1" "/usr/local/bin/omvm-hidpi $2 $3 $want" 2>&1)" >>"$STATE/hidpi.log"
  ) </dev/null >/dev/null 2>&1 &
  disown
}
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

session_do() { # desktop | vm PORT|NAME [WxH|client][@MAXFPS] [auto|0|1 HiDPI]
  mkdir -p "$STATE"
  local w=${SUNSHINE_CLIENT_WIDTH:-1920} h=${SUNSHINE_CLIENT_HEIGHT:-1080} fps=${SUNSHINE_CLIENT_FPS:-60}
  local size=${3:-client} hidpi=${4:-auto} mode
  if [[ $1 == vm ]]; then
    [[ ${size%@*} =~ ^([0-9]+)x([0-9]+)$ ]] && { w=${BASH_REMATCH[1]}; h=${BASH_REMATCH[2]}; }
    [[ $size == *@* ]] && (( fps > ${size#*@} )) && fps=${size#*@}
    # macOS only offers even sizes (an odd width comes back one pixel smaller),
    # and the 2x REMOTE scale needs them too
    w=$(( w / 2 * 2 )); h=$(( h / 2 * 2 ))
    local p; p=$(vm_port "$2"); [[ -n $p ]] || die "VM $2 is not running"; set -- vm "$p" "${@:3}"
  fi
  mode="${w}x${h}@${fps}"
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
    kill_viewers "$2"
    [[ -s $STATE/guest-size.$2 ]] || guest_size "$2" >"$STATE/guest-size.$2"
    setsid -f bash -c 'echo $$ >"$1"; exec vncviewer -Shared=1 -RemoteResize=1 -FullScreen=1 \
      -FullScreenMode=Selected -FullScreenSelectedMonitors=1 -AlertOnFatalError=0 -ReconnectOnError=1 \
      "127.0.0.1:$2"' _ "$STATE/viewer.pid" "$2" >"$STATE/viewer.log" 2>&1
    local addr="" vpid=""
    for _ in $(seq 50); do
      # setsid -f returns before the child has written its pid
      vpid=$(cat "$STATE/viewer.pid" 2>/dev/null || true)
      [[ $vpid =~ ^[0-9]+$ ]] || { sleep 0.1; continue; }
      addr=$(hyprctl clients -j | jq -r --argjson p "$vpid" '.[] | select(.pid == $p) | .address' | head -1)
      [[ -n $addr ]] && break; sleep 0.2
    done
    if [[ -n $addr ]]; then
      lua "hl.dispatch(hl.dsp.window.move({ workspace = '$WS', follow = true, window = 'address:$addr' }))"
      lua "hl.dispatch(hl.dsp.window.fullscreen({ mode = 'fullscreen', action = 'set', window = 'address:$addr' }))"
    fi
    # TigerVNC shrinks its window when the guest already has the screen's size
    # ("avoid accidental full-screen request") and resizes the guest to that;
    # once the viewer is full screen, ask for the exact size ourselves.
    ( sleep 1.5; python3 "$(dirname "$SELF")/vnc-setsize.py" "$2" "$w" "$h" 1 ) >/dev/null 2>&1 || true
    echo "$2" >"$STATE/vm-port"
    guest_hidpi "$2" "$w" "$h" "$hidpi"
  else
    hyprctl dispatch "hl.dsp.focus({ monitor = '$OUT' })" >/dev/null 2>&1 || true
  fi
  echo "$(date +%T) session $* at $mode" >>"$STATE/sessions.log"
}

session_undo() {
  if [[ -f $STATE/viewer.pid ]]; then kill "$(cat "$STATE/viewer.pid")" 2>/dev/null || true; rm -f "$STATE/viewer.pid"; fi
  if [[ -f $STATE/vm-port ]]; then
    local port sz; port=$(cat "$STATE/vm-port"); rm -f "$STATE/vm-port"
    kill_viewers "$port"
    # back to the size (1:1 mode) the guest had before the stream
    sz=$(cat "$STATE/guest-size.$port" 2>/dev/null || true); rm -f "$STATE/guest-size.$port"
    if [[ $sz =~ ^([0-9]+)x([0-9]+)$ ]]; then
      gssh "$port" "/usr/local/bin/omvm-hidpi 0 0 0" >/dev/null 2>&1 || true
      python3 "$(dirname "$SELF")/vnc-setsize.py" "$port" "${BASH_REMATCH[1]}" "${BASH_REMATCH[2]}" 2 >/dev/null 2>&1 || true
    fi
  fi
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
  local desc="Sunshine remote desktop for Omarchy (omvm)" after=""
  if [[ -n $INSTANCE ]]; then
    desc="Sunshine remote desktop for the $INSTANCE VM, ports $PORT+ (omvm)"
    after=" omvm-vm@$INSTANCE.service"
  fi
  cat >"$UDIR/$UNIT.service" <<EOF
[Unit]
Description=$desc
PartOf=graphical-session.target
After=graphical-session.target$after

[Service]
ExecStartPre=$ME prepare
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

# Keep a libvirt-session VM running whenever the laptop is up: start it at boot
# (lingering user manager, no login needed) and check every minute that it
# still runs. A stream ending never stops the VM, it only resizes it.
# To really stop it: systemctl --user disable --now omvm-vm@NAME.timer
cmd_keepalive() { # VM
  local vm=${1:?usage: $0 keepalive VM}
  mkdir -p "$UDIR"
  cat >"$UDIR/omvm-vm@.service" <<'EOF'
[Unit]
Description=Start the %i VM (libvirt session) if it is not running (omvm)

[Service]
Type=oneshot
ExecStart=-/bin/sh -c 'virsh -c qemu:///session domstate %i 2>/dev/null | grep -qx running || virsh -c qemu:///session start %i'
TimeoutStartSec=120

[Install]
WantedBy=default.target
EOF
  cat >"$UDIR/omvm-vm@.timer" <<'EOF'
[Unit]
Description=Restart the %i VM if it died (omvm)

[Timer]
OnBootSec=20
OnUnitInactiveSec=60
AccuracySec=5

[Install]
WantedBy=timers.target
EOF
  # the hand-made unit of earlier versions
  if [[ -f $UDIR/omvm-vm-$vm.service ]]; then
    systemctl --user disable "omvm-vm-$vm.service" 2>/dev/null || true
    rm -f "$UDIR/omvm-vm-$vm.service"
  fi
  systemctl --user daemon-reload
  virsh -c qemu:///session autostart "$vm" >/dev/null
  systemctl --user enable "omvm-vm@$vm.service" >/dev/null 2>&1
  systemctl --user enable --now "omvm-vm@$vm.timer"
  [[ $(loginctl show-user "$USER" -p Linger --value 2>/dev/null) == yes ]] || sudo loginctl enable-linger "$USER"
  echo "$vm: libvirt autostart on, omvm-vm@$vm.timer checks every minute, linger=$(loginctl show-user "$USER" -p Linger --value)"
}

cmd_setup() {
  pacman -Q sunshine >/dev/null 2>&1 || sudo pacman -S --needed --noconfirm sunshine
  # Sunshine ports relative to the base port: TCP -5 +0 +1 +21, UDP +9..+21
  local tcp="$((PORT-5)),$PORT,$((PORT+1)),$((PORT+21))" udp="$((PORT+9)):$((PORT+21))"
  if systemctl is-active -q ufw; then
    for net in $LAN_NETS; do
      sudo ufw allow from "$net" to any port "$tcp" proto tcp comment "sunshine${INSTANCE:+-$INSTANCE}"
      sudo ufw allow from "$net" to any port "$udp" proto udp comment "sunshine${INSTANCE:+-$INSTANCE}"
    done
  fi
  write_conf
  if [[ ! -s $CRED ]]; then
    umask 077
    echo "sunshine $(head -c 12 /dev/urandom | base64 | tr -d '/+=')" >"$CRED"
    read -r u p <"$CRED"
    sunshine "$CONF" --creds "$u" "$p" >/dev/null 2>&1
  fi
  echo "web UI https://127.0.0.1:$((PORT+1)) ; login (user password) is in $CRED"
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
  local addr=$ip; [[ -n $INSTANCE ]] && addr="$ip:$PORT"
  echo "Sunshine up. Moonlight: add host $addr ; web UI https://$ip:$((PORT+1)) ; lid close won't suspend."
  echo "apps: $(jq -r '[.apps[].name] | join(", ")' "$APPS")"
}

cmd_stop() {
  systemctl --user stop "$UNIT" 2>/dev/null || true
  [[ -n $INSTANCE ]] || systemctl --user stop "$LIDUNIT" 2>/dev/null || true
  session_undo >/dev/null 2>&1 || true
  echo "stopped${INSTANCE:+ $UNIT}${INSTANCE:- (lid close suspends again)}"
}

# Pairing: Moonlight shows a PIN; hand it to whichever instance (laptop or a
# VM's own host) has a pairing request waiting. -i picks one explicitly.
cmd_pin() { # PIN [device-name]
  [[ -n ${1:-} ]] || die "usage: $0 [-i VM] pin 1234 [device-name]"
  local dirs=("$CONF_DIR") d u p port api id
  [[ -n $INSTANCE ]] || dirs+=("$HOME"/.config/sunshine-*)
  for d in "${dirs[@]}"; do
    [[ -s $d/omvm-webui-login && -f $d/sunshine.conf ]] || continue
    port=$(sed -n 's/^port *= *\([0-9]*\).*/\1/p' "$d/sunshine.conf"); port=${port:-47989}
    read -r u p <"$d/omvm-webui-login"
    api="https://127.0.0.1:$((port+1))/api/pin"
    id=$(curl -sk -u "$u:$p" "$api" | python3 -c 'import json,sys; p=json.load(sys.stdin).get("pairings") or []; print(p[-1]["id"] if p else "")' 2>/dev/null || true)
    [[ -n $id ]] || continue
    echo -n "$(sed -n 's/^sunshine_name *= *//p' "$d/sunshine.conf") (port $port): "
    curl -sk -u "$u:$p" -H 'Content-Type: application/json' \
      -d "{\"pairing_id\":\"$id\",\"pin\":\"$1\",\"name\":\"${2:-phone}\"}" "$api"; echo
    return 0
  done
  die "no pending pairing: start pairing in Moonlight first"
}

cmd_status() {
  for u in "$UNIT" "$LIDUNIT" ${INSTANCE:+omvm-vm@$INSTANCE.timer}; do printf '%-26s %s\n' "$u" "$(systemctl --user is-active "$u")"; done
  hyprctl monitors | grep -A1 "Monitor $OUT " || echo "no $OUT monitor (no stream running)"
  tail -3 "$STATE/sessions.log" 2>/dev/null || true
}

case "${1:-}" in
  setup) cmd_setup ;;
  start) cmd_start ;;
  stop) cmd_stop ;;
  enable) write_units
          [[ -z $INSTANCE ]] || cmd_keepalive "$INSTANCE"
          systemctl --user enable --now "$LIDUNIT" "$UNIT" ;;
  disable) systemctl --user disable --now "$UNIT"; [[ -n $INSTANCE ]] || systemctl --user disable --now "$LIDUNIT" ;;
  keepalive) cmd_keepalive "${2:-}" ;;
  prepare) cmd_prepare ;;
  session-do) shift; session_do "$@" ;;
  session-undo) session_undo ;;
  display) has_output "$OUT" || die "no stream running"; set_mode "${2:?WxH[@Hz]}" ;;
  pin) cmd_pin "${2:-}" "${3:-}" ;;
  status) cmd_status ;;
  log) journalctl --user -u "$UNIT" -n 100 --no-pager ;;
  *) sed -n '2,36p' "$0"; exit 1 ;;
esac
