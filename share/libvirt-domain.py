#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Print a libvirt (qemu:///session) domain for an omvm macOS guest, so it can be
started, stopped and viewed from virt-manager / virsh.

    libvirt-domain.py NAME VMDIR QEMU_BIN FIRMWARE ECID SSH_PORT [CPUS] [RAM_GIB]

VMDIR holds disk.img, aux.img.trimmed (and vm.json), plus optional switch files:
guest_major (e.g. 27; docs/graphics.md "macOS 27 updates") and apple_vendor_cap.
The vmapple machine and its devices are not modelled by libvirt, so they are
passed as QEMU arguments; libvirt owns the lifecycle, memory (memfd, shared), vCPUs, the VNC console and the monitor.
"""
import json, os, sys, uuid
from xml.sax.saxutils import quoteattr

name, vmdir, qemu, fw, ecid, ssh_port = sys.argv[1:7]
cpus = sys.argv[7] if len(sys.argv) > 7 else "8"
ram = sys.argv[8] if len(sys.argv) > 8 else "16"
qdir = os.path.dirname(qemu)
home = os.path.expanduser("~")
# macOS 27 guests (VMDIR/guest_major holds 27 or more): their virtio transport
# loops forever on QEMU's descending PCI capability list, so the disks, network
# and sound link their capabilities in address order (QEMU patches 0006, 0007).
try:
    major = int(open(f"{vmdir}/guest_major").read().strip() or 0)
except (OSError, ValueError):
    major = 0
asc = major >= 27
# Apple's vendor capability (VMDIR/apple_vendor_cap) also reorders, but it says
# "transport encryption disabled": only for images installed with it, never for a
# 26 image updated to 27 (its data-protected files become unreadable).
vcap = ",apple-vendor-cap=on" if os.path.exists(f"{vmdir}/apple_vendor_cap") else ""
blk = vcap or (",ascending-capabilities=on" if asc else "")
virtio_asc = ",x-ascending-capabilities=on" if asc else ""
icd = os.environ.get("VK_DRIVER_FILES", f"{home}/opt/mesa-honeykrisp-sb/share/vulkan/icd.d/asahi_icd.aarch64.json")
aux, disk = f"{vmdir}/aux.img.trimmed", f"{vmdir}/disk.img"
# Stable libvirt UUID per VM name.
dom_uuid = uuid.uuid5(uuid.NAMESPACE_URL, f"omvm:{name}")
mac = "52:54:00:%02x:%02x:%02x" % tuple(dom_uuid.bytes[:3])
xdg = os.environ.get("XDG_RUNTIME_DIR", f"/run/user/{os.getuid()}")
AUDIODEV = f"pipewire,id=snd0,out.stream-name={name},in.stream-name={name}"

# The SysCfg serial and MLB Apple personalised this VM with, if known. Both are
# plain files beside the image so the values stay out of this script; without
# them QEMU falls back to its placeholders (serial 1234, no MLB).
identity_args = ""
for prop, fname in (("serial", "serial"), ("mlb", "mlb")):
    path = os.path.join(vmdir, fname)
    if os.path.isfile(path):
        value = open(path).read().strip()
        if value:
            identity_args += f",{prop}={value}"

args = [
    "-machine", f"uuid={ecid},aux-ram-share=on,identity=on{identity_args}",
    "-L", f"{qdir}/qemu-bundle/usr/local/share/qemu",
    "-drive", f"if=pflash,format=raw,file.filename={aux},file.locking=off",
    "-drive", f"if=pflash,format=raw,file.filename={disk},file.locking=off",
    "-drive", f"if=none,format=raw,file.filename={aux},file.locking=off,cache=unsafe,id=aux",
    "-device", f"vmapple-virtio-blk-pci,variant=aux,drive=aux,share-rw=on{blk}",
    "-drive", f"if=none,format=raw,file.filename={disk},file.locking=off,cache=unsafe,id=root",
    "-device", f"vmapple-virtio-blk-pci,variant=root,drive=root,share-rw=on{blk}",
    "-netdev", f"user,id=net0,ipv6=off,hostfwd=tcp:127.0.0.1:{ssh_port}-:22",
    "-device", f"virtio-net-pci,netdev=net0,mac={mac}{virtio_asc}",
    # libvirt runs QEMU with -nodefaults, which drops vmapple's default USB
    # keyboard and tablet: add them back.
    "-device", "qemu-xhci,id=omvm-usb",
    "-device", "usb-kbd,bus=omvm-usb.0",
    "-device", "usb-vmapple-tablet,bus=omvm-usb.0",
    # Sound: virtio-snd (macOS's AppleVirtIOSound, "Apple Virtual Sound Device")
    # on the host's PipeWire. Stream 0 is output (the guest's speakers), stream 1
    # input (its microphone, the host's default source).
    "-audiodev", AUDIODEV,
    "-device", f"virtio-sound-pci,audiodev=snd0,streams=2{virtio_asc}",
]
# The paravirtual M2 scaler (106b:1a0b, reims-vgpu's scaler on the host GPU), which
# a guest's VideoToolbox would use for pixel transfers instead of a Metal compute
# fallback. Opt-in (OMVM_M2SCALER=1): the host side starts (kernels made on the M1
# Max), but a macOS 27.2 guest's kernel collection has no AppleM2ScalerParavirtDriver,
# so nothing binds it there (docs/graphics.md, "The M2 scaler").
if os.environ.get("OMVM_M2SCALER", "0") == "1":
    args += ["-device", "apple-m2scaler-pci"]
# Second NIC on a UDP socket, for kdp. A userspace terminator
# bridges it to a TUN peer: kdp's LLDB transport is
# guest-initiated and the user-mode net0 cannot carry it. Opt-in (OMVM_KDP=1).
# The guest UART (0x20010000) is wired to serial_hd(0). Capturing it gives the
# AVPBooter and XNU panic text, which is otherwise only on a console we do not
# have. Opt-in (OMVM_SERIAL=/path/to/log).
if os.environ.get("OMVM_SERIAL"):
    args += ["-serial", f"file:{os.environ['OMVM_SERIAL']}"]
if os.environ.get("OMVM_KDP", "0") == "1":
    args += ["-netdev", "socket,id=net1,udp=127.0.0.1:42001,localaddr=127.0.0.1:42002",
             "-device", f"virtio-net-pci,netdev=net1,mac=52:54:00:c4:07:47{virtio_asc}"]
env = {
    "VK_DRIVER_FILES": icd,
    "REIMS_VGPU_WINDOW": "0",
    "REIMS_VGPU_MAX_REFRESH_HZ": "60",
    "REIMS_VGPU_DRAW_LOG_PATH": "off",
    # reims-vgpu's own error lines (a refused dispatch it skips, say) in the
    # domain's log; silent otherwise.
    "REIMS_VGPU_LOG": "error",
    "TMPDIR": f"{home}/.cache/reims-vgpu",
    "XDG_RUNTIME_DIR": xdg,   # the user's PipeWire socket, for sound
    # Maps the AVP config DMA mailbox at 0x4ffff8. The identity device is
    # useless without it: the platform expert fetches the host key (the UDID)
    # through that mailbox, and IdentityService asserts on it and never queues.
    "OMVM_MAILBOX": "1",
}
# Identity-payload options for the experimental QEMU identity device.
# Source and transport notes are preserved under contrib/apple-services/.
# ID_SELFDESC serves the 4/4 and 4/6 payload as a serialised message; the 4/3
# shape and 32-byte body are what the guest accepts.
env.setdefault("ID_SELFDESC", "1")
env.setdefault("ID_S3", "1")
env.setdefault("ID_BLEN64", "1")
env.setdefault("ID_BO4", "1")
for _k in ("ID_BLEN64", "ID_S3", "ID_SELFDESC", "ID_NB0", "ID_BO4"):
    if os.environ.get(_k):
        env[_k] = os.environ[_k]
# Experimental real-SEP identity bridge, explicitly enabled per VM. Keep this
# beside the VM artifacts so `omvm virt` preserves the operator's provider.
provider_file = os.path.join(vmdir, "identity-provider.json")
if os.path.exists(provider_file):
    with open(provider_file) as provider_stream:
        provider = json.load(provider_stream)
    expected = {"certificate_chain", "public_key", "trust_root", "socket"}
    if not isinstance(provider, dict) or set(provider) != expected:
        raise SystemExit("identity-provider.json must contain exactly four provider paths")
    for key, variable in (("certificate_chain", "OMVM_IDENTITY_CERT_CHAIN"),
                          ("public_key", "OMVM_IDENTITY_PUBLIC_KEY"),
                          ("trust_root", "OMVM_IDENTITY_TRUST_ROOT")):
        value = provider[key]
        if not isinstance(value, str) or not value:
            raise SystemExit("identity provider file paths must be nonempty strings")
        path = os.path.abspath(os.path.join(vmdir, value))
        if not os.path.isfile(path):
            raise SystemExit("identity provider file is missing: " + key)
        env[variable] = path
    endpoint = provider["socket"]
    if not isinstance(endpoint, str) or not endpoint.startswith("/") or len(endpoint.encode()) >= 108:
        raise SystemExit("identity provider socket must be a valid absolute Unix path")
    env["OMVM_IDENTITY_SIGNER"] = endpoint

x = lambda s: quoteattr(str(s))
print(f"""<domain type='kvm' xmlns:qemu='http://libvirt.org/schemas/domain/qemu/1.0'>
  <name>{name}</name>
  <uuid>{dom_uuid}</uuid>
  <title>macOS ({name})</title>
  <description>omvm macOS guest. SSH: omvm ssh {name} (port {ssh_port}).</description>
  <metadata><omvm xmlns='https://github.com/sapoepsilon/omvm'><vmdir>{vmdir}</vmdir><ssh>{ssh_port}</ssh></omvm></metadata>
  <memory unit='GiB'>{ram}</memory>
  <memoryBacking><source type='memfd'/><access mode='shared'/></memoryBacking>
  <vcpu>{cpus}</vcpu>
  <os>
    <type arch='aarch64' machine='vmapple'>hvm</type>
    <loader type='rom' readonly='yes'>{fw}</loader>
  </os>
  <cpu mode='host-passthrough'/>
  <on_reboot>restart</on_reboot>
  <devices>
    <emulator>{qemu}</emulator>
    <graphics type='vnc' autoport='yes' listen='127.0.0.1'><listen type='address' address='127.0.0.1'/></graphics>
    <video><model type='none'/></video>
    <memballoon model='none'/>
  </devices>
  <qemu:commandline>""")
for a in args:
    print(f"    <qemu:arg value={x(a)}/>")
for k, v in env.items():
    print(f"    <qemu:env name={x(k)} value={x(v)}/>")
print("""  </qemu:commandline>
</domain>""")
