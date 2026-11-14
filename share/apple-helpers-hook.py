#!/usr/bin/env python3
"""Preserve an existing omvm hook while forwarding phase and XML to readiness."""
import os
from pathlib import Path
import re
import stat
import tempfile

path=Path(os.environ.get('XDG_CONFIG_HOME',str(Path.home()/'.config')))/'libvirt/hooks/qemu'
st=path.lstat()
if not stat.S_ISREG(st.st_mode) or st.st_uid!=os.getuid():
    raise SystemExit('existing omvm hook must be a regular file owned by this user')
text=path.read_text()
old=r'''(?m)^exec (.+) virt-hook "\$1" "\$2" >/dev/null 2>&1 </dev/null$'''
new,count=re.subn(old,r'exec \1 virt-hook "$1" "$2" "$3"',text)
if count==0:
    if re.search(r'(?m)^exec .+ virt-hook "\$1" "\$2" "\$3"$',text):
        print('omvm hook already forwards phase and domain XML')
        raise SystemExit(0)
    raise SystemExit('unrecognized hook; preserve it and merge the readiness call manually')
if count!=1:raise SystemExit('ambiguous hook; not modified')
# All vmapple guests share the hardware owner, including a VM outside IMAGES.
# The root gate parses XML and ignores non-vmapple guests.
guard=r'(?m)^(\[ -f .+/vms/\$1/ssh_port" \] \|\| exit 0)$'
new=re.sub(guard,r'case "$2/$3" in prepare/begin|release/end) ;; *) \1 ;; esac',new)
backup=path.with_name('qemu.before-apple-helpers')
if not backup.exists():
    fd=os.open(backup,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
    with os.fdopen(fd,'w') as f:f.write(text)
fd,name=tempfile.mkstemp(prefix='.qemu-',dir=path.parent)
try:
    with os.fdopen(fd,'w') as f:f.write(new); f.flush(); os.fsync(f.fileno())
    os.chmod(name,stat.S_IMODE(st.st_mode))
    os.replace(name,path)
finally:
    if os.path.exists(name):os.unlink(name)
print('omvm hook forwards phase and domain XML; existing environment is preserved')
