# omac: macOS apps on Omarchy

`omac` is a small launcher on top of omvm, in the spirit of Wine: `omac run Foo.app`
copies an arm64 macOS app into a dedicated macOS guest, opens it there and brings the
guest's screen to the front. It is not Wine. Each app runs inside a full macOS VM, and
you see that VM's **whole desktop in one borderless window** (the `reims-vgpu` window
of `omvm mode local`, or a VNC viewer in remote mode). There is no seamless mode where
individual macOS windows become Hyprland windows.

## Setup (once)

```sh
ln -s ~/Work/omvm/bin/omac ~/.local/bin/omac
omac init            # clones the shut-off macos27 into the app VM "macapps"
omac up              # boots it (no watchdog) and waits for SSH, at most 5 minutes
```

`omac init [--from VM] [--remote]` refuses if `vms/macapps/` or a `macapps` domain
already exists, if the source is not `shut off`, and always for the source `macos`.
It reflinks exactly `disk.img`, `aux.img.trimmed` and `vm.json` from the source
(instant on btrfs), writes `guest_major`, `guest_user` (both taken from the source)
and a fresh `ssh_port` that no other `vms/*/ssh_port` uses, then runs
`omvm virt macapps`, which only defines the libvirt domain because `disk.img` is
already there. No identity files, certificates or backups are copied. The domain
is switched to local (window) mode when a Wayland session and the Wayland Mesa
are present; `--remote` keeps VNC. Libvirt autostart and the `omvm-vm@` watchdog
stay off. Work happens under `vms/macapps/.agent.lock` and is logged to
`vms/macapps/agent-notes.log`.

The environment defaults to `~/.config/omvm/gui.env`, then to
`OMVM_UPSTREAM=~/Work/macos-vm/apple-macos-arm64-vm-guest`,
`OMVM_IMAGES=~/vm-artifacts`, `OMVM_KEY=~/.ssh/vmapple_runner`. The guest account
comes from `vms/macapps/guest_user`. `OMAC_VM` picks another VM name,
`OMAC_SOURCE` another clone source.

## Use

```sh
omac run ~/Downloads/Foo.app            # rsync -a into the guest's ~/Applications, then open
omac run ~/Downloads/Bar.dmg --flag     # every .app in the image, args go to the app
omac run TextEdit                       # already in the guest: just open it
omac list                               # apps in /Applications, /System/Applications, ~/Applications
omac desktop Foo                        # "Foo" in the Omarchy launcher (omac run Foo)
omac show | stop | status | shell [CMD]
```

`run` checks the host path first (a missing path or a file that is neither
`.app` nor `.dmg` fails before anything boots), boots the VM if needed, clears
`com.apple.quarantine` on what it copied, runs `open -a` in the guest over SSH and
then `omvm show macapps`. Without `WAYLAND_DISPLAY`/`DISPLAY` (over SSH, headless)
it skips the show, so no viewer pops up on someone else's screen; a failed show is
only a warning, since the app is already open. A `.dmg`
goes to the guest's `/tmp` by scp, is attached read-only with `-nobrowse`
(licence prompts are accepted), each `.app` is copied to `~/Applications`, and the
image is detached and deleted. Copies overwrite the previous version of the same
app. Installer packages (`.pkg`) are not supported.

`up` checks first: the domain exists, fewer than two QEMU guests run, `macos27`
is not running (the clone shares its identity), AC power or a battery at 20 % or
more, and 20 GB of free RAM. It starts the VM with plain `virsh start`, not
`omvm start`, so closing the guest does not bring it back a minute later. If SSH
does not answer within 5 minutes it prints `info blockstats` twice, 30 s apart,
and the domain state, and fails. `stop` is `omvm stop macapps`.

Files move only over SSH (rsync/scp with `OMVM_KEY`): there is no shared folder,
and guest disks are never mounted on the host.

## Limits

- **One window for the whole desktop.** Not seamless; the Dock, menu bar and every
  app share it. `omac show` brings it to the front; Ctrl+Alt+M and the "macOS"
  launcher entry are bound to `omvm show`, i.e. the `macos` VM, not `macapps`.
- **arm64 macOS apps only.** Intel apps under Rosetta are untested.
- **Self-contained apps only.** A copy of a built-in app (e.g. `/System/Applications/Calculator.app`)
  will not launch from `~/Applications` (launch constraints, `Launchd job spawn failed`, POSIX 162),
  and apps nested in Xcode (FileMerge, Accessibility Inspector) need Xcode's frameworks next to them.
  Run built-in apps by name (`omac run TextEdit`).
- **No Apple Account.** Apps that need an Apple Account, iMessage, iCloud, the App
  Store, or licence checks tied to Apple hardware or identity will not work.
- **Graphics:** Metal works through the paravirtual GPU but without Metal 3; see
  [graphics.md](graphics.md#guest-metal-feature-set-why-there-is-no-metal-3).
- **Two guests at most** (the QEMU limit omvm keeps), and each takes ~16 GB of RAM:
  with `macos` running there is room for `macapps` only, and `macos27` must be off.
- **One app VM for all apps.** Every app installs into the same guest, so apps
  share its state, and a broken app can affect the others.
- **Shared identity.** The clone carries the same `vm.json` as `macos27`, exactly
  as `macos27` shares it with `macos`. Never run the clone and its source together.
