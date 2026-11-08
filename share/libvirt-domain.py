#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Print a libvirt (qemu:///session) domain for an omvm macOS guest, so it can be
started, stopped and viewed from virt-manager / virsh.

    libvirt-domain.py NAME VMDIR QEMU_BIN FIRMWARE ECID SSH_PORT [CPUS] [RAM_GIB]

VMDIR holds disk.img, aux.img.trimmed (and vm.json). The vmapple machine and its
devices are not modelled by libvirt, so they are passed as QEMU arguments; libvirt
owns the lifecycle, memory (memfd, shared), vCPUs, the VNC console and the monitor.
"""
import os, sys, uuid
from xml.sax.saxutils import quoteattr

name, vmdir, qemu, fw, ecid, ssh_port = sys.argv[1:7]
cpus = sys.argv[7] if len(sys.argv) > 7 else "8"
ram = sys.argv[8] if len(sys.argv) > 8 else "16"
qdir = os.path.dirname(qemu)
home = os.path.expanduser("~")
icd = os.environ.get("VK_DRIVER_FILES", f"{home}/opt/mesa-honeykrisp-sb/share/vulkan/icd.d/asahi_icd.aarch64.json")
aux, disk = f"{vmdir}/aux.img.trimmed", f"{vmdir}/disk.img"
# Stable libvirt UUID per VM name.
dom_uuid = uuid.uuid5(uuid.NAMESPACE_URL, f"omvm:{name}")
mac = "52:54:00:%02x:%02x:%02x" % tuple(dom_uuid.bytes[:3])

args = [
    "-machine", f"uuid={ecid},aux-ram-share=on",
    "-L", f"{qdir}/qemu-bundle/usr/local/share/qemu",
    "-drive", f"if=pflash,format=raw,file.filename={aux},file.locking=off",
    "-drive", f"if=pflash,format=raw,file.filename={disk},file.locking=off",
    "-drive", f"if=none,format=raw,file.filename={aux},file.locking=off,cache=unsafe,id=aux",
    "-device", "vmapple-virtio-blk-pci,variant=aux,drive=aux,share-rw=on",
    "-drive", f"if=none,format=raw,file.filename={disk},file.locking=off,cache=unsafe,id=root",
    "-device", "vmapple-virtio-blk-pci,variant=root,drive=root,share-rw=on",
    "-netdev", f"user,id=net0,ipv6=off,hostfwd=tcp:127.0.0.1:{ssh_port}-:22",
    "-device", f"virtio-net-pci,netdev=net0,mac={mac}",
    "-audiodev", "none,id=snd0",
    "-device", "virtio-sound-pci,audiodev=snd0,streams=1",
]
env = {
    "VK_DRIVER_FILES": icd,
    "REIMS_VGPU_WINDOW": "0",
    "REIMS_VGPU_MAX_REFRESH_HZ": "60",
    "REIMS_VGPU_DRAW_LOG_PATH": "off",
    "TMPDIR": f"{home}/.cache/reims-vgpu",
}
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
