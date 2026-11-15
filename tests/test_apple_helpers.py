#!/usr/bin/env python3
"""Lifecycle contracts with fake services, never SEP/AES operations or a guest.

Protects the root trust boundary, one/two-owner gates, provider poison/reuse and
socket-peer identity. Existing SEP wire tests do not cover orchestration.
"""
import contextlib
import fcntl
import importlib.util
import json
import os
from pathlib import Path
import socket
import shlex
import subprocess
import sys
import tempfile
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import patch

TEST_TMP='/run' if os.geteuid()==0 else None
SRC=Path(__file__).resolve().parents[1]/'share/apple-helpers.py'
spec=importlib.util.spec_from_file_location('helpers',SRC)
h=importlib.util.module_from_spec(spec);spec.loader.exec_module(h)
CFG={'allow_uid':1000,'vms':{'one':{'identifier':{}}},'provider':{'diagnostic':{'path':'/fake/diagnostic'}}}
TWO={**CFG,'max_active_vms':2,'backend':{'path':'/fake/backend'},
     'vms':{name:{'identifier':{'path':'/fake/'+name}} for name in ('one','two','three')}}


def fake_uuid(name):
    return str(h.uuid.uuid5(h.uuid.NAMESPACE_DNS, 'omvm-test-'+name))


XML=('<domain xmlns:qemu="http://libvirt.org/schemas/domain/qemu/1.0"><name>one</name><uuid>'+fake_uuid('one')+'</uuid><os><type machine="vmapple"/></os><qemu:commandline><qemu:arg value="-device"/><qemu:arg value="apple-fairplay-pci,relay-socket=/run/omvm-fairplay-managed-one/relay.sock"/><qemu:env name="OMVM_IDENTITY_SIGNER" value="/run/omvm-identity/sep.sock"/></qemu:commandline></domain>').encode()


def vm_xml(name, managed=True):
    if managed:
        return XML.replace(b'one',name.encode()).replace(fake_uuid('one').encode(),fake_uuid(name).encode())
    return f'<domain><name>{name}</name><uuid>{fake_uuid(name)}</uuid><os><type machine="vmapple"/></os></domain>'.encode()


def write_reservation(directory,name,pid=501,started=100,qemu_pid=None,qemu_start=300,legacy=False):
    directory.mkdir(parents=True,exist_ok=True)
    path=directory/(name+'.json')
    record={'version':2 if legacy else 3,'vm':name,'daemon_pid':pid,'daemon_start':started}
    if not legacy:
        record.update(uuid_sha256=h.uuid_digest(fake_uuid(name)),prepare_tick=max(200,started))
        if qemu_pid is not None:record.update(qemu_pid=qemu_pid,qemu_start=qemu_start)
    path.write_text(json.dumps(record))
    path.chmod(0o600)
    return path


def fake_guest(name='one',pid=101,started=300):
    return {'pid':pid,'name':name,'start':started,'uuid_sha256':h.uuid_digest(fake_uuid(name)),
            'machine_verified':True}


@contextlib.contextmanager
def fake_binding(guest=None):
    guest=fake_guest() if guest is None else guest
    @contextlib.contextmanager
    def pidfile(cfg,name):yield guest['pid'],SimpleNamespace(st_dev=os.makedev(0,50),st_ino=900)
    with patch.object(h,'canonical_pid_file',side_effect=pidfile) as pidfile_call, \
         patch.object(h,'guest_process',return_value=guest) as process, \
         patch.object(h,'pid_file_locked',return_value=True) as kernel_lock, \
         patch.object(h,'verify_qemu_owner') as owner:
        yield SimpleNamespace(pidfile=pidfile_call,process=process,kernel_lock=kernel_lock,owner=owner)


@contextlib.contextmanager
def fake_two_gate(run,running=None,starts=None):
    """Only the trust primitives are replaced; admission/ledger code is real.

    No /proc, systemd, provider, or root-owned path is read by these tests.
    The process-shared fcntl lifecycle lock has separate root-only coverage.
    """
    running=[] if running is None else running
    starts={501:100} if starts is None else starts
    mutex=threading.Lock()
    @contextlib.contextmanager
    def locked(path):
        with mutex:yield
    def private_dir(path):path.mkdir(mode=0o700,parents=True,exist_ok=True)
    with contextlib.ExitStack() as stack:
        replacements={
            'RUN':run,'locked':locked,'private_dir':private_dir,
            'secure_file':lambda path,limit=None:Path(path).read_bytes(),
            'running_guest_processes':lambda:list(running),
            'process_start':lambda pid:starts.get(pid),
            'daemon_identity':lambda:{'daemon_pid':501,'daemon_start':100},
            'prepare_epoch':lambda:200,
            'validate':lambda cfg:cfg,'backend_executable':lambda cfg:(8,9),
            'verify_running_backends':lambda *args,**kwargs:set(),
            'provider_status':lambda cfg:{'state':2,'flags':6},
        }
        for name,value in replacements.items():stack.enter_context(patch.object(h,name,value))
        command=stack.enter_context(patch.object(h,'command',return_value=b''))
        ready=stack.enter_context(patch.object(h,'ready'))
        clock=stack.enter_context(patch.object(h,'wait_for_clock'))
        yield SimpleNamespace(command=command,ready=ready,clock=clock,starts=starts)


class GateTests(unittest.TestCase):
    def test_bad_domain_or_existing_guest_never_starts_helpers(self):
        for xml,guests,reason in [(XML.replace(b'<name>one',b'<name>two'),set(),'name mismatch'),
                                  (XML.replace(b'/run/omvm-identity/sep.sock',b'/tmp/wrong'),set(),'missing'),
                                  (XML,{'another'},'another macOS guest')]:
            with self.subTest(reason=reason),tempfile.TemporaryDirectory(dir=TEST_TMP) as d, \
                 patch.object(h,'RUN',Path(d)),patch.object(h,'locked',return_value=contextlib.nullcontext()), \
                 patch.object(h,'running_guests',return_value=guests),patch.object(h,'command') as command:
                with self.assertRaisesRegex(h.Failure,reason):h.gate(CFG,'one','prepare','begin',xml)
                command.assert_not_called()

    def test_socket_substring_cannot_mask_wrong_device_or_duplicate_signer(self):
        wrong=XML.replace(b'apple-fairplay-pci,relay-socket=/run/omvm-fairplay-managed-one/relay.sock',b'apple-fairplay-pci,relay-socket=/tmp/wrong,comment=/run/omvm-fairplay-managed-one/relay.sock')
        duplicate=XML.replace(b'</qemu:commandline>',b'<qemu:env name="OMVM_IDENTITY_SIGNER" value="/tmp/wrong"/></qemu:commandline>')
        for xml in [wrong,duplicate]:
            with self.subTest(xml=xml),self.assertRaises(h.Failure):h.check_domain('one',h.domain('one',xml))

    def test_double_dash_device_and_global_cannot_bypass_exact_socket_contract(self):
        h.check_domain('one',h.domain('one',XML.replace(b'-device',b'--device')))
        duplicate=XML.replace(b'</qemu:commandline>',
            b'<qemu:arg value="--device"/><qemu:arg value="apple-fairplay-pci,relay-socket=/tmp/wrong"/></qemu:commandline>')
        override=XML.replace(b'</qemu:commandline>',
            b'<qemu:arg value="--global"/><qemu:arg value="apple-fairplay-pci.relay-socket=/tmp/wrong"/></qemu:commandline>')
        for xml in (duplicate,override):
            with self.subTest(xml=xml),self.assertRaises(h.Failure):h.check_domain('one',h.domain('one',xml))

    def test_unmanaged_vmapple_guest_cannot_bypass_active_guest_guard(self):
        xml=b'<domain><name>other</name><os><type machine="vmapple"/></os></domain>'
        with tempfile.TemporaryDirectory(dir=TEST_TMP) as d,patch.object(h,'RUN',Path(d)), \
             patch.object(h,'locked',return_value=contextlib.nullcontext()),patch.object(h,'running_guests',return_value={'one'}):
            with self.assertRaisesRegex(h.Failure,'another macOS guest'):h.gate(CFG,'other','prepare','begin',xml)

    def test_foreign_user_or_unregistered_linux_helper_domain_fails(self):
        with patch.dict(os.environ,{'SUDO_UID':'1001'}):
            with self.assertRaisesRegex(h.Failure,'caller'):h.gate(CFG,'one','prepare','begin',XML)
        with patch.dict(os.environ,{'SUDO_UID':'1000'}):
            with self.assertRaisesRegex(h.Failure,'absent'):h.gate(CFG,'unknown','prepare','begin',XML.replace(b'<name>one',b'<name>unknown'))
            h.gate(CFG,'ordinary','prepare','begin',b'<domain><name>ordinary</name></domain>')

    @unittest.skipUnless(sys.platform=='linux','Linux /proc contract')
    def test_live_reservation_blocks_even_without_qemu_yet(self):
        with tempfile.TemporaryDirectory(dir=TEST_TMP) as d:
            root=Path(d);(root/'active.json').write_text('{}')
            with patch.object(h,'RUN',root),patch.object(h,'locked',return_value=contextlib.nullcontext()), \
                 patch.object(h,'running_guests',return_value=set()), \
                 patch.object(h,'secure_file',return_value=json.dumps({'vm':'other','daemon_pid':os.getpid()}).encode()), \
                 patch.object(h,'command') as command:
                with self.assertRaisesRegex(h.Failure,'reserved'):h.gate(CFG,'one','prepare','begin',XML)
                command.assert_not_called()


class ManifestTests(unittest.TestCase):
    @contextlib.contextmanager
    def manifest(self):
        with tempfile.TemporaryDirectory(dir=TEST_TMP) as d:
            cache=Path(d)/'cache';cache.mkdir();(cache/'asset').write_bytes(b'cache')
            hashes={
                'module':'ee1f7ab9f1a05d2c043bd13694a095e71bb3d4d372cdd0463ba65c741841d4da',
                'diagnostic':'4c016ac4e28d2dd65f4405ca32859dd5daa2fe3757f736edab6beb30d38a0b11',
                'seeds':'1c6a5cc41f941e0788e436148f280dd5a875caf57929811b802aadca9e253c8d',
                'boot':'0'*64,'update_m1n1':'1'*64,
            }
            cfg={'version':1,'allow_uid':1000,
                 'provider':{'kernel':'7.2.11-15vmapple-1-ARCH',
                             **{key:{'path':'/fake/'+key,'sha256':digest} for key,digest in hashes.items()}},
                 'backend':{'path':'/fake/backend','sha256':'2'*64},
                 'cache':{'path':str(cache),'files':{'asset':'3'*64}},
                 'vms':{'one':{'identifier':{'path':'/fake/one','sha256':'4'*64}},
                        'two':{'identifier':{'path':'/fake/two','sha256':'5'*64}}}}
            contents={'/fake/seeds':b's'*32,'/fake/one':b'a'*16,'/fake/two':b'b'*16}
            with patch.object(h,'artifact',side_effect=lambda record,limit=None:contents.get(record['path'],b'asset')) as artifact, \
                 patch.object(h,'backend_executable',return_value=(8,9)), \
                 patch.object(h,'executable_identity',return_value=(8,9)), \
                 patch.object(h,'command',return_value=b'{"schema_version":1,"device_aes_arbitration":"transaction-flock-v1"}') as command:
                yield cfg,contents,artifact,command

    def test_default_and_explicit_one_preserve_legacy_without_capability_probe(self):
        with self.manifest() as (cfg,contents,artifact,command):
            self.assertEqual(h.max_active_vms(h.validate(cfg)),1)
            cfg['max_active_vms']=1
            h.validate(cfg)
            command.assert_not_called()

    def test_limit_is_exact_integer_one_or_two(self):
        for invalid in (True,False,0,3,-1,1.0,2.0,'2',None):
            with self.subTest(invalid=invalid),self.manifest() as (cfg,contents,artifact,command):
                cfg['max_active_vms']=invalid
                with self.assertRaisesRegex(h.Failure,'must be 1 or 2'):h.validate(cfg)
                artifact.assert_not_called();command.assert_not_called()

    def test_two_validates_backend_pin_before_the_pure_capability_probe(self):
        with self.manifest() as (cfg,contents,artifact,command):
            cfg['max_active_vms']=2
            h.validate(cfg)
            self.assertIn(cfg['backend'],[call.args[0] for call in artifact.call_args_list])
            self.assertEqual([call.args[0] for call in command.call_args_list],
                             [['/fake/backend','-print-capabilities'],['/fake/diagnostic','-print-capabilities']])
            self.assertTrue(all(call.kwargs=={'timeout':5} for call in command.call_args_list))
            artifact.side_effect=h.Failure('artifact digest mismatch')
            command.reset_mock()
            with self.assertRaisesRegex(h.Failure,'digest'):h.validate(cfg)
            command.assert_not_called()

    def test_missing_malformed_or_wrong_capability_is_refused(self):
        answers=[b'',b'not json',b'[]',b'{}',b'{"schema_version":true,"device_aes_arbitration":"transaction-flock-v1"}',
                 b'{"schema_version":2,"device_aes_arbitration":"transaction-flock-v1"}',
                 b'{"schema_version":1,"device_aes_arbitration":"per-ioctl-lock"}']
        for answer in answers:
            with self.subTest(answer=answer),self.manifest() as (cfg,contents,artifact,command):
                cfg['max_active_vms']=2;command.return_value=answer
                with self.assertRaisesRegex(h.Failure,'transaction flock capability'):h.validate(cfg)
        with self.manifest() as (cfg,contents,artifact,command):
            cfg['max_active_vms']=2;command.side_effect=h.Failure('old flag parser')
            with self.assertRaisesRegex(h.Failure,'transaction flock capability'):h.validate(cfg)

    def test_diagnostic_also_requires_transaction_capability_and_reviewed_pin(self):
        with self.manifest() as (cfg,contents,artifact,command):
            cfg['max_active_vms']=2
            command.side_effect=[b'{"schema_version":1,"device_aes_arbitration":"transaction-flock-v1"}',b'{}']
            with self.assertRaisesRegex(h.Failure,'diagnostic with transaction flock capability'):h.validate(cfg)
            command.reset_mock()
            cfg['provider']['diagnostic']['sha256']='f'*64
            with self.assertRaisesRegex(h.Failure,'unreviewed UID1 diagnostic'):h.validate(cfg)
            command.assert_not_called()

    def test_duplicate_contents_are_private_even_with_distinct_paths_and_pins(self):
        with self.manifest() as (cfg,contents,artifact,command):
            cfg['max_active_vms']=2;contents['/fake/two']=contents['/fake/one']
            with self.assertRaises(h.Failure) as failure:h.validate(cfg)
            self.assertEqual(str(failure.exception),'two-VM mode requires distinct enrolled identifiers')
            command.assert_not_called()
            # Legacy manifests retain their existing one-at-a-time behavior.
            cfg.pop('max_active_vms');h.validate(cfg)


class TwoGateTests(unittest.TestCase):
    def test_unmanaged_machine_aliases_cannot_bypass_two_pending_slots(self):
        for option,value in [('-machine','vmapple'),('--machine','vmapple'),('-M','type=vmapple'),
                             ('--M','type=vmapple'),('-machine','accel=kvm,type=vmapple'),
                             ('--machine=type=vmapple',None)]:
            with self.subTest(option=option,value=value),tempfile.TemporaryDirectory(dir=TEST_TMP) as d:
                run=Path(d)
                for name in ('one','two'):write_reservation(run/'reservations',name)
                arguments=f'<qemu:arg value="{option}"/>'
                if value is not None:arguments+=f'<qemu:arg value="{value}"/>'
                xml=('<domain xmlns:qemu="http://libvirt.org/schemas/domain/qemu/1.0"><name>unmanaged</name>'
                     f'<qemu:commandline>{arguments}</qemu:commandline></domain>').encode()
                with fake_two_gate(run) as fake:
                    with self.assertRaisesRegex(h.Failure,'two-VM limit'):
                        h.gate(TWO,'unmanaged','prepare','begin',xml)
                    fake.command.assert_not_called()

    def test_two_pending_starts_are_admitted_and_third_is_refused(self):
        with tempfile.TemporaryDirectory(dir=TEST_TMP) as d:
            run=Path(d)
            with fake_two_gate(run) as fake:
                for name in ('one','two'):h.gate(TWO,name,'prepare','begin',vm_xml(name))
                with self.assertRaisesRegex(h.Failure,'two-VM limit'):
                    h.gate(TWO,'three','prepare','begin',vm_xml('three'))
            self.assertEqual({path.stem for path in (run/'reservations').iterdir()},{'one','two'})
            self.assertEqual([call.args[0] for call in fake.command.call_args_list],
                             [['/usr/bin/systemctl','start',h.unit(name)] for name in ('one','two')])
            for path in (run/'reservations').iterdir():
                self.assertEqual(path.stat().st_mode&0o777,0o600)
                self.assertEqual(json.loads(path.read_text())['daemon_start'],100)

    def test_running_qemu_and_its_reservation_are_one_slot(self):
        with tempfile.TemporaryDirectory(dir=TEST_TMP) as d:
            run=Path(d);running=[fake_guest()]
            write_reservation(run/'reservations','one',qemu_pid=101)
            with fake_two_gate(run,running) as fake:
                h.gate(TWO,'two','prepare','begin',vm_xml('two'))
                with self.assertRaisesRegex(h.Failure,'two-VM limit'):
                    h.gate(TWO,'three','prepare','begin',vm_xml('three'))
            self.assertEqual(fake.command.call_count,1)

    def test_unbound_same_name_is_not_merged_even_with_matching_ancestry(self):
        for ancestry in ({},{'daemon_pid':502,'daemon_start':100},{'daemon_pid':501,'daemon_start':101}):
            with self.subTest(ancestry=ancestry),tempfile.TemporaryDirectory(dir=TEST_TMP) as d:
                run=Path(d);running=[{'pid':101,'name':'one',**ancestry}]
                write_reservation(run/'reservations','one')
                with fake_two_gate(run,running) as fake:
                    with self.assertRaisesRegex(h.Failure,'two-VM limit'):
                        h.gate(TWO,'two','prepare','begin',vm_xml('two'))
                    fake.command.assert_not_called()

    def test_unmanaged_and_unnamed_qemu_processes_consume_slots(self):
        for running in ([{'pid':101,'name':'unmanaged'},{'pid':102,'name':None}],
                        [{'pid':101,'name':'one'},{'pid':102,'name':'unmanaged'}]):
            with self.subTest(running=running),tempfile.TemporaryDirectory(dir=TEST_TMP) as d:
                with fake_two_gate(Path(d),running) as fake:
                    with self.assertRaisesRegex(h.Failure,'two-VM limit'):
                        h.gate(TWO,'two','prepare','begin',vm_xml('two'))
                    fake.command.assert_not_called()

    def test_unmanaged_prepares_also_reserve_capacity(self):
        with tempfile.TemporaryDirectory(dir=TEST_TMP) as d:
            run=Path(d)
            with fake_two_gate(run) as fake:
                h.gate(TWO,'unmanaged','prepare','begin',vm_xml('unmanaged',False))
                h.gate(TWO,'one','prepare','begin',vm_xml('one'))
                with self.assertRaisesRegex(h.Failure,'two-VM limit'):
                    h.gate(TWO,'two','prepare','begin',vm_xml('two'))
            self.assertTrue((run/'reservations/unmanaged.json').exists())
            self.assertEqual(fake.command.call_count,1)

    def test_duplicate_process_names_fail_without_collapsing_them(self):
        with tempfile.TemporaryDirectory(dir=TEST_TMP) as d:
            running=[{'pid':101,'name':'one'},{'pid':102,'name':'one'}]
            with fake_two_gate(Path(d),running) as fake:
                with self.assertRaisesRegex(h.Failure,'duplicate running guest names'):
                    h.gate(TWO,'two','prepare','begin',vm_xml('two'))
                fake.command.assert_not_called()

    def test_concurrent_prepares_reserve_exactly_two_slots(self):
        with tempfile.TemporaryDirectory(dir=TEST_TMP) as d:
            run=Path(d);barrier=threading.Barrier(3);outcomes=[]
            def prepare(name):
                barrier.wait()
                try:
                    h.gate(TWO,name,'prepare','begin',vm_xml(name));outcomes.append(('ok',name))
                except h.Failure as failure:outcomes.append((str(failure),name))
            with fake_two_gate(run) as fake:
                threads=[threading.Thread(target=prepare,args=(name,)) for name in ('one','two','three')]
                for thread in threads:thread.start()
                for thread in threads:thread.join(timeout=5)
                self.assertFalse(any(thread.is_alive() for thread in threads))
            self.assertEqual(sum(result=='ok' for result,name in outcomes),2)
            self.assertEqual(sum('two-VM limit' in result for result,name in outcomes),1)
            self.assertEqual(len(list((run/'reservations').iterdir())),2)
            self.assertEqual(fake.command.call_count,2)

    def test_release_removes_only_its_own_absent_guest_reservation(self):
        with tempfile.TemporaryDirectory(dir=TEST_TMP) as d:
            run=Path(d);one=write_reservation(run/'reservations','one');two=write_reservation(run/'reservations','two')
            running=[{'pid':101,'name':'one'}]
            with fake_two_gate(run,running) as fake:
                h.gate(TWO,'one','release','end',vm_xml('one'));self.assertTrue(one.exists())
                running.clear()
                h.gate(TWO,'one','release','end',vm_xml('one'))
                self.assertFalse(one.exists());self.assertTrue(two.exists())
                fake.command.assert_not_called();fake.ready.assert_not_called();fake.clock.assert_not_called()

    def test_dead_or_reused_daemon_pid_preserves_uncertain_orphan_slot(self):
        for starts in ({501:100},{501:100,700:201}):
            with self.subTest(starts=starts),tempfile.TemporaryDirectory(dir=TEST_TMP) as d:
                run=Path(d);stale=write_reservation(run/'reservations','old',pid=700,started=200)
                with fake_two_gate(run,starts=starts):
                    h.gate(TWO,'one','prepare','begin',vm_xml('one'))
                    with self.assertRaisesRegex(h.Failure,'two-VM limit'):
                        h.gate(TWO,'two','prepare','begin',vm_xml('two'))
                self.assertTrue(stale.exists(),'one VM must not delete another VM reservation')

    def test_same_vm_cannot_replace_dead_or_reused_daemon_record(self):
        with tempfile.TemporaryDirectory(dir=TEST_TMP) as d:
            run=Path(d);record=write_reservation(run/'reservations','one',pid=700,started=200)
            with fake_two_gate(run,starts={501:100,700:201}):
                with self.assertRaisesRegex(h.Failure,'explicit all-off cleanup'):
                    h.gate(TWO,'one','prepare','begin',vm_xml('one'))
            self.assertEqual(json.loads(record.read_text())['daemon_pid'],700)

    def test_foreign_or_reused_daemon_release_cannot_delete_live_prepare(self):
        for pid,started in [(700,100),(501,101)]:
            with self.subTest(pid=pid,started=started),tempfile.TemporaryDirectory(dir=TEST_TMP) as d:
                run=Path(d);record=write_reservation(run/'reservations','one',pid=pid,started=started)
                original=record.read_bytes()
                with fake_two_gate(run) as fake:
                    with self.assertRaisesRegex(h.Failure,'another libvirt daemon'):
                        h.gate(TWO,'one','release','end',XML)
                    self.assertEqual(record.read_bytes(),original)
                    fake.command.assert_not_called();fake.clock.assert_not_called()

    def test_live_or_uncertain_prepare_is_never_expired_by_age(self):
        for unavailable in (False,True):
            with self.subTest(unavailable=unavailable),tempfile.TemporaryDirectory(dir=TEST_TMP) as d:
                run=Path(d)
                for name in ('one','two'):write_reservation(run/'reservations',name,pid=700,started=200)
                with fake_two_gate(run,starts={501:100,700:200}) as fake:
                    with patch.object(h,'process_start',side_effect=OSError('private test error')) if unavailable else contextlib.nullcontext():
                        with self.assertRaisesRegex(h.Failure,'two-VM limit'):
                            h.gate(TWO,'three','prepare','begin',vm_xml('three'))
                    fake.command.assert_not_called()

    def test_same_live_pending_vm_cannot_prepare_twice(self):
        with tempfile.TemporaryDirectory(dir=TEST_TMP) as d:
            run=Path(d);write_reservation(run/'reservations','one')
            with fake_two_gate(run) as fake:
                with self.assertRaisesRegex(h.Failure,'start is reserved'):
                    h.gate(TWO,'one','prepare','begin',vm_xml('one'))
                fake.command.assert_not_called()

    def test_legacy_ledger_is_never_deleted_or_silently_migrated(self):
        with tempfile.TemporaryDirectory(dir=TEST_TMP) as d:
            run=Path(d);legacy=run/'active.json';legacy.write_text('{"vm":"one","daemon_pid":700}')
            original=legacy.read_bytes()
            with fake_two_gate(run) as fake:
                for operation,phase in [('prepare','begin'),('release','end')]:
                    with self.assertRaisesRegex(h.Failure,'explicitly migrate'):
                        h.gate(TWO,'two',operation,phase,vm_xml('two'))
                self.assertEqual(legacy.read_bytes(),original);fake.command.assert_not_called()

    def test_downgrade_does_not_ignore_new_pending_reservations(self):
        with tempfile.TemporaryDirectory(dir=TEST_TMP) as d:
            run=Path(d);write_reservation(run/'reservations','two')
            with fake_two_gate(run),patch.object(h,'running_guests',return_value=set()):
                with self.assertRaisesRegex(h.Failure,'two-VM reservations block one-VM mode'):
                    h.gate(CFG,'one','prepare','begin',XML)

    def test_poison_or_unhealthy_sibling_never_starts_or_reinitializes_helpers(self):
        cases=[('provider_status',lambda cfg:{'state':3,'flags':6},'poisoned'),
               ('verify_running_backends',lambda *args:(_ for _ in ()).throw(h.Failure('unhealthy sibling')),'unhealthy')]
        for target,behavior,error in cases:
            with self.subTest(target=target),tempfile.TemporaryDirectory(dir=TEST_TMP) as d:
                run=Path(d)
                with fake_two_gate(run) as fake,patch.object(h,target,side_effect=behavior):
                    with self.assertRaisesRegex(h.Failure,error):h.gate(TWO,'one','prepare','begin',XML)
                    fake.command.assert_not_called();fake.ready.assert_not_called()
                self.assertFalse(list((run/'reservations').iterdir()))

    def test_failed_start_is_not_retried_restarted_or_enrolled(self):
        with tempfile.TemporaryDirectory(dir=TEST_TMP) as d:
            run=Path(d)
            with fake_two_gate(run) as fake:
                fake.ready.side_effect=h.Failure('wrong peer')
                with self.assertRaisesRegex(h.Failure,'wrong peer'):h.gate(TWO,'one','prepare','begin',XML)
                fake.command.assert_called_once_with(['/usr/bin/systemctl','start',h.unit('one')],timeout=120)
            self.assertFalse(list((run/'reservations').iterdir()))

    def test_capacity_is_rechecked_after_helpers_become_ready(self):
        with tempfile.TemporaryDirectory(dir=TEST_TMP) as d:
            run=Path(d);running=[]
            with fake_two_gate(run,running) as fake:
                fake.ready.side_effect=lambda *args,**kwargs:running.extend([
                    {'pid':101,'name':'unmanaged'},{'pid':102,'name':'another'}])
                with self.assertRaisesRegex(h.Failure,'two-VM limit'):h.gate(TWO,'one','prepare','begin',XML)
            self.assertFalse(list((run/'reservations').iterdir()))


class StartedGateTests(unittest.TestCase):
    def test_reparented_qemu_binding_admits_second_guest_and_refuses_third(self):
        with tempfile.TemporaryDirectory(dir=TEST_TMP) as d:
            run=Path(d);running=[]
            with fake_two_gate(run,running) as fake:
                h.gate(TWO,'one','prepare','begin',XML)
                running.append(fake_guest());fake.starts[101]=300
                self.assertEqual(h.reservation_slots(run/'reservations',running)[0],2)
                with fake_binding():h.gate(TWO,'one','started','begin',XML)
                self.assertEqual(h.reservation_slots(run/'reservations',running)[0],1)
                record=json.loads((run/'reservations/one.json').read_text())
                self.assertEqual((record['version'],record['qemu_pid'],record['qemu_start']),(3,101,300))
                self.assertNotIn(fake_uuid('one'),(run/'reservations/one.json').read_text())
                h.gate(TWO,'two','prepare','begin',vm_xml('two'))
                with self.assertRaisesRegex(h.Failure,'two-VM limit'):
                    h.gate(TWO,'three','prepare','begin',vm_xml('three'))
                self.assertEqual(fake.command.call_count,2)

    def test_bound_process_remains_one_slot_when_original_daemon_has_exited(self):
        with tempfile.TemporaryDirectory(dir=TEST_TMP) as d:
            run=Path(d);write_reservation(run/'reservations','one',qemu_pid=101)
            with fake_two_gate(run,starts={}),patch.object(h,'process_start',side_effect=AssertionError('not needed')):
                self.assertEqual(h.reservation_slots(run/'reservations',[fake_guest()]),(1,{'one'},set()))

    def test_binding_is_idempotent_and_cannot_move_to_another_pid(self):
        with tempfile.TemporaryDirectory(dir=TEST_TMP) as d:
            run=Path(d);record=write_reservation(run/'reservations','one',qemu_pid=101)
            original=record.read_bytes()
            with fake_two_gate(run,[fake_guest()],starts={501:100,101:300}),fake_binding():
                h.gate(TWO,'one','started','begin',XML)
            self.assertEqual(record.read_bytes(),original)
            with fake_two_gate(run,[fake_guest(pid=102)],starts={501:100,102:300}),fake_binding(fake_guest(pid=102)):
                with self.assertRaisesRegex(h.Failure,'cannot replace'):h.gate(TWO,'one','started','begin',XML)
            self.assertEqual(record.read_bytes(),original)

    def test_foreign_daemon_or_uuid_cannot_complete_pending_reservation(self):
        for change in ('daemon','uuid','legacy'):
            with self.subTest(change=change),tempfile.TemporaryDirectory(dir=TEST_TMP) as d:
                run=Path(d);record=write_reservation(run/'reservations','one',legacy=change=='legacy')
                original=record.read_bytes()
                xml=XML.replace(fake_uuid('one').encode(),fake_uuid('other').encode()) if change=='uuid' else XML
                with fake_two_gate(run,[fake_guest()],starts={501:100,101:300}),fake_binding(),contextlib.ExitStack() as stack:
                    if change=='daemon':stack.enter_context(patch.object(h,'daemon_identity',return_value={'daemon_pid':700,'daemon_start':100}))
                    with self.assertRaises(h.Failure):h.gate(TWO,'one','started','begin',xml)
                self.assertEqual(record.read_bytes(),original)

    def test_stale_reused_wrong_uuid_or_wrong_machine_pid_preserves_pending(self):
        cases=[{**fake_guest(),'start':200},{**fake_guest(),'start':199},
               {**fake_guest(),'uuid_sha256':h.uuid_digest(fake_uuid('other'))},
               {**fake_guest(),'name':'other'},{**fake_guest(),'machine_verified':False},
               {'pid':101,'name':None}]
        for guest in cases:
            with self.subTest(guest=guest),tempfile.TemporaryDirectory(dir=TEST_TMP) as d:
                run=Path(d);record=write_reservation(run/'reservations','one');original=record.read_bytes()
                with fake_two_gate(run,[guest],starts={501:100,101:300}) as fake,fake_binding(guest):
                    with self.assertRaisesRegex(h.Failure,'canonical PID'):h.gate(TWO,'one','started','begin',XML)
                    fake.command.assert_not_called();fake.ready.assert_not_called()
                self.assertEqual(record.read_bytes(),original)

    def test_missing_kernel_lock_or_bad_process_owner_preserves_pending(self):
        for failure in ('lock','owner'):
            with self.subTest(failure=failure),tempfile.TemporaryDirectory(dir=TEST_TMP) as d:
                run=Path(d);record=write_reservation(run/'reservations','one');original=record.read_bytes()
                with fake_two_gate(run,[fake_guest()],starts={501:100,101:300}),fake_binding() as binding:
                    if failure=='lock':binding.kernel_lock.return_value=False
                    else:binding.owner.side_effect=h.Failure('wrong QEMU owner')
                    with self.assertRaises(h.Failure):h.gate(TWO,'one','started','begin',XML)
                self.assertEqual(record.read_bytes(),original)

    def test_pidfile_replacement_or_late_process_reuse_cannot_bind(self):
        for change in ('pidfile','qemu','daemon'):
            with self.subTest(change=change),tempfile.TemporaryDirectory(dir=TEST_TMP) as d:
                run=Path(d);record=write_reservation(run/'reservations','one');original=record.read_bytes()
                with fake_two_gate(run,[fake_guest()],starts={501:100,101:300}) as fake,fake_binding() as binding:
                    if change=='pidfile':
                        stats=iter([900,901])
                        @contextlib.contextmanager
                        def changed_file(cfg,name):yield 101,SimpleNamespace(st_dev=os.makedev(0,50),st_ino=next(stats))
                        binding.pidfile.side_effect=changed_file
                    else:fake.starts[101 if change=='qemu' else 501]+=1
                    with self.assertRaises(h.Failure):h.gate(TWO,'one','started','begin',XML)
                self.assertEqual(record.read_bytes(),original)

    def test_failed_atomic_binding_keeps_pending_and_cleans_its_temporary_file(self):
        with tempfile.TemporaryDirectory(dir=TEST_TMP) as d:
            run=Path(d);record=write_reservation(run/'reservations','one');original=record.read_bytes()
            with fake_two_gate(run,[fake_guest()],starts={501:100,101:300}),fake_binding(), \
                 patch.object(h.os,'replace',side_effect=OSError('fake replace failure')):
                with self.assertRaises(OSError):h.gate(TWO,'one','started','begin',XML)
            self.assertEqual(record.read_bytes(),original)
            self.assertEqual(list((run/'reservations').iterdir()),[record])

    def test_new_daemon_releases_only_provably_completed_and_exited_binding(self):
        for current,release in [(None,True),(301,True),(300,False),(PermissionError('test'),False)]:
            with self.subTest(current=current),tempfile.TemporaryDirectory(dir=TEST_TMP) as d:
                run=Path(d);record=write_reservation(run/'reservations','one',qemu_pid=101)
                with fake_two_gate(run) as fake, \
                     patch.object(h,'daemon_identity',return_value={'daemon_pid':700,'daemon_start':600}), \
                     patch.object(h,'process_start',side_effect=current) if isinstance(current,Exception) else \
                     patch.object(h,'process_start',return_value=current):
                    if release:h.gate(TWO,'one','release','end',XML)
                    else:
                        with self.assertRaises(h.Failure):h.gate(TWO,'one','release','end',XML)
                    self.assertEqual(record.exists(),not release)
                    fake.command.assert_not_called();fake.ready.assert_not_called()

    def test_release_uuid_mismatch_cannot_clear_completed_binding(self):
        with tempfile.TemporaryDirectory(dir=TEST_TMP) as d:
            run=Path(d);record=write_reservation(run/'reservations','one',qemu_pid=101)
            with fake_two_gate(run):
                with self.assertRaisesRegex(h.Failure,'UUID'):
                    h.gate(TWO,'one','release','end',XML.replace(fake_uuid('one').encode(),fake_uuid('other').encode()))
            self.assertTrue(record.exists())

    def test_old_or_unbound_record_is_not_deduplicated_against_an_arbitrary_name(self):
        for legacy in (False,True):
            with self.subTest(legacy=legacy),tempfile.TemporaryDirectory(dir=TEST_TMP) as d:
                run=Path(d);write_reservation(run/'reservations','one',legacy=legacy)
                with fake_two_gate(run):
                    self.assertEqual(h.reservation_slots(run/'reservations',[fake_guest()])[0],2)

    def test_started_without_prepare_fails_and_legacy_default_ignores_new_phase(self):
        with tempfile.TemporaryDirectory(dir=TEST_TMP) as d:
            with fake_two_gate(Path(d)) as fake:
                with self.assertRaisesRegex(h.Failure,'no launch reservation'):h.gate(TWO,'one','started','begin',XML)
                h.gate(CFG,'one','started','begin',b'not XML')
                fake.command.assert_not_called();fake.ready.assert_not_called()


@unittest.skipUnless(os.geteuid()==0 and sys.platform=='linux','Linux root two-VM ledger/lock contract')
class RootTwoGateTests(unittest.TestCase):
    def test_real_lifecycle_lock_and_root_private_ledgers_admit_exactly_two(self):
        real_locked,real_private_dir,real_secure_file=h.locked,h.private_dir,h.secure_file
        with tempfile.TemporaryDirectory(dir='/run') as d:
            run=Path(d);barrier=threading.Barrier(3);outcomes=[]
            def prepare(name):
                barrier.wait()
                try:
                    h.gate(TWO,name,'prepare','begin',vm_xml(name));outcomes.append('ok')
                except h.Failure as failure:outcomes.append(str(failure))
            with fake_two_gate(run),patch.object(h,'locked',real_locked), \
                 patch.object(h,'private_dir',real_private_dir),patch.object(h,'secure_file',real_secure_file):
                threads=[threading.Thread(target=prepare,args=(name,)) for name in ('one','two','three')]
                for thread in threads:thread.start()
                for thread in threads:thread.join(timeout=5)
                self.assertFalse(any(thread.is_alive() for thread in threads))
                self.assertEqual(outcomes.count('ok'),2)
                self.assertEqual(sum('two-VM limit' in result for result in outcomes),1)
                records=list((run/'reservations').iterdir());self.assertEqual(len(records),2)
                for path in records:
                    self.assertEqual(path.stat().st_uid,0)
                    self.assertEqual(path.stat().st_mode&0o777,0o600)
                    h.read_reservation(path)
                records[0].chmod(0o644)
                with self.assertRaisesRegex(h.Failure,'ownership/mode'):h.read_reservation(records[0])


@unittest.skipUnless(os.geteuid()==0 and sys.platform=='linux','Linux root libvirt gate contract')
class ClockGateTests(unittest.TestCase):
    def test_unsynchronized_clock_creates_no_reservation_or_helper_start(self):
        with tempfile.TemporaryDirectory(dir='/run') as d:
            run=Path(d)
            original=Path.read_text
            def process_name(path,*args,**kwargs):
                if str(path)==f'/proc/{os.getppid()}/comm':return 'virtqemud\n'
                return original(path,*args,**kwargs)
            with patch.object(h,'RUN',run),patch.object(h,'running_guests',return_value=set()), \
                 patch.object(h,'locked',return_value=contextlib.nullcontext()), \
                 patch.object(h,'command',return_value=b'no\n') as command, \
                 patch.object(h.time,'monotonic',side_effect=[0,0,30]), \
                 patch.object(Path,'read_text',process_name), \
                 patch.object(h,'ready') as ready:
                with self.assertRaisesRegex(h.Failure,'clock is not synchronized.*retry VM start'):
                    h.gate(CFG,'one','prepare','begin',XML)
                self.assertFalse((run/'active.json').exists())
                self.assertEqual([c.args[0][0] for c in command.call_args_list],['/usr/bin/timedatectl'])
                ready.assert_not_called()

    def test_launch_is_admitted_after_clock_synchronizes(self):
        with tempfile.TemporaryDirectory(dir='/run') as d:
            run=Path(d);events=[];answers=iter([b'no\n',b'yes\n'])
            original=Path.read_text
            def process_name(path,*args,**kwargs):
                if str(path)==f'/proc/{os.getppid()}/comm':return 'virtqemud\n'
                return original(path,*args,**kwargs)
            def command(argv,timeout=30):
                if argv[0]=='/usr/bin/timedatectl':
                    answer=next(answers);events.append(answer.strip().decode());return answer
                self.assertEqual(argv,['/usr/bin/systemctl','start','omvm-fairplay@one.service'])
                events.append('start');return b''
            with patch.object(h,'RUN',run),patch.object(h,'running_guests',return_value=set()), \
                 patch.object(h,'command',side_effect=command),patch.object(h,'ready'), \
                 patch.object(h.time,'sleep'),patch.object(Path,'read_text',process_name):
                h.gate(CFG,'one','prepare','begin',XML)
            self.assertEqual(events,['no','yes','start'])
            self.assertEqual(json.loads((run/'active.json').read_text())['vm'],'one')

    def test_unavailable_clock_query_fails_closed_within_deadline(self):
        with patch.object(h,'command',side_effect=subprocess.TimeoutExpired('timedatectl',5)) as command, \
             patch.object(h.time,'monotonic',side_effect=[0,0,30]):
            with self.assertRaisesRegex(h.Failure,'clock is not synchronized'):h.wait_for_clock()
            self.assertEqual(command.call_args.kwargs['timeout'],5)

    def test_release_does_not_wait_for_clock_or_touch_helpers(self):
        with tempfile.TemporaryDirectory(dir='/run') as d:
            run=Path(d);reservation=run/'active.json'
            reservation.write_text(json.dumps({'vm':'one','daemon_pid':os.getpid()}))
            with patch.object(h,'RUN',run),patch.object(h,'running_guests',return_value=set()), \
                 patch.object(h,'command') as command:
                h.gate(CFG,'one','release','end',XML)
                self.assertFalse(reservation.exists())
                command.assert_not_called()


class FilesAndSocketsTests(unittest.TestCase):
    def test_writable_ancestor_and_symlink_are_refused(self):
        # Root-private file under a world-writable ancestor is still not an
        # approved privileged executable/config location.
        with tempfile.TemporaryDirectory(dir=TEST_TMP) as d:
            writable=Path(d)/'writable';writable.mkdir();writable.chmod(0o777)
            p=writable/'config';p.write_bytes(b'{}')
            with self.assertRaisesRegex(h.Failure,'ancestor'):h.secure_file(p)
            link=Path(d)/'link';link.symlink_to(p)
            with self.assertRaises((h.Failure,OSError)):h.secure_file(link)

    @unittest.skipUnless(os.geteuid()==0,'root peer ownership check needs root test process')
    def test_ready_socket_must_belong_to_expected_service_process(self):
        with tempfile.TemporaryDirectory(dir=TEST_TMP) as d:
            p=Path(d)/'sock';s=socket.socket(socket.AF_UNIX,socket.SOCK_STREAM);s.bind(str(p));s.listen(3)
            try:
                h.peer(p,os.getpid())
                with self.assertRaisesRegex(h.Failure,'peer'):h.peer(p,os.getpid()+1)
            finally:s.close()

    @unittest.skipUnless(os.geteuid()==0 and sys.platform=='linux','Linux root/client socket-owner contract')
    def test_sep_client_owned_socket_still_requires_root_service_peer(self):
        with tempfile.TemporaryDirectory(dir=TEST_TMP) as d:
            p=Path(d)/'sep.sock';s=socket.socket(socket.AF_UNIX,socket.SOCK_STREAM);s.bind(str(p));s.listen(4)
            os.chown(p,1000,-1);os.chmod(p,0o600)
            try:
                with self.assertRaisesRegex(h.Failure,'owner'):h.peer(p,os.getpid())
                h.peer(p,os.getpid(),owner_uid=1000)
                with self.assertRaisesRegex(h.Failure,'peer'):h.peer(p,os.getpid()+1,owner_uid=1000)
                with patch.object(h,'SEP',p),patch.object(h,'service_pid',return_value=os.getpid()):
                    h.sep_peer(CFG)
            finally:s.close()

    @unittest.skipUnless(os.geteuid()==0 and sys.platform=='linux','Linux root lock ownership contract')
    def test_lock_acquisition_is_bounded(self):
        with tempfile.TemporaryDirectory(dir='/run') as d:
            p=Path(d)/'gate.lock'
            with h.locked(p):
                with self.assertRaisesRegex(h.Failure,'still holds'):
                    with h.locked(p,timeout=.01):self.fail('second owner admitted')


class HookTests(unittest.TestCase):
    def test_existing_hook_keeps_environment_and_forwards_phase_xml(self):
        with tempfile.TemporaryDirectory(dir=TEST_TMP) as d:
            root=Path(d);hook=root/'libvirt/hooks/qemu';hook.parent.mkdir(parents=True)
            recorder=root/'recorder.py'
            recorder.write_text('import sys,json; print(json.dumps([sys.argv[1:],sys.stdin.read()]))\n')
            hook.write_text('#!/bin/sh\n[ -f "'+d+'/vms/$1/ssh_port" ] || exit 0\nexport OMVM_IMAGES="'+d+'"\nexec '+shlex.quote(sys.executable)+' '+shlex.quote(str(recorder))+' virt-hook "$1" "$2" >/dev/null 2>&1 </dev/null\n')
            hook.chmod(0o700)
            env={**os.environ,'XDG_CONFIG_HOME':d}
            installer=SRC.parent/'apple-helpers-hook.py'
            subprocess.run([sys.executable,str(installer)],env=env,check=True,capture_output=True)
            for operation,phase in [('prepare','begin'),('started','begin'),('release','end')]:
                output=subprocess.check_output([str(hook),'one',operation,phase],input=XML)
                args,xml=json.loads(output)
                self.assertEqual(args,['virt-hook','one',operation,phase])
                self.assertEqual(xml,XML.decode())
            before=hook.read_bytes()
            subprocess.run([sys.executable,str(installer)],env=env,check=True,capture_output=True)
            self.assertEqual(hook.read_bytes(),before)

    def test_phase_aware_hook_is_upgraded_to_forward_started_for_unmanaged_guests(self):
        with tempfile.TemporaryDirectory(dir=TEST_TMP) as d:
            root=Path(d);hook=root/'libvirt/hooks/qemu';hook.parent.mkdir(parents=True)
            recorder=root/'recorder.py'
            recorder.write_text('import sys,json; print(json.dumps([sys.argv[1:],sys.stdin.read()]))\n')
            original=('#!/bin/sh\ncase "$2/$3" in prepare/begin|release/end) ;; *) [ -f "'+d+
                      '/vms/$1/ssh_port" ] || exit 0 ;; esac\nexport OMVM_IMAGES="'+d+'"\nexec '+
                      shlex.quote(sys.executable)+' '+shlex.quote(str(recorder))+' virt-hook "$1" "$2" "$3"\n')
            hook.write_text(original);hook.chmod(0o700)
            env={**os.environ,'XDG_CONFIG_HOME':d};installer=SRC.parent/'apple-helpers-hook.py'
            subprocess.run([sys.executable,str(installer)],env=env,check=True,capture_output=True)
            output=subprocess.check_output([str(hook),'unmanaged','started','begin'],input=vm_xml('unmanaged',False))
            args,xml=json.loads(output)
            self.assertEqual(args,['virt-hook','unmanaged','started','begin'])
            self.assertEqual(xml,vm_xml('unmanaged',False).decode())
            self.assertEqual(hook.with_name('qemu.before-apple-helpers').read_text(),original)
            before=hook.read_bytes()
            subprocess.run([sys.executable,str(installer)],env=env,check=True,capture_output=True)
            self.assertEqual(hook.read_bytes(),before)
            self.assertEqual(subprocess.check_output([str(hook),'unmanaged','stopped','end'],input=b''),b'')

    def test_cli_started_binding_precedes_preserved_managed_followups(self):
        # Execute only the real virt-hook case arm with fake commands, not the
        # CLI's host initialization or an installed privileged helper.
        source=(SRC.parent.parent/'bin/omvm').read_text()
        case=source.split('\nvirt-hook) shift\n',1)[1].split('\nssh) shift;',1)[0]
        for managed,fail in [(True,False),(False,False),(True,True)]:
            with self.subTest(managed=managed,fail=fail),tempfile.TemporaryDirectory(dir=TEST_TMP) as d:
                root=Path(d);trace=root/'trace';helper=root/'helper';sudo=root/'sudo'
                helper.write_text('#!'+sys.executable+'\nimport os,sys,json\n'
                                  'with open(os.environ["TRACE"],"a") as f: f.write(json.dumps(["gate",sys.argv[1:],sys.stdin.read()])+"\\n")\n'
                                  'sys.exit(int(os.environ["FAIL"]))\n')
                helper.chmod(0o700)
                sudo.write_text('#!/bin/sh\n[ "$1" = -n ] && shift\nexec "$@"\n');sudo.chmod(0o700)
                if managed:
                    vm=root/'vms/one';vm.mkdir(parents=True);(vm/'ssh_port').write_text('1')
                script=root/'hook-case'
                functions='\n'.join(name+'() { echo '+value+' >> "$TRACE"; }' for name,value in
                                    [('clip_start','clip'),('follow_start','follow'),('governor_start','governor'),
                                     ('clip_stop','clip-stop'),('governor_stop','governor-stop')])
                # The real name check, which the case arm runs first.
                functions+='\n'+next(l for l in source.splitlines() if l.startswith('valid_name() {'))
                script.write_text('#!/bin/bash\nset -euo pipefail\n'+functions+'\ncase "$1" in\nvirt-hook) shift\n'+
                                  case.replace('/usr/local/libexec/omvm-apple-helpers',shlex.quote(str(helper)))+'\nesac\n')
                script.chmod(0o700)
                env={**os.environ,'PATH':d+':'+os.environ.get('PATH',''),'TRACE':str(trace),'IMAGES':d,'FAIL':'7' if fail else '0'}
                result=subprocess.run([str(script),'virt-hook','one','started','begin'],input=XML,env=env,capture_output=True)
                self.assertEqual(result.returncode,7 if fail else 0,result.stderr)
                lines=trace.read_text().splitlines()
                self.assertEqual(json.loads(lines[0]),['gate',['gate','one','started','begin'],XML.decode()])
                self.assertEqual(lines[1:],['clip','follow','governor'] if managed and not fail else [])


class ProcessIdentityTests(unittest.TestCase):
    def test_libvirt_machine_type_with_omvm_property_clause_keeps_exact_identity(self):
        base=(b'/fake/qemu-system-aarch64\0-machine\0vmapple,accel=kvm\0-name\0guest=one,debug-threads=on\0'
              b'-uuid\0'+fake_uuid('one').encode()+b'\0')
        properties=b'-machine\0uuid=1234,aux-ram-share=on,identity=on\0'
        for argv in (base+properties, properties+base):
            # The executable stays first even when options precede the type.
            if argv.startswith(properties):
                argv=base.split(b'\0',1)[0]+b'\0'+properties+base.split(b'\0',1)[1]
            with self.subTest(order=argv.startswith(base)),patch.object(Path,'read_bytes',return_value=argv), \
                 patch.object(h,'process_start',return_value=300):
                self.assertEqual(h.guest_process(Path('/fake/proc/101')),fake_guest())
        for extra in (b'--machine\0type=vmapple\0',b'-machine\0type=virt\0'):
            with self.subTest(conflict=extra),patch.object(Path,'read_bytes',return_value=base+properties+extra), \
                 patch.object(h,'process_start',return_value=300):
                self.assertFalse(h.guest_process(Path('/fake/proc/101'))['machine_verified'])

    def test_stable_reparented_qemu_has_uuid_and_start_without_daemon_ancestry(self):
        argv=(b'/fake/qemu-system-aarch64\0--machine\0type=vmapple\0--name\0guest=one,debug-threads=on\0'
              b'--uuid\0'+fake_uuid('one').encode()+b'\0')
        with patch.object(Path,'read_bytes',return_value=argv),patch.object(h,'process_start',return_value=300), \
             patch.object(h,'daemon_identity',side_effect=AssertionError('QEMU ancestry must not be required')):
            self.assertEqual(h.guest_process(Path('/fake/proc/101')),fake_guest())

    def test_ambiguous_uuid_name_or_machine_cannot_be_a_bound_identity(self):
        base=b'/fake/qemu-system-aarch64\0-machine\0vmapple\0-name\0one\0-uuid\0'+fake_uuid('one').encode()+b'\0'
        for extra,field in [(b'-uuid\0'+fake_uuid('other').encode()+b'\0','uuid_sha256'),
                            (b'--name\0two\0','name'),(b'--machine\0vmapple\0','machine_verified')]:
            with self.subTest(field=field),patch.object(Path,'read_bytes',return_value=base+extra), \
                 patch.object(h,'process_start',return_value=300):
                self.assertFalse(h.guest_process(Path('/fake/proc/101')).get(field))

    def test_prepare_epoch_crosses_tick_and_fails_closed_if_clock_does_not_advance(self):
        with patch.object(h.os,'sysconf',return_value=100), \
             patch.object(h.time,'clock_gettime_ns',side_effect=[2_000_000_000,2_000_000_000,2_010_000_000]), \
             patch.object(h.time,'monotonic',return_value=0),patch.object(h.time,'sleep') as sleep:
            self.assertEqual(h.prepare_epoch(),200);sleep.assert_called_once_with(.01)
        with patch.object(h.os,'sysconf',return_value=100), \
             patch.object(h.time,'clock_gettime_ns',return_value=2_000_000_000), \
             patch.object(h.time,'monotonic',side_effect=[0,2]):
            with self.assertRaisesRegex(h.Failure,'start ordering'):h.prepare_epoch()

    def test_proc_scan_counts_each_pid_including_duplicate_or_missing_names(self):
        processes={
            '/fake/proc/10/cmdline':b'/fake/qemu-system-aarch64\0-machine\0vmapple\0-name\0guest=one,debug-threads=on\0',
            '/fake/proc/11/cmdline':b'/fake/qemu-system-aarch64\0-machine\0vmapple\0-name\0guest=one\0',
            '/fake/proc/12/cmdline':b'/fake/qemu-system-aarch64\0-machine\0vmapple\0',
            '/fake/proc/13/cmdline':b'/fake/qemu-system-aarch64\0-machine\0virt\0-name\0linux\0',
            '/fake/proc/14/cmdline':b'/fake/other\0vmapple\0',
        }
        with patch.object(Path,'glob',return_value=[Path(path).parent for path in processes]), \
             patch.object(Path,'read_bytes',lambda path:processes[str(path)]), \
             patch.object(h,'process_start',return_value=1000):
            self.assertEqual(h.running_guest_processes(),
                             [{'pid':10,'name':'one','start':1000,'machine_verified':True},
                              {'pid':11,'name':'one','start':1000,'machine_verified':True},
                              {'pid':12,'name':None,'start':1000,'machine_verified':True}])

    def test_qemu_pid_reuse_or_unreadable_identity_cannot_merge_a_pending_slot(self):
        for starts in ([1000,1001],[1000,None],[None,1000],[PermissionError(),1000]):
            with self.subTest(starts=starts),patch.object(Path,'glob',return_value=[Path('/fake/proc/10')]), \
                 patch.object(Path,'read_bytes',return_value=b'/fake/qemu-system-aarch64\0-machine\0vmapple\0-name\0one\0'), \
                 patch.object(h,'process_start',side_effect=starts), \
                 patch.object(h,'daemon_identity',return_value={'daemon_pid':501,'daemon_start':100}):
                self.assertEqual(h.running_guest_processes(),[{'pid':10,'name':None}])

    def test_fairplay_proc_scan_finds_managed_and_untracked_device_backends(self):
        processes={
            '/fake/proc/10/cmdline':b'/fake/backend\0-device-aes\0/fake/device\0',
            '/fake/proc/11/cmdline':b'/fake/legacy\0-device-aes=/fake/device\0',
            '/fake/proc/12/cmdline':b'/fake/backend\0-print-capabilities\0',
            '/fake/proc/13/cmdline':b'/fake/other\0',
            '/fake/proc/14/cmdline':b'/fake/legacy\0--device-aes\0/fake/device\0',
            '/fake/proc/15/cmdline':b'/fake/legacy\0--device-aes=/fake/device\0',
        }
        with patch.object(Path,'glob',return_value=[Path(path).parent for path in processes]), \
             patch.object(Path,'read_bytes',lambda path:processes[str(path)]):
            self.assertEqual(h.running_fairplay_processes(),{10,11,14,15})

    def test_start_identity_handles_parentheses_and_missing_or_unreadable_proc(self):
        value='501 (odd (daemon) name) '+' '.join(['S','1']+['0']*17+['123456','0'])
        with patch.object(Path,'read_text',return_value=value):self.assertEqual(h.process_start(501),123456)
        with patch.object(Path,'read_text',side_effect=FileNotFoundError):self.assertIsNone(h.process_start(501))
        with patch.object(Path,'read_text',side_effect=PermissionError):
            with self.assertRaises(PermissionError):h.process_start(501)
        with patch.object(Path,'read_text',return_value='malformed'):
            with self.assertRaisesRegex(h.Failure,'identity'):h.process_start(501)

    def test_nearest_daemon_ancestry_and_pid_reuse_detection(self):
        values={'/proc/40/comm':'sudo\n','/proc/40/status':'Name:\tsudo\nPPid:\t50\n',
                '/proc/50/comm':'virtqemud\n'}
        with patch.object(h.os,'getppid',return_value=40),patch.object(Path,'read_text',lambda path:values[str(path)]), \
             patch.object(h,'process_start',side_effect=[400,400,500,500]):
            self.assertEqual(h.daemon_identity(),{'daemon_pid':50,'daemon_start':500})
        with patch.object(h.os,'getppid',return_value=50),patch.object(Path,'read_text',return_value='virtqemud\n'), \
             patch.object(h,'process_start',side_effect=[500,501]):
            with self.assertRaisesRegex(h.Failure,'daemon changed'):h.daemon_identity()


class PidMetadataTests(unittest.TestCase):
    def test_kernel_pidfile_lock_requires_granted_posix_write_owner_and_inode(self):
        st=SimpleNamespace(st_dev=os.makedev(1,2),st_ino=300)
        good='2: POSIX ADVISORY WRITE 101 01:02:300 0 0\n'
        cases=[(good,True),(good.replace(' 0 0\n',' 0 EOF\n'),True),
               (good.replace('2: ','2: -> '),False),(good.replace('101','102'),False),
               (good.replace(':300',':301'),False),(good.replace('WRITE','READ'),False),
               (good.replace('POSIX','OFDLCK'),False),(good.replace(' 0 0\n',' 1 1\n'),False),
               ('invalid private lock data\n',False)]
        for text,expected in cases:
            with self.subTest(text=text),patch.object(Path,'read_text',return_value=text):
                self.assertEqual(h.pid_file_locked(st,101),expected)

    def test_qemu_owner_and_real_executable_are_required(self):
        for owner,executable,accepted in [(1000,'/fake/qemu-system-aarch64',True),
                                        (0,'/fake/qemu-system-aarch64',False),(1000,'/fake/python',False)]:
            with self.subTest(owner=owner,executable=executable), \
                 patch.object(Path,'stat',return_value=SimpleNamespace(st_uid=owner)), \
                 patch.object(h.os,'readlink',return_value=executable):
                if accepted:h.verify_qemu_owner(TWO,101)
                else:
                    with self.assertRaisesRegex(h.Failure,'owner/executable'):h.verify_qemu_owner(TWO,101)

    @unittest.skipUnless(os.geteuid()==0 and sys.platform=='linux','Linux root canonical PID metadata contract')
    def test_canonical_pid_file_ownership_links_modes_types_and_bounded_content(self):
        for change in ('valid','symlink','fifo','owner','mode','size','contents','directory-link','directory-mode'):
            with self.subTest(change=change),tempfile.TemporaryDirectory(dir='/run') as d:
                users=Path(d)/'users';users.mkdir(mode=0o700)
                current=users
                for part in ('1000','libvirt','qemu','run'):
                    current=current/part;current.mkdir(mode=0o700);os.chown(current,1000,-1)
                path=current/'one.pid';path.write_text('101\n');path.chmod(0o644);os.chown(path,1000,-1)
                if change=='symlink':
                    target=current/'actual';path.rename(target);path.symlink_to(target)
                elif change=='fifo':path.unlink();os.mkfifo(path)
                elif change=='owner':os.chown(path,0,-1)
                elif change=='mode':path.chmod(0o666)
                elif change=='size':path.write_text('1'*33)
                elif change=='contents':path.write_text('private-not-a-pid')
                elif change=='directory-link':
                    target=current.with_name('actual-run');current.rename(target);current.symlink_to(target)
                elif change=='directory-mode':current.chmod(0o770)
                with patch.object(h,'PID_RUN',users):
                    if change=='valid':
                        with h.canonical_pid_file(TWO,'one') as (pid,st):
                            self.assertEqual(pid,101);self.assertEqual(st.st_uid,1000)
                    else:
                        with self.assertRaises((h.Failure,OSError)):
                            with h.canonical_pid_file(TWO,'one'):self.fail('untrusted metadata accepted')


class BackendGuardTests(unittest.TestCase):
    @contextlib.contextmanager
    def services(self,units=None,processes=None,identities=None):
        units={'omvm-fairplay@one.service':('active',101)} if units is None else units
        processes={101} if processes is None else processes
        identities={101:(8,9)} if identities is None else identities
        def command(args,timeout=30):
            if args[1]=='list-units':
                return '\n'.join(name+' loaded '+state+' running' for name,(state,pid) in units.items()).encode()
            self.assertEqual(args[1],'show')
            state,pid=units[args[2]]
            return f'ActiveState={state}\nMainPID={pid}\n'.encode()
        def process_exe(path,*args,**kwargs):
            pid=int(path.parent.name);device,inode=identities[pid]
            return SimpleNamespace(st_dev=device,st_ino=inode)
        with patch.object(h,'command',side_effect=command) as calls, \
             patch.object(Path,'stat',process_exe), \
             patch.object(h,'running_fairplay_processes',return_value=processes), \
             patch.object(h,'peer') as peer:
            yield calls,peer

    def test_every_service_executable_and_root_socket_peer_is_verified(self):
        units={h.unit('one'):('active',101),h.unit('two'):('active',102)}
        with self.services(units,{101,102},{101:(8,9),102:(8,9)}) as (command,peer):
            self.assertEqual(h.verify_running_backends(TWO,(8,9)),{101,102})
            self.assertEqual([call.args for call in peer.call_args_list],
                             [(h.paths('one')[0],101),(h.paths('two')[0],102)])
            self.assertTrue(all(call.args[0][1] in ('show','list-units') for call in command.call_args_list))

    def test_mixed_old_inode_legacy_unit_and_unmanaged_process_are_refused(self):
        cases=[({h.unit('one'):('active',101)},{101},{101:(8,10)},'pinned executable'),
               ({'omvm-fairplay-legacy.service':('active',101)},{101},{101:(8,9)},'legacy or unmanaged'),
               ({'omvm-fairplay-legacy.service':('activating',0)},set(),{},'legacy or unmanaged'),
               ({h.unit('one'):('active',101)},{101,999},{101:(8,9)},'unmanaged FairPlay hardware'),
               ({h.unit('one'):('deactivating',101)},{101},{101:(8,9)},'stopping')]
        for units,processes,identities,error in cases:
            with self.subTest(error=error),self.services(units,processes,identities):
                with self.assertRaisesRegex(h.Failure,error):h.verify_running_backends(TWO,(8,9))

    def test_only_own_canonical_starting_mainpid_may_be_pre_exec_wrapper(self):
        with self.services(identities={101:(8,10)}) as (command,peer):
            self.assertEqual(h.verify_running_backends(TWO,(8,9),starting=(h.unit('one'),101)),{101})
            peer.assert_not_called()
            with self.assertRaisesRegex(h.Failure,'pinned executable'):
                h.verify_running_backends(TWO,(8,9),starting=(h.unit('two'),101))

    def test_dependency_wait_without_process_is_not_a_running_backend(self):
        with self.services({h.unit('one'):('activating',0)},set(),{}) as (command,peer):
            self.assertEqual(h.verify_running_backends(TWO,(8,9)),set());peer.assert_not_called()

    def test_wrong_root_socket_peer_is_not_restarted(self):
        with self.services() as (command,peer):
            peer.side_effect=h.Failure('unexpected helper socket peer')
            with self.assertRaisesRegex(h.Failure,'socket peer'):h.verify_running_backends(TWO,(8,9))
            self.assertTrue(all(call.args[0][1] in ('show','list-units') for call in command.call_args_list))


class ProviderTests(unittest.TestCase):
    def status(self,state,flags=6):
        return {'status':{'state':state,'flags':flags,'completed_ops':5}}

    def test_status_refuses_busy_and_unknown(self):
        for state,flags,error in [(2,7,'busy'),(4,0,'unknown')]:
            with patch.object(h,'command',return_value=json.dumps(self.status(state,flags)).encode()):
                with self.assertRaisesRegex(h.Failure,error):h.provider_status(CFG)

    def test_two_vm_status_allows_only_ready_busy_snapshot(self):
        with patch.object(h,'command',return_value=json.dumps(self.status(2,7)).encode()):
            self.assertEqual(h.provider_status(TWO)['flags'],7)
        for state in (0,1,3):
            with self.subTest(state=state),patch.object(h,'command',return_value=json.dumps(self.status(state,7)).encode()):
                with self.assertRaisesRegex(h.Failure,'busy'):h.provider_status(TWO)

    def test_two_vm_ready_busy_initialization_reuses_provider_without_any_work(self):
        with patch.object(h,'provider_status',return_value=self.status(2,7)['status']),patch.object(h,'command') as command:
            h.initialize_provider(TWO);command.assert_not_called()

    def test_two_vm_ready_busy_startup_checks_pinned_service_and_both_peers(self):
        with patch.object(h,'validate'),patch.object(h,'backend_executable',return_value=(8,9)), \
             patch.object(h,'provider_status',return_value=self.status(2,7)['status']), \
             patch.object(h,'service_pid',return_value=101), \
             patch.object(h,'verify_running_backends',return_value={101}) as backends, \
             patch.object(h,'sep_peer') as sep,patch.object(h,'peer') as peer,patch.object(h,'command') as command:
            h.ready(TWO,'one')
            backends.assert_called_once_with(TWO,(8,9));sep.assert_called_once_with(TWO)
            peer.assert_called_once_with(h.paths('one')[0],101);command.assert_not_called()

    def test_two_vm_readiness_refuses_poison_or_missing_resources(self):
        for state,flags,error in [(3,6,'poisoned'),(2,1,'retained')]:
            with self.subTest(state=state),patch.object(h,'validate'),patch.object(h,'backend_executable',return_value=(8,9)), \
                 patch.object(h,'provider_status',return_value=self.status(state,flags)['status']), \
                 patch.object(h.time,'monotonic',side_effect=[0,0,10]),patch.object(h.time,'sleep'), \
                 patch.object(h,'command') as command,patch.object(h,'verify_running_backends') as backends:
                with self.assertRaisesRegex(h.Failure,error):h.ready(TWO,'one',wait=1)
                command.assert_not_called();backends.assert_not_called()

    def test_ready_reuse_and_poison_never_issue_hardware_work(self):
        for state in [2,3]:
            with self.subTest(state=state),patch.object(h,'provider_status',return_value=self.status(state)['status']),patch.object(h,'command') as command:
                if state==2:h.initialize_provider(CFG)
                else:
                    with self.assertRaisesRegex(h.Failure,'poisoned'):h.initialize_provider(CFG)
                command.assert_not_called()

    def test_selftest_failure_prevents_init_and_success_orders_it_once(self):
        cfg={**CFG,'provider':{**CFG['provider'],'seeds':{'path':'/fake/seeds'}}}
        untested={'state':0,'flags':0,'completed_ops':0}
        for after,success in [(untested,False),(self.status(1)['status'],True)]:
            with self.subTest(success=success),patch.object(h,'provider_status',side_effect=[untested,after,self.status(2)['status']]),patch.object(h,'command') as command:
                if success:h.initialize_provider(cfg)
                else:
                    with self.assertRaisesRegex(h.Failure,'self-test'):h.initialize_provider(cfg)
                actions=[c.args[0][4] for c in command.call_args_list]
                self.assertEqual(actions,['selftest','init'] if success else ['selftest'])

    def test_readiness_requires_live_sep_and_exact_fairplay_process(self):
        with patch.object(h,'provider_status',return_value={'state':2,'flags':6}), \
             patch.object(h,'command',return_value=b'ActiveState=active\nMainPID=1234\n'), \
             patch.object(h,'peer',side_effect=h.Failure('wrong peer')) as peer:
            with self.assertRaisesRegex(h.Failure,'wrong peer'):h.ready(CFG,'one',wait=.01)
            self.assertEqual(peer.call_args.args[0],h.SEP)


if __name__=='__main__':unittest.main()
