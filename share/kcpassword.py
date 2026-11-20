#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Encode a macOS automatic-login password the way loginwindow reads /etc/kcpassword.

    kcpassword.py PASSWORD_FILE   -> base64 of the kcpassword bytes on stdout

The password is the first line of PASSWORD_FILE (read from a file, never argv,
so it does not show up in the host's process list). loginwindow XORs the file
with a fixed 11-byte key; the plaintext is the password followed by NUL padding
up to the next multiple of 12 bytes (always at least one NUL). macOS 13 and
later reject files that are not padded to a multiple of 12.
"""

import base64
import sys

KEY = bytes([0x7D, 0x89, 0x52, 0x23, 0xD2, 0xBC, 0xDD, 0xEA, 0xA3, 0xB9, 0x1F])


def encode(password: str) -> bytes:
    data = password.encode("utf-8")
    data += b"\0" * (12 - len(data) % 12)
    return bytes(b ^ KEY[i % len(KEY)] for i, b in enumerate(data))


def decode(blob: bytes) -> str:
    data = bytes(b ^ KEY[i % len(KEY)] for i, b in enumerate(blob))
    return data.split(b"\0", 1)[0].decode("utf-8")


def main(argv):
    if len(argv) != 2:
        print("usage: kcpassword.py PASSWORD_FILE", file=sys.stderr)
        return 2
    with open(argv[1], encoding="utf-8") as f:
        password = f.readline().rstrip("\n")
    if not password:
        print("kcpassword.py: empty password", file=sys.stderr)
        return 1
    print(base64.b64encode(encode(password)).decode("ascii"))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
