# Work log

A running, dated log of changes to this setup (the omvm repo and the Omarchy
host it runs on). Newest first. Agents: append an entry after each change.

## 2026-11-09

- **Final Cut Pro in `macos`: runs, but stops at the Creator Studio paywall; one GPU
  gap kills the VM.** Apple dropped the 90-day FCP trial (apple.com/final-cut-pro/trial
  301s to /final-cut-pro/, "Try it free" is the App Store's Creator Studio, which needs
  an Apple Account). The owner's App Store FCP 12.4 copied into the guest verifies
  (`spctl`: Mac App Store), launches and draws its UI with no Metal errors, then asks
  for $12.99/month and "Sign in to your Apple Account", which this VM can't do; import,
  playback, effects and export in FCP are untested. The same work through AVFoundation
  + a Metal CIContext (colour + Gaussian blur + overlay) exports 30 s of 4K H.264 to
  1080p H.264 in 26.6 s, 4K H.264 in 30.2 s, ProRes 422 in 27.2 s; VideoToolbox is
  software-only (no hardware decode for H.264/HEVC/ProRes, no
  `AppleM2ScalerParavirtDriver`). A 10-bit ProRes 1080p -> H.264 export killed the VM:
  `reims-vgpu: fatal: platform call dispatchThreadgroups:threadsPerThreadgroup:: ...
  Format VK_FORMAT_R8G8B8A8_UNORM, usage: SampledImage` (GAP-1, repro and suggested
  fix in `docs/fcp.md`). Guest GUI driven from the host (grim + ydotool relative
  motion), since guest `screencapture` has no TCC grant over SSH.

- **`omvm perf always|ac|off`: the governor switch is a setting.** Default `always`
  (performance while a local-mode VM runs, on AC and battery), kept in
  `~/.config/omvm/perf`; `OMVM_LOCAL_GOVERNOR` still overrides it. `ac` installs a udev
  rule on the Mains supply's change event that starts `omvm-power.service` (user), which
  runs `omvm perf apply`. `omvm-gui` has the same three-way switch under Display ("CPU
  performance (local mode)", with the governor and power source now). `omvm help` now
  prints the whole header, not lines 3-24. Tested with `macos` running local: `off` put
  back schedutil, `always` set performance on all three policies, `ac` on AC set
  performance; with `OMVM_AC_ONLINE=0` set in the user manager, `udevadm trigger
  --action=change` on `macsmc-ac` ran the unit and put back schedutil, `=1` performance
  again; `omvm stop macos` restored schedutil, `omvm start macos` with `off` left it,
  and switching to `always` while running set performance. `omvm-gui --selftest`
  passes with the new perf checks.

- **`macos` pointer lag: the CPU governor; the guest now boots in macOS's default
  scaling.** Measured with a uinput mouse on the host (`/tmp/lat.py`, not in the
  repo) against `~/bin/latprobe` in the guest (a full-screen window that turns
  white or black on the mouse-moved event, clocks matched over its SSH pipe), and
  `grim` polling one pixel (~9 ms a sample): with `schedutil` a move reached the
  guest's NSEvent in 10 ms median (p90 17) and the screen in 51 ms (p90 58); the
  host-drawn cursor showed in 26 ms (p90 34). With the `performance` governor on
  all three clusters: 1.4 ms (p90 2.8), 20 ms (p90 28.5) and 13 ms (p90 17); the
  guest's display link ran 120.0/s with frame gaps of 8.40 ms p95, 8.54 ms max.
  schedutil leaves the cores at low clocks between the guest's bursts, and each
  move waits for them to ramp. Not the cause: the cursor (SDL's colour cursor,
  drawn by Hyprland; reims draws it into the image only while the guest moves it
  on its own), the swapchain (MAILBOX, 4 images), the tablet (1 ms bInterval).
  Hyprland's `render:direct_scanout = 1` changed nothing (the window was never
  scanned out) and was put back to 0.
  - `omvm`'s libvirt hook now sets the `performance` governor while a local-mode
    VM runs (its QEMU has `REIMS_VGPU_WINDOW=1`; checked in `/proc`, since a hook
    must not call libvirt) and puts the saved governors back when the last one
    stops (`$XDG_RUNTIME_DIR/omvm-governor`). `OMVM_LOCAL_GOVERNOR=keep` skips
    it. Needs passwordless sudo.
  - Scaling: `omvm-display-follow` set each new size's native 1x mode, so local
    mode ran 3024x1964 at 1x (tiny UI). It now sets the mode macOS marks default
    (`kDisplayModeDefaultFlag`: 1512x982 points at 2x here), else native 1x, and
    keeps the last size it acted on in `~/Library/omvm/display-follow.state`, so a
    scaling picked in System Settings survives reboots until the host offers
    another size. The agent is now ad-hoc signed as `org.omvm.display-follow`
    after a rebuild; launchd refused its first spawn
    (`OS_REASON_CODESIGNING`) on 27.2.

- **`macos` (27.2, local mode) runs at ~110 fps again; the lag was `macos27`
  sharing the GPU, not the 60 Hz cap.** The domain carried
  `REIMS_VGPU_MAX_REFRESH_HZ=60` from `libvirt-domain.py` (the headless
  remote default, there since the first virt-manager commit), but the
  steelbrain reims that `qemu-sb`/`qemu-sb-bdifw` link never reads it (only
  qemu-fleet's reims does): the guest's modes all read 120 Hz (`ioreg`
  `SyncRate` 7864320) and a CADisplayLink probe (`~/bin/fpsprobe` in the
  guest, NSView display link at 120, animating a layer) ticked 117-120/s.
  What reached the window was the problem: with `macos27` running headless
  (QEMU at ~200 % CPU, host swap 15-28 GB, kswapd busy) reims-vgpu counted
  12-26 guest frames/s, max gaps 120-280 ms, window GPU 16-47 ms per frame.
  `omvm stop macos27` alone brought it to 100-120/s (avg ~110), max gaps
  17-38 ms, window GPU 1.1-1.5 ms, swap 1 GB. Both VMs on the one AGX queue
  starve the local window; keep only one running for a smooth desktop.
  - `share/libvirt-mode.py` now sets `REIMS_VGPU_MAX_REFRESH_HZ` to the
    panel's rate in local mode and back to 60 in remote, so a reims that
    honours the cap also offers 120 Hz locally. `omvm virt macos` rewrote the
    domain (backup `domain-local-pre-120hz-20261109.xml`). Measured after,
    `OMVM_STATS=1`, probe at 3024x1964: guest 99-116 frames/s (first second
    76), window presents the same, window GPU 1.2-1.5 ms.
  - The guest now logs in by itself after a reboot (`sysadminctl -autologin`
    plus `/etc/kcpassword`; `sysadminctl` printed error 22 and wrote only the
    `autoLoginUser` key, so `kcpassword` was written by hand).
  - Still open: the guest runs 3024x1964 at 1x (scale 1.0), not the HiDPI
    1512x982 the docs expect; `mds` indexes after each boot (~47 % CPU).

- **`macos` showed a black Reims window: it was stuck in a macOS 27 upgrade
  reboot loop; it now runs 27.2.** At 09:44 the guest user (uid 501, with
  admin authorization, from Software Update in the guest; automatic installs
  are off) started the 27.2 (26B123) update, and at 09:45:34 the VM rebooted
  into it. `macos` had no `guest_major`, so it ran `build/qemu-sb` and the
  26-era AVPBooter, and first-stage iBoot panicked and reset about twice a
  second from then on (QMP `GUEST_CRASHLOADED`/`RESET`, PC `0x100000`,
  `Duplicate block info` spam from virtqemud, no disk write since 09:45:34).
  The user's restarts at 14:16 looped too, since the aux NVRAM holds
  `boot-command=upgrade`. Not caused by `macos27` running beside it or by
  today's rebuilds: `qemu-sb` was relinked at 09:23 (patch 0004,
  `apple-vendor-cap` default off, same behaviour as before) and never linked
  the 14:05 iOS Simulator library.
  - Fix: `echo 27 > ~/vm-artifacts/vms/macos/guest_major`, `omvm virt macos`
    (local mode kept: `REIMS_VGPU_WINDOW=1`, 120 Hz, the `-wl` Mesa), destroy
    and start. Reflink backups first in `~/vm-artifacts/vms/macos/`:
    `disk.img.pre-27-20261109`, `aux.img.trimmed.pre-27-20261109`,
    `domain-pre-27-20261109.xml` (the 26 domain).
  - ssh answered 2 minutes later on 27.2 (26B123); post-upgrade migration then
    ran behind the Apple logo in the Reims window. `macos` and `macos27` both
    run `build/qemu-sb-bdifw` now. docs/graphics.md "macOS 27 updates"
    describes the failure.
  - First boot on 27.2: the lock screen ignored keys (the known
    first-boot-after-update state; `macos` had no system input source), and
    at 14:36 the guest turned its display off (pmset log) although
    `displaysleep` is 0, which froze the Reims window on its last frame until
    `caffeinate -u` over ssh. Copied macos27's
    `/Library/Preferences/com.apple.HIToolbox.plist` (ABC) into `macos`,
    rebooted the guest (`shutdown -r now`, back in 20 s), and the password
    typed with HMP `sendkey` logged in. After two Setup Assistant panes
    (Liquid Glass, Welcome) the desktop shows in the 120 Hz Reims window.

- **The iOS Simulator runs in `macos27`.** Xcode 27.2 (27B52) was already in
  the guest; `sudo xcodebuild -runFirstLaunch` and `xcodebuild -downloadPlatform iOS`
  (no Apple ID, ~8.3 GB at 10-20 MB/s over Wi-Fi) installed the iOS 27.2
  runtime (24B8117). Metal in the guest is "Apple Paravirtual device"
  (families apple1-5 and mac2, no apple7/metal3); a swiftc compute + render
  test gave exact results. `simctl boot` of iPhone 17 took 38 s cold, 11 s
  warm; the home screen, Settings and a SwiftUI test app (built with
  `xcrun -sdk iphonesimulator swiftc`, ad-hoc signed, `simctl install`) render
  correctly, and Xcode 27's Simulator window (now `Device Hub.app`,
  `Xcode.app/Contents/Applications/DeviceHub.app`) shows the device live.
  - Before the fix, the first `simctl io screenshot`, app launch or Device
    Hub frame killed QEMU: `reims-vgpu: fatal: platform call drawPrimitives...
    the bind state was refused: Unsupported(SamplerBicubicFilter)`. A
    diagnostic build traced it to `bind/heap.rs`: a cubic sampler in an
    argument buffer beside a fragment stage, which metal2vulkan refuses.
    `patches/graphics/metal2vulkan/0002` holds such a sampler as a linear
    VkSampler (a logged degrade, `REIMS_VGPU_CUBIC_ARGUMENT_SAMPLERS_LINEAR=0`
    restores the refusal); reims rebuilt (`cargo xtask dist`, ~10 min
    incremental) and `build/qemu-sb-bdifw` relinked. Only macos27's QEMU
    links it; the `macos` VM's `qemu-sb` binary was not relinked.
  - Speed: CADisplayLink in the app reports 60 Hz, but a serialized Metal
    command buffer round trip is ~85 ms (11.8 full-screen 1206x2622 passes/s
    waited one by one, 672/s pipelined), and `simctl io recordVideo` caught
    37 frames in 10.8 s. Usable for UI checks and tests, not smooth.
  - Something else on the host restarted macos27 within ~30 s after each
    crash (not `on_crash`, which is `destroy`).
  - Backups: VM dir `~/vm-artifacts/vms/macos27.pre-iossim-20261109/`
    (reflinks, before the runtime install); the old `libreims_vgpu.a` and
    `qemu-system-aarch64` in `~/vm-artifacts/rollback-iossim-20261109/`.

- **`macos27` has sound, and `omvm virt` makes macOS 27 domains.** QEMU
  3a14b4eadb on `sb-kvm-bdif-write` (exported as `patches/graphics/qemu/0007`)
  adds `x-ascending-capabilities` to `virtio-sound-pci` and moves the
  capability reordering into `virtio_pci_link_capabilities_ascending()`
  (virtio-net uses it too). macos27 now has `virtio-sound-pci,streams=2` on
  PipeWire again: `system_profiler SPAudioDataType` lists "Apple Virtual Sound
  Device" (2 in, 2 out, mic input), and `afplay Glass.aiff` in the guest showed
  up on the host as the `macos27` output stream (pw-record on it: peak 11759 /
  4901, silent otherwise), linked to the speakers' convolver; the input stream
  is linked to the MacBook mic.
  - `guest_major` (a file in the VM dir, `27`) makes `omvm virt` use
    `build/qemu-sb-bdifw` (`OMVM_QEMU27`), the 27.2 AVPBooter
    (`OMVM_AVPBOOTER27`) and the four capability switches. `guest_env` no
    longer picks the 27 AVPBooter for other VMs (the glob could sort it first).
    Regenerating macos27 with it gave the hand-made domain minus the serial /
    `-d` debug args; macos27 boots from it to the desktop.
  - The bdifw build had no `pc-bios/keymaps` (only `qemu-system-aarch64` was
    built), so QEMU refused to start with its own `-L`; `ninja` of the 32 keymap
    targets fixed it.
  - Login window keyboard: could not reproduce. After a cold boot with autologin
    off, after `pkill loginwindow`, and with the HIToolbox prefs removed, VNC
    typing and HMP `sendkey` both logged in. The failing first boot after the
    OTA had no input menu and SecurityAgent logged "No selected input source
    for user", so it looks like a first-boot-after-update state. Added a
    system `/Library/Preferences/com.apple.HIToolbox.plist` (ABC) in the guest.
    Autologin is back on.
  - Backup before the sound change: `~/vm-artifacts/vms/macos27.pre-sound-20261109/`
    (27.2.1, reflinks). The `.failed-vcap-20261109` images and `~/m27work`
    scratch are deleted.

- **`macos27` is on macOS 27.2.1 (26B131)** and boots to the desktop
  (autologin `aquarat`, Setup Assistant done: Apple Account skipped, no
  FileVault, updates download-only). Two more QEMU fixes on top of the bdif
  write fix below, now committed on `sb-kvm-bdif-write` in
  `build/qemu-sb-bdifw/src` and exported as `patches/graphics/qemu/0005`
  (bdif writes, f7865b7924) and `0006` (`ascending-capabilities`,
  3b875bb399); `0004` (`apple-vendor-cap`, 07279a4a8e) is committed with
  them because `0006` builds on it.
  - The earlier iBEC panic (`99180f7bfe1a22b:991`) did not come back.
    Disassembly of the 27.2 iBoot (`Firmware/all_flash/iBoot.vma2.RELEASE.im4p`,
    linked at 0x7006c000) shows it: the boot-args builder panics when the
    boot type stage 1 handed over is 7 (iBEC) and boot-args lack `rd=`, i.e.
    the upgrade command booted a kernel without its update ramdisk. On the
    27.2.1 attempt a gdbstub breakpoint (`gdbserver` over HMP + `hbreak`)
    showed boot-args `rd=md0 -progress -restore` and no panic.
  - The update ramdisk then hung: all CPUs in the 27 kernel, zero aux/root
    I/O for minutes. Cause: macOS 27's virtio transport needs the PCI
    capability list in address order. `apple-vendor-cap=on` fixed the probe
    but, powered off mid-ramdisk, iBoot fell back to 26.4, which then lost
    its data-protected files (ssh key auth failed) because the vendor cap
    also disables transport encryption. Disk and aux were restored from the
    pre-install reflink backup and `0006` adds `ascending-capabilities`
    (reorder only). With it on both vmapple-virtio-blk devices plus
    `x-ascending-capabilities=on` on virtio-net, 26.4 booted with its data
    intact, `softwareupdate -i ... --stdinpass -R` applied 27.2.1 in about
    5 minutes, and ssh/sudo work on 27.2.1. virtio-sound-pci was removed
    from the domain (no reorder switch yet).
  - HMP `sendkey` and VNC keys did not reach the 27.2.1 login window (the
    mouse did); on the desktop the keyboard works. Autologin
    (`/etc/kcpassword` + `autoLoginUser`) was set over ssh instead.
  - Backups (reflinks): `~/vm-artifacts/vms/macos27.pre-ota2721-20261109/`
    (26.4 with 27.2.1 downloaded); `disk.img`/`aux.img.trimmed`
    `.failed-vcap-20261109` in the VM dir (the vendor-cap fallback, safe to
    delete). Serial logs `logs/serial-20261109-{vcap,asc}.log`.
  - The `macos` VM and `build/qemu-sb` are untouched. To roll out: `git am`
    `0005` + `0006` onto `build/qemu-sb/src` (`0004` is already there),
    `ninja`, then add `ascending-capabilities=on` to both vmapple-virtio-blk
    devices and `x-ascending-capabilities=on` to virtio-net before updating a
    guest to 27 (the new switches default off, so 26 guests are unchanged).

- `macos27` boots again (macOS 26.4 25E246, login window), but the 27.2 OTA
  did not apply. It was never an AVPBooter hang: with a serial console
  (`-chardev file,...,path=~/vm-artifacts/vms/macos27/logs/serial-*.log`
  `-serial chardev:omvmser0` as qemu:arg) the guest showed the OTA's
  precommitted 27.2 iBootStage1 (mBoot-20457.41.3, `illb` at aux offset
  0x220000) panicking in a reset loop (`iBoot Panic: 64383f188f1c630:234`,
  54 resets in 30 s; PC in 0x7007xxxx-0x700bxxxx is iBoot, not the ROM).
  Disassembly of the dumped iBoot (`pmemsave 0x70000000`) shows it bumps a
  counter (3 -> 4) in the aux disk's `virt_pmu_sram` record (`UMPv`) before
  it loads the next stage, and panics when the write fails. QEMU's vmapple
  BDIF backdoor dropped every write (`/* Not needed, iBoot only reads */`).
  Fix: a patched QEMU that implements BDIF writes and asks for write
  permission on the backdoor's drives (without the permission it aborts on
  `child->perm & BLK_PERM_WRITE`). Built separately so `macos` keeps its
  binary: `build/qemu-sb-bdifw/` in apple-macos-arm64-vm-guest (reflink copy
  of qemu-sb/src, branch `sb-kvm-bdif-write`, uncommitted; diff in
  `build/qemu-sb-bdifw/bdif-write.patch`). With it the 27.2 iBootStage1
  writes the counter, resets, then loads the 27.2 iBootStage2 ("Remote boot",
  the upgrade iBEC), which panics too (`99180f7bfe1a22b:991`, iBoot's NVRAM
  code); iBoot then falls back to the 26.4 chain and macOS 26.4 boots.
  `boot-command` is now cleared (not settable from the guest: "not
  permitted"); softwareupdate now offers 27.2.1 (26B131, 11 GB).
  macos27 now runs the 27.2 host's AVPBooter
  (`artifacts/firmware/AVPBooter.vmapple2.macos27.2-26B123.bin`, mBoot-20457.41.3,
  sha256 c9c4fdb8…bec8a, copied from Virtualization.framework on uzi's Mac,
  macOS 27.2 26B123) and the patched QEMU; with the boot chain back on
  26.4 both AVPBooters boot it. Serial and `-d guest_errors,unimp`
  (`logs/qemu-d-20261109.log`) stay on in macos27's domain. Backup of the
  pre-change VM dir + both XMLs: `~/vm-artifacts/vms/macos27.pre-avpbooter-20261109/`
  (reflinks). Next for 27.x: catch the iBEC panic (memory dump at the
  panic, e.g. a second `-qmp` socket and a stop on "iBoot Panic" after
  "Remote boot") on the next OTA attempt.

- `macos27` (26.4 clone) hangs in AVPBooter after the macOS 27.2 OTA's own
  apply-reboot. The OTA finished downloading ~09:55; the guest rebooted at
  09:52:04 (aux.img.trimmed and disk.img mtimes) and never came back: CPU0
  loops in firmware (PC around 0x100000 / 0x700a2xxx), CPUs 1-7 stay at PC=0,
  zero I/O on both the aux and root virtio drives (`virsh qemu-monitor-command
  macos27 --hmp "info blockstats"`; `domblkstat` is useless because the disks
  come in via qemu:arg), VNC frame black. vmapple QEMU does not survive an
  in-guest reboot, so a fresh process was tried: `virsh destroy macos27` +
  `virsh start macos27` at 10:38 (the REIMS_VGPU_* / VK_DRIVER_FILES env lives
  in the domain XML as qemu:env, so plain start reproduces the config). Result:
  same hang. After 5 min: aux and root reads 0 bytes, CPU0 in firmware, other
  CPUs never started, VNC shows "Guest has not initialized the display (yet).",
  no ssh banner on 43757. Firmware is AVPBooter.vmapple2.mBoot-18000.161.10
  (26-era); untested guess is that the 27.2 boot objects/policy staged in aux
  need newer AVPBooter. Left running in that state; no retry, no reinstall.

## 2026-11-08

- Mesa `agx-16bit-flat-varyings` now credits aquarat: the change is byte-identical
  to his `patches/mesa/0001` + `0002` (apple-macos-arm64-vm-guest 9b62919, 636da1e;
  MIT). Message-only amend (tree unchanged) adds a body line and
  `Co-developed-by: Aaron Scheiner <blue@aquarat.co.uk>`; 2b37de4b -> 64c25aa0,
  force-pushed to github.com/sapoepsilon/mesa. Hash references updated.
- **LICENSING.md** added (linked from the README's Legal section): omvm is
  GPL-2.0-or-later; the PAC kernel patch is steelbrain's unlicensed work and is
  fetched from aquarat's repo at build time, not included (steelbrain#1); each
  `patches/graphics/` patch is offered under its upstream's licence (Mesa MIT,
  QEMU GPL-2.0-or-later, reims-vgpu and metal2vulkan GPL-2.0-or-later OR
  LGPL-3.0-or-later); `share/bake-xcode-dmg.sh` is derived from aquarat's
  GPL-2.0-or-later `bake-xcode.sh`; no Apple software is included.
- **Guest user renamed `aquarat` -> `killerisya`** (macOS 26.4 VM `macos`; short
  name, home `/Users/killerisya`, full name; UID 501 unchanged). `dscl` RecordName,
  RealName, `admin` GroupMembership, `/etc/sudoers.d/killerisya` (NOPASSWD; the
  `aquarat` file is gone) and loginwindow `RecentUsers`/`FirstLogins` were changed over
  SSH. The home move and `NFSHomeDirectory` are blocked by TCC on a live system
  (SIP on; `mv /Users/aquarat` = "Operation not permitted" even as root over SSH or
  from a LaunchDaemon), so they ran in a KVM single-user boot (create-account.sh's
  method: `apfs_boot_util`, bootstrap opendirectoryd, `mv`, `dscl -create`) on a
  reflink copy that was then copied back. display-follow LaunchAgent rebuilt for the
  new home. Backups (reflink, VM off): `~/vm-artifacts/vms/macos/{disk.img,aux.img.trimmed,vm.json}.pre-rename-20261108`
  + `domain-pre-rename-20261108.xml`; `disk.img.failed-rename-20261108` = a first
  attempt (record renamed, home not moved) before it was restored from backup.
- **`OMVM_GUEST_USER`** (default `aquarat`): the guest account `omvm` (ssh, run,
  stop, display-follow, clipboard, setup -> upstream `GUEST_USER`, Xcode bake),
  `stream-host.sh` and `omvm-clip.py` log in as. `bin/omvm` and `stream-host.sh`
  fall back to `~/.config/omvm/gui.env` (Sunshine/systemd don't read `~/.bashrc`);
  the libvirt hook exports it. This host: `OMVM_GUEST_USER=killerisya` in
  `gui.env`, `~/.bashrc` and `~/.config/libvirt/hooks/qemu`.
- Mesa branches published on GitHub while the gitlab.freedesktop.org account
  awaits verification: https://github.com/sapoepsilon/mesa (no official GitHub mirror exists, so not a fork;
  full history pushed from `~/src/mesa-upstream-mr`, remote `gh`).
  `hk-fragment-shader-interlock` a3561cde, `agx-16bit-flat-varyings` 64c25aa0;
  compare against upstream main: `https://github.com/sapoepsilon/mesa/compare/1f935e49...<branch>`.
- **`omvm start|stop|restart|pause|resume NAME`** for libvirt VMs (`bin/omvm`,
  `cmd_power`; `omvm start NAME IMAGE` / `omvm stop NAME` of a throwaway run are
  unchanged). stop: watchdog timer *and* its service off first (they used to race
  the shutdown: the GUI stopped the timer and sent `virsh shutdown` in parallel and
  left a running `ensure-vm` alone), resumes a paused guest, then `vm_shutdown`.
  start: `virsh start` (or resume) + watchdog on. pause/resume: `virsh
  suspend|resume`. `vm_shutdown` now treats `in shutdown`/`paused` as still on.
- **`omvm-gui` rework**: power buttons go through the CLI above (no duplicated stop
  sequence); Start / Pause⇄Resume / Stop / Restart show a spinner + "Stopping…" in
  the button and state row, every button is disabled while an action runs, state is
  polled every 2 s during an action and every 10 s idle (polls no longer flash the
  header spinner), success/failure as Adw toasts (stderr's last line; "Force off"
  on a failed stop) + an `omarchy-notification-send` desktop notification for
  start/stop/restart/mode. Confirm dialogs for Stop, Restart, mode switch.
  Omarchy look: colors from `~/.local/state/omarchy/current/theme/colors.toml`
  (accent, backgrounds, red/green/yellow) as libadwaita CSS variables, dark/light
  from its `mode`, the monospace font (`fc-match monospace`, JetBrainsMono Nerd
  Font), follows `omarchy theme set` live; `--install` adds
  `o.window("^dev\\.omvm\\.Gui$", { tag = "+floating-window" })` to
  `~/.config/hypr/looknfeel.lua` (875x600, floating, centered). Esc / Ctrl+W
  close, Ctrl+R / F5 refresh. Open desktop uses `omvm show`. Resolution only in
  remote mode. Fixes: `--install` from a shell without `OMVM_*` wiped
  `~/.config/omvm/gui.env` (now merges); subprocess timeouts kill the whole process
  group; PATH gets `~/.local/bin` for launcher starts; paired-client parsing
  tolerates missing keys and marks disabled clients. `omvm-gui --selftest` checks
  the read-only paths headlessly (19 checks pass).
- Tested in the owner's session (local mode) through AT-SPI clicks + grim:
  Pause→Resume (paused/running), Stop (confirm, spinner, off in ~15 s), Start
  (guest SSH in ~9 s), Restart (off at +14 s, running at +15 s), mode switch confirm
  → Cancel (stays local), Esc closes. VM left running in local mode, watchdog on.

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
  a3561cde and `agx-16bit-flat-varyings` 64c25aa0. VK-GL-CTS
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
