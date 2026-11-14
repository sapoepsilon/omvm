#!/usr/bin/env python3
"""Install reviewed helpers; enable host prerequisites and launch VM helpers on demand."""
import argparse
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile

HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('helpers',HERE/'apple-helpers.py')
helpers=importlib.util.module_from_spec(spec)
spec.loader.exec_module(helpers)


def atomic(path,data,mode):
    path=Path(path)
    path.parent.mkdir(parents=True,exist_ok=True)
    fd,name=tempfile.mkstemp(prefix='.'+path.name+'-',dir=path.parent)
    try:
        os.fchmod(fd,mode)
        with os.fdopen(fd,'wb') as f:
            f.write(data); f.flush(); os.fsync(f.fileno())
        os.replace(name,path)
        directory=os.open(path.parent,os.O_RDONLY|os.O_DIRECTORY)
        try: os.fsync(directory)
        finally: os.close(directory)
    finally:
        if os.path.exists(name):os.unlink(name)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('manifest',type=Path)
    a=p.parse_args()
    helpers.require(os.geteuid()==0,'run installer as root')
    data=helpers.secure_file(a.manifest,1024*1024)
    cfg=helpers.validate(json.loads(data))
    helpers.require(Path('/etc/systemd/system/omvm-sep-identity.service').is_file(),
                    'install the reviewed SEP identity service first')
    managed_names=set(cfg['vms'])
    if helpers.CONFIG.exists():
        old=helpers.config()
        managed_names.update(old['vms'])
        if helpers.secure_file(helpers.CONFIG)!=data:
            for name in managed_names:
                r=subprocess.run(['/usr/bin/systemctl','is-active','--quiet',helpers.unit(name)])
                helpers.require(r.returncode!=0,'stop persistent FairPlay services before changing their manifest')
    content=f"#{cfg['allow_uid']} ALL=(root) NOPASSWD: /usr/local/libexec/omvm-apple-helpers gate *, /usr/local/libexec/omvm-apple-helpers status *\n"
    with tempfile.NamedTemporaryFile(mode='w',prefix='omvm-sudoers-',delete=True) as f:
        f.write(content); f.flush()
        helpers.command(['/usr/bin/visudo','-cf',f.name])
    backups=Path('/var/lib/omvm/apple-helpers/install-backups')
    backups.mkdir(parents=True,exist_ok=True,mode=0o700)
    destinations={
        Path('/usr/local/libexec/omvm-apple-helpers'):(HERE/'apple-helpers.py',0o755),
        Path('/etc/systemd/system/omvm-uid1-provider.service'):(HERE/'omvm-uid1-provider.service',0o644),
        Path('/etc/systemd/system/omvm-fairplay@.service'):(HERE/'omvm-fairplay@.service',0o644),
    }
    for target,(source,mode) in destinations.items():
        new=source.read_bytes()
        if target.exists() and target.read_bytes()!=new:
            old=target.read_bytes()
            atomic(backups/(target.name+'.'+helpers.hashlib.sha256(old).hexdigest()[:12]),old,0o600)
        atomic(target,new,mode)
    if helpers.CONFIG.exists() and helpers.secure_file(helpers.CONFIG)!=data:
        old=helpers.secure_file(helpers.CONFIG)
        atomic(backups/('manifest.'+helpers.hashlib.sha256(old).hexdigest()[:12]+'.json'),old,0o600)
    atomic(helpers.CONFIG,data,0o600)
    atomic('/etc/sudoers.d/omvm-apple-helpers',content.encode(),0o440)
    for name in cfg['vms']:
        helpers.private_dir(helpers.paths(name)[1].parent)
    helpers.command(['/usr/bin/systemctl','daemon-reload'])
    helpers.command(['/usr/bin/systemctl','enable','omvm-uid1-provider.service','omvm-sep-identity.service'])
    # Eager sibling startup bypasses the one-guest gate and may overlap hardware
    # access. The existing libvirt gate starts and checks the selected helper.
    # Remove old boot links without --now: running helper state stays intact.
    helpers.command(['/usr/bin/systemctl','disable']+[helpers.unit(n) for n in sorted(managed_names)])
    print('Installed helpers. Host prerequisites enabled; VM helpers start at guest launch.')
    print('No service was started, stopped or restarted.')
    print('As the VM owner, run: omvm helpers install-hook')
    print('For each new helper state, explicitly enroll the stopped VM before starting its service.')


if __name__=='__main__':
    try:main()
    except (helpers.Failure,OSError,ValueError,KeyError,subprocess.TimeoutExpired) as exc:
        print('omvm helpers install: '+str(exc),file=helpers.sys.stderr)
        raise SystemExit(1)
