# USB passthrough (`omvm usb`)

Hot-plugs a host USB device into a running libvirt VM, without restarting it.

```sh
omvm usb list [VM]                              # host devices; "-> macos" = attached
omvm usb attach BUS-PORT|VID:PID|NAME [VM]      # e.g. omvm usb attach iphone
omvm usb detach BUS-PORT|VID:PID|NAME [VM]
omvm usb trust [VM] [SECONDS]                   # pair an attached iPhone (owner taps Trust)
```

`VM` defaults to `$OMVM_VM` or `macos`. `NAME` is a case-insensitive substring of
the manufacturer + product string (`iphone`), `BUS-PORT` the sysfs name (`2-1`,
`1-1.3`). `omvm-gui`'s USB buttons call the same commands.

## How it is wired

- The domain already has a USB 3 controller: `libvirt-domain.py` adds
  `-device qemu-xhci,id=omvm-usb` (libvirt's `-nodefaults` drops vmapple's own).
  No domain change or restart is needed.
- `attach` runs QEMU's monitor command
  `device_add usb-host,id=omvm-usb-BUS-PORT,bus=omvm-usb.0,hostbus=BUS,hostport=PORT`
  through `virsh qemu-monitor-command --hmp` (libvirt marks the domain
  "custom-monitor" tainted; harmless). `detach` is `device_del omvm-usb-BUS-PORT`.
- Matching is by bus and port, not by device number, so QEMU follows a device that
  re-enumerates on the same port (iPhones do that whenever their USB mode changes).
- The attachment is live only: it ends on detach, unplug-for-good or VM stop.
  Re-run `omvm usb attach` after a VM restart.
- QEMU runs as the user (`qemu:///session`). `attach` appends a line to
  `/etc/udev/rules.d/70-omvm-usb.rules` giving the user the device node
  (`OWNER=<user>, MODE=0660` for that VID:PID) and re-triggers it, so it also works
  without a local seat (remote mode, lid closed). Needs passwordless sudo.
- Host drivers on the device (Linux binds `apple-mfi-fastcharge`, `ipheth` and
  `cdc_ncm` to an iPhone) are detached by QEMU's libusb when it claims the
  interfaces. Nothing else on the host may hold the phone: no `usbmuxd`, no
  gvfs/gphoto (neither is installed on this host).
- The QEMU build needs libusb (`usb-host` in `device_add usb-host,help`); the
  `sb-kvm-bdif-write` build has it. iPhones also need the xHCI patch below.

## iPhone notes (iPhone 17 Pro, iOS 27.2, macOS 27.2 guest, 2026-11-09)

Result: usable. `devicectl list devices` shows it `connected` (paired, wired,
tunnel connected, Developer Mode on, DDI services available), Finder lists it under
Locations, Xcode/`xctrace list devices` lists it, `usbmuxd` lists it.

- **QEMU fix needed** (`patches/usb/0001-hw-usb-hcd-xhci-IOC-event-after-a-short-packet.patch`,
  commit `760d1d0d29` on the `sb-kvm-bdif-write` tree). macOS posts the phone's
  NCM receive buffers as two-TRB TDs (16384 + 16380 bytes). On a short packet,
  QEMU's `xhci_xfer_report` sent the event for the first TRB (ISP) and skipped
  the IOC event of the TD's last TRB; macOS completes a TD only on that event.
  So each NCM function got exactly 4 receive completions (`InputRecordCount` = 4)
  that macOS never saw, `netstat -I anri0` showed 0 input packets, the guest's IPv6
  neighbour solicitations went unanswered and `remoted` timed out connecting to the
  phone's RemoteServiceDiscovery port: devicectl said `unavailable` and `usbmuxd`
  listed nothing. With the IOC event sent, packets flow and CoreDevice connects.
  Built in `build/qemu-sb-bdifw/build` (old binary kept as
  `qemu-system-aarch64.pre-xhci-ioc`); the VM needs a restart to load it.
- The phone enumerates at 10 Gb/s on the host (SuperSpeed Plus); `qemu-xhci` gives
  it to the guest at 5 Gb/s. macOS sees it in `system_profiler SPUSBHostDataType`
  (`SPUSBDataType` is gone in macOS 27) and `ioreg -p IOUSB`.
- **Mode switch on the host.** The phone comes up in its charging mode (USB
  configuration 1, mode byte 4). macOS's `AppleUSBHostiOSDevice` reads the mode
  (vendor request `0xc0 0x45`) and switches it (`0xc0 0x52`, wIndex 4); on a real
  Mac the phone then drops off and comes back. Passed through, the host does not
  see that: every later request fails with EPROTO (`-71` in usbmon,
  `0xe00002ed transaction error` and "getPreferredConfiguration ... completed with
  0xe00002ed" once a second in the guest) and the phone stays in configuration 1.
  Sent from the host instead (`share/usb-apple-mode.py ensure BUS-PORT`, libusb via
  ctypes), the phone re-enumerates normally and reports mode 6; macOS then finds
  nothing to switch and selects configuration 6 (PTP, usbmux, Apple USB Ethernet,
  two NCM functions). `attach` does this for 05ac:12xx before `device_add`.
- Do not `usbreset` the phone: a second reset a minute after another left it off
  the bus (USB 2 fallback, `-71`) until the cable was replugged.
- Apple devices are attached with `guest-reset=off`: the guest's port reset would
  make QEMU reset the phone back into its charging mode. Every `device_del` does
  that too, so a re-attach always goes through the host-side switch again.
- **Watcher.** The phone also re-enumerates on its own (after Trust, after a
  reboot) and comes back in charging mode. `attach` starts
  `omvm-usb-watch-VM-BUS-PORT` (`systemd-run --user`): configuration 1 for 15 s →
  `device_del`, host-side switch, `device_add`; at most once a minute, five times.
- **Pairing.** Unpaired, the phone shows up in `xcrun devicectl list devices` with
  `pairingState: unpaired` in `--json-output`. `omvm usb trust` pauses the watcher
  (a re-attach dismisses the Trust and passcode screens), starts
  `xcrun devicectl manage pair` in the guest (this puts "Trust This Computer?" on
  the phone) and, until the state is `paired` or the time runs out (default 300 s),
  every ~5 s plays an alarm on the host speakers (volume to 90 % and unmuted,
  restored after), shows a critical desktop notification and has the guest `say`
  "Tap trust on your iPhone". After `paired` it waits 90 s before restarting the
  watcher. The owner unlocks the phone, taps Trust and enters the passcode;
  nothing here bypasses that.

## Diagnosing

```sh
lsusb -t                                     # host view: Driver=usbfs = held by QEMU
cat /sys/bus/usb/devices/2-1/bConfigurationValue   # 1 = charging mode, 6 = Mac mode
python3 share/usb-apple-mode.py get 2-1      # first byte 04 = charging, 06 = Mac mode
omvm ssh macos netstat -I anri0              # Ipkts 0 = NCM receive broken (xHCI patch missing)
virsh -c qemu:///session qemu-monitor-command macos --hmp 'info usb'
sudo modprobe usbmon; sudo cat /sys/kernel/debug/usb/usbmon/2u   # raw URBs on bus 2
virsh -c qemu:///session qemu-monitor-command macos --hmp 'trace-event usb_host_req_* on'
  # -> ~/.cache/libvirt/qemu/log/macos.log; turn it off again with "... off"
omvm ssh macos system_profiler SPUSBHostDataType
omvm ssh macos xcrun devicectl list devices
omvm ssh macos "sudo log show --last 5m --predicate 'sender CONTAINS[c] \"usb\"'"
```
