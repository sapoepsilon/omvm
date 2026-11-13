# omac: macOS apps on Omarchy

`omac` is a small launcher on top of omvm, in the spirit of Wine: `omac run Foo.app`
copies an arm64 macOS app into a dedicated macOS guest, opens it there and brings the
guest's screen to the front. It is not Wine. Each app runs inside a full macOS VM.
By default you see that VM's **whole desktop in one borderless window** (the
`reims-vgpu` window of `omvm mode local`, or a VNC viewer in remote mode). In remote
mode, `omac seamless` instead shows **each macOS app window as its own Hyprland
window** (see [Seamless mode](#seamless-mode-omac-seamless)).

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
omac seamless TextEdit                  # each guest window its own Hyprland window (remote mode)
omac run --seamless Foo.app             # open Foo, start seamless mode unless it runs
omac desktop --seamless Foo             # launcher entry "Foo (macOS)" for omac run --seamless Foo
omac show | stop | status | shell [CMD]
omac windows [--all] [--watch [--hz N]] # window geometry as JSON (what seamless mode follows)
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

## Window geometry (`omac windows`)

The building block of seamless mode: `share/omac/winlist.swift` is sent
over SSH, compiled in the guest with `swiftc -O` into
`~/Library/Application Support/omac/winlist` (rebuilt when the host copy's sha256
changes, ~3 s) and run there. It reads `CGWindowListCopyWindowInfo`, which works from
a plain SSH session (no `launchctl asuser` or LaunchAgent needed) and without a
Screen Recording grant: ids, owner pid/name, bundle id, layer, bounds, alpha and
on-screen state are all present; only window titles are missing (except the Window
Server's own "Menubar").

```json
{"display":{"h":1080,"id":1,"ph":1080,"pw":1920,"scale":1,"w":1920},
 "overlays":[],
 "windows":[{"alpha":1,"bounds":{"h":505,"w":603,"x":213,"y":94},"bundle":"com.apple.TextEdit",
             "id":40,"layer":0,"onscreen":true,"owner":"TextEdit","pid":369}, ...]}
```

- Default (`--apps`): `windows` = layer-0 app windows, `overlays` = higher-layer
  windows of the same pids (menus are layer 101) plus UserNotificationCenter
  permission prompts. `--all` lists everything (Dock, menu bar, Notification Center).
  Arrays are front to back, matching what the screen shows. Placeholder windows of
  `talagentd` (restored-app snapshots under the app's owner name) are dropped.
- `--watch` prints one line (`seq`, `t` in ms) per change, polling at 30 Hz by
  default. It ends on SIGTERM/SIGINT/SIGHUP, on a closed reader (kqueue EV_EOF) and
  when its parent sshd goes away; killing `omac windows --watch` leaves nothing in
  the guest. Guest CPU: ~4 % of a core at 30 Hz, ~10 % at 60 Hz; a one-shot run
  ~50 ms; SSH adds 2–5 ms per line.
- Bounds are points from the main display's top left. In remote (VNC) mode the
  display is 1920x1080 at scale 1, so points equal `virsh screenshot` pixels.
  Verified by cropping: an app window's rectangle is exact (no shadow; a 1-px dark
  outline sits just outside it, the rounded corners show the background). Menus are
  reported with a ~75 pt transparent shadow margin on every side.
- Moving or resizing another app's window is not possible this way: AppleScript
  `set bounds` from SSH triggers an Automation prompt ("sshd-keygen-wrapper wants
  access to control TextEdit") and blocks until it is answered; arbitrary apps need
  Accessibility (AXUIElement), which this guest has not granted.

## Seamless mode (`omac seamless`)

```sh
omac seamless [--no-menubar] [--no-trim] [--no-round] [--hz N] [--stats N]
              [--control SOCKET] [--selftest [--selftest-text T]] [APP...]
omac seamless --stop
```

`share/omac/seamless.py` (Python 3, GTK 4 through PyGObject, no other dependencies)
makes every guest app window a Wayland toplevel of its own, the way Wine does for
Windows programs. It needs the VM in **remote (VNC) mode** (`omac init --remote`, or
`omvm mode remote macapps`); in local mode there is no VNC display and it refuses.
`omac seamless` boots the VM if needed, opens the APPs, writes its pid to
`$XDG_RUNTIME_DIR/omac-seamless-macapps.pid` (one instance per VM) and runs in the
foreground; `omac run --seamless APP` opens the app and starts it detached (log in
`~/.local/state/omac/seamless-macapps.log`) unless it already runs, in which case the
new window simply appears. `omac seamless --stop` sends it SIGTERM.

How it works:

- **One VNC connection** to QEMU's VNC server on 127.0.0.1 (no password: it only
  listens on loopback; a password would be refused with a clear error). It is a
  small RFB 3.8 client in the script (raw/CopyRect/DesktopSize/cursor, 32-bit BGRX),
  connected as a shared client so a vncviewer can stay connected. A reader thread
  keeps the whole framebuffer; each update marks the windows whose rectangles it
  touches, and only those repaint.
- **One `omac windows --watch --hz 30`** child for the window list (see above), and
  one long-lived `omac shell /bin/sh` for `open -b` (focus sync). Both get SIGTERM
  when the Python process dies, even by SIGKILL (`PR_SET_PDEATHSIG`).
- **One host window per guest window**: undecorated GTK 4 window, app id
  **`org.omvm.omac`**, title = the app's name (window titles need Screen Recording in
  the guest, which is not granted). It paints the live crop of the framebuffer at the
  window's bounds as a texture (GPU-scaled), and above it the left part of the guest
  **menu bar** (30 pt on this guest, read from the Window Server's `Menubar` window)
  so File/Edit/... can be clicked. The menu bar is the guest's global one: it shows
  the menus of the app in front in the guest, in every host window. `--no-menubar`
  drops the strip. A host window of another size than the guest window (tiled)
  shows it scaled to fit with letterboxing; input is mapped back through the same
  scale and offset. Corners are masked to the guest's 10 pt radius (`--no-round`).
- **Window lifecycle**: a new guest window gets a host window, a guest window that
  goes away closes its host window. **Closing a host window** (Super+W, or the
  compositor's close) clicks 4 px below the top edge of the guest window's title
  bar (draggable area, no controls) to bring it to the front, then sends Cmd+W.
  Nothing in the guest needs a permission for this. Apps that do not close windows
  on Cmd+W keep them; an unsaved document shows its save sheet. Either way, if
  the guest window is still there after 3 s, the host window comes back.
- **Overlays**: menus, popovers, tooltips and permission prompts (`overlays` of
  `omac windows`) appear as `GtkPopover`s (xdg_popup, no grab) of the app's front
  host window, positioned at their guest offset even when they reach outside it;
  menus opened from the menu bar strip follow the strip. Menus (layer 101) have
  their ~75 pt transparent shadow margin trimmed and rounded corners (`--no-trim`
  shows them raw). Sheets and dialogs that macOS draws as separate layer-0 windows
  (a window of the same app, in front of and inside a bigger one) are shown the
  same way, attached to their window, instead of as host windows of their own.
- **Focus sync**: when a host window becomes active and its guest window is not in
  front, `open -b BUNDLE` (LaunchServices, no Automation grant) activates the app,
  or, for another window of the app already in front, the title-bar click above.
- **Input**: pointer motion, buttons (left/middle/right), scroll (wheel or touchpad,
  ~20 px per wheel click, sent as RFB buttons 4/5) and keys go through the same VNC
  connection at the mapped guest coordinates. Keys are sent as X keysyms (GDK keyvals), which QEMU maps to
  the guest keyboard like for omvm's VNC viewer: **Super = Command, Alt = Option,
  Ctrl = Control** (Meta is sent as Super, AltGr as right Option). Hyprland keeps
  the Super shortcuts it binds itself unless the window is in the passthrough
  submap: `share/hypr-macos-vm.lua` now also switches to the "macos-vm" submap when
  an `org.omvm.omac` window has focus, so Super+W, Super+Q, Super+C... reach macOS as
  Cmd+W, Cmd+Q, Cmd+C; Ctrl+Alt+Escape gives the keys back, Ctrl+Alt+M and
  Ctrl+Alt+1..5 leave as before. Keys held while focus leaves are released.
- **Exit**: SIGTERM/SIGINT/SIGHUP, the VNC connection closing or the watcher ending
  (VM stopped) end it; it closes its windows, terminates both children and waits
  for them (exit code 3 when the VM went away).

Hyprland: new windows follow your normal rules (tiled, or floating on Omarchy's
floating workspaces). To float them at the guest's size:

```lua
-- ~/.config/hypr/hyprland.lua (or a file it requires)
hl.window_rule({ name = "omac-float", match = { class = "^org\\.omvm\\.omac$" }, float = true })
```

Debugging and tests: `--stats N` logs VNC updates/s, repaints/s per window and the
process CPU; `--control SOCKET` accepts one JSON request per connection
(`seamless.py ctl SOCKET '{"op":"list"}'`; ops `list`, `stats`, `click`, `scroll`,
`type`, `key`, `focus`, `close`, `probe`/`probes`, `drag`, `quit`); `--selftest`
clicks into the first TextEdit window and types a line. The ops call the same
`input_*` methods the GTK event handlers call (host coordinates in, VNC events out),
so they test the mapping without touching the real keyboard or pointer.

Measured on `macapps` (macOS 27.2, 1920x1080, M1 Max), test windows on a Hyprland
headless output:

| | |
|---|---|
| start to first host windows | VNC connected at 0.3–0.45 s, windows mapped at ~0.8 s |
| guest window appears to host window mapped | 2–4 ms after its watch line (`omac run --seamless Chess`: 4.2 s, all of it the app's launch) |
| Cmd+Q in the guest to host window closed | 284 ms |
| typing in TextEdit | 27 VNC updates/s, 27 repaints/s of that window, 0 of the others; 5.8 % of a core |
| idle | 0–1.4 % of a core, RSS ~145 MB |
| key in to its pixels back over VNC | 81–88 ms (median 84 ms, 20 samples; macOS text layout + QEMU's VNC refresh) |

Limits of seamless mode:

- **Overlapping guest windows**: the guest still has one screen. A host window shows
  whatever covers its guest window there (another app's window, a notification, a
  menu), and a covered region only updates when it is uncovered. Host stacking and
  guest stacking are independent; focusing a host window brings its guest window
  to the front, which fixes what it shows.
- **No guest window moves or resizes from the host**: resizing a host window scales
  the picture, it does not resize the macOS window (that needs Accessibility).
  Move windows inside the guest by dragging their title bar in the host window.
- **Global menu bar**: the strip always shows the menus of the guest's front app.
- **Titles**: every host window of an app has the app's name as title.
- **Not seen**: the Dock, Spotlight, Notification Center, Control Center and the
  desktop; windows of apps without a normal (layer 0) window.
- **Pixels**: VNC at the guest's 1920x1080, scale 1: no HiDPI, scaled up on a
  HiDPI panel. Updates follow QEMU's VNC refresh (~30/s while something changes).
- **Scrolling does not work yet**: the wheel events arrive as RFB buttons 4/5 at the
  right position, but TextEdit did not scroll (also with slow press/release from a
  separate VNC client), so the gap is between QEMU's VNC wheel buttons and the
  `usb-vmapple-tablet` / macOS, not in seamless.py; QEMU's VNC server has no
  horizontal wheel at all. Scroll with the keyboard (Page Up/Down) or scroll bars.
- **Not tested on the real seat**: all tests ran on a headless output with
  synthetic input through the control socket; real keyboard/pointer events through
  GTK, focus changes from Hyprland and the passthrough submap were not exercised.

## Limits

- **One window for the whole desktop** unless you use seamless mode (remote mode
  only); the Dock, menu bar and every app share it. `omac show` brings it to the front; Ctrl+Alt+M and the "macOS"
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
