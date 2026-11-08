# Using the macOS VM from a phone or tablet (Moonlight + Sunshine)

Sunshine runs on the Linux host, not in the guest. Nothing gets installed in macOS.

```
macOS guest ──QEMU VNC 127.0.0.1:59xx──> TigerVNC viewer, full screen on a virtual
Hyprland monitor "SUNVM" (1440x1080) ──wlr-screencopy──> Sunshine (libx264) ──LAN──> Moonlight
Moonlight touch/keys ──> Sunshine uinput devices ──> Hyprland ──> viewer ──VNC──> guest
```

## Setup and use

```sh
~/Work/omvm/share/stream-host.sh setup          # once: sunshine package, ufw LAN rules, web UI login
~/Work/omvm/share/stream-host.sh start [5931]   # VNC port of the VM (sb1 = 5931)
~/Work/omvm/share/stream-host.sh stop
```

On the phone or tablet:

1. Install **Moonlight** (App Store or Play Store). The phone must be on the same Wi-Fi as the laptop.
2. Open Moonlight. The host `omarchy-macos-vm` may show up by itself. If it doesn't, tap **+** and enter the laptop's IP address (`start` prints it).
3. Tap the host. Moonlight shows a 4-digit PIN.
4. On the laptop, run `stream-host.sh pin <PIN> <device-name>`. You can also open `https://<laptop-ip>:47990` → **PIN**. The login is in `~/.config/sunshine/omvm-webui-login`.
5. Tap **Desktop**.
6. Recommended settings: resolution 1440x1080 (or 1080p, with letterboxing), 60 FPS, 10–20 Mbps, H.264.

Controls:
- A tap clicks where you touch. Moonlight's trackpad mode also works.
- Three-finger tap opens the keyboard on Android and iOS.
- Keys go to the viewer once it has focus. Super works as Cmd, through the omvm `macos-vm` submap.

## Measured (loopback Moonlight client on the same laptop, 1440x1080@60)

- 59–60 fps were received and rendered, with 0% network drops.
- Host processing latency averaged 15–22 ms (min 6, max 54).
- Sunshine used about 2 cores of the M1 Max with libx264 superfast/zerolatency.

## Caveats

- The virtual monitor sits to the right of the laptop screen while streaming. The laptop's own cursor can wander onto it.
- Phone input moves the host's single cursor and keyboard focus. Streaming and using the laptop at the same time interfere with each other.
- Absolute input only lands correctly while the monitor layout starts at 0,0, with the laptop screen at 0x0 and SUNVM to its right. `start` sets that up.
- `native_pen_touch` is disabled. Phone touches then arrive as absolute mouse clicks. Hyprland would bind native touch to one monitor, so those touches would land on the wrong screen.
- Only H.264 is available. Asahi has no hardware encoder.
- macOS can't run the VM itself here. The guest's resolution is fixed at 1440x1080.
- Outside the LAN, use Tailscale. Add a ufw rule for `100.64.0.0/10` (same ports).
- While a stream runs, Sunshine sets the host's default audio sink to its own. It restores the sink when the stream ends.

## Alternatives considered

- **Sunshine inside the macOS guest.** It needs a logged-in GUI session plus Screen Recording and Accessibility (TCC) grants clicked in the GUI. The VM has no VideoToolbox hardware encoder, so encoding would be software on 8 vCPUs. Not chosen, and not tested.
- **Parsec.** It can't host on Linux at all. macOS hosting needs hardware VideoToolbox encode, which this VM lacks. Not viable.
- **Zero-install fallback.** Enable macOS Screen Sharing (System Settings → General → Sharing). Forward a port with QMP `hostfwd_add net0 tcp:0.0.0.0:5900-:5900` and open it in ufw. Then use a VNC app on the phone (RealVNC Viewer, Jump). Another option is an SSH tunnel to QEMU's own VNC (`ssh -L 5931:127.0.0.1:5931 laptop`). Both are much laggier than Moonlight.
