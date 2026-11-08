# Drafts for proposing omvm to Omarchy

Omarchy's own guidelines decide where each piece goes (research of 2026-11-07):

- **omacom/omarchy** (core): feature ideas go to *Discussions › Suggestions*.
  GitHub issues are for verified bugs only, and PRs target `quattro`, one
  problem per PR, with verification evidence.
- **omacom/omarchy-mac-pkgs**: a new Mac-only package needs an issue first,
  then a PR against `main`.
- **omacom/omarchy-pkgs**: one package per PR, from `master`, with every source
  pinned.
- **Blocker for packaging the kernel:** the PAC VM-key patch is steelbrain's
  work and has no licence (all rights reserved). See
  [steelbrain#1](https://github.com/steelbrain/experiment-macOS-arm64-on-asahi-linux-arm64/issues/1),
  still open. Until he licenses it, no Omarchy package can ship it. omvm gets
  around this by downloading the patch on the user's machine at build time.

So the plan is: (1) publish omvm as a standalone repo and an AUR package,
(2) open a Discussion in omarchy, (3) open a proposal issue in
omarchy-mac-pkgs. A kernel PR waits until the patch licence is resolved.

---

## 1. omacom/omarchy: Discussion › Suggestions

**Title:** macOS guest VMs under KVM on Omarchy M (Apple Silicon): working, looking for the right home

> I have headless macOS 26.4 guests (with Xcode 27.2) booting under KVM on an
> M1 Max running Omarchy M. It's a port of aquarat/apple-macos-arm64-vm-guest
> (Fedora Asahi) to Omarchy, packaged as a small CLI, **omvm**:
> `<repo link>`.
>
> **What it takes on the host**
> - A side-by-side `linux-aurora-vmapple` kernel: linux-aurora plus two small
>   KVM patches, built from Omarchy's own PKGBUILD. Stock linux-aurora stays
>   the default Limine entry unless the user changes it.
> - The vmapple QEMU fork.
> - A one-time step in macOS. Apple's Virtualization framework restores the
>   VM, and the boot ROM is copied from the user's own macOS install. No Apple
>   files are redistributed.
>
> **Results**
> - The guest reaches SSH in about 25 s.
> - CPU-bound work runs at 95–99% of host speed.
> - The two-guest limit is enforced, per Apple's licence.
>
> **Questions for maintainers**
> 1. Is there interest in KVM support for macOS guests in `linux-aurora` itself?
>    The NISV MMIO-emulation patch is GPL-2.0. The PAC VM-key patch is waiting
>    on a licence from its author.
> 2. Would an `omarchy-mac-pkgs` package for the QEMU fork be welcome, or
>    should this stay third-party (AUR)?
> 3. Omarchy's boot check assumes exactly one Apple kernel, so a second kernel
>    trips `omarchy update`. Would a supported "extra kernel" pattern make sense?
>
> Tested on: MacBookPro18,4 (M1 Max), linux-aurora 7.2.11.aurora14/15,
> macOS host 26.6.2, AVPBooter mBoot-18000.161.10.

## 2. omacom/omarchy-mac-pkgs: issue (proposal before a PR)

**Title:** Proposal: package the vmapple QEMU fork for macOS guest VMs

> **What:** `qemu-vmapple`, the aquarat/qemu-reims-vgpu fork (GPL-2.0-or-later)
> pinned to a commit, building `qemu-system-aarch64` with the `vmapple` machine
> and KVM. It installs into its own prefix, so it doesn't conflict with Arch's
> qemu.
>
> **Why:** it's the userspace half of running macOS guests on Omarchy M. The
> tested flow, the results and the legal notes (no Apple files are shipped)
> are in `<repo link>`.
>
> **Not included:** the kernel side, which needs a patch whose licence is
> pending (steelbrain#1).
>
> Happy to open the PR against `main` if this fits the repo's scope.

## 3. Graphics fixes upstream (send these first)

### 3a. Mesa (Asahi/Honeykrisp): merge request
**Title:** hk: expose VK_EXT_fragment_shader_interlock (pixel interlock)

> The AGX compiler already lowers `begin_invocation_interlock` to `wait_pix`.
> Gallium uses this to order spilled render-target image load/store. This MR
> exposes `fragmentShaderPixelInterlock` in Honeykrisp and makes
> `end_invocation_interlock` a no-op, since the pixel is released when the
> fragment ends.
>
> Use case: reims-vgpu translates macOS guests' Metal framebuffer-fetch
> shaders to Vulkan. That needs either pixel interlock or
> rasterization-order attachment access. With this patch, a macOS 26 desktop
> renders correctly on an M1 Max under KVM.
>
> Patch: `patches/graphics/mesa/0003-hk-fragment-shader-interlock.patch`.
> CTS: TODO, run `dEQP-VK.fragment_shader_interlock.*` before submitting.

### 3b. steelbrain/metal2vulkan: issue + PR
**Title:** Importer without VK_EXT_external_memory_host (dma-buf route, Honeykrisp)

> Honeykrisp has no host-pointer import, but it does have
> `EXT_external_memory_dma_buf` and image DRM format modifiers. With this
> change, the Importer exists when the dma-buf route is available. Pointer
> imports are refused, and no-copy objects go through udmabuf dma-bufs
> supplied by reims-vgpu.
>
> Patch: `patches/graphics/metal2vulkan/0001-*.patch`.

### 3c. steelbrain/reims-vgpu: issue + PR
**Title:** Asahi Linux host (Honeykrisp): dma-buf imports, memfd-backed allocations, XR10 opt-in

> On an arm64 Linux KVM host with Honeykrisp, a macOS 26 vmapple guest
> renders cleanly with four switchable changes:
> - dma-buf imports instead of host pointers;
> - memfd-backed `allocate_anywhere` and `allocate_fixed_overwrite`;
> - extended XR10 formats off unless `REIMS_VGPU_EXTENDED_XR10=1`;
> - unsupported pipeline states returned as an NSError.
>
> Also: the library needs `-C target-cpu=native` (LSE atomics) for
> `aarch64-unknown-linux-gnu`.
>
> Patch: `patches/graphics/reims-vgpu/0001-*.patch`. Screenshots: <link>.

### 3d. aquarat/qemu-reims-vgpu + steelbrain/qemu-reims-vgpu
> Our port of aquarat's vmapple-on-KVM work onto steelbrain's current pin
> (`patches/graphics/qemu/0001`).
>
> Finding: steelbrain's macOS 27 virtio-blk vendor capability (d235e51310)
> makes a macOS 26 image's data-protected files unreadable under KVM, so
> logins and SSH authentication fail. `0002` reverts it for this host. A
> proper fix probably gates it on the guest version.

### 3e. Kernel PAC VM-key patch: licence request (steelbrain)
> Could the PAC VM-key KVM patch get a licence (GPL-2.0, like the kernel)?
> It's the only piece that stops distributions such as Omarchy M from
> packaging macOS-guest support. It's currently all rights reserved.
