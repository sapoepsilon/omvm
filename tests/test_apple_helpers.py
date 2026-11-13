#!/usr/bin/env python3
"""Lifecycle contracts with fake services, never SEP/AES operations or a guest.

Protects the root trust boundary, one-owner gate, provider poison/reuse and
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
import unittest
from unittest.mock import patch

SRC=Path(__file__).resolve().parents[1]/'share/apple-helpers.py'
spec=importlib.util.spec_from_file_location('helpers',SRC)
h=importlib.util.module_from_spec(spec);spec.loader.exec_module(h)
CFG={'allow_uid':1000,'vms':{'one':{'identifier':{}}},'provider':{'diagnostic':{'path':'/fake/diagnostic'}}}
XML=b'<domain xmlns:qemu="http://libvirt.org/schemas/domain/qemu/1.0"><name>one</name><os><type machine="vmapple"/></os><qemu:commandline><qemu:arg value="-device"/><qemu:arg value="apple-fairplay-pci,relay-socket=/run/omvm-fairplay-managed-one/relay.sock"/><qemu:env name="OMVM_IDENTITY_SIGNER" value="/run/omvm-identity/sep.sock"/></qemu:commandline></domain>'


class GateTests(unittest.TestCase):
    def test_bad_domain_or_existing_guest_never_starts_helpers(self):
        for xml,guests,reason in [(XML.replace(b'<name>one',b'<name>two'),set(),'name mismatch'),
                                  (XML.replace(b'/run/omvm-identity/sep.sock',b'/tmp/wrong'),set(),'missing'),
                                  (XML,{'another'},'another macOS guest')]:
            with self.subTest(reason=reason), patch.object(h,'locked',return_value=contextlib.nullcontext()), \
                 patch.object(h,'running_guests',return_value=guests),patch.object(h,'command') as command:
                with self.assertRaisesRegex(h.Failure,reason):h.gate(CFG,'one','prepare','begin',xml)
                command.assert_not_called()

    def test_socket_substring_cannot_mask_wrong_device_or_duplicate_signer(self):
        wrong=XML.replace(b'apple-fairplay-pci,relay-socket=/run/omvm-fairplay-managed-one/relay.sock',b'apple-fairplay-pci,relay-socket=/tmp/wrong,comment=/run/omvm-fairplay-managed-one/relay.sock')
        duplicate=XML.replace(b'</qemu:commandline>',b'<qemu:env name="OMVM_IDENTITY_SIGNER" value="/tmp/wrong"/></qemu:commandline>')
        for xml in [wrong,duplicate]:
            with self.subTest(xml=xml),self.assertRaises(h.Failure):h.check_domain('one',h.domain('one',xml))

    def test_unmanaged_vmapple_guest_cannot_bypass_active_guest_guard(self):
        xml=b'<domain><name>other</name><os><type machine="vmapple"/></os></domain>'
        with patch.object(h,'locked',return_value=contextlib.nullcontext()),patch.object(h,'running_guests',return_value={'one'}):
            with self.assertRaisesRegex(h.Failure,'another macOS guest'):h.gate(CFG,'other','prepare','begin',xml)

    def test_foreign_user_or_unregistered_linux_helper_domain_fails(self):
        with patch.dict(os.environ,{'SUDO_UID':'1001'}):
            with self.assertRaisesRegex(h.Failure,'caller'):h.gate(CFG,'one','prepare','begin',XML)
        with patch.dict(os.environ,{'SUDO_UID':'1000'}):
            with self.assertRaisesRegex(h.Failure,'absent'):h.gate(CFG,'unknown','prepare','begin',XML.replace(b'<name>one',b'<name>unknown'))
            h.gate(CFG,'ordinary','prepare','begin',b'<domain><name>ordinary</name></domain>')

    @unittest.skipUnless(sys.platform=='linux','Linux /proc contract')
    def test_live_reservation_blocks_even_without_qemu_yet(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);(root/'active.json').write_text('{}')
            with patch.object(h,'RUN',root),patch.object(h,'locked',return_value=contextlib.nullcontext()), \
                 patch.object(h,'running_guests',return_value=set()), \
                 patch.object(h,'secure_file',return_value=json.dumps({'vm':'other','daemon_pid':os.getpid()}).encode()), \
                 patch.object(h,'command') as command:
                with self.assertRaisesRegex(h.Failure,'reserved'):h.gate(CFG,'one','prepare','begin',XML)
                command.assert_not_called()


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
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'config';p.write_bytes(b'{}')
            with self.assertRaisesRegex(h.Failure,'ancestor'):h.secure_file(p)
            link=Path(d)/'link';link.symlink_to(p)
            with self.assertRaises((h.Failure,OSError)):h.secure_file(link)

    @unittest.skipUnless(os.geteuid()==0,'root peer ownership check needs root test process')
    def test_ready_socket_must_belong_to_expected_service_process(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'sock';s=socket.socket(socket.AF_UNIX,socket.SOCK_STREAM);s.bind(str(p));s.listen(3)
            try:
                h.peer(p,os.getpid())
                with self.assertRaisesRegex(h.Failure,'peer'):h.peer(p,os.getpid()+1)
            finally:s.close()

    @unittest.skipUnless(os.geteuid()==0 and sys.platform=='linux','Linux root/client socket-owner contract')
    def test_sep_client_owned_socket_still_requires_root_service_peer(self):
        with tempfile.TemporaryDirectory() as d:
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
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);hook=root/'libvirt/hooks/qemu';hook.parent.mkdir(parents=True)
            recorder=root/'recorder.py'
            recorder.write_text('import sys,json; print(json.dumps([sys.argv[1:],sys.stdin.read()]))\n')
            hook.write_text('#!/bin/sh\n[ -f "'+d+'/vms/$1/ssh_port" ] || exit 0\nexport OMVM_IMAGES="'+d+'"\nexec '+shlex.quote(sys.executable)+' '+shlex.quote(str(recorder))+' virt-hook "$1" "$2" >/dev/null 2>&1 </dev/null\n')
            hook.chmod(0o700)
            env={**os.environ,'XDG_CONFIG_HOME':d}
            installer=SRC.parent/'apple-helpers-hook.py'
            subprocess.run([sys.executable,str(installer)],env=env,check=True,capture_output=True)
            output=subprocess.check_output([str(hook),'one','prepare','begin'],input=XML)
            args,xml=json.loads(output)
            self.assertEqual(args,['virt-hook','one','prepare','begin'])
            self.assertEqual(xml,XML.decode())
            before=hook.read_bytes()
            subprocess.run([sys.executable,str(installer)],env=env,check=True,capture_output=True)
            self.assertEqual(hook.read_bytes(),before)


class ProviderTests(unittest.TestCase):
    def status(self,state,flags=6):
        return {'status':{'state':state,'flags':flags,'completed_ops':5}}

    def test_status_refuses_busy_and_unknown(self):
        for state,flags,error in [(2,7,'busy'),(4,0,'unknown')]:
            with patch.object(h,'command',return_value=json.dumps(self.status(state,flags)).encode()):
                with self.assertRaisesRegex(h.Failure,error):h.provider_status(CFG)

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
        with patch.object(h,'provider_status',return_value={'state':2}), \
             patch.object(h,'command',return_value=b'ActiveState=active\nMainPID=1234\n'), \
             patch.object(h,'peer',side_effect=h.Failure('wrong peer')) as peer:
            with self.assertRaisesRegex(h.Failure,'wrong peer'):h.ready(CFG,'one',wait=.01)
            self.assertEqual(peer.call_args.args[0],h.SEP)


if __name__=='__main__':unittest.main()
