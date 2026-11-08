# Artifact-free GPU desktop (upstream reims-vgpu on Honeykrisp)

`omvm gui` uses this stack when it's built. Without it, `omvm gui` falls back to the older out-of-process aquarat Reims fork, and the desktop shows missing icons, ghost menus and no wallpaper.

| Piece | Source | Local patches (`patches/graphics/`) |
|---|---|---|
| QEMU | [steelbrain/qemu-reims-vgpu](https://github.com/steelbrain/qemu-reims-vgpu) `1b41f5f5db` (reims-vgpu's `vendor/qemu` pin) | `qemu/0001`: aquarat's vmapple-on-KVM work, rebased. `qemu/0002`: macOS 26 disk compatibility (keeps the guest's protected files readable) |
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

## Known limits

- The first login takes about 2 minutes while shaders compile, because the pipeline cache starts empty.
- App launches can stall for about 2 seconds.
- 10-bit extended-range (XR10) formats are off. They may work now that interlock exists, but that's untested.
- The resolution is the guest's choice (1440x1080) and doesn't follow the viewer window.
- It has been tested with effects reduced (the `71-reduce-effects` layer) and with the default Tahoe wallpaper. Full Liquid Glass hasn't been tested yet.

## Upstreaming

- `mesa/0003` → Asahi Mesa (Honeykrisp).
- `metal2vulkan/0001` and `reims-vgpu/0001` → steelbrain.
- `qemu/*` → aquarat and steelbrain.

Drafts are in `docs/upstream-drafts.md`.
