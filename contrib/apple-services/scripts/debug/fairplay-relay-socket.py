#!/usr/bin/env python3
"""Private Unix-socket adapter for one-request OFP1/OFR1 relay commands."""
import argparse
import asyncio
import os
import signal
import stat
import struct
import sys
from pathlib import Path

LIMIT = 1024 * 1024


async def serve_request(reader, writer, command):
    process = None
    try:
        header = await reader.readexactly(12)
        magic, length, capacity = struct.unpack('<4sII', header)
        if magic not in (b'OFP1', b'OFP2') or not (0 < length <= LIMIT and 0 < capacity <= LIMIT):
            raise ValueError('invalid request header')
        if magic == b'OFP2':
            queue = await reader.readexactly(4)
            if struct.unpack('<I', queue)[0] not in (0, 3):
                raise ValueError('unsupported queue')
            header += queue
        request = header + await reader.readexactly(length)
        if await reader.read(1):
            raise ValueError('trailing request data')
        process = await asyncio.create_subprocess_exec(
            *command, stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL,
            start_new_session=True)
        process.stdin.write(request)
        await process.stdin.drain()
        process.stdin.close()
        reply_header = await process.stdout.readexactly(16)
        magic, stage, status, length = struct.unpack('<4sIII', reply_header)
        if magic != b'OFR1' or stage > 4 or length > capacity:
            raise ValueError('invalid response header')
        if (stage or status) and length:
            raise ValueError('error response has payload')
        body = await process.stdout.readexactly(length)
        if await process.stdout.read(1):
            raise ValueError('trailing response data')
        result = await process.wait()
        if result != (1 if stage or status else 0):
            raise ValueError('response/exit disagreement')
        print('relay completed input=%d output=%d stage=%d status=%d' %
              (len(request) - len(header), length, stage, status),
              file=sys.stderr, flush=True)
        writer.write(reply_header + body)
        await writer.drain()
    finally:
        if process is not None and process.returncode is None:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            await process.wait()


async def run(args):
    path = Path(args.socket)
    parent = path.parent.stat()
    if parent.st_uid != os.getuid() or stat.S_IMODE(parent.st_mode) & 0o077:
        raise ValueError('socket parent must be owned by current user, mode 0700')
    # Refuse stale/existing paths rather than unlink someone else's listener.
    if os.path.lexists(path):
        raise ValueError('socket path already exists')
    active = set()
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, stop.set)

    async def connected(reader, writer):
        task = asyncio.current_task()
        if len(active) >= 4:
            writer.close()
            await writer.wait_closed()
            return
        active.add(task)
        try:
            await asyncio.wait_for(serve_request(reader, writer, args.command),
                                   timeout=args.timeout)
        except (ValueError, OSError, asyncio.IncompleteReadError,
                asyncio.TimeoutError):
            print('relay transport request failed', file=sys.stderr, flush=True)
        finally:
            writer.close()
            try:
                await writer.wait_closed()
            except OSError:
                pass
            active.discard(task)

    old_mask = os.umask(0o077)
    try:
        server = await asyncio.start_unix_server(connected, path=str(path))
        os.chmod(path, 0o600)
    finally:
        os.umask(old_mask)
    identity = path.stat()
    try:
        async with server:
            await stop.wait()
    finally:
        tasks = list(active)
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        if path.exists():
            current = path.stat()
            if (current.st_dev, current.st_ino) == (identity.st_dev, identity.st_ino):
                path.unlink()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--socket', required=True)
    parser.add_argument('--timeout', type=float, default=12)
    parser.add_argument('command', nargs=argparse.REMAINDER)
    args = parser.parse_args()
    if args.command[:1] == ['--']:
        args.command.pop(0)
    if not args.command or args.timeout <= 0:
        parser.error('provide a positive timeout and a relay command after --')
    asyncio.run(run(args))


if __name__ == '__main__':
    main()
