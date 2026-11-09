# Remote control from a phone, tablet or another computer (Moonlight + Sunshine)

Sunshine runs on the Linux host, and nothing gets installed in macOS. Moonlight sees two kinds of host:

- **omarchy** (default ports, base 47989): the app **Desktop**, the Omarchy desktop itself. A VM without a host of its own also shows up here as **macOS NAME**.
- **NAME**, a VM's own host (`omvm remote -i NAME ...`, base port 48989): a second Sunshine with its own config dir `~/.config/sunshine-NAME`, its own pairings and its own headless monitor `REMOTE-NAME`. Its apps are **macOS NAME**, which follows the client's resolution, and one fixed tile per device:

| App | Guest pixels | Guest points (HiDPI) | fps cap |
|---|---|---|---|
| macOS – Pixel Fold | 2076x2152 (Pixel 9 Pro Fold inner screen) | 1038x1076 | 60 |
| macOS – Fold cover | 1080x2424 (cover screen) | 540x1212 | 60 |
| macOS – iPhone | whatever the iPhone asks for, rounded to even | half of it | 60 |
| macOS – MacBook 14 | 3024x1964 | 1512x982 | 50 |

The list is `DEVICES` in `share/stream-host.sh`. Set each device's Moonlight resolution to its native size, or Sunshine scales the frame into whatever it asks for. macOS has no 3x modes, so HiDPI is always 2x.

```
Moonlight connects (asks for W x H @ FPS)
  └─ Sunshine prep-cmd: stream-host.sh session-do ...
       ├─ creates the headless Hyprland monitor REMOTE at exactly W x H @ FPS
       ├─ Desktop:    lid closed? → built-in screen off, every workspace moves to REMOTE
       └─ macOS NAME: TigerVNC viewer full screen on REMOTE (-RemoteResize=1)
                      → QEMU patch 0003 → macOS switches to W x H
Sunshine captures REMOTE (wlr-screencopy) → libx264 → LAN → Moonlight
Moonlight touch/keys → Sunshine uinput → Hyprland
Quit the app in Moonlight → REMOTE removed, built-in screen back
```

## Setup and use

```sh
omvm remote setup      # once: sunshine package, ufw rules (LAN + Tailscale), web UI login
omvm remote start      # Sunshine + lid inhibitor as user services (this login)
omvm remote enable     # ... and at every login
omvm remote status | stop | disable | log
omvm remote display 2560x1440@60    # resize the live remote monitor

omvm remote -i macos setup     # the VM's own host: ufw for ports 48984-49010, its web UI login
omvm remote -i macos enable    # its Sunshine at every login, and keep the VM running (below)
omvm remote pin <PIN> <name>   # finish pairing on whichever host asked
```

(`omvm remote` is `share/stream-host.sh`. The laptop's list of macOS apps is rebuilt from the running VMs each time Sunshine starts; a VM's own host always has its tiles, the VM is looked up when you connect.)

### The VM stays on

`omvm remote keepalive NAME` (also run by `-i NAME enable`) turns on libvirt autostart, enables linger so the user manager starts at boot without a login, and installs `omvm-vm@NAME.service` (start the VM if it isn't running, at boot) plus `omvm-vm@NAME.timer`, which re-runs it every minute. Ending a stream only resizes the guest back, it never stops it. To really shut the VM down, first `systemctl --user disable --now omvm-vm@NAME.timer`. Sunshine itself still needs the graphical session (Hyprland), so the hosts appear after the autologin; the LUKS passphrase still has to be typed after a reboot.

The VM can instead show in a window on the laptop's own screen at 120 Hz (`omvm mode local`, see [graphics.md](graphics.md#local-window-omvm-mode-local)). Streaming needs remote mode: in local mode the VM's tiles fail at once with "macos is in local mode … run 'omvm mode remote'", and `omvm mode remote` brings the stream back.

On the phone or tablet:

1. Install **Moonlight**. It must be on the same network as the laptop, or on the same tailnet.
2. Add the host. It often appears by itself. Otherwise tap **+** and enter the laptop's address (LAN IP, or the Tailscale 100.x address from anywhere). For a VM's own host add `ADDRESS:48989`; Moonlight for Android 10.10+, iOS and the desktop apps accept `host:port`.
3. Moonlight shows a PIN. On the laptop, run `omvm remote pin <PIN> <device-name>`; it finds the host that is waiting. You can also do it in the web UI at `https://<ip>:47990` (a VM's host: `:48990`) → **PIN**. The login is in `omvm-webui-login` in that host's config dir.
4. Pick **Desktop**, **macOS NAME** or a device tile. For Desktop and **macOS NAME** the resolution and FPS you choose in Moonlight's settings become the size of the remote monitor, and for **macOS NAME** also the guest's size.
5. When you're done, long-press the app and choose **Quit**. Only quitting removes the remote monitor. A plain disconnect leaves the session running so you can reconnect.

## Clamshell (lid closed)

`start` and `enable` hold a `handle-lid-switch` inhibitor (unit `omvm-remote-lid`). Closing the lid still locks the session the Omarchy way, but the laptop no longer suspends. Connect with Moonlight, then unlock with your password on the lock screen. If the lid is closed when **Desktop** starts, the built-in screen is switched off for that session, and it comes back when you quit. Set `OMVM_STREAM_KEEP_INTERNAL=1` to keep the built-in screen on. `omvm remote stop` releases the inhibitor, so closing the lid suspends again.

The disk is encrypted (LUKS). After a reboot, someone has to type the passphrase at the laptop, so don't reboot it remotely.

## SSH

`omarchy setup security sshd --gh-keys <github-user>` (or `--key="ssh-ed25519 …"`) sets up the server. It installs and enables sshd, authorizes the keys, turns off password logins and rate-limits port 22 in ufw.

## Tested (loopback Moonlight client on the same laptop)

- Desktop at 1280x720@30: REMOTE was created at 1280x720@30, Sunshine captured it, and REMOTE was removed on quit.
- macOS at 1600x1000@30: macOS switched to 1600x1000 and drew the full desktop on REMOTE.
- An earlier version measured 59–60 fps at 1440x1080@60 with 0% drops and 15–22 ms host latency. Sunshine used about 2 cores.
- The macos host from a Mac (Moonlight 6.2, `host:48989`), each device tile at its device's size: macOS switched to 1038x1076pt/2076x2152px, 540x1212pt/1080x2424px, 1512x982pt/3024x1964px and, for the iPhone tile, 589x1278pt/1178x2556px (asked 1179x2556) and 1278x589pt/2556x1178px. Frames were live; quitting put the guest back to its old size.

## Caveats

- With the lid open, REMOTE sits to the right of the laptop screen, and the laptop's cursor can wander onto it. Phone input and local input share one cursor and one keyboard focus.
- Absolute input lands correctly only while the layout starts at 0,0. REMOTE is placed at `auto-right`, or at `0x0` when it is the only monitor.
- `native_pen_touch` is off. Touches arrive as absolute clicks, because Hyprland would bind native touch to one monitor.
- Video is H.264 software encoding only, because Asahi has no hardware encoder. Above about 1440p the frame rate drops.
- To reach it from outside the LAN, use Tailscale. `setup` already opens `100.64.0.0/10`.
- During a stream, Sunshine switches the default audio sink to its own and restores it afterwards.
- A local VNC viewer with remote resize (e.g. `vncviewer localhost:5900` on the laptop) fights the stream over the guest's size. Close it before streaming.
- TigerVNC shrinks its window when the guest already has the screen's size; `session-do` then sets the exact size itself.
- The lock screen on REMOTE when you connect with the lid closed hasn't been tested yet.

## Alternatives considered

- **Sunshine inside the macOS guest.** It needs TCC grants clicked in the GUI and would encode in software on 8 vCPUs. Not chosen.
- **Parsec.** It can't host on Linux, and macOS hosting needs VideoToolbox, which the VM lacks.
- **Plain VNC.** Use an SSH tunnel to QEMU's VNC (`ssh -L 5931:127.0.0.1:5931 laptop`, then a VNC app). It works, but it's laggier.
