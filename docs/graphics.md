# Artifact-free GPU desktop (upstream reims-vgpu on Honeykrisp)

`omvm gui` uses this stack when it's built. Without it, `omvm gui` falls back to the older out-of-process aquarat Reims fork, and the desktop shows missing icons, ghost menus and no wallpaper.

| Piece | Source | Local patches (`patches/graphics/`) |
|---|---|---|
| QEMU | [steelbrain/qemu-reims-vgpu](https://github.com/steelbrain/qemu-reims-vgpu) `1b41f5f5db` (reims-vgpu's `vendor/qemu` pin) | `qemu/0001`: aquarat's vmapple-on-KVM work, rebased. `qemu/0002`: macOS 26 disk compatibility (keeps the guest's protected files readable). `qemu/0003`: the desktop follows the VNC viewer's window size, and `resolution` works headless ("Resolution", below). `qemu/0004`-`0007`: macOS 27 ("macOS 27 updates", below) |
| GPU library | [steelbrain/reims-vgpu](https://github.com/steelbrain/reims-vgpu) `1fe0acb6` | `reims-vgpu/0001`: dma-buf imports instead of host pointers, memfd-backed own allocations, 10-bit extended-range formats off, unsupported pipelines answered as NSErrors. Each change has an environment switch. `reims-vgpu/0002`: a run-time trace gate and tune file, and the window's latency stages ("Pointer latency"). `reims-vgpu/0003`: a dispatch the runtime refuses as unsupported is skipped, not the VM's end |
| Shader translator | [steelbrain/metal2vulkan](https://github.com/steelbrain/metal2vulkan) `219f0136` | `metal2vulkan/0001`: an importer that works without `VK_EXT_external_memory_host`. `metal2vulkan/0002`: a cubic sampler in an argument buffer filters bilinearly instead of refusing the draw (the iOS Simulator needs it; `REIMS_VGPU_CUBIC_ARGUMENT_SAMPLERS_LINEAR=0` refuses again). `metal2vulkan/0003`: logs what a binding view refused for want of `SAMPLED` is. `metal2vulkan/0004`: a 4:2:2 texture over a surface (a ProRes frame) gets a decoded twin its samples read (docs/fcp.md, GAP-1) |
| Vulkan driver | Mesa (Honeykrisp) 26.2.6 (the tested version), plus aquarat's `patches/mesa/0001-0002` | `mesa/0003`: exposes `VK_EXT_fragment_shader_interlock`, which macOS's framebuffer-fetch shaders need |

## Build (about 40 minutes)

The paths match `omvm gui` (`$OMVM_UPSTREAM` is the aquarat harness checkout).

```sh
P=~/Work/omvm/patches/graphics
B=$OMVM_UPSTREAM/build

# 1. Mesa: aquarat's two patches plus the interlock one, into a private prefix.
cp $P/mesa/*.patch $OMVM_UPSTREAM/patches/mesa/
MESA_REF=mesa-26.2.6 MESA_SRC=~/src/mesa-honeykrisp-sb \
  $OMVM_UPSTREAM/scripts/build-mesa-honeykrisp.sh ~/opt/mesa-honeykrisp-sb

# 2. GPU library and shader translator.
git clone https://github.com/steelbrain/reims-vgpu $B/reims-steelbrain/reims
git clone https://github.com/steelbrain/metal2vulkan $B/reims-steelbrain/metal2vulkan
git -C $B/reims-steelbrain/reims checkout 1fe0acb6 && git -C $B/reims-steelbrain/reims am $P/reims-vgpu/*.patch
git -C $B/reims-steelbrain/metal2vulkan checkout 219f0136 && git -C $B/reims-steelbrain/metal2vulkan am $P/metal2vulkan/*.patch
(cd $B/reims-steelbrain/reims && CARGO_TARGET_AARCH64_UNKNOWN_LINUX_GNU_RUSTFLAGS="-C target-cpu=native" cargo xtask dist)

# 3. QEMU on the library.
git clone https://github.com/steelbrain/qemu-reims-vgpu $B/qemu-sb/src
git -C $B/qemu-sb/src checkout 1b41f5f5db && git -C $B/qemu-sb/src am $P/qemu/*.patch
mkdir -p $B/qemu-sb/build && cd $B/qemu-sb/build
PKG_CONFIG_PATH=$B/reims-steelbrain/reims/target/dist-vulkan/lib/pkgconfig ../src/configure \
  --target-list=aarch64-softmmu --enable-kvm --enable-pvg --enable-gnutls --enable-vnc \
  --disable-docs --disable-werror
ninja

# 4. Host: let udmabuf map a whole guest (needs root; persists across reboots).
printf 'w /sys/module/udmabuf/parameters/list_limit - - - - 262144\nw /sys/module/udmabuf/parameters/size_limit_mb - - - - 4096\n' |
  sudo tee /etc/tmpfiles.d/omvm-udmabuf.conf && sudo systemd-tmpfiles --create /etc/tmpfiles.d/omvm-udmabuf.conf
```

Then run `omvm gui NAME`. Set `OMVM_GFX_STACK=oop` to force the old stack.

## Resolution

The guest desktop follows the VNC viewer's window. Resize a TigerVNC `vncviewer` window (remote resize is on by default), and after about half a second macOS switches to that size at 1x. Any client that sends RFB `SetDesktopSize` works the same way; QEMU's GTK display does too.

Pick the starting size with `RESOLUTION`:

```sh
RESOLUTION=2560x1440 omvm gui NAME     # passes -global apple-gfx-mmio.resolution=2560x1440
```

Without `RESOLUTION` the desktop starts at 1920x1080. `WxH@PPI` sets the density the guest is told, which decides HiDPI. Above about 146.67 ppi the guest runs HiDPI ("A chosen density's boundary" in reims-vgpu's `docs/qemu.md`). A density at which the guest's scale isn't known fails at start.

How it works:

- **QEMU (`qemu/0003`).** A headless `apple-gfx` display answers QEMU's `ui_info`, which is how VNC's `SetDesktopSize` and GTK window resizes arrive. After the requests settle for 500 ms, it offers the asked size, rounded to even pixels and clamped to 640x480–7680x4320, as the display's only mode. It offers that one mode alone because, given a list, macOS runs the mode closest to the display's proportions, not the first one. The display is told it is as wide as 3840x2160 at 110 ppi, so every size up to about 5000 pixels wide runs at 1x. Turn it off with `-global apple-gfx-mmio.follow-ui-size=off`; the guest then gets the resolution plus the standard modes that fit inside it.
- **Guest agent (`share/omvm-display-follow.swift`).** When the size shrinks, macOS always switches. When it grows, macOS usually switches too, but sometimes keeps its current mode, because that mode is still one it can derive from the new one. It can also go back to the mode saved in `com.apple.windowserver.displays`. `omvm gui` installs a LaunchAgent over SSH that sets the new native mode whenever the offered mode changes. The agent is built in the guest with `swiftc`, so the guest needs Command Line Tools. Set `OMVM_DISPLAY_FOLLOW=0` to skip it. The first time it runs, macOS shows an "App Background Activity" notice. Its log is `/tmp/omvm-display-follow.log` in the guest. The host side logs to `artifacts/runs/NAME/logs/display-follow.log`.
- **Displays settings.** Because the display offers a single mode, System Settings lists only that size, along with the scaled sizes macOS derives from it.

Tested on 26.4 over VNC. The VM started at 1728x1117 and was then resized to 1280x800, 3008x1692, 1728x1117, 2560x1600, 1920x1200, 2560x1440, 1440x900 and 2304x1296. Each size ran at 1x with the full desktop.

## Local window (`omvm mode local`)

A `virt` VM shows its screen one of two ways, switched with `omvm mode`:

```sh
omvm mode                 # prints local or remote (default VM: macos; or omvm mode NAME)
omvm mode local [NAME]    # reims-vgpu's own window on the laptop screen
omvm mode remote [NAME]   # back to VNC + Sunshine (the default)
```

| | remote (default) | local |
|---|---|---|
| libvirt display | `<graphics type='vnc'>` on 127.0.0.1 | none, so QEMU runs `-display none` |
| reims-vgpu | headless (`REIMS_VGPU_WINDOW=0`) | SDL3/Vulkan window (`REIMS_VGPU_WINDOW=1`), borderless full screen, zero-copy |
| Guest mode | follows the VNC viewer, 60 Hz | `resolution` = the panel at its density (`3024x1964@254`, HiDPI) at the panel's rate (`REIMS_VGPU_WINDOW_REFRESH=120`) |
| Frame rate | VNC caps at ~33 fps (QEMU `ui/vnc.c` refreshes every 30 ms) | the guest's own rate, up to 120 |
| Moonlight | the VM's host and tiles work | tiles fail at once: "macos is in local mode" |
| Boot | libvirt autostart + `omvm-vm@NAME.timer` | autostart off; the timer starts it once the Wayland session exists (in a scope of its own, `omvm-virtqemud-PID.scope`, so the oneshot's end does not take QEMU with it) |

A switch backs up the domain (`$OMVM_IMAGES/vms/NAME/domain-<mode>-<time>.xml`), stops the
watchdog timer, shuts the guest down cleanly (`virsh shutdown`, then `sudo shutdown -h now`
over SSH after 10 s, gives up after 4 minutes), rewrites the domain with
`share/libvirt-mode.py` and starts it again. The mode is the libvirt definition itself, so it
survives reboots. `local -> remote` gives back the exact XML `omvm virt` wrote. A reboot of
the guest logs its user out, so log in again (VNC/Moonlight or the window).

Closing the window powers the guest off. The watchdog starts it again within a minute; to keep
it off, `systemctl --user stop omvm-vm@NAME.timer` first.

Knobs: `OMVM_LOCAL_RESOLUTION` (default: the built-in panel from `hyprctl`),
`OMVM_LOCAL_REFRESH`, `OMVM_LOCAL_ICD`, `OMVM_STATS=1` (reims-vgpu writes guest and window
frames per second once a second to `~/.cache/libvirt/qemu/log/NAME.log`). `omvm gui` takes
`OMVM_MODE=local` for a throwaway run in a window.

**The window needs Mesa with Wayland WSI.** The stack's Mesa above is built with
`-Dplatforms=`, and SDL then refuses the window ("Installed Vulkan doesn't implement the
VK_KHR_wayland_surface extension"). Local mode uses a second build of the same tree (26.2.6 +
the three patches) with `-Dplatforms=wayland`, in `~/opt/mesa-honeykrisp-sb-wl`; remote mode
keeps the original ICD:

```sh
rsync -a --exclude /build ~/src/mesa-honeykrisp-sb/ ~/src/mesa-honeykrisp-sb-wl/
cd ~/src/mesa-honeykrisp-sb-wl
meson setup build --prefix=$HOME/opt/mesa-honeykrisp-sb-wl --buildtype=release -Db_ndebug=true \
  -Dvulkan-drivers=asahi -Dgallium-drivers= -Dplatforms=wayland -Dglx=disabled -Degl=disabled \
  -Dgbm=disabled -Dopengl=false -Dgles1=disabled -Dgles2=disabled -Dllvm=enabled -Dvideo-codecs= -Dtools=
ninja -C build install     # about 5 minutes on an M1 Max
```

Measured 2026-11-08 (M1 Max, 3024x1964 panel at 120 Hz, guest at the login window,
`OMVM_STATS=1`): the window opened borderless full screen on eDP-1 (1512x982 points at 2x =
3024x1964 pixels); the guest's display timing reads 120 Hz (`ioreg`: `VerticalAttributes`
`SyncRate` = 7864320 = 120 x 65536; remote mode is 60 Hz); reims-vgpu counted 86-93 guest
frames/s and the same number of window presents/s, window GPU time 1.2-1.3 ms, with one
~235 ms idle gap per second, i.e. 120 Hz pacing whenever the guest draws. Remote mode, same
guest, measured 54-60 fps in the guest (display link) and ~33 fps through VNC.

Measured 2026-11-09 on macOS 27.2 (`qemu-sb-bdifw`): 99-116 guest frames/s, window GPU
1.2-1.5 ms, with no other VM running. With `macos27` running headless beside it the window
fell to 12-26 frames/s (window GPU 16-47 ms): both guests share the one GPU queue, so stop
the other VM (`omvm stop NAME`) for a smooth local desktop. Local mode also sets
`REIMS_VGPU_MAX_REFRESH_HZ` to the panel's rate (remote: 60); the steelbrain reims these
builds link ignores it, but qemu-fleet's reims caps the guest's modes with it.

### Pointer latency

The `omvm` libvirt hook switches every CPU cluster to the `performance` governor while a
local-mode VM runs and restores the previous governors when the last one stops (needs
passwordless sudo). `omvm perf` sets when, kept in `~/.config/omvm/perf`:

```sh
omvm perf          # the setting, then the governor, power source and local VMs now
omvm perf always   # performance while a local VM runs, on AC and battery (default)
omvm perf ac       # only on AC power: back to the saved governor on battery
omvm perf off      # never touch the governor
```

`ac` installs `/etc/udev/rules.d/90-omvm-power.rules`: a change of the Mains supply
(`macsmc-ac`) starts the user unit `omvm-power.service`, which runs `omvm perf apply`; no
polling. `OMVM_LOCAL_GOVERNOR` overrides the file (`keep` = off, a governor name = always with
that governor). The GUI has the same switch (Display, "CPU performance"). With `schedutil` a pointer
move took 51 ms to show in the guest's image (10 ms to reach the guest); with `performance`
20 ms (1.4 ms). The cursor itself is the host's: SDL's colour cursor with the guest's glyph,
drawn by Hyprland, 13 ms (26 ms with schedutil). Measured 2026-11-09 with a uinput mouse,
a guest window that flips colour on the mouse-moved event and `grim` polling a pixel
(docs/log.md).

**Where the ~20 ms goes** (2026-11-09, `macos` on 27.2, 120 Hz, window full screen; medians,
`share/latency/lat.py --no-pixel --trace` for the guest and reims stages, `floor2.py` for the
compositor):

| Stage | Time | Notes |
|---|---|---|
| uinput move -> the guest's NSEvent | 1.3-1.6 ms | Hyprland, SDL, QEMU's tablet, xHCI |
| NSEvent -> the guest presents its frame | 5.5 ms (p90 ~14) | WindowServer waits for its own 120 Hz tick, ~2 ms of GPU for the frame, ~1 ms in the guest between the GPU's completion and the present; a missed tick adds 8.3 ms |
| guest present -> `vkQueuePresentKHR` | 0.4-0.5 ms | reims-vgpu: new-frame signal, render thread, image, encode |
| the window's copy on the GPU | ~0.9 ms | 3024x1964, before Hyprland can latch the buffer |
| Hyprland + DCP: commit -> scanout | 11-13 ms (min 10.9, spikes to 30+) | a plain shm client measures the same: one composite frame plus one flip |

So reims-vgpu's own share is ~1.4 ms; the rest is the guest's compositor and Hyprland/DCP,
each paced by its own 120 Hz clock. Tried and not kept: a 240 Hz guest mode
(`REIMS_VGPU_WINDOW_REFRESH=240`: NSEvent -> present got slower, 7.8-8.5 ms); `IMMEDIATE`
present mode with tearing (Hyprland refuses tearing at scale 2: "Tearing commit requested but
scale factor is not 1"); direct scanout (blocked by the bar/dock/notification layers and the
software cursor); Hyprland's `render:new_render_scheduling` (no change), `render:async_commit`
(commit -> scanout ~21 ms), `render:cm_enabled`/`use_fp16` (no change); disabling the CPUs' deep
idle state (no change). Per-command GPU round trip from the guest is not the problem:
`share/latency/metalbench.swift` measures 0.25 ms for a one-threadgroup compute or a small
render pass (commit to `waitUntilCompleted`), 0.05 ms per 1080p render pass pipelined,
~320 GB/s copies and ~1.2 TFLOP/s FMA, and 2.8 ms for the first use of a new pipeline.

**Tools** (`share/latency/`, `build.sh` builds the host helpers into `~/.cache/omvm-latency`):

- `lat.py [N] [label] [--trace FILE] [--no-pixel]`: a uinput mouse crosses the window;
  the guest's `latprobe` (`latprobe.swift`, built in the guest as `~/bin/latprobe`) flips its
  full-screen window on the mouse-moved event; `pixpoll` (one persistent wlr-screencopy
  client) reports the first composited frame with the new colour. Continuous screencopy keeps
  Hyprland near 100 % CPU and delays input and composition itself (guest-event latency went
  from 1.4 to 8-10 ms under it on a busy afternoon), so take stage timings with `--no-pixel`.
- reims-vgpu's trace (`reims-vgpu/0002`): local mode sets `REIMS_VGPU_TRACE`,
  `REIMS_VGPU_TRACE_GATE` and `REIMS_VGPU_TUNE` (under `~/.cache/reims-vgpu`); events are
  written only while `trace.on` exists (`touch` it, run, `rm` it), with the window's stages
  (`wnew`, `wdraw`, `wacq`, `wsched`, `wpres`) beside the guest's (`cmd`, `cbdone`,
  `present`). `lat.py --trace` lines them up per move.
- `tune`: `present_mode=mailbox|fifo|immediate` switches the window's swapchain at run time.
- `floor2.py`: a full-screen shm window's commit -> `wp_presentation` time, Hyprland's floor
  (it takes full screen from the Reims window; `fs.sh` gives it back).
- `metalbench.swift` (guest): per-command round trips, pipelined rate, bandwidth, FLOPs and
  new-pipeline costs on the guest's Metal device.

Keep the Reims window full screen when measuring: another full-screen window on the workspace
(the floor test's) takes it away, and a windowed Reims window is scaled and composited with
the bar, which adds several milliseconds.

The guest's display agent (`share/omvm-display-follow.swift`) puts each new size in the mode
macOS marks default: local mode's `3024x1964@254` runs 1512x982 points at 2x. A scaling picked
in System Settings stays across reboots until the host offers another size.

## macOS 27 updates

A macOS 26 guest can take the macOS 27 OTA (tested: 26.4 25E246 to 27.2.1 26B131 on `macos27`) with these QEMU changes and the 27-era AVPBooter:

- **`qemu/0005`, backdoor disk writes.** macOS 27.2's iBoot writes to the aux disk through the vmapple backdoor (a boot counter in the `virt_pmu_sram` record at aux 0x1000000, and the NVRAM banks at 0xa00000/0xa80000). QEMU used to drop those writes; 27.2's first-stage iBoot then panics in a reset loop on the upgrade boot (`iBoot Panic: 64383f188f1c630:234`).
- **`qemu/0006`, `ascending-capabilities`.** macOS 27's virtio transport loops forever on QEMU's descending PCI capability list, so a 27 kernel (the update ramdisk first) never starts the disk: empty progress bar, no disk I/O. `qemu/0004`'s `apple-vendor-cap=on` fixes that too, but it also says "transport encryption disabled", which makes the image's data-protected files unreadable (ssh keys and logins fail on the 26.4 fallback boot). `ascending-capabilities=on` reorders only.
- **`qemu/0007`, sound.** The same capability-order switch for `virtio-sound-pci` (`x-ascending-capabilities`, default off); the reordering is now one helper, `virtio_pci_link_capabilities_ascending()`, which virtio-net uses too. With it a 27 guest shows "Apple Virtual Sound Device" (2 in, 2 out) and plays through PipeWire like the 26 VM.
- **Firmware.** `artifacts/firmware/AVPBooter.vmapple2.macos27.2-26B123.bin` (mBoot-20457.41.3, from Virtualization.framework on a macOS 27.2 host). The 26-era AVPBooter hangs on the upgrade reboot.

`omvm virt NAME` emits all of it when the VM has a `guest_major` file holding 27 or more (`echo 27 > ~/vm-artifacts/vms/NAME/guest_major`, then `omvm virt NAME` again; set it before updating a 26 guest): the patched QEMU (`build/qemu-sb-bdifw/build/qemu-system-aarch64`, or `OMVM_QEMU27`), the 27-era AVPBooter (or `OMVM_AVPBOOTER27`) and these device switches:

```
-device vmapple-virtio-blk-pci,variant=aux,drive=aux,share-rw=on,ascending-capabilities=on
-device vmapple-virtio-blk-pci,variant=root,drive=root,share-rw=on,ascending-capabilities=on
-device virtio-net-pci,...,x-ascending-capabilities=on
-device virtio-sound-pci,audiodev=snd0,streams=2,x-ascending-capabilities=on
```

Other VMs keep `build/qemu-sb` and the 26-era AVPBooter. The patched QEMU is a second build so `macos` keeps its binary: a reflink copy of `build/qemu-sb`, `git am` `qemu/0005`-`0007` onto its `src`, then `ninja` in its `build` with no target (`ninja qemu-system-aarch64` alone skips `pc-bios/keymaps`, and QEMU then refuses to start: "could not find keymap file for language 'en-us'").

Login window keyboard: on the first boot after the 27.2.1 OTA, typed keys (VNC and HMP `sendkey`) did not reach the login window, while the mouse did; that login window also had no input menu ("ABC") and SecurityAgent logged "No selected input source for user". It did not happen again on any later boot or logout (VNC typing and `sendkey` both log in), so it looks like a first-boot-after-update state (the input-source cache `com.apple.IntlDataCache.le` is rebuilt on that boot). The guest now also has a system-wide input source (`/Library/Preferences/com.apple.HIToolbox.plist`, ABC enabled and selected; it had none). If it happens again, set autologin over ssh (`/etc/kcpassword` plus `autoLoginUser`) and reboot.

A 26 guest that takes the 27 OTA *without* `guest_major` (System Settings offers it as recommended, and nothing stops a click on it) reboots into the upgrade under `build/qemu-sb` and the 26-era AVPBooter; first-stage iBoot then panics and resets about twice a second forever. Signs: the Reims window (or VNC) stays black, the vCPU PC sits at `0x100000` and iBoot addresses, QMP events are `GUEST_CRASHLOADED`/`RESET` pairs, virtqemud logs `Duplicate block info` every second, and the guest's ssh never answers. A cold restart loops too, because the aux NVRAM holds `boot-command=upgrade` (`strings aux.img.trimmed | grep -E 'boot-command|ota-os-version'`). Fix: `echo 27 > ~/vm-artifacts/vms/NAME/guest_major`, `omvm virt NAME` (it keeps local or remote mode), then `virsh destroy NAME` and `virsh start NAME`. The upgrade finishes in about 2 minutes, followed by post-upgrade migration behind the Apple logo.

Update from the guest: `softwareupdate -d "macOS 27.2.1-26B131"`, then `echo PASSWORD | sudo softwareupdate -i "macOS 27.2.1-26B131" --agree-to-license --user USER --stdinpass -R`. The guest reboots twice (first stage, then the update iBEC and its ramdisk) and comes back on 27.2.1 in about 5 minutes. Don't power the VM off while the update ramdisk runs: iBoot counts that as a failed attempt and falls back to 26.

## Guest Metal feature set (why there is no Metal 3)

A macOS guest on this stack reports `Apple Paravirtual device` with `MTLGPUFamilyApple1`-`Apple5`,
`Mac2` and `Common1`-`3`, and no `Apple6`+, `Metal3` or `Metal4`. That is the guest driver's
choice, not something the host withholds, and it is what Apple's own hosts give a VM.

- **What the host tells the guest.** reims-vgpu answers the guest's device-info request
  (`crates/reims-vgpu-core/src/guest/abi/device_info.rs`) with the families of an M3 Max:
  key 37 (the highest family) is 1009, `Apple9`, and key 44 (the family mask) is 0x1f,
  `Apple5`-`Apple9` (`crates/reims-vgpu-vulkan/src/gpu/caps.rs`, `stand_in::FAMILIES`). The
  protocol has no key for Metal 3, ray tracing, mesh shaders, sparse textures or MetalFX.
- **What the guest holds.** `share/bench/pvinfo.m` (guest `~/bin/pvinfo`) reads the driver's
  own copy (`AppleParavirtDevice._deviceInfo`): `HostGPUFamilyClamped = 1009`,
  `HostGPUFamilies = 0x1f`, `MaxMetalShaderVersion = 0x20007`. With those in hand the driver
  still answers `featureProfile = 6`, `supportsFamily(Apple6...) = NO`, `supportsRaytracing`,
  `supportsMeshShaders`, `supportsSparseTextures`, `supportsFunctionPointers`,
  `supportsDynamicLibraries` = NO and `requiresMeshShaderEmulation`,
  `requiresRaytracingEmulation` = YES (macOS 27.2, 26B123).
- **Apple's own hosts do the same.** On Virtualization.framework guests the device reports
  `MTLGPUFamilyApple5 (1005)` while the host beside it reports `Apple9` and `Metal3`: Tart
  issue 1032 (a macOS 15.6 host with Sequoia and Sonoma guests: "`MTLGPUFamilyMetal3` is not
  exposed in the Guest"; a maintainer adds that a Tahoe guest on a Tahoe host is level 5 too),
  Godot issue 124859 (a 26.3 guest: "Apple1–5 and Mac2 families, no Metal3"), riff issue 76
  (GitHub's `macos-14` runners). No report of a guest above Apple5 was found; no Apple host
  was at hand to measure (the `kentra` VM was off).
- **Probed in the guest** (`share/bench/metalcaps.swift`, guest `~/bin/metalcaps`): a mesh
  render pipeline fails to compile (the compiler service ends), a sparse heap asserts in the
  driver (`IOGPUMetalHeap`), ray tracing is off; argument buffers tier 2, BC textures, 32-bit
  float filtering and MSAA, barycentrics, pull-model interpolation, rasterization-rate maps,
  vertex amplification 2 and `MTLIOCommandQueue` are there.

So there is nothing to advertise: the host already offers Apple9, and a guest-side shim that
overrides `supportsFamily:` per process (what cua's "GPU passthrough" does) would promise
features the paravirtual protocol cannot carry.

## The M2 scaler (`apple-m2scaler-pci`) cannot attach in a 27.2 guest

QEMU's `apple-m2scaler-pci` (106b:1a0b) is the device a guest's `AppleM2ScalerParavirtDriver`
drives for VideoToolbox's pixel transfers. In the `macos` guest (27.2, 26B123) nothing ever
binds it, because the guest's kernel has no such driver:

- `/System/Library/Extensions/AppleM2ScalerParavirtDriver.kext` is a codeless bundle (an
  `Info.plist` with the two personalities, `IOPCIPrimaryMatch 0x1a0b106b`, no executable).
- The boot kernel collection (`.../com.apple.kernelcaches/kernelcache`, LZFSE-decoded) holds no
  `AppleM2ScalerParavirtDriver` string and no `0x1a0b106b` match; `kmutil inspect` lists
  `AppleM2ScalerCSCDriver` (the hardware scaler's) and `AppleVideoToolboxParavirtualization`
  (106b:1a03), not the paravirtual scaler. `ioclasscount AppleM2ScalerParavirtDriver`:
  "no such class". `kmutil load` of the bundle: "Bad code signature".
- So the personalities are not in the kernel's catalogue, no `AppleVirtIOPCITransport` is
  made for the PCI function, and the `status=0x0` writes QEMU traced were its own resets at
  start.

A kernel collection is sealed and signed by Apple, and there is no binary to put in an
auxiliary one, so this is out of reach from the host. `OMVM_M2SCALER=1` stays as the opt-in
for a guest whose kernel has the driver. VideoToolbox's fallback, the Metal compute kernel,
works since `metal2vulkan/0004` (docs/fcp.md, GAP-1).

## Known limits

- The very first login (cold pipeline cache, e.g. after a new Mesa or library build) takes about 2 minutes while shaders compile. Later boots use the cache: the desktop is complete about 30 s after login.
- App launches can stall for about 2 seconds.
- 10-bit extended-range (XR10) formats are off. They may work now that interlock exists, but that's untested.
- Sizes wider than about 5000 pixels may run HiDPI, because the guest's scale for them wasn't measured.
- It has been tested with effects reduced (the `71-reduce-effects` layer) and with the default Tahoe wallpaper. Full Liquid Glass hasn't been tested yet.

## Upstreaming

- `mesa/0003` → Asahi Mesa (Honeykrisp).
- `metal2vulkan/0001` and `reims-vgpu/0001` → steelbrain.
- `qemu/*` → aquarat and steelbrain.

Drafts are in `docs/upstream-drafts.md`.
