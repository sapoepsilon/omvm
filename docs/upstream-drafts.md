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
