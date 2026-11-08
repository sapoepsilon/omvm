---
title: "Running macOS VMs on Linux, on a MacBook: KVM on Omarchy M"
date: 2026-11-08
status: draft
---

# Running macOS VMs on Linux, on a MacBook

I run Omarchy M (an Arch Linux ARM distribution with an Asahi-based kernel) on my M1 Max MacBook Pro. I wanted to stop dual-booting just to use Xcode. The usual answer is that macOS virtual machines need macOS as the host. On Apple Silicon hardware, that turned out not to be fully true.

## The short version

- A macOS 26 Tahoe guest boots under **KVM** on Linux, on the same M1 Max.
- I can SSH in, and `xcodebuild` runs at **95–99 % of native CPU speed**.
- A paravirtual GPU draws the desktop cleanly over VNC.
- The tooling is open source as **[omvm](https://github.com/sapoepsilon/omvm)**, a small CLI for Omarchy.

## How it works

Apple's Virtualization.framework exposes a VM "machine" called *vmapple*. QEMU has an implementation of it. Other people did the hard groundwork:

- **aquarat/apple-macos-arm64-vm-guest**: runs vmapple on Asahi Linux with KVM.
- **steelbrain/reims-vgpu**: translates the guest's Metal GPU commands to Vulkan.
- **Two small kernel patches**: one for pointer-authentication keys, one for emulating certain memory accesses.

My part was porting this to Omarchy:

1. **Kernel.** I built a side-by-side kernel package, `linux-aurora-vmapple`: Omarchy's own kernel plus the two KVM patches. It's installed next to the stock kernel and selected in Limine. I pinned the m1n1 device trees to the stock kernel so the boot check stays happy.
2. **The macOS half, done once.** In native macOS, a script shrinks the APFS container, creates an exFAT transfer partition and restores a Tahoe VM bundle with Apple's own tools. It copies the VM's boot ROM (AVPBooter) and your already-installed Xcode next to it, then reboots into Linux. Nothing Apple-owned is downloaded or redistributed. Everything comes from your own Mac.
3. **On Linux**, the bundle is ingested and booted by QEMU's vmapple under KVM. Layered "bakes" add a user account, SSH, the Command Line Tools, Xcode and desktop settings. Each layer is a golden image, and every run is a copy-on-write clone.

```
omvm setup --xcode
omvm run -- 'sw_vers; xcodebuild -version'
```

## Things that bit me

- **Symlinked IPSWs** are rejected by Virtualization.framework (VZError 10005). Copy them.
- **Two kernels** confused Omarchy's m1n1 update script and its boot check. Pin DTBS explicitly.
- **Hardware model v2 VMs can't move to Linux.** Their data-volume keys are tied to the host Mac's Secure Enclave, and under KVM they panic with "unencrypted data volume is not allowed". VMs made with hardware model v1 work. Migration Assistant can move an existing v2 VM's contents into a v1 VM.
- **A misleading microbenchmark.** A volatile stack-chain loop looked 3× slower in the guest. That's an M1 memory-renaming quirk, not KVM overhead. Real workloads (qsort, builds) ran within a few percent of native.
- **`com.apple.universalaccess` can't be written over SSH** (TCC). The `com.apple.Accessibility` keys work instead.

## Licensing

The macOS license allows up to two macOS VMs on Apple-branded hardware. QEMU here enforces that limit. omvm ships no Apple files. The boot ROM, the OS and Xcode all come from the user's own machine. The CLI is GPL-2.0. One kernel patch has no license, so it's downloaded at build time rather than redistributed.

## Graphics: the honest part

The first GPU path I tried was an older out-of-process fork of reims-vgpu. It got the login window up over VNC, but the desktop was unusable: missing icons, ghost copies of menus, a Dock made of blocks and no wallpaper. One bug was easy to find. The icon service kept aborting because the device reported a 256-byte linear-texture alignment that Metal's own validation then rejected. Fixing that stopped the crashes, but the rest stayed broken.

The real fix was moving to upstream **steelbrain/reims-vgpu**, which targets Linux/Vulkan hosts too, and adding the vmapple-on-KVM QEMU changes to its QEMU. Honeykrisp, the Vulkan driver for Apple GPUs on Linux, needed three workarounds:

- **No host-pointer import** (`VK_EXT_external_memory_host`). Guest memory is passed to the GPU as dma-bufs made with udmabuf instead, and the library's own allocations are memfd-backed so they can take the same route. The udmabuf module's limits have to be raised.
- **No framebuffer fetch ordering.** macOS's CoreAnimation reads the framebuffer in almost every shader. That needs `VK_EXT_fragment_shader_interlock`, which Honeykrisp didn't expose, even though the Asahi compiler already had the ordering instruction it needs. An 11-line Mesa patch exposes it.
- **No 10-bit extended-range pixel format.** It's turned off, and pipelines the driver can't build return a Metal error to the guest instead of killing QEMU.

With those in place the desktop draws cleanly over VNC: wallpaper, Dock, app icons, menus and System Settings, with no leftover rectangles when windows close. The first login takes about two minutes while shaders compile, and after that it's quick.

## Try it

https://github.com/sapoepsilon/omvm — start with `omvm doctor`.
