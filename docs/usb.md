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
  `sb-kvm-bdif-write` build has it.

## iPhone notes (iPhone 17 Pro, iOS 27.2, macOS 27.2 guest, 2026-11-09)

- The phone enumerates at 10 Gb/s on the host (SuperSpeed Plus); `qemu-xhci` gives
  it to the guest at 5 Gb/s. macOS sees it in `system_profiler SPUSBHostDataType`
  (`SPUSBDataType` is gone in macOS 27) and `ioreg -p IOUSB`.
- **Mode switch.** The phone comes up in its charging mode (USB configuration 1).
  macOS's `AppleUSBHostiOSDevice` reads its mode (vendor request `0xc0 0x45`) and
  switches it (`0xc0 0x52`); on a real Mac the phone then drops off and comes back.
  Passed through, the host does not see that: every later request fails with
  EPROTO (`-71` in usbmon, `0xe00002ed transaction error` in the guest's kernel
  log, "getPreferredConfiguration ... completed with 0xe00002ed" once a second) and
  the phone stays in configuration 1. A host-side reset (`usbreset BUS/DEV`)
  re-enumerates it in the new mode; QEMU follows it by port and macOS selects
  configuration 6 (PTP, usbmux, Apple USB Ethernet, two NCM functions).
  `attach` starts a watcher (`systemd-run --user`, unit
  `omvm-usb-watch-VM-BUS-PORT`) that does that reset when the device sits in
  configuration 1 for 12 s, at most once a minute and three times.
  Once, a second reset a minute after a successful one left the phone off the
  bus (the host kept retrying it at full speed on the USB 2 bus, `-71`): that
  needs the cable unplugged and plugged back.
- Apple devices are attached with `guest-reset=off`: the guest's port reset would
  make QEMU reset the phone, which drops it back to its charging mode.
- **Pairing.** Unpaired, the phone shows up in `xcrun devicectl list devices` as
  `available` (CoreDevice reaches it over the restricted NCM link, `anri0`), with
  `pairingState: unpaired` in `--json-output`. `omvm usb trust` starts
  `xcrun devicectl manage pair` in the guest (this puts "Trust This Computer?" on
  the phone) and, until the state is `paired` or the time runs out (default 300 s),
  every ~5 s plays an alarm on the host speakers (volume to 90 % and unmuted,
  restored after), shows a critical desktop notification and has the guest `say`
  "Tap trust on your iPhone". The owner unlocks the phone, taps Trust and enters
  the passcode; nothing here bypasses that.
- **After pairing** the phone re-enumerates again and needs the same reset. In the
  first test it then stayed `unavailable` in devicectl: the guest's IPv6 neighbour
  solicitations on `anri0` got no answer and `remoted` timed out connecting to the
  phone's RemoteServiceDiscovery port; `usbmuxd` logged "device connected" but
  listed no device to clients. Not resolved yet (see docs/log.md).

## Diagnosing

```sh
lsusb -t                                     # host view: Driver=usbfs = held by QEMU
cat /sys/bus/usb/devices/2-1/bConfigurationValue   # 1 = charging mode, 6 = Mac mode
virsh -c qemu:///session qemu-monitor-command macos --hmp 'info usb'
sudo modprobe usbmon; sudo cat /sys/kernel/debug/usb/usbmon/2u   # raw URBs on bus 2
virsh -c qemu:///session qemu-monitor-command macos --hmp 'trace-event usb_host_req_* on'
  # -> ~/.cache/libvirt/qemu/log/macos.log; turn it off again with "... off"
omvm ssh macos system_profiler SPUSBHostDataType
omvm ssh macos xcrun devicectl list devices
omvm ssh macos "sudo log show --last 5m --predicate 'sender CONTAINS[c] \"usb\"'"
```
