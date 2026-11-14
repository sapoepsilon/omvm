# Drafts for proposing omvm to Omarchy

**Historical drafts and posting record.** For the consolidated Apple-services
source, current testing gates and proposed component split, use the
[current upstream plan](apple-services-upstream.md). Preserve the posted links
below; do not replay an old proposal as a new submission.

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

### 3a. Mesa (Asahi/Honeykrisp): two merge requests

Prepared 2026-11-08 on omarchy in the worktree `~/src/mesa-upstream-mr`
(off `~/src/mesa-honeykrisp-sb`), each branch one commit on upstream `main`
@ `1f935e49`. Interim copies are on GitHub (see Posted). Diff backups of the old 26.2.6 trees:
`~/src/mesa-backup-2026-11-08/`.

Mesa policy (docs/submittingpatches.rst): commit messages, code comments and
MR text must be in your own words, and AI involvement must be disclosed. Both
commits carry `Assisted-by: LLM`; rewrite the messages and the code comments
yourself before pushing.

CTS: VK-GL-CTS main (built 2026-11-08, `~/src/cts`), deqp-runner 0.24.0,
M1 Max (G13C C0), `VK_ICD_FILENAMES` pointing at each branch's build.
Raw results: `~/src/cts/out/<run>/results.csv`.

#### MR 1: `hk-fragment-shader-interlock` (a3561cde39cc)
**Title:** hk: expose VK_EXT_fragment_shader_interlock

> The AGX compiler already lowers `begin_invocation_interlock` to `wait_pix`.
> Gallium uses this to order spilled render-target image load/store. This MR
> exposes `fragmentShaderPixelInterlock` in Honeykrisp and makes
> `end_invocation_interlock` a no-op, since the pixel is released when the
> fragment ends. Also updates features.txt and new_features.txt.
>
> Use case: reims-vgpu translates macOS guests' Metal framebuffer-fetch
> shaders to Vulkan. That needs either pixel interlock or
> rasterization-order attachment access. With this patch, a macOS 26 desktop
> renders correctly on an M1 Max under KVM.
>
> CTS `dEQP-VK.fragment_shader_interlock.*` (576 cases):
> Pass 128, Fail 64, NotSupported 384. Without the patch: NotSupported 576.

**Blocker, do not open as-is:** all 64 failures are
`pixel_{ordered,unordered}.4xaa.no_sample_shading.*` (image and ssbo,
discard and nodiscard, every size). Pixel interlock passes at 1x and with
sample shading. A test-only build that also sets
`fragmentShaderSampleInterlock = true` passes every `sample_*` case
(320 pass, the same 64 fail). So `wait_pix` looks per-sample: two fragments
covering different samples of one pixel are not ordered. Options: expose
sample interlock (passes) and fix or restrict pixel interlock under MSAA
before submitting.

#### MR 2: `agx-16bit-flat-varyings` (64c25aa0ac5a)
**Title:** agx: fix 16-bit flat varyings

The code is aquarat's (`patches/mesa/0001` + `0002` in
apple-macos-arm64-vm-guest, applied unchanged); the commit credits him with
`Co-developed-by: Aaron Scheiner <blue@aquarat.co.uk>`.

> 16-bit varyings (e.g. SPIR-V Float16 outputs/inputs) reached `st_vary` as
> 16-bit values and 16-bit flat loads returned a 32-bit def, which aborted
> the backend ("unaligned reg" / `st_vary` packing assertion). Widen 16-bit
> outputs by type in agx_nir_lower_uvs and narrow flat inputs in
> agx_nir_lower_interpolation.
>
> CTS: hk does not expose `storageInputOutput16`, so the 16-bit CTS cases
> are NotSupported on a stock build. Varying subset (`dEQP-VK.glsl.linkage.
> varying.*`, `draw.*differing_interpolation*`, `rasterization.flatshading.*`,
> `spirv_assembly.instruction.graphics.16bit_storage.input_output_*`, 1786
> cases): Pass 96, Fail 0, NotSupported 1690, same as main (no regressions).
>
> With `storageInputOutput16 = true` forced in a test-only build,
> `16bit_storage.input_output_*` (1686 cases): main crashes 1030
> (`st_vary ^r0h, ^r0l`: `value.size == AGX_SIZE_32`), pass 176; with this
> patch: Pass 1106, Fail 100, NotSupported 480 (64-bit cases), Crash 0.
> All float16 cases pass. The 100 remaining failures are integer 16-bit
> varyings (wrong values, "fragment output data point mismatch"), crashes
> on main too; follow-up needed before `storageInputOutput16` can be exposed.

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

## Posted (2026-11-08)
- Omarchy Discussion: https://github.com/omacom/omarchy/discussions/18195
- omarchy-mac-pkgs proposal: https://github.com/omacom/omarchy-mac-pkgs/issues/107
- steelbrain/reims-vgpu#150, steelbrain/metal2vulkan#12, aquarat/apple-macos-arm64-vm-guest#1
- PAC licence request, +1 comment: steelbrain/experiment-macOS-arm64-on-asahi-linux-arm64#1
- Not posted: the Mesa MRs on gitlab.freedesktop.org (account awaiting verification; run the CTS first).
- Interim Mesa branches on GitHub (no official GitHub mirror to fork, so https://github.com/sapoepsilon/mesa):
  [hk-fragment-shader-interlock](https://github.com/sapoepsilon/mesa/tree/hk-fragment-shader-interlock)
  ([diff vs upstream main](https://github.com/sapoepsilon/mesa/compare/1f935e49...hk-fragment-shader-interlock)),
  [agx-16bit-flat-varyings](https://github.com/sapoepsilon/mesa/tree/agx-16bit-flat-varyings)
  ([diff vs upstream main](https://github.com/sapoepsilon/mesa/compare/1f935e49...agx-16bit-flat-varyings)).
