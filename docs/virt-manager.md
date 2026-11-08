# Managing macOS VMs in virt-manager

`omvm virt NAME [IMAGE]` makes a persistent VM, disk in `~/vm-artifacts/vms/NAME`, and registers it with libvirt's per-user connection (`qemu:///session`). After that, virt-manager can start it, stop it and show its screen.

```sh
omarchy pkg add libvirt virt-manager
omvm virt macos            # clone the newest image and register it
virt-manager               # "QEMU/KVM User session" → macos → Run / Open
omvm ssh macos             # SSH works as with every omvm VM
omvm virt rm macos         # unregister; the disk stays
```

- **The machine itself:** libvirt doesn't model the vmapple machine, so its devices (disks, network, sound) are passed through `<qemu:commandline>` (`share/libvirt-domain.py`). libvirt still owns the lifecycle, memory (memfd, shared), vCPUs, the VNC console and the monitor.
- **Clipboard and display:** when the VM starts, a hook turns on clipboard sharing and display-follow, so the guest resizes with the viewer window. libvirt only reads hooks from `/etc/libvirt/hooks/qemu`, so `omvm virt` installs a three-line hook there once (with sudo). That hook hands the event to `~/.config/libvirt/hooks/qemu`.
- **Graphics:** this needs the GPU stack from [graphics.md](graphics.md).
- **VM limit:** macOS allows two VMs per host. VMs started by libvirt count toward it too.
