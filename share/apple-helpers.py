#!/usr/bin/env python3
"""Root-owned Linux helper lifecycle. No account data or Apple assets are logged.

Install a validated manifest once, then use the libvirt prepare/release hook.
The UID1 driver is never unloaded, reset, or retried after a poisoned operation.
"""
import argparse
import contextlib
import errno
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import socket
import stat
import struct
import subprocess
import sys
import time
import xml.etree.ElementTree as ET

CONFIG = Path('/etc/omvm/apple-helpers.json')
RUN = Path('/run/omvm-apple-helpers')
STATE = Path('/var/lib/omvm/apple-helpers')
SEP = Path('/run/omvm-identity/sep.sock')
NAME = re.compile(r'[a-zA-Z0-9][a-zA-Z0-9_-]{0,63}\Z')
HASH = re.compile(r'[0-9a-f]{64}\Z')
DEVICE = Path('/dev/omvm-uid1-provider')
BOARD = Path('/sys/bus/platform/devices/39b060000.crypto')
MODULE = Path('/sys/module/omvm_uid1_provider')


class Failure(Exception):
    pass


def require(value, message):
    if not value:
        raise Failure(message)


def secure_file(path, limit=None):
    """Reject symlinks and user-writable ancestors before privileged reads/exec."""
    path = Path(path)
    require(path.is_absolute() and '..' not in path.parts, 'path must be absolute')
    for parent in reversed(path.parents):
        st = parent.lstat()
        require(stat.S_ISDIR(st.st_mode) and st.st_uid == 0 and not st.st_mode & 0o022,
                'artifact ancestor is not root-owned and immutable')
    fd = os.open(path, os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW)
    try:
        st = os.fstat(fd)
        require(stat.S_ISREG(st.st_mode) and st.st_uid == 0 and not st.st_mode & 0o022,
                'artifact is not a root-owned regular file')
        require(limit is None or st.st_size <= limit, 'artifact exceeds size limit')
        with os.fdopen(fd, 'rb', closefd=False) as stream:
            return stream.read()
    finally:
        os.close(fd)


def artifact(record, limit=None):
    require(isinstance(record, dict) and set(record) == {'path', 'sha256'}, 'invalid artifact record')
    require(isinstance(record['sha256'], str) and HASH.fullmatch(record['sha256']), 'invalid SHA256')
    data = secure_file(record['path'], limit)
    require(hashlib.sha256(data).hexdigest() == record['sha256'], 'artifact digest mismatch')
    return data


def validate(cfg):
    require(set(cfg) == {'version', 'allow_uid', 'provider', 'backend', 'cache', 'vms'}, 'invalid manifest fields')
    require(cfg['version'] == 1 and type(cfg['allow_uid']) is int and cfg['allow_uid'] > 0, 'invalid manifest version/uid')
    p = cfg['provider']
    require(set(p) == {'kernel', 'module', 'diagnostic', 'seeds', 'boot', 'update_m1n1'}, 'invalid provider fields')
    require(p['kernel'] == '7.2.11-15vmapple-1-ARCH', 'unreviewed provider kernel')
    for key in ('module', 'diagnostic', 'seeds', 'boot', 'update_m1n1'):
        artifact(p[key])
    require(p['module']['sha256'] == 'ee1f7ab9f1a05d2c043bd13694a095e71bb3d4d372cdd0463ba65c741841d4da', 'unreviewed UID1 module')
    require(p['diagnostic']['sha256'] == '4c016ac4e28d2dd65f4405ca32859dd5daa2fe3757f736edab6beb30d38a0b11', 'unreviewed UID1 diagnostic')
    require(p['seeds']['sha256'] == '1c6a5cc41f941e0788e436148f280dd5a875caf57929811b802aadca9e253c8d', 'wrong seed bundle')
    require(len(artifact(p['seeds'], 32)) == 32, 'wrong seed bundle size')
    artifact(cfg['backend'])
    cache = cfg['cache']
    require(set(cache) == {'path', 'files'} and cache['files'], 'invalid cache manifest')
    base = Path(cache['path'])
    for relative, digest in cache['files'].items():
        require(not Path(relative).is_absolute() and '..' not in Path(relative).parts, 'invalid cache file')
        artifact({'path':str(base / relative), 'sha256':digest})
    actual = {str(f.relative_to(base)) for f in base.rglob('*') if not f.is_dir()}
    require(actual == set(cache['files']), 'cache contains unpinned files')
    require(isinstance(cfg['vms'], dict) and cfg['vms'], 'no configured VMs')
    for name, vm in cfg['vms'].items():
        require(NAME.fullmatch(name), 'invalid VM name')
        require(set(vm) == {'identifier'}, 'invalid VM fields')
        require(len(artifact(vm['identifier'],16)) == 16, 'identifier must be exactly 16 bytes')
    return cfg


def config():
    return json.loads(secure_file(CONFIG, 1024*1024))


def command(args, timeout=30):
    result = subprocess.run(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=timeout)
    require(result.returncode == 0, 'command failed: ' + Path(args[0]).name)
    return result.stdout


def private_dir(path):
    path.mkdir(mode=0o700, parents=True, exist_ok=True)
    st = path.lstat()
    require(stat.S_ISDIR(st.st_mode) and st.st_uid == 0 and stat.S_IMODE(st.st_mode) == 0o700,
            'private directory ownership/mode mismatch')


@contextlib.contextmanager
def locked(path, timeout=90):
    private_dir(path.parent)
    fd = os.open(path, os.O_CREAT | os.O_RDWR | os.O_CLOEXEC | os.O_NOFOLLOW, 0o600)
    try:
        st=os.fstat(fd)
        require(stat.S_ISREG(st.st_mode) and st.st_uid == 0 and stat.S_IMODE(st.st_mode)==0o600,
                'lock ownership/mode mismatch')
        deadline=time.monotonic()+timeout
        while True:
            try:
                fcntl.flock(fd, fcntl.LOCK_EX|fcntl.LOCK_NB)
                break
            except BlockingIOError:
                require(time.monotonic()<deadline,'another helper operation still holds the lifecycle lock')
                time.sleep(.1)
        yield
    finally:
        os.close(fd)


def provider_status(cfg):
    data = json.loads(command([cfg['provider']['diagnostic']['path'], '-device',str(DEVICE),'-action','status']))
    status = data['status']
    require(status['state'] in (0,1,2,3), 'unknown UID1 provider state')
    require(not status['flags'] & 1, 'UID1 provider is busy')
    return status


def ensure_provider(cfg):
    validate(cfg)
    require(os.uname().release == cfg['provider']['kernel'], 'boot the reviewed provider kernel')
    require(b'apple,j314c\0' in Path('/proc/device-tree/compatible').read_bytes(), 'unsupported board')
    with locked(RUN / 'provider.lock'):
        require(not Path('/sys/module/apple_sio_aes_snapshot').exists(), 'another AES provider is loaded')
        require(Path('/sys/kernel/kexec_loaded').read_text().strip() == '0', 'kexec image is loaded')
        if MODULE.exists():
            require((BOARD/'driver').resolve().name == 'omvm-uid1-provider', 'unexpected AES owner')
        else:
            require(BOARD.is_dir() and not (BOARD/'driver').exists(), 'AES device is owned or missing')
            for irq in Path('/sys/kernel/irq').glob('*/hwirq'):
                require(int(irq.read_text()) != 0x1045d, 'AES IRQ already mapped; normal reboot required')
            Path('/proc/sys/kernel/kexec_load_disabled').write_text('1\n')
            command(['/usr/bin/insmod',cfg['provider']['module']['path'],'j314c_irq_diagnostic=1'])
            require((BOARD/'driver').resolve().name == 'omvm-uid1-provider', 'UID1 bind failed')
        expected_note=command(['/usr/bin/objcopy','--dump-section','.note.gnu.build-id=/dev/stdout',
                               cfg['provider']['module']['path'],'/dev/null'])
        require(expected_note and (MODULE/'notes/.note.gnu.build-id').read_bytes()==expected_note,
                'loaded UID1 provider does not match the reviewed module')
        initialize_provider(cfg)
        print('UID1 READY')


def initialize_provider(cfg):
    """Only advance the admitted provider state; never reset or repeat READY work."""
    st = provider_status(cfg)
    require(st['state'] != 3, 'UID1 provider is poisoned; normal platform reset required')
    if st['state'] == 0:
        require(st['completed_ops'] == 0 and st['flags'] == 0, 'unexpected untested provider state')
        command([cfg['provider']['diagnostic']['path'],'-device',str(DEVICE),'-action','selftest'])
        st=provider_status(cfg)
        require(st['state'] == 1, 'UID1 self-test did not complete')
    if st['state'] == 1:
        command([cfg['provider']['diagnostic']['path'],'-device',str(DEVICE),'-action','init','-seed-file',cfg['provider']['seeds']['path']])
        st=provider_status(cfg)
    require(st['state'] == 2, 'UID1 provider is not READY')
    require(st['flags'] & 6 == 6, 'READY provider has not retained its resources')


def unit(name):
    require(NAME.fullmatch(name), 'invalid VM name')
    return 'omvm-fairplay@'+name+'.service'


def vm_config(cfg, name):
    require(NAME.fullmatch(name) and name in cfg['vms'], 'VM is not configured for Linux helpers')
    return cfg['vms'][name]


def paths(name):
    return Path('/run/omvm-fairplay-managed-'+name)/'relay.sock', STATE/'vms'/name/'state.bin'


def peer(path, expected_pid, owner_uid=0):
    st=path.lstat()
    require(stat.S_ISSOCK(st.st_mode) and st.st_uid==owner_uid, 'helper socket owner/type mismatch')
    s=socket.socket(socket.AF_UNIX,socket.SOCK_STREAM)
    s.settimeout(2)
    try:
        s.connect(str(path))
        pid,uid,_=struct.unpack('3i',s.getsockopt(socket.SOL_SOCKET,socket.SO_PEERCRED,12))
        require(uid==0 and expected_pid>0 and pid==expected_pid, 'unexpected helper socket peer')
    finally:
        s.close()


def service_pid(name):
    values=command(['/usr/bin/systemctl','show',name,'-p','MainPID','-p','ActiveState']).decode().splitlines()
    properties=dict(x.split('=',1) for x in values if '=' in x)
    require(properties.get('ActiveState') in ('active','activating'), 'helper service is not running: '+name)
    pid=int(properties.get('MainPID','0'))
    require(pid>0,'helper service has no main process: '+name)
    return pid


def sep_peer(cfg):
    # The SEP signer intentionally gives the client UID ownership of its 0600
    # socket. SO_PEERCRED must still identify the root systemd service process.
    peer(SEP,service_pid('omvm-sep-identity.service'),owner_uid=cfg['allow_uid'])


def ready(cfg, name, acl=False, wait=30):
    vm_config(cfg,name)
    sock,_=paths(name)
    deadline=time.monotonic()+wait
    last='helper startup timed out'
    while time.monotonic()<deadline:
        try:
            status=provider_status(cfg)
            require(status['state']==2, 'UID1 is not READY')
            pid=service_pid(unit(name))
            sep_peer(cfg)
            peer(sock,pid)
            if acl:
                command(['/usr/bin/setfacl','-m',f"u:{cfg['allow_uid']}:--x",str(sock.parent)])
                command(['/usr/bin/setfacl','-m',f"u:{cfg['allow_uid']}:rw-",str(sock)])
            return
        except (Failure,OSError,ValueError) as e:
            last=str(e)
            time.sleep(.2)
    raise Failure(last)


def serve(cfg,name):
    validate(cfg)
    vm=vm_config(cfg,name)
    sock,state=paths(name)
    private_dir(state.parent)
    require(state.exists(), 'helper state is missing; explicit enrollment is required')
    secure_file(state, 16*1024*1024)
    require(provider_status(cfg)['state']==2, 'UID1 is not READY')
    sep_peer(cfg)
    os.environ['XDG_CACHE_HOME']=cfg['cache']['path']
    argv=[cfg['backend']['path'],'-socket',str(sock),'-identifier-file',vm['identifier']['path'],
          '-device-aes',str(DEVICE),'-device-aes-dsb','-state-file',str(state)]
    os.execv(argv[0],argv)


def running_guests():
    """Read /proc, not libvirt (hooks must never recurse into its daemon)."""
    names=set()
    for proc in Path('/proc').glob('[0-9]*'):
        try:
            args=(proc/'cmdline').read_bytes().split(b'\0')
            if not args or not Path(os.fsdecode(args[0])).name.startswith('qemu-system-'):
                continue
            if not any(b'vmapple' in x for x in args):
                continue
            i=args.index(b'-name')
            name=os.fsdecode(args[i+1]).split(',')[0].removeprefix('guest=')
            names.add(name)
        except (OSError,ValueError,IndexError):
            continue
    return names


def domain(name,xml):
    require(len(xml)<=2*1024*1024, 'domain XML too large')
    root=ET.fromstring(xml)
    require(root.findtext('name')==name, 'domain name mismatch')
    return root


def check_domain(name,root):
    ns='{http://libvirt.org/schemas/domain/qemu/1.0}'
    args=[x.attrib.get('value','') for x in root.findall('.//'+ns+'arg')]
    machines=[]
    for i,arg in enumerate(args):
        if arg in ('-machine','-M'):
            require(i+1<len(args),'truncated machine option')
            machines.append(args[i+1].split(',')[0])
        require(not (arg=='-global' and i+1<len(args) and args[i+1].startswith('apple-fairplay-pci.')),
                'FairPlay global overrides are not allowed')
    require(len(machines)<=1 and all(m=='vmapple' or '=' in m for m in machines),'ambiguous machine configuration')
    sock,_=paths(name)
    identities=[e.attrib.get('value','') for e in root.findall('.//'+ns+'env') if e.attrib.get('name')=='OMVM_IDENTITY_SIGNER']
    require(identities==[str(SEP)],'domain is missing its configured Linux SEP socket')
    devices=[]
    for i,arg in enumerate(args):
        if arg=='-device':
            require(i+1<len(args),'truncated QEMU device option')
            parts=args[i+1].split(',')
            if parts[0]=='apple-fairplay-pci':devices.append(parts[1:])
    require(len(devices)==1,'domain needs exactly one FairPlay device')
    properties=[p.split('=',1) for p in devices[0] if '=' in p]
    require([v for k,v in properties if k=='relay-socket']==[str(sock)],'domain has the wrong FairPlay socket')


def wait_for_clock(timeout=30):
    """Do not seed a guest RTC from an unsynchronized Asahi host clock."""
    deadline=time.monotonic()+timeout
    while True:
        remaining=deadline-time.monotonic()
        if remaining<=0:break
        try:
            synchronized=command(['/usr/bin/timedatectl','show','-p','NTPSynchronized','--value'],
                                 timeout=min(5,remaining)).strip()
            if synchronized==b'yes':return
        except (Failure,OSError,subprocess.TimeoutExpired):
            # Unavailable time service is not evidence of a synchronized clock.
            pass
        remaining=deadline-time.monotonic()
        if remaining<=0:break
        time.sleep(min(.25,remaining))
    raise Failure('host clock is not synchronized; check timedatectl and the network/time service, '
                  'then retry VM start (no guest was started)')


def gate(cfg,name,operation,phase,xml):
    require(NAME.fullmatch(name), 'invalid VM name')
    caller=int(os.environ.get('SUDO_UID','0'))
    require(caller in (0,cfg['allow_uid']), 'caller cannot operate this helper configuration')
    if (operation,phase) not in [('prepare','begin'),('release','end')]:
        return
    root=domain(name,xml)
    machine=root.find('os/type')
    managed=name in cfg['vms']
    args=[e.attrib.get('value','') for e in root.findall('.//{http://libvirt.org/schemas/domain/qemu/1.0}arg')]
    vmapple=(machine is not None and machine.attrib.get('machine')=='vmapple') or any(
        v in ('-machine','-M') and i+1<len(args) and args[i+1].split(',')[0]=='vmapple'
        for i,v in enumerate(args))
    require(not managed or vmapple,'configured helper VM is not a vmapple domain')
    if not vmapple:return
    if not managed:
        require(b'/run/omvm-fairplay-' not in xml,'Linux helper VM is absent from root manifest')
    with locked(RUN/'guest.lock'):
        reservation=RUN/'active.json'
        running=running_guests()
        if operation=='release':
            if reservation.exists():
                active=json.loads(secure_file(reservation,4096))
                if active['vm']==name and name not in running:
                    reservation.unlink()
            return
        if managed:check_domain(name,root)
        require(not running, 'another macOS guest is running; stop it before starting this VM')
        if reservation.exists():
            active=json.loads(secure_file(reservation,4096))
            # release/end owns clearing successful or aborted prepares. Never time out
            # an uncertain reservation while the same libvirt daemon could still start.
            require(not Path('/proc/'+str(active['daemon_pid'])).exists(),
                    'another VM start is reserved; wait for release/end or inspect the daemon')
        # Only guest launch depends on clock synchronization. Existing helpers
        # can start at boot without network access and are never reinitialized here.
        wait_for_clock()
        if reservation.exists():
            reservation.unlink()
        if managed:
            command(['/usr/bin/systemctl','start',unit(name)],timeout=120)
            ready(cfg,name,acl=True)
        record={'vm':name,'daemon_pid':os.getppid()}
        # sudo's parent may be the hook shell, which is short-lived. Record the
        # nearest virtqemud ancestor instead so a crashed hook cannot clear a live start.
        pid=os.getppid()
        command_line=''
        for _ in range(12):
            try:
                command_line=Path(f'/proc/{pid}/comm').read_text().strip()
                if command_line in ('virtqemud','libvirtd'):
                    record['daemon_pid']=pid
                    break
                status=Path(f'/proc/{pid}/status').read_text()
                pid=int(re.search(r'^PPid:\s+(\d+)',status,re.M).group(1))
            except (OSError,AttributeError):
                break
        else:
            raise Failure('cannot identify the libvirt daemon')
        require(command_line in ('virtqemud','libvirtd'), 'gate must run from a libvirt hook')
        fd=os.open(reservation,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
        with os.fdopen(fd,'w') as f:
            json.dump(record,f)
            f.flush()
            os.fsync(f.fileno())


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('action',choices=['validate','provider','serve','ready','gate','enroll','status'])
    p.add_argument('args',nargs='*')
    a=p.parse_args()
    require(os.geteuid()==0,'root is required')
    cfg=config()
    if a.action=='validate':
        validate(cfg); print('manifest verified')
    elif a.action=='provider':
        ensure_provider(cfg)
    elif a.action=='serve':
        serve(cfg,*a.args)
    elif a.action=='ready':
        ready(cfg,*a.args,acl=True)
    elif a.action=='gate':
        require(len(a.args)==3,'gate requires VM operation phase')
        gate(cfg,*a.args,sys.stdin.buffer.read(2*1024*1024+1))
    elif a.action=='enroll':
        require(len(a.args)==1,'enroll requires VM')
        validate(cfg)
        vm=vm_config(cfg,a.args[0]); _,state=paths(a.args[0])
        require(not running_guests(),'stop all macOS guests before explicit enrollment')
        private_dir(state.parent)
        command([cfg['backend']['path'],'-identifier-file',vm['identifier']['path'],
                 '-state-file',str(state),'-initialize-state'])
        print('empty helper state initialized; account recovery is not yet verified')
    elif a.action=='status':
        name=a.args[0]; vm_config(cfg,name)
        try:
            ready(cfg,name,wait=1)
            print('Linux helpers READY; Apple Account and service status are separate')
        except (Failure,OSError) as e:
            print('Linux helpers unavailable: '+str(e)); return 1
    return 0


if __name__=='__main__':
    try:
        sys.exit(main())
    except (Failure,OSError,ValueError,KeyError,TypeError,ET.ParseError,subprocess.TimeoutExpired) as exc:
        print('omvm helpers: '+str(exc),file=sys.stderr)
        sys.exit(1)
