#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Extract VMApple flash from a stopped VM's native auxiliary storage.

Keep the complete native file with its paired disk/profile. Version 2 may
contain metadata after the flash region; that metadata is not a QEMU drive.
The caller must stop the VM before invoking this tool.
"""
import argparse
import os
from pathlib import Path
import stat
import struct
import tempfile

MAGIC = 0x271DAD97FEB3D5A5
FLASH_OFFSET = 0x4000
FLASH_SIZE = 0x2000000


def extract(source, destination):
    if destination.exists() and os.path.samefile(source, destination):
        raise ValueError('source and destination must be different files')
    fd = os.open(source, os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW)
    temporary = None
    try:
        with os.fdopen(fd, 'rb') as src:
            info = os.fstat(src.fileno())
            if not stat.S_ISREG(info.st_mode):
                raise ValueError('source must be a regular native auxiliary file')
            header = src.read(24)
            if len(header) != 24:
                raise ValueError('truncated native auxiliary header')
            magic, version, kind = struct.unpack('<QQQ', header)
            if magic != MAGIC or version not in (1, 2) or kind != 1:
                raise ValueError('unsupported native auxiliary header')
            minimum = FLASH_OFFSET + FLASH_SIZE
            if info.st_size < minimum or (version == 1 and info.st_size != minimum):
                raise ValueError('invalid native auxiliary file size')
            src.seek(FLASH_OFFSET)
            with tempfile.NamedTemporaryFile(prefix='.' + destination.name + '.',
                                              dir=destination.parent, delete=False) as out:
                temporary = Path(out.name)
                remaining = FLASH_SIZE
                while remaining:
                    data = src.read(min(1024 * 1024, remaining))
                    if not data:
                        raise ValueError('source truncated during flash extraction')
                    out.write(data)
                    remaining -= len(data)
                out.flush()
                os.fsync(out.fileno())
            os.replace(temporary, destination)
            temporary = None
            return version
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path)
    parser.add_argument('destination', type=Path)
    args = parser.parse_args()
    try:
        version = extract(args.source, args.destination)
    except (OSError, ValueError) as error:
        parser.exit(1, 'error: ' + str(error) + '\n')
    print(f'extracted {FLASH_SIZE} flash bytes from native auxiliary version {version}')


if __name__ == '__main__':
    main()
