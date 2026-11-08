# Artifact-free GPU desktop (upstream reims-vgpu on Honeykrisp)

`omvm gui` uses this stack when it's built. Without it, `omvm gui` falls back to the older out-of-process aquarat Reims fork, and the desktop shows missing icons, ghost menus and no wallpaper.

| Piece | Source | Local patches (`patches/graphics/`) |
|---|---|---|
| QEMU | [steelbrain/qemu-reims-vgpu](https://github.com/steelbrain/qemu-reims-vgpu) `1b41f5f5db` (reims-vgpu's `vendor/qemu` pin) | `qemu/0001`: aquarat's vmapple-on-KVM work, rebased. `qemu/0002`: macOS 26 disk compatibility (keeps the guest's protected files readable). `qemu/0003`: the desktop follows the VNC viewer's window size, and `resolution` works headless ("Resolution", below) |
| GPU library | [steelbrain/reims-vgpu](https://github.com/steelbrain/reims-vgpu) `1fe0acb6` | `reims-vgpu/0001`: dma-buf imports instead of host pointers, memfd-backed own allocations, 10-bit extended-range formats off, unsupported pipelines answered as NSErrors. Each change has an environment switch |
| Shader translator | [steelbrain/metal2vulkan](https://github.com/steelbrain/metal2vulkan) `219f0136` | `metal2vulkan/0001`: an importer that works without `VK_EXT_external_memory_host` |
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
