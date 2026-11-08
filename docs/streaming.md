# Remote control from a phone, tablet or another computer (Moonlight + Sunshine)

Sunshine runs on the Linux host, and nothing gets installed in macOS. One Sunshine serves two kinds of Moonlight app:

- **Desktop**: the Omarchy desktop itself.
- **macOS NAME**: one app for each running VM.

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
```

(`omvm remote` is `share/stream-host.sh`. The list of macOS apps is rebuilt from the running VMs each time Sunshine starts. Run `omvm remote start` again after you start a VM.)

On the phone or tablet:

1. Install **Moonlight**. It must be on the same network as the laptop, or on the same tailnet.
2. Add the host. It often appears by itself. Otherwise tap **+** and enter the laptop's IP address, which `start` prints.
3. Moonlight shows a PIN. On the laptop, run `omvm remote pin <PIN> <device-name>`. You can also do it in the web UI at `https://<ip>:47990` → **PIN**. The login is in `~/.config/sunshine/omvm-webui-login`.
4. Pick **Desktop** or **macOS NAME**. The resolution and FPS you choose in Moonlight's settings become the size of the remote monitor. For a macOS app, they also become the guest's size.
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

## Caveats

- With the lid open, REMOTE sits to the right of the laptop screen, and the laptop's cursor can wander onto it. Phone input and local input share one cursor and one keyboard focus.
- Absolute input lands correctly only while the layout starts at 0,0. REMOTE is placed at `auto-right`, or at `0x0` when it is the only monitor.
- `native_pen_touch` is off. Touches arrive as absolute clicks, because Hyprland would bind native touch to one monitor.
- Video is H.264 software encoding only, because Asahi has no hardware encoder. Above about 1440p the frame rate drops.
- To reach it from outside the LAN, use Tailscale. `setup` already opens `100.64.0.0/10`.
- During a stream, Sunshine switches the default audio sink to its own and restores it afterwards.
- The lock screen on REMOTE when you connect with the lid closed hasn't been tested yet.

## Alternatives considered

- **Sunshine inside the macOS guest.** It needs TCC grants clicked in the GUI and would encode in software on 8 vCPUs. Not chosen.
- **Parsec.** It can't host on Linux, and macOS hosting needs VideoToolbox, which the VM lacks.
- **Plain VNC.** Use an SSH tunnel to QEMU's VNC (`ssh -L 5931:127.0.0.1:5931 laptop`, then a VNC app). It works, but it's laggier.
