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
import tempfile
import time
import uuid
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
PID_RUN = Path('/run/user')
REVIEWED_DIAGNOSTIC_SHA256 = {
    '4c016ac4e28d2dd65f4405ca32859dd5daa2fe3757f736edab6beb30d38a0b11',
    'b6c0543eae149de5eb1c0e24c0cd0c39d9a33d0ab00c9a903eee1845179c5fcc',
}


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


def max_active_vms(cfg):
    maximum = cfg.get('max_active_vms', 1)
    require(type(maximum) is int and maximum in (1, 2), 'max_active_vms must be 1 or 2')
    return maximum


def executable_identity(record):
    st = Path(record['path']).lstat()
    require(stat.S_ISREG(st.st_mode) and st.st_uid == 0 and st.st_mode & 0o111,
            'pinned program must be a root-owned executable')
    return st.st_dev, st.st_ino


def backend_executable(cfg):
    return executable_identity(cfg['backend'])


def transaction_capabilities(record, identity, description):
    """This pinned probe must not open the provider or initialize account state."""
    before = identity()
    try:
        capabilities = json.loads(command([record['path'], '-print-capabilities'], timeout=5))
    except (Failure, OSError, ValueError, subprocess.TimeoutExpired):
        raise Failure('two-VM mode requires a '+description+' with transaction flock capability') from None
    require(isinstance(capabilities, dict)
            and type(capabilities.get('schema_version')) is int
            and capabilities['schema_version'] == 1
            and capabilities.get('device_aes_arbitration') == 'transaction-flock-v1',
            'two-VM mode requires a '+description+' with transaction flock capability')
    require(identity() == before, 'pinned program changed during capability verification')


def backend_capabilities(cfg):
    transaction_capabilities(cfg['backend'], lambda: backend_executable(cfg), 'backend')


def validate(cfg):
    fields = {'version', 'allow_uid', 'provider', 'backend', 'cache', 'vms'}
    require(isinstance(cfg, dict) and set(cfg) in (fields, fields | {'max_active_vms'}), 'invalid manifest fields')
    maximum = max_active_vms(cfg)
    require(cfg['version'] == 1 and type(cfg['allow_uid']) is int and cfg['allow_uid'] > 0, 'invalid manifest version/uid')
    p = cfg['provider']
    require(set(p) == {'kernel', 'module', 'diagnostic', 'seeds', 'boot', 'update_m1n1'}, 'invalid provider fields')
    require(p['kernel'] == '7.2.11-15vmapple-1-ARCH', 'unreviewed provider kernel')
    for key in ('module', 'diagnostic', 'seeds', 'boot', 'update_m1n1'):
        artifact(p[key])
    require(p['module']['sha256'] == 'ee1f7ab9f1a05d2c043bd13694a095e71bb3d4d372cdd0463ba65c741841d4da', 'unreviewed UID1 module')
    require(p['diagnostic']['sha256'] in REVIEWED_DIAGNOSTIC_SHA256, 'unreviewed UID1 diagnostic')
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
    identifiers = set()
    for name, vm in cfg['vms'].items():
        require(NAME.fullmatch(name), 'invalid VM name')
        require(set(vm) == {'identifier'}, 'invalid VM fields')
        identifier = artifact(vm['identifier'],16)
        require(len(identifier) == 16, 'identifier must be exactly 16 bytes')
        if maximum == 2:
            require(identifier not in identifiers, 'two-VM mode requires distinct enrolled identifiers')
            identifiers.add(identifier)
    if maximum == 2:
        backend_capabilities(cfg)
        transaction_capabilities(p['diagnostic'], lambda: executable_identity(p['diagnostic']), 'diagnostic')
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
    # A read-only status can race a sibling transaction. The backend's device
    # flock, not a snapshot of this flag, arbitrates actual hardware work.
    require(not status['flags'] & 1 or (max_active_vms(cfg) == 2 and status['state'] == 2),
            'UID1 provider is busy')
    return status


def require_ready(status):
    require(status['state'] != 3, 'UID1 provider is poisoned; normal platform reset required')
    require(status['state'] == 2, 'UID1 is not READY')
    require(status['flags'] & 6 == 6, 'READY provider has not retained its resources')


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


def service_properties(name):
    values=command(['/usr/bin/systemctl','show',name,'-p','MainPID','-p','ActiveState']).decode().splitlines()
    return dict(x.split('=',1) for x in values if '=' in x)


def service_pid(name):
    properties=service_properties(name)
    require(properties.get('ActiveState') in ('active','activating'), 'helper service is not running: '+name)
    pid=int(properties.get('MainPID','0'))
    require(pid>0,'helper service has no main process: '+name)
    return pid


def sep_peer(cfg):
    # The SEP signer intentionally gives the client UID ownership of its 0600
    # socket. SO_PEERCRED must still identify the root systemd service process.
    peer(SEP,service_pid('omvm-sep-identity.service'),owner_uid=cfg['allow_uid'])


def running_fairplay_processes():
    """Find hardware backends outside the admitted systemd instances as well."""
    pids = set()
    for proc in Path('/proc').glob('[0-9]*'):
        try:
            args = (proc/'cmdline').read_bytes().split(b'\0')
        except (FileNotFoundError, ProcessLookupError):
            continue
        except OSError:
            raise Failure('cannot verify running FairPlay processes') from None
        if any(arg.split(b'=', 1)[0] in (b'-device-aes', b'--device-aes') for arg in args):
            pids.add(int(proc.name))
    return pids


def verify_running_backends(cfg, expected, starting=None):
    """Never mix the new arbiter with an old or unmanaged hardware backend."""
    output = command(['/usr/bin/systemctl', 'list-units', '--type=service',
                      '--state=active,activating,deactivating', '--no-legend', '--plain',
                      '--no-pager', 'omvm-fairplay*.service'])
    allowed = {unit(name): name for name in cfg['vms']}
    admitted = set()
    for line in output.decode().splitlines():
        if not line.strip():
            continue
        service = line.split()[0]
        require(service in allowed, 'a legacy or unmanaged FairPlay service is running')
        properties = service_properties(service)
        require(properties.get('ActiveState') in ('active', 'activating'),
                'a FairPlay service is stopping; wait for it to stop')
        pid = int(properties.get('MainPID', '0'))
        # A unit waiting on the provider dependency has no executable yet.
        if properties['ActiveState'] == 'activating' and pid == 0:
            continue
        require(pid > 0, 'a FairPlay service has no main process')
        require(pid not in admitted, 'ambiguous FairPlay service process')
        admitted.add(pid)
        if starting == (service, pid):
            continue
        try:
            st = Path(f'/proc/{pid}/exe').stat()
        except OSError:
            raise Failure('cannot verify a running FairPlay executable') from None
        require((st.st_dev, st.st_ino) == expected, 'a running FairPlay backend does not match the pinned executable')
        sock, _ = paths(allowed[service])
        peer(sock, pid)
    require(running_fairplay_processes() <= admitted, 'an unmanaged FairPlay hardware backend is running')
    return admitted


def ready(cfg, name, acl=False, wait=30):
    vm_config(cfg,name)
    maximum = max_active_vms(cfg)
    if maximum == 2:
        validate(cfg)
        expected = backend_executable(cfg)
    sock,_=paths(name)
    deadline=time.monotonic()+wait
    last='helper startup timed out'
    while time.monotonic()<deadline:
        try:
            status=provider_status(cfg)
            require_ready(status)
            pid=service_pid(unit(name))
            if maximum == 2:
                require(pid in verify_running_backends(cfg, expected), 'helper service changed during readiness')
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
    require_ready(provider_status(cfg))
    if max_active_vms(cfg) == 2:
        admitted = verify_running_backends(cfg, backend_executable(cfg), starting=(unit(name), os.getpid()))
        require(os.getpid() in admitted, 'two-VM helpers must run in their configured systemd service')
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


def uuid_digest(value):
    try:
        return hashlib.sha256(uuid.UUID(value).bytes).hexdigest()
    except (ValueError, AttributeError, TypeError):
        raise Failure('domain needs one valid UUID') from None


def domain_uuid(root):
    values=root.findall('uuid')
    require(len(values)==1, 'domain needs one valid UUID')
    return uuid_digest(values[0].text)


def guest_process(proc):
    """A stable physical QEMU identity, independent of libvirt reparenting."""
    pid = int(proc.name)
    try:
        before = process_start(pid)
    except (Failure, OSError):
        before = None
    try:
        raw = (proc/'cmdline').read_bytes().split(b'\0')
    except (FileNotFoundError, ProcessLookupError):
        return None
    except OSError:
        raise Failure('cannot inspect running guests') from None
    if not raw or not Path(os.fsdecode(raw[0])).name.startswith('qemu-system-'):
        return None
    if not any(b'vmapple' in arg for arg in raw):
        return None
    guest = {'pid': pid, 'name': None}
    try:
        args = [os.fsdecode(arg) for arg in raw]
        names = qemu_options(args, ('-name',))
        if len(names) == 1:
            values=[]
            for i, part in enumerate(names[0].split(',')):
                key, separator, value = part.partition('=')
                if key == 'guest' and separator:
                    values.append(value)
                elif i == 0 and not separator:
                    values.append(key)
            if len(values) == 1 and NAME.fullmatch(values[0]):
                guest['name'] = values[0]
        identities = qemu_options(args, ('-uuid',))
        if len(identities) == 1:
            guest['uuid_sha256'] = uuid_digest(identities[0])
        # libvirt supplies the type; omvm adds a separate -machine clause
        # containing only identity/storage properties. Those do not select
        # another type. Duplicate or conflicting explicit types still fail.
        guest['machine_verified'] = [types for types in machine_types(args) if types] == [['vmapple']]
    except Failure:
        guest = {'pid': pid, 'name': None}
    try:
        after = process_start(pid)
    except (Failure, OSError):
        after = None
    if before is None or after != before:
        # Retain the physical slot without binding old argv to a recycled PID.
        return {'pid': pid, 'name': None}
    guest['start'] = before
    return guest


def running_guest_processes():
    """Keep every observed vmapple PID, including unnamed/uncertain processes."""
    guests = []
    for proc in Path('/proc').glob('[0-9]*'):
        guest = guest_process(proc)
        if guest is not None:
            guests.append(guest)
    return guests


def process_start(pid):
    """Linux starttime distinguishes a live daemon from a reused PID."""
    require(type(pid) is int and pid > 0, 'invalid process identity')
    try:
        value = Path(f'/proc/{pid}/stat').read_text()
    except (FileNotFoundError, ProcessLookupError):
        return None
    # comm can contain whitespace and parentheses; the last ')' ends it.
    fields = value.rsplit(')', 1)
    require(len(fields) == 2, 'cannot verify process identity')
    try:
        started = int(fields[1].split()[19])
    except (IndexError, ValueError):
        raise Failure('cannot verify process identity') from None
    require(started >= 0, 'cannot verify process identity')
    return started


def daemon_identity(pid=None):
    """Hook/sudo shells exit early; reserve against the owning libvirt daemon."""
    pid = os.getppid() if pid is None else pid
    for _ in range(12):
        try:
            before = process_start(pid)
            require(before is not None, 'gate must run from a live libvirt hook')
            name = Path(f'/proc/{pid}/comm').read_text().strip()
            if name in ('virtqemud', 'libvirtd'):
                require(process_start(pid) == before, 'libvirt daemon changed while reserving a start')
                return {'daemon_pid': pid, 'daemon_start': before}
            status = Path(f'/proc/{pid}/status').read_text()
            parent = int(re.search(r'^PPid:\s+(\d+)', status, re.M).group(1))
            require(process_start(pid) == before, 'hook ancestry changed while reserving a start')
            pid = parent
        except (OSError, AttributeError, ValueError):
            break
    raise Failure('gate must run from a libvirt hook')


def read_reservation(path):
    require(stat.S_IMODE(path.lstat().st_mode) == 0o600, 'reservation ownership/mode mismatch')
    record = json.loads(secure_file(path, 4096))
    base = {'version', 'vm', 'daemon_pid', 'daemon_start'}
    require(isinstance(record, dict) and base <= set(record)
            and type(record['version']) is int and record['version'] in (2, 3)
            and isinstance(record['vm'], str) and NAME.fullmatch(record['vm'])
            and path.name == record['vm'] + '.json'
            and type(record['daemon_pid']) is int and record['daemon_pid'] > 0
            and type(record['daemon_start']) is int and record['daemon_start'] >= 0,
            'invalid two-VM reservation; inspect it before starting guests')
    if record['version'] == 2:
        require(set(record) == base, 'invalid legacy two-VM reservation')
    else:
        fields = base | {'uuid_sha256', 'prepare_tick'}
        require(set(record) in (fields, fields | {'qemu_pid', 'qemu_start'})
                and isinstance(record['uuid_sha256'], str) and HASH.fullmatch(record['uuid_sha256'])
                and type(record['prepare_tick']) is int and record['prepare_tick'] >= record['daemon_start'],
                'invalid launch reservation')
        if 'qemu_pid' in record:
            require(type(record['qemu_pid']) is int and record['qemu_pid'] > 0
                    and type(record['qemu_start']) is int and record['qemu_start'] > record['prepare_tick'],
                    'invalid bound launch identity')
    return record


def reservation_slots(directory, running):
    """Count only pending starts; the matching live QEMU already owns its slot."""
    names = [guest['name'] for guest in running if guest['name'] is not None]
    require(len(names) == len(set(names)), 'duplicate running guest names; inspect guests before starting another')
    pending = set()
    for path in directory.iterdir():
        require(path.suffix == '.json', 'unexpected two-VM reservation entry')
        record = read_reservation(path)
        represented = 'qemu_pid' in record and any(
            guest['name'] == record['vm']
            and guest['pid'] == record['qemu_pid']
            and guest.get('start') == record['qemu_start']
            and guest.get('uuid_sha256') == record['uuid_sha256']
            and guest.get('machine_verified') is True
            for guest in running)
        if not represented:
            # Daemon death/PID reuse does not prove that an orphaned pre-exec
            # launch child is gone. Only started/begin binds an exact QEMU;
            # an old/unbound record remains pending until its owning release
            # or explicit all-off cleanup.
            pending.add(record['vm'])
    return len(running) + len(pending), set(names), pending


def prepare_epoch():
    """Return a boot tick that has ended before libvirt may spawn the QEMU."""
    frequency = os.sysconf('SC_CLK_TCK')
    def ticks():
        return time.clock_gettime_ns(time.CLOCK_BOOTTIME) * frequency // 1_000_000_000
    started = ticks()
    deadline = time.monotonic() + 1
    while ticks() <= started:
        require(time.monotonic() < deadline, 'cannot establish launch start ordering')
        time.sleep(min(1 / frequency, .01))
    return started


@contextlib.contextmanager
def canonical_pid_file(cfg, name):
    """Open only the canonical session-libvirt PID file; never follow links."""
    require(NAME.fullmatch(name), 'invalid VM name')
    for parent in reversed(PID_RUN.parents):
        st = parent.lstat()
        require(stat.S_ISDIR(st.st_mode) and st.st_uid == 0 and not st.st_mode & 0o022,
                'untrusted libvirt runtime directory')
    flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC
    directory = os.open(PID_RUN, flags)
    fd = None
    try:
        st = os.fstat(directory)
        require(stat.S_ISDIR(st.st_mode) and st.st_uid == 0 and not st.st_mode & 0o022,
                'untrusted libvirt runtime directory')
        for part in (str(cfg['allow_uid']), 'libvirt', 'qemu', 'run'):
            child = os.open(part, flags, dir_fd=directory)
            os.close(directory)
            directory = child
            st = os.fstat(directory)
            require(stat.S_ISDIR(st.st_mode) and st.st_uid == cfg['allow_uid'] and not st.st_mode & 0o022,
                    'untrusted libvirt runtime directory')
        fd = os.open(name + '.pid', os.O_RDONLY | os.O_NONBLOCK | os.O_NOFOLLOW | os.O_CLOEXEC,
                     dir_fd=directory)
        st = os.fstat(fd)
        require(stat.S_ISREG(st.st_mode) and st.st_uid == cfg['allow_uid']
                and not st.st_mode & 0o022 and st.st_size <= 32,
                'untrusted libvirt domain PID file')
        data = os.read(fd, 33)
        require(len(data) <= 32 and re.fullmatch(rb'[1-9][0-9]*\n?', data),
                'invalid libvirt domain PID file')
        yield int(data), st
    finally:
        if fd is not None:
            os.close(fd)
        os.close(directory)


def pid_file_locked(st, pid):
    """A number alone is not provenance: QEMU must own the inode's POSIX lock."""
    for line in Path('/proc/locks').read_text().splitlines():
        fields = line.split()
        # Blocked waiter lines have an extra '->'; they do not own a lock.
        if len(fields) != 8 or fields[1:4] != ['POSIX', 'ADVISORY', 'WRITE']:
            continue
        try:
            major, minor, inode = fields[5].split(':')
            matches = (int(major, 16), int(minor, 16), int(inode)) == (
                os.major(st.st_dev), os.minor(st.st_dev), st.st_ino)
            if int(fields[4]) == pid and matches and fields[6] == '0' and fields[7] in ('0', 'EOF'):
                return True
        except ValueError:
            continue
    return False


def verify_qemu_owner(cfg, pid):
    try:
        proc = Path('/proc')/str(pid)
        require(proc.stat().st_uid == cfg['allow_uid']
                and Path(os.readlink(proc/'exe')).name.startswith('qemu-system-'),
                'started process is not the expected QEMU owner/executable')
    except OSError:
        raise Failure('cannot verify the started QEMU executable') from None


def bind_started(cfg, name, root, reservation, running):
    require(reservation.exists(), 'started VM has no launch reservation')
    record = read_reservation(reservation)
    require(record['version'] == 3, 'legacy unbound reservation requires explicit all-off cleanup')
    require(domain_uuid(root) == record['uuid_sha256'], 'started domain UUID does not match its reservation')
    owner = daemon_identity()
    require(all(record[key] == owner[key] for key in ('daemon_pid', 'daemon_start')),
            'started hook does not belong to the reserving libvirt daemon')
    require(len(running) <= 2, 'too many running guests to bind the launch reservation')
    with canonical_pid_file(cfg, name) as (pid, st):
        guest = guest_process(Path('/proc')/str(pid))
        require(guest is not None and guest['name'] == name and guest.get('machine_verified') is True
                and guest.get('uuid_sha256') == record['uuid_sha256']
                and guest.get('start', -1) > record['prepare_tick'],
                'canonical PID does not match the newly started domain')
        require(any(item['pid'] == pid and item.get('start') == guest['start'] for item in running)
                and not any(item['name'] == name and item['pid'] != pid for item in running),
                'started QEMU does not have an unambiguous running process identity')
        verify_qemu_owner(cfg, pid)
        require(pid_file_locked(st, pid), 'canonical PID file is not locked by the started QEMU')
        with canonical_pid_file(cfg, name) as (current_pid, current):
            require(current_pid == pid and (current.st_dev, current.st_ino) == (st.st_dev, st.st_ino),
                    'canonical PID file changed during launch verification')
        try:
            current_qemu, current_daemon = process_start(pid), process_start(owner['daemon_pid'])
        except (Failure, OSError):
            raise Failure('cannot verify launch process identities; reservation retained') from None
        require(current_qemu == guest['start'], 'QEMU process changed during launch verification')
        require(current_daemon == owner['daemon_start'],
                'libvirt daemon changed during launch verification')
    bound = {'qemu_pid': pid, 'qemu_start': guest['start']}
    if 'qemu_pid' in record:
        require(all(record[key] == value for key, value in bound.items()),
                'started hook cannot replace an existing QEMU binding')
        return
    fd, temporary = tempfile.mkstemp(prefix='.' + name + '.', dir=reservation.parent)
    try:
        with os.fdopen(fd, 'w') as stream:
            os.fchmod(stream.fileno(), 0o600)
            json.dump({**record, **bound}, stream)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, reservation)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def gate_two(cfg, name, operation, root, managed):
    """Called under guest.lock; a legacy ledger requires deliberate migration."""
    require(not os.path.lexists(RUN/'active.json'),
            'legacy active.json blocks two-VM mode; stop all guests and pending starts, '
            'then explicitly migrate the old reservation while the libvirt daemon is stopped')
    directory = RUN/'reservations'
    private_dir(directory)
    reservation = directory/(name + '.json')
    running = running_guest_processes()
    if operation == 'started':
        if managed:
            check_domain(name, root)
        return bind_started(cfg, name, root, reservation, running)
    if operation == 'release':
        if reservation.exists() and not any(guest['name'] == name for guest in running):
            record = read_reservation(reservation)
            owner = daemon_identity()
            if record['version'] == 3:
                require(domain_uuid(root) == record['uuid_sha256'], 'released domain UUID does not match its reservation')
            if 'qemu_pid' in record:
                try:
                    current = process_start(record['qemu_pid'])
                except (Failure, OSError):
                    raise Failure('cannot prove the bound QEMU has exited; reservation retained') from None
                require(current != record['qemu_start'],
                        'bound QEMU is still running; reservation retained')
            else:
                require(all(record[key] == owner[key] for key in ('daemon_pid', 'daemon_start')),
                        'reservation belongs to another libvirt daemon; explicit all-off cleanup is required')
            reservation.unlink()
        return
    if managed:
        check_domain(name, root)
    validate(cfg)
    expected = backend_executable(cfg)
    slots, names, pending = reservation_slots(directory, running)
    require(name not in names, 'this macOS guest is already running')
    require(name not in pending, 'this VM start is reserved; wait for its owning release/end or perform explicit all-off cleanup')
    require(slots < 2, 'two macOS guests or pending starts already occupy the two-VM limit')
    identity = daemon_identity()
    identity_digest = domain_uuid(root)
    require_ready(provider_status(cfg))
    verify_running_backends(cfg, expected)
    wait_for_clock()
    if managed:
        command(['/usr/bin/systemctl', 'start', unit(name)], timeout=120)
        ready(cfg, name, acl=True)
    # Another reserved launch can become a QEMU while this hook waits. Count
    # again, still under guest.lock, before admitting this pending prepare.
    slots, names, pending = reservation_slots(directory, running_guest_processes())
    require(name not in names and name not in pending, 'this macOS guest is already running or reserved')
    require(slots < 2, 'two macOS guests or pending starts already occupy the two-VM limit')
    require(process_start(identity['daemon_pid']) == identity['daemon_start'],
            'libvirt daemon changed while reserving a start')
    fd = os.open(reservation, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, 'w') as stream:
        os.fchmod(stream.fileno(), 0o600)
        json.dump({'version': 3, 'vm': name, **identity, 'uuid_sha256': identity_digest,
                   'prepare_tick': prepare_epoch()}, stream)
        stream.flush()
        os.fsync(stream.fileno())


def domain(name,xml):
    require(len(xml)<=2*1024*1024, 'domain XML too large')
    root=ET.fromstring(xml)
    require(root.findtext('name')==name, 'domain name mismatch')
    return root


def qemu_options(args, names):
    """Recognize QEMU's single/double-dash aliases, including inline values."""
    values = []
    for i, arg in enumerate(args):
        option, separator, value = arg.partition('=')
        if option.startswith('--'):
            option = option[1:]
        if option not in names:
            continue
        if not separator:
            require(i + 1 < len(args), 'truncated QEMU option')
            value = args[i + 1]
        values.append(value)
    return values


def machine_types(args):
    machines = []
    for value in qemu_options(args, ('-machine', '-M')):
        types = []
        for i, part in enumerate(value.split(',')):
            key, separator, setting = part.partition('=')
            if separator and key == 'type':
                types.append(setting)
            elif not separator and i == 0:
                types.append(key)
        machines.append(types)
    return machines


def check_domain(name,root):
    ns='{http://libvirt.org/schemas/domain/qemu/1.0}'
    args=[x.attrib.get('value','') for x in root.findall('.//'+ns+'arg')]
    machines=machine_types(args)
    require(len(machines)<=1 and all(len(types)<=1 and all(kind=='vmapple' for kind in types)
                                    for types in machines),'ambiguous machine configuration')
    require(not any(value.startswith('apple-fairplay-pci.') for value in qemu_options(args, ('-global',))),
            'FairPlay global overrides are not allowed')
    sock,_=paths(name)
    identities=[e.attrib.get('value','') for e in root.findall('.//'+ns+'env') if e.attrib.get('name')=='OMVM_IDENTITY_SIGNER']
    require(identities==[str(SEP)],'domain is missing its configured Linux SEP socket')
    devices=[]
    for value in qemu_options(args, ('-device',)):
        parts=value.split(',')
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
    if (operation,phase) not in [('prepare','begin'),('started','begin'),('release','end')]:
        return
    if operation == 'started' and max_active_vms(cfg) == 1:
        return
    root=domain(name,xml)
    machine=root.find('os/type')
    managed=name in cfg['vms']
    args=[e.attrib.get('value','') for e in root.findall('.//{http://libvirt.org/schemas/domain/qemu/1.0}arg')]
    vmapple=(machine is not None and machine.attrib.get('machine')=='vmapple') or any(
        'vmapple' in types for types in machine_types(args))
    require(not managed or vmapple,'configured helper VM is not a vmapple domain')
    if not vmapple:return
    if not managed:
        require(b'/run/omvm-fairplay-' not in xml,'Linux helper VM is absent from root manifest')
    with locked(RUN/'guest.lock'):
        if max_active_vms(cfg) == 2:
            return gate_two(cfg, name, operation, root, managed)
        require(not (RUN/'reservations').exists() or not any((RUN/'reservations').iterdir()),
                'two-VM reservations block one-VM mode; stop all guests and pending starts, '
                'then explicitly migrate the reservations while the libvirt daemon is stopped')
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
