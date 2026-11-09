# Work log

A running, dated log of changes to this setup (the omvm repo and the Omarchy
host it runs on). Newest first. Agents: append an entry after each change.

## 2026-11-08

- **Switching keys** (`share/hypr-macos-vm.lua`, installed into
  `~/.config/hypr/bindings.lua`): Ctrl+Alt+M toggles macOS ⇄ Omarchy (from the VM
  to the most recently focused other window, by Hyprland's focus history; from
  anywhere else to the VM's window or VNC viewer, else `omvm show`);
  Ctrl+Alt+1..5 leave the VM for workspace N. Lua bind options
  `dont_inhibit = true` (the old `p` flag: past reims-vgpu's
  keyboard-shortcuts-inhibitor, which SDL takes while input is captured) and
  `submap_universal = true` (past the VNC "macos-vm" submap). Verified with
  ydotool in local mode, uncaptured and captured: Ctrl+Alt+M and Ctrl+Alt+1 left
  the captured window and capture was released. Remote mode not exercised live.
  On this host keyd maps Caps Lock (hold) to Control and turns the physical left
  Control off, so Ctrl here is Caps Lock. wtype input does not trigger Hyprland
  binds; ydotool through keyd does. Never synthesize Ctrl+Alt+F-keys: they
  switch VTs (one test did; `sudo chvt 1` brought the session back).
- **`omvm show [NAME]`** and launcher entry "macOS" (`share/omvm-macos.desktop`,
  copied to `~/.local/share/applications/`): start the VM if it is off, then
  focus reims-vgpu's window (local) or a VNC viewer, opening
  `vncviewer -Shared=1 127.0.0.1:PORT` if none (remote).
- **Guest sound**: virtio-snd moved from `-audiodev none` (output only) to
  `-audiodev pipewire,id=snd0,out.stream-name=macos,in.stream-name=macos` with
  `streams=2`, and `XDG_RUNTIME_DIR` is now kept in both modes so QEMU finds the
  user's PipeWire. `libvirt-domain.py` writes it; `libvirt-mode.py` upgrades older
  definitions on every mode switch (and on its own: `libvirt-mode.py sound`); the
  remote backups in `~/Work/omvm-backups/` were upgraded too (originals:
  `*.pre-sound.xml`). Guest after a restart: "Apple Virtual Sound Device" with
  2 output and 2 input channels. `afplay Ping.aiff` in the guest showed up as a
  running `qemu-system-aarch64` stream (44.1 kHz) into `audio_effect.j314-convolver`
  → `RawSpeakers`; a guest AVAudioEngine capture opened a `qemu-system-aarch64`
  input stream linked from `omarchy_asahi_mic` but read zeros over SSH (TCC
  microphone permission, which a headless SSH process does not have; the first
  GUI app that records will prompt). Both streams close when the guest stops.
- **Host sound** was not broken: speakers (asahi convolver → RawSpeakers,
  speakersafetyd running) verified by playing a 660 Hz tone and finding it in a
  recording from the built-in mic.
- **"Process crashed: mpv"**: Omarchy's screen-recording webcam overlay
  (`omarchy-capture-screenrecording --with-webcam`, mpv on `av://v4l2:/dev/video1`)
  segfaulted every time the overlay closed: FFmpeg's v4l2 input hands out frames
  that point into the camera's mmap buffers, the device unmaps them on close
  while mpv's VO still uploads the last frame (crash in `pl_tex_upload`, on Vulkan
  and on OpenGL alike). Fix in `~/.config/mpv/mpv.conf`: an auto profile for
  `av://v4l2:` paths that appends `vf=lavfi=[copy]`. Reproduced 2/2 before,
  0/2 after.
- **`omvm-gui`** (new, optional): a GTK4 + libadwaita window (`bin/omvm-gui`,
  PyGObject; `sudo pacman -S --needed python-gobject gtk4 libadwaita`) that only
  shells out to `omvm`, `virsh -c qemu:///session`, `systemctl --user`, `hyprctl`,
  `vncviewer` and `lsusb`. Sections: VM state + Start/Stop/Restart (stops the
  `omvm-vm@macos.timer` watchdog first, then `virsh shutdown`, guest
  `sudo shutdown -h now` after ~10 s, like `vm_shutdown`), Open desktop (local:
  focus `class:reims-vgpu`; remote: `vncviewer localhost:59xx`), display mode
  toggle with a confirm dialog (`omvm mode`), resolution (`omvm res`), Moonlight
  hosts :47989/:48989 on the Tailscale IP with paired client names (names only,
  read from `sunshine_state.json`), Pair (`omvm remote [-i macos] pin PIN NAME`),
  USB (`omvm usb attach|detach VID:PID macos`) and shared folders
  (`omvm share add|remove PATH`): both greyed out with "not available yet" until
  `omvm help` lists them. A log pane shows each command and its output (lines
  that look like credentials are hidden). `omvm-gui --install` adds the
  "macOS VM" launcher entry, links `~/.local/bin/omvm-gui`, and saves the shell's
  `OMVM_*` variables to `~/.config/omvm/gui.env` (the launcher doesn't read
  `~/.bashrc`). Installed `usbutils` (this M1 Max lists no USB devices: lsusb
  exits 1). Tested on a temporary headless Hyprland output (VM untouched): state,
  mode, hosts, clients and lsusb render and log; Stop/Restart/mode switch/Open
  were not clicked.
- **`omvm mode local|remote`** (`omvm mode` prints the current one; default VM
  `macos`). local: no libvirt `<graphics>` (QEMU `-display none`), reims-vgpu's
  SDL3/Vulkan window borderless full screen on eDP-1 (`REIMS_VGPU_WINDOW=1`,
  `REIMS_VGPU_WINDOW_REFRESH=120`, resolution `3024x1964@254`), libvirt
  autostart off. remote: the previous XML exactly (VNC + Sunshine), autostart
  on. The mode lives in the libvirt definition (`share/libvirt-mode.py`), so it
  survives reboots. Watchdog `omvm-vm@NAME` now runs `stream-host.sh ensure-vm`
  (local: waits for the Wayland socket); the VM's Moonlight tiles fail in ~25 ms
  in local mode with "macos is in local mode … run 'omvm mode remote'".
  Remote XML backup: `~/Work/omvm-backups/macos-remote-2026-11-08.xml`.
- The window needed Mesa with Wayland WSI: the stack's Mesa is built with
  `-Dplatforms=` ("Installed Vulkan doesn't implement the VK_KHR_wayland_surface
  extension"). Built the same tree (26.2.6 + 3 patches) with
  `-Dplatforms=wayland` into `~/opt/mesa-honeykrisp-sb-wl` (source copy
  `~/src/mesa-honeykrisp-sb-wl`); only local mode uses it.
- Local mode measured: window on eDP-1 at 1512x982 pt x2 = 3024x1964 px; guest
  display timing 120 Hz (ioreg `SyncRate` 7864320 = 120 x 65536; remote is
  60 Hz); `REIMS_VGPU_STATS`: 86-93 guest frames/s = window presents/s at the
  macOS login window (one ~235 ms idle gap a second, 120 Hz pacing otherwise),
  window GPU 1.2-1.3 ms/frame. Remote mode: 54-60 fps in the guest, ~33 fps
  through VNC. Box left in remote mode; tiles and guest SSH verified.
- Commit history: Co-Authored-By/Claude trailers stripped from all omvm commits
  (force-pushed); the old history is on `backup/pre-coauthor-strip-20261108`.
- Mesa upstreaming: branches in `~/src/mesa-upstream-mr` (worktree off
  `~/src/mesa-honeykrisp-sb`, on upstream `main`): `hk-fragment-shader-interlock`
  a3561cde and `agx-16bit-flat-varyings` 2b37de4b. VK-GL-CTS
  `dEQP-VK.fragment_shader_interlock.*` (576 cases): Pass 128, Fail 64,
  NotSupported 384 (without the patch: NotSupported 576). The 64 failures are
  MSAA 4x pixel-interlock cases, still open. Waiting on a
  gitlab.freedesktop.org account (sign in with GitHub) to open the MRs; drafts
  in `docs/upstream-drafts.md`.
- OpenBubbles (iMessage client) runs under muvm + FEX with the Mac's hardware
  info; blocked at iCloud Terms acceptance, which crashes its webview (pending).
- Apple ID sign-in inside the macOS VM: blocked. The guest has no Secure Enclave
  identity on a Linux host, so Apple Account/iCloud sign-in fails.
- Stream performance: Sunshine encodes in software only (libx264, no hardware
  encoder on Asahi). Measured fps by stream size:

  | Stream | fps |
  |---|---|
  | 3840x1080 | 60 |
  | 5120x1440 | ~53 |
  | 7680x2160 | ~24 |

  VNC (QEMU `ui/vnc.c:61`, 30 ms refresh) caps the guest feed at ~33 fps.
- VM always on: linger enabled, libvirt autostart on, `omvm-vm@macos.timer`
  restarts the VM within a minute if it dies (`omvm remote keepalive macos`).
- Sunshine second instance for the VM (`omvm remote -i macos`, base port
  48989, Moonlight host `macos` at 192.168.50.74:48989) with per-device tiles
  (Pixel Fold, Fold cover, iPhone, MacBook 14); clients paired.
- Removed the `sb1` VM.
- Joined Tailscale: the host is `omarchy` at 100.72.93.99.
