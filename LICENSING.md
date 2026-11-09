# Licensing

omvm is licensed under the GNU General Public License, version 2 or (at your
option) any later version (`GPL-2.0-or-later`); the full text is in
[LICENSE](LICENSE). The exceptions below are files that patch other projects,
code derived from other projects, and things omvm deliberately does not
include.

## Not in this repository: the PAC kernel patch (unlicensed)

`omvm kernel build` needs two Linux patches. omvm does not include either of
them. At build time it clones
[aquarat/apple-macos-arm64-vm-guest](https://github.com/aquarat/apple-macos-arm64-vm-guest)
and concatenates them from that checkout (`bin/omvm`, `cmd_kernel`):

| Patch (in the upstream checkout) | Licence |
| --- | --- |
| `patches/linux-7.1.13-vmapple-pac-vmkey.patch` | **None.** Anees Iqbal's (steelbrain) work, rebased to Linux 7.1.13 by aquarat; all rights reserved |
| `patches/linux-7.1.13-kvm-nisv-ldst.patch` | GPL-2.0 (Linux) |

The PAC patch comes from
[steelbrain/experiment-macOS-arm64-on-asahi-linux-arm64](https://github.com/steelbrain/experiment-macOS-arm64-on-asahi-linux-arm64),
which has no licence. A licence has been requested in
[steelbrain#1](https://github.com/steelbrain/experiment-macOS-arm64-on-asahi-linux-arm64/issues/1).
Until one is granted, omvm will not copy that patch into this repository, and
no prebuilt kernel package is offered. The kernel you build stays on your
machine.

## Patches to other projects

A patch is a change to another project, so it is offered under that
project's licence:

| Patch | Upstream | Licence |
| --- | --- | --- |
| `patches/graphics/mesa/0003-hk-fragment-shader-interlock.patch` | Mesa (Honeykrisp) | MIT |
| `patches/graphics/qemu/0001-vmapple-on-KVM-Asahi-port-aquarat-qemu-reims-vgpu-c6.patch` | [steelbrain/qemu-reims-vgpu](https://github.com/steelbrain/qemu-reims-vgpu) (QEMU) | GPL-2.0-or-later |
| `patches/graphics/qemu/0002-hw-vmapple-virtio-blk-drop-the-macOS-27-vendor-capab.patch` | steelbrain/qemu-reims-vgpu (QEMU) | GPL-2.0-or-later |
| `patches/graphics/qemu/0003-hw-display-apple-gfx-headless-displays-follow-the-UI.patch` | steelbrain/qemu-reims-vgpu (QEMU) | GPL-2.0-or-later |
| `patches/graphics/reims-vgpu/0001-asahi-honeykrisp-host.patch` | [steelbrain/reims-vgpu](https://github.com/steelbrain/reims-vgpu) | GPL-2.0-or-later OR LGPL-3.0-or-later |
| `patches/graphics/metal2vulkan/0001-dma-buf-importer-without-host-pointer.patch` | [steelbrain/metal2vulkan](https://github.com/steelbrain/metal2vulkan) | GPL-2.0-or-later OR LGPL-3.0-or-later |

`qemu/0001` is a port, not new work: it rebases the vmapple-on-KVM changes from
[aquarat/qemu-reims-vgpu](https://github.com/aquarat/qemu-reims-vgpu)
(c6d87a8406), including Anees Iqbal's vmapple KVM commit (7f39007f9a) and
Mohamed Mediouni's RFC v7 "vmapple: make it work on the latest macOS
release", onto steelbrain/qemu-reims-vgpu 1b41f5f5db. Authorship of that code
stays with them.

reims-vgpu and metal2vulkan are each dual-licensed by their authors under
`GPL-2.0-or-later OR LGPL-3.0-or-later` (see their LICENSE files); the patches
here are offered under the same choice.

The graphics build ([docs/graphics.md](docs/graphics.md)) also applies
aquarat's Mesa patches `patches/mesa/0001` and `0002` from the upstream
checkout. They are not in this repository; they are offered under Mesa's MIT
licence.

## Code derived from other projects

- `share/bake-xcode-dmg.sh` is derived from `scripts/bake-xcode.sh` in
  aquarat/apple-macos-arm64-vm-guest (`GPL-2.0-or-later`), modified for omvm
  to install Xcode from a .dmg. It stays `GPL-2.0-or-later`.

The rest of `bin/` and `share/` is omvm's own work. omvm drives scripts from
the aquarat/apple-macos-arm64-vm-guest checkout at run time (for example
`share/run-on-macos.sh` fetches it on the Mac); those scripts keep their own
licences, set out in upstream's
[LICENSING.md](https://github.com/aquarat/apple-macos-arm64-vm-guest/blob/master/LICENSING.md).

## Apple software

omvm does not include or redistribute any Apple software, and never downloads
Apple files on your behalf from anywhere other than Apple:

- **AVPBooter** (the VM boot ROM) is copied from your own macOS install.
- **The restore image (IPSW)** is downloaded from Apple's servers by the
  macOS-side script.
- **Xcode** is copied from your own installed Xcode.app.

Apple's terms still apply to what you run:

- The macOS licence allows up to **two additional copies** of macOS in
  virtual machines, on **Apple-branded hardware** you own or control, for
  permitted purposes. omvm enforces the two-guest limit; don't remove it.
  Running the VMs with Linux as the host on that hardware is a setup Apple
  doesn't specifically address, so judge it for yourself.
- The macOS licence (§2K) forbids redistributing the boot ROM and firmware,
  and the Xcode and SDK agreement (§2.7) forbids redistributing Xcode. Never
  publish guest disk images, `vm.json`, AVPBooter, restore images or Xcode
  images.

"macOS", "Xcode" and "Apple" are trademarks of Apple Inc. omvm is not
affiliated with or endorsed by Apple.
