# omvm

Run macOS guest VMs under KVM on **Omarchy on Apple Silicon** (M1/M2), headless
over SSH, with Xcode, at near-native CPU speed.

`omvm` is a thin, Omarchy-specific wrapper around
[aquarat/apple-macos-arm64-vm-guest](https://github.com/aquarat/apple-macos-arm64-vm-guest),
which builds on
[steelbrain's original experiment](https://github.com/steelbrain/experiment-macOS-arm64-on-asahi-linux-arm64).
All the hard parts (the KVM patches, the `vmapple` QEMU fork, the boot hand-off)
are their work. omvm makes it repeatable on Omarchy: it builds the side-by-side
patched kernel from Omarchy's own `linux-aurora` recipe, takes care of Limine and
m1n1, and wraps the guest lifecycle in a few commands.

> **Status: experimental.** One person has tested it on one machine: an M1 Max,
> Omarchy M, linux-aurora 7.2.11, with a macOS 26.4 guest and Xcode 27.2. It
> replaces nothing. Your stock kernel stays installed and is one menu entry away.

## What you get

```console
$ omvm run -- 'sw_vers; xcodebuild -version'
ProductName:    macOS
ProductVersion: 26.4
Xcode 27.2
```

- A guest boots to SSH in about 25 s. Every `omvm run` starts from a clean,
  throwaway copy of the image. That's instant on btrfs because it uses reflinks.
- `omvm start NAME` / `omvm ssh NAME` / `omvm stop NAME` give you a longer-lived VM.
  For a libvirt VM (`omvm virt`), `omvm start|stop|restart|pause|resume NAME` power it;
  stop holds off the watchdog until the next start.
- CPU-bound work runs at 95–99% of the host's speed.
- At most **two** macOS guests can run at once. That's Apple's licence limit,
  and the QEMU fork enforces it.

- `omvm gui NAME` boots a guest with the paravirtual GPU, which translates Metal
  to Vulkan on the host's M1/M2 GPU, and serves its screen over **VNC**
  (`vncviewer 127.0.0.1:59xx`). With the upstream reims-vgpu stack built
  ([docs/graphics.md](docs/graphics.md)), the desktop draws without artifacts:
  wallpaper, Dock, icons, menus and System Settings. The first login takes about
  2 minutes while shaders compile. Without that stack, `omvm gui` falls back to
  the older fork, which leaves missing icons and ghost menus. Bake
  `share/70-desktop.sh` into the image first; it turns off display sleep, Setup
  Assistant and crash dialogs.

- `omvm virt NAME` registers a persistent VM in **virt-manager** (libvirt), so you can
  start, stop and view it from a GUI ([docs/virt-manager.md](docs/virt-manager.md)).
- `omvm mode local|remote` switches a virt VM between a window on the laptop screen (120 Hz,
  zero-copy) and VNC + Moonlight streaming (the default); `omvm mode` prints the current one
  ([docs/graphics.md](docs/graphics.md#local-window-omvm-mode-local)).
- `omvm perf always|ac|off` picks when a local-mode VM runs the CPU at the `performance`
  governor, which cuts pointer lag from ~51 to ~20 ms: always (the default), only on AC
  power (switching on plug/unplug), or never; `omvm perf` prints the setting and the
  governor now ([docs/graphics.md](docs/graphics.md#pointer-latency)).
- **Clipboard** (text) is shared both ways with the Wayland host, and the guest's
  **resolution follows the viewer window** (`RESOLUTION=WxH` sets the start size;
  `omvm res NAME 2560x1440` changes it from the shell).
- **Remote control:** `omvm remote start` runs Sunshine, so Moonlight on a phone, tablet
  or computer can drive the Omarchy desktop or any VM on a virtual monitor sized to the
  client, with the lid closed too ([docs/streaming.md](docs/streaming.md)).
- **GUI (optional):** `omvm-gui` is a small GTK4/libadwaita window over the same CLI:
  VM state and power (start, pause/resume, stop, restart, with progress and toasts),
  local/remote mode, CPU performance (`omvm perf`), resolution, Moonlight hosts and pairing, and a log of every command it
  runs. It follows the Omarchy theme and floats like other Omarchy tools. `omvm-gui
  --install` adds "macOS VM" to the app launcher and the Hyprland float rule (needs
  `python-gobject gtk4 libadwaita`; the CLI works without them); `--selftest` checks it.
- **Switching:** `share/hypr-macos-vm.lua` (append it to `~/.config/hypr/bindings.lua`)
  adds keys that work in both modes, even while the VM has the keyboard captured:

  | Keys | What it does |
  |---|---|
  | Ctrl+Alt+M | macOS ⇄ Omarchy: from the VM back to the window you came from; from anywhere else to the VM (`omvm show`: its window, or a VNC viewer in remote mode, starting the VM if it is off) |
  | Ctrl+Alt+1 … 5 | leave the VM for Omarchy workspace 1 … 5 |
  | Ctrl+Alt+Super | (local mode window) release the mouse and keyboard, stay on the VM |
  | Ctrl+Alt+Esc | (VNC viewer) give the keys back to Hyprland, stay on the VM |

  "macOS" in the app launcher (`share/omvm-macos.desktop`, copy it to
  `~/.local/share/applications/`) runs `omvm show` too.
- **Keyboard:** the same file makes Hyprland pass every key, Super = Cmd included, to a
  focused VNC viewer; the local-mode window captures keys itself after a click.
- **Sound:** the guest has a virtio-snd card ("Apple Virtual Sound Device") on the host's
  PipeWire: macOS output plays through the laptop's speakers (a stream named after the VM),
  and its input records from the host's default microphone.
- **Apple Account:** experimental Linux SEP/FairPlay source and lifecycle tooling
  are available in [the helper guide](docs/apple-helpers.md). This is a development
  integration, not a complete installer. Full encrypted-data sync, Contact Key
  Verification and authenticated host-reboot recovery remain under test.
- **macOS apps:** `omac run Foo.app` runs an arm64 application in a dedicated guest;
  see [the application guide](docs/omac.md).

## Requirements

- An Apple Silicon Mac running **Omarchy M** with `linux-aurora` installed.
- **macOS still installed** on the same Mac, used once. Only real macOS can
  create the VM: Apple personalises the restore for each VM, and the VM boot ROM
  ships inside macOS. Plan on ~100 GB of free space in macOS, though the space
  can be freed afterwards.
- About 60 GB of free space in Linux per guest image, plus ~30–60 minutes for
  the kernel build.

## Install

```sh
git clone https://github.com/sapoepsilon/omvm ~/.local/share/omvm-src
ln -s ~/.local/share/omvm-src/bin/omvm ~/.local/bin/omvm
omvm doctor
```

## Setup (once)

```sh
omvm kernel build      # patched linux-aurora-vmapple, built from Omarchy's own PKGBUILD (30-60 min)
omvm kernel install    # installs it beside the stock kernel; pins m1n1 device trees to stock
omvm qemu build        # the vmapple QEMU fork (~10 min)
omvm macos-step        # prints the one-time macOS instructions and stages the script
```

`omvm macos-step` walks you through booting macOS **once**. There, one command
does the rest:

1. It shrinks the macOS container, after showing you the numbers and asking first.
2. It creates a shared exFAT partition, `VMXFER`.
3. It downloads Apple's restore image **from Apple** and restores the VM with
   Apple's Virtualization framework.
4. It copies your *installed* Xcode.app.
5. It reboots back into Omarchy.

Then, on the patched kernel. Pick `linux-aurora-vmapple` in Limine, or run
`omvm kernel default`:

```sh
omvm ingest            # imports the VM from VMXFER (checksummed)
omvm setup --xcode     # account + SSH, headless settings + CLT, Xcode
omvm run -- 'xcodebuild -version'
```

The guest account is `aquarat` (upstream's default). To use another name, set
`OMVM_GUEST_USER` before `omvm setup`, or after renaming the account in macOS,
and save it with `omvm-gui --install` (services read `~/.config/omvm/gui.env`).

## How it works

| Piece | What it is | Where it comes from |
| --- | --- | --- |
| `linux-aurora-vmapple` | Omarchy's kernel plus two small KVM patches (Apple PAC VM keys, and emulating one MMIO store XNU makes) | Built on *your* machine from Omarchy's PKGBUILD; the patches are downloaded from upstream at build time |
| QEMU `vmapple` fork | QEMU's Apple VM machine type, made to work on KVM | `aquarat/qemu-reims-vgpu`, built locally |
| AVPBooter | The VM boot ROM | Copied from **your** macOS install, never distributed |
| Restore image (IPSW) | macOS itself | Downloaded from **Apple's CDN** by the macOS-side script |
| Xcode | Developer tools | Copied from **your** installed Xcode.app |

`omvm` changes three things on the host, and each is reversible:
- it installs the `linux-aurora-vmapple` package (`sudo pacman -R linux-aurora-vmapple`);
- it appends a marked block to `/etc/default/update-m1n1` (a backup is saved as `.pre-omvm`);
- optionally, `omvm kernel default` changes the Limine boot order (undo with `omvm kernel revert`).

Run `omarchy update` from the **stock** kernel. Omarchy's boot check doesn't
know about the second kernel.

## Legal

- **This project contains no Apple software** and never downloads Apple files
  on your behalf from anywhere other than Apple. The boot ROM and Xcode come
  from your own Mac, and the restore image comes from Apple's servers.
- **Apple's macOS licence** allows up to two additional copies of macOS in
  virtual machines on Apple-branded hardware you own or control, for permitted
  purposes. Read the licence for your macOS version. Running the VMs with
  Linux as the host on that same Apple hardware is a setup Apple doesn't
  specifically address, so judge it for yourself. omvm enforces the two-guest
  limit; don't remove that.
- **Xcode** is subject to Apple's Xcode and SDK agreement. Use your own copy.
- **Never share** guest images, `vm.json` (the VM's identity), AVPBooter,
  restore images or Xcode images.
- **omvm** is GPL-2.0-or-later; [LICENSING.md](LICENSING.md) lists the
  patches and third-party code it carries and their licences. The upstream
  code it fetches has its own licences: see upstream's
  [LICENSING.md](https://github.com/aquarat/apple-macos-arm64-vm-guest/blob/master/LICENSING.md).
  In particular, the PAC kernel patch is steelbrain's work and is
  **unlicensed** (a licence was requested in
  [steelbrain#1](https://github.com/steelbrain/experiment-macOS-arm64-on-asahi-linux-arm64/issues/1)).
  That's why omvm downloads it at build time instead of including it, and why
  no prebuilt kernel package is offered.
- Apple's licence (§2K) forbids redistributing its boot ROM and firmware, and
  the Xcode agreement (§2.7) forbids redistributing Xcode. Never publish guest
  disk images.
- "macOS", "Xcode" and "Apple" are trademarks of Apple Inc. This project is
  not affiliated with or endorsed by Apple, Omarchy or 37signals.

## Troubleshooting

- `omvm doctor` shows what's missing.
- **Guest stops early in boot** with `failed to service VMApple PAC HVC`:
  you're not running the patched kernel.
- **macOS restore fails with "restore image does not exist":** the IPSW is a
  symlink. Copy it instead.
- **Logs** for each run are in `<data>/upstream/artifacts/runs/<name>/logs/`.

## Credits

- Anees Iqbal ([steelbrain](https://github.com/steelbrain)): the original
  macOS-on-Asahi KVM bring-up.
- [aquarat](https://github.com/aquarat): the production flow, the QEMU and
  Reims forks, the Tahoe fixes, and the kernel patch rebase.
- Asahi Linux, Aurora Silicon and Omarchy: the platform this runs on.
