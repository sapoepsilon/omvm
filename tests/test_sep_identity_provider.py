#!/usr/bin/env python3
"""Provider boundary checks; no SEP calls or real host identity are used."""

import errno
import importlib.util
import multiprocessing
import os
from pathlib import Path
import socket
import stat
import struct
import subprocess
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

SOURCE = Path(__file__).resolve().parents[1] / "share" / "sep-identity-provider.py"
if not SOURCE.exists():
    SOURCE = Path("/tmp/sep-identity-provider.py")
SPEC = importlib.util.spec_from_file_location("sep_identity_provider", SOURCE)
PROVIDER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(PROVIDER)
POINT = bytes.fromhex(
    "046b17d1f2e12c4247f8bce6e563a440f277037d812deb33a0f4a13945d898c296"
    "4fe342e2fe1a7f9b8ee7eb4a7c0f9e162bce33576b315ececbb6406837bf51f5"
)
SIGNATURE = bytes.fromhex("3006020101020101")
ATTESTATION = bytes.fromhex("300a02010230050403616263")


def startup_export(point=POINT, der=ATTESTATION):
    return bytearray(PROVIDER.EXPORT_HEADER.pack(1, len(der), point, bytes(7))
                     + der.ljust(PROVIDER.EXPORT_DER_MAX, b"\0"))


class FakeSigner:
    def __init__(self):
        self.payloads = []
        self.digests = []

    def sign(self, payload):
        self.payloads.append(payload)
        return SIGNATURE

    def sign_digest(self, digest):
        self.digests.append(digest)
        return SIGNATURE

    def close(self):
        pass


def fake_server(path, allow_uid):
    PROVIDER.serve(Path(path), allow_uid, FakeSigner())


class CredentialsProxy:
    def __init__(self, connection, uid):
        self.connection = connection
        self.uid = uid

    def getsockopt(self, *_args):
        return struct.pack("=3i", os.getpid(), self.uid, 0)

    def __getattr__(self, name):
        return getattr(self.connection, name)


class ProviderTest(unittest.TestCase):
    def startup_patches(self, ioctl):
        from contextlib import ExitStack
        stack = ExitStack()
        stack.enter_context(patch.object(PROVIDER, "read_pinned_point", return_value=POINT))
        stack.enter_context(patch.object(PROVIDER, "open_root_file", return_value=1233))
        stack.enter_context(patch.object(PROVIDER.os, "open", return_value=1234))
        stack.enter_context(patch.object(PROVIDER.os, "close"))
        def file_stat(fd):
            mode = (stat.S_IFREG if fd == 1233 else stat.S_IFCHR) | 0o600
            return os.stat_result((mode, 0, 0, 1, 0, 0, 251, 0, 0, 0))
        stack.enter_context(patch.object(PROVIDER.os, "fstat", side_effect=file_stat))
        stack.enter_context(patch.object(PROVIDER.fcntl, "ioctl", side_effect=ioctl))
        return stack

    def exchange(self, wire, *, fake_uid=None, half_close=False):
        left, right = socket.socketpair()
        signer = FakeSigner()
        connection = CredentialsProxy(left, fake_uid) if fake_uid is not None else left
        thread = threading.Thread(target=PROVIDER.handle_connection,
                                  args=(connection, signer, os.getuid(), 0.1))
        thread.start()
        try:
            right.sendall(wire)
            if half_close:
                right.shutdown(socket.SHUT_WR)
            right.settimeout(1)
            response = right.recv(80)
            status, length = PROVIDER.HEADER.unpack(response[:8])
            thread.join(1)
            self.assertFalse(thread.is_alive())
            self.assertEqual(length, len(response[8:]))
            return status, response[8:], signer
        finally:
            right.close()
            left.close()

    def test_exact_protocol_signs_raw_payload(self):
        payload = b"challenge\0with binary data"
        status, signature, signer = self.exchange(PROVIDER.HEADER.pack(1, len(payload)) + payload)
        self.assertEqual((status, signature), (0, SIGNATURE))
        self.assertEqual(signer.payloads, [payload])

    def test_digest_protocol_preserves_all_32_digest_bytes(self):
        digest = bytes(range(32))
        status, signature, signer = self.exchange(PROVIDER.HEADER.pack(2, 32) + digest)
        self.assertEqual((status, signature), (0, SIGNATURE))
        self.assertEqual(signer.digests, [digest])
        self.assertFalse(signer.payloads)

    def test_rejects_untrusted_peer_before_signing(self):
        status, signature, signer = self.exchange(PROVIDER.HEADER.pack(1, 0), fake_uid=424242)
        self.assertEqual((status, signature), (errno.EACCES, b""))
        self.assertFalse(signer.payloads)

    def test_rejects_oversized_unknown_and_truncated_requests(self):
        cases = [
            (PROVIDER.HEADER.pack(1, 65537), False, errno.EMSGSIZE),
            (PROVIDER.HEADER.pack(3, 0), False, errno.EOPNOTSUPP),
            (PROVIDER.HEADER.pack(2, 0), False, errno.EINVAL),
            (PROVIDER.HEADER.pack(2, 31), False, errno.EINVAL),
            (PROVIDER.HEADER.pack(2, 33), False, errno.EINVAL),
            (PROVIDER.HEADER.pack(2, 65537), False, errno.EMSGSIZE),
            (PROVIDER.HEADER.pack(2, 32) + bytes(31), True, errno.EPROTO),
            (b"\x00\x01", True, errno.EPROTO),
            (PROVIDER.HEADER.pack(1, 9) + b"short", True, errno.EPROTO),
        ]
        for wire, half_close, expected in cases:
            with self.subTest(expected=expected):
                status, signature, signer = self.exchange(wire, half_close=half_close)
                self.assertEqual((status, signature), (expected, b""))
                self.assertFalse(signer.payloads)
                self.assertFalse(signer.digests)

    def test_slow_sender_has_a_total_deadline(self):
        started = time.monotonic()
        status, signature, signer = self.exchange(PROVIDER.HEADER.pack(1, 9))
        self.assertEqual((status, signature), (errno.ETIMEDOUT, b""))
        self.assertLess(time.monotonic() - started, 0.5)
        self.assertFalse(signer.payloads)

    def test_timed_out_signer_never_spawns_concurrent_work(self):
        class SlowSigner(FakeSigner):
            active = 0
            maximum = 0
            def sign(self, payload):
                self.active += 1
                self.maximum = max(self.maximum, self.active)
                time.sleep(0.1)
                self.active -= 1
                return SIGNATURE
        hardware = SlowSigner()
        signer = PROVIDER.BoundedSigner(hardware, timeout=0.01)
        try:
            with self.assertRaises(OSError) as timeout:
                signer.sign(b"first")
            self.assertEqual(timeout.exception.errno, errno.ETIMEDOUT)
            with self.assertRaises(OSError) as busy:
                signer.sign_digest(bytes(32))
            self.assertEqual(busy.exception.errno, errno.EBUSY)
            self.assertEqual(hardware.maximum, 1)
        finally:
            signer.close()

    def test_ioctl_hashes_raw_challenge_and_rejects_a_different_key(self):
        signer = object.__new__(PROVIDER.SepSigner)
        signer.fd, signer.point = 1234, POINT
        payload = b"raw Value bytes"
        def ioctl(_fd, command, response, _mutate):
            self.assertEqual(command, 0xC0B0B10A)
            _n, digest, _point, _signature, _reserved = PROVIDER.ATTEST.unpack(response)
            self.assertEqual(digest, PROVIDER.hashlib.sha256(payload).digest())
            response[:] = PROVIDER.ATTEST.pack(8, digest, POINT, SIGNATURE.ljust(72, b"\0"), bytes(3))
        with patch.object(PROVIDER.fcntl, "ioctl", side_effect=ioctl), \
                patch.object(PROVIDER, "verify_signature") as verify:
            self.assertEqual(signer.sign(payload), SIGNATURE)
            verify.assert_called_once_with(POINT, payload, SIGNATURE)
        signer.point = b"\x04" + bytes(64)
        with patch.object(PROVIDER.fcntl, "ioctl", side_effect=ioctl), \
                patch.object(PROVIDER, "verify_signature") as verify:
            with self.assertRaises(OSError) as error:
                signer.sign(payload)
            self.assertEqual(error.exception.errno, errno.EKEYREJECTED)
            verify.assert_not_called()

    def test_digest_ioctl_signs_prehashed_input_without_hashing_again(self):
        signer = object.__new__(PROVIDER.SepSigner)
        signer.fd, signer.point = 1234, POINT
        digest = bytes(range(32))
        def ioctl(_fd, command, response, _mutate):
            self.assertEqual(command, PROVIDER.IOC_ATTEST)
            _n, actual_digest, _point, _signature, _reserved = PROVIDER.ATTEST.unpack(response)
            self.assertEqual(actual_digest, digest)
            response[:] = PROVIDER.ATTEST.pack(8, actual_digest, POINT, SIGNATURE.ljust(72, b"\0"), bytes(3))
        with patch.object(PROVIDER.fcntl, "ioctl", side_effect=ioctl), \
                patch.object(PROVIDER, "verify_signature") as verify:
            self.assertEqual(signer.sign_digest(digest), SIGNATURE)
            verify.assert_called_once_with(POINT, digest, SIGNATURE, prehashed=True)
        with patch.object(PROVIDER.fcntl, "ioctl") as ioctl:
            for invalid in [b"", bytes(31), bytes(33)]:
                with self.assertRaises(OSError) as error:
                    signer.sign_digest(invalid)
                self.assertEqual(error.exception.errno, errno.EINVAL)
            ioctl.assert_not_called()

    def test_digest_worker_dispatch_uses_the_same_serial_signer(self):
        hardware = FakeSigner()
        signer = PROVIDER.BoundedSigner(hardware)
        try:
            digest = bytes(range(32))
            self.assertEqual(signer.sign_digest(digest), SIGNATURE)
            self.assertEqual(hardware.digests, [digest])
            self.assertFalse(hardware.payloads)
        finally:
            signer.close()

    def test_startup_populates_existing_only_cache_before_any_legacy_sign(self):
        commands = []
        def ioctl(_fd, command, response, _mutate):
            commands.append(command)
            if command == PROVIDER.IOC_EXPORT_ATTESTATION:
                self.assertEqual(len(response), 4176)
                response[:] = startup_export()
            elif command == PROVIDER.IOC_ATTEST:
                _n, digest, _point, _signature, _reserved = PROVIDER.ATTEST.unpack(response)
                response[:] = PROVIDER.ATTEST.pack(8, digest, POINT, SIGNATURE.ljust(72, b"\0"), bytes(3))
            else:
                self.fail("unexpected ioctl")
        with self.startup_patches(ioctl), patch.object(PROVIDER, "verify_signature"):
            signer = PROVIDER.SepSigner("/fake/device", "/fake/pinned-point")
            try:
                self.assertEqual(commands, [0x9050B10C])
                self.assertEqual(signer.sign(b"first allowed challenge"), SIGNATURE)
                self.assertEqual(commands, [0x9050B10C, 0xC0B0B10A])
            finally:
                signer.close()

    def test_corrupt_or_mismatched_startup_export_never_calls_legacy_sign(self):
        bad_header = startup_export()
        bad_header[0] = 2
        nonzero_tail = startup_export()
        nonzero_tail[-1] = 1
        framed = bytes(8) + ATTESTATION
        cases = [
            (bad_header, errno.EIO),
            (nonzero_tail, errno.EIO),
            (startup_export(der=framed), errno.EIO),
            (startup_export(point=b"\x04" + bytes(64)), errno.EKEYREJECTED),
        ]
        for returned, expected in cases:
            with self.subTest(expected=expected):
                commands = []
                def ioctl(_fd, command, response, _mutate):
                    commands.append(command)
                    self.assertEqual(command, PROVIDER.IOC_EXPORT_ATTESTATION)
                    response[:] = returned
                with self.startup_patches(ioctl):
                    with self.assertRaises(OSError) as error:
                        PROVIDER.SepSigner("/fake/device", "/fake/pinned-point")
                    self.assertEqual(error.exception.errno, expected)
                self.assertEqual(commands, [PROVIDER.IOC_EXPORT_ATTESTATION])

    def test_older_driver_or_missing_reference_has_no_legacy_fallback(self):
        commands = []
        def ioctl(_fd, command, _response, _mutate):
            commands.append(command)
            raise OSError(errno.ENOTTY, "old module")
        with self.startup_patches(ioctl):
            with self.assertRaises(OSError) as error:
                PROVIDER.SepSigner("/fake/device", "/fake/pinned-point")
            self.assertEqual(error.exception.errno, errno.ENOTTY)
        self.assertEqual(commands, [PROVIDER.IOC_EXPORT_ATTESTATION])
        with self.startup_patches(ioctl), \
                patch.object(PROVIDER, "open_root_file", side_effect=FileNotFoundError):
            with self.assertRaises(FileNotFoundError):
                PROVIDER.SepSigner("/fake/device", "/fake/pinned-point")
        self.assertEqual(commands, [PROVIDER.IOC_EXPORT_ATTESTATION])

    @unittest.skipUnless(hasattr(os, "memfd_create"), "Linux anonymous fds required")
    def test_openssl_independently_verifies_signature_and_rejects_tampering(self):
        # Ephemeral software test key exists only in memory and anonymous fds.
        key = subprocess.check_output(["/usr/bin/openssl", "genpkey", "-algorithm", "EC",
                                       "-pkeyopt", "ec_paramgen_curve:P-256", "-outform", "DER"])
        fd = os.memfd_create("ephemeral-provider-test", os.MFD_CLOEXEC)
        try:
            os.write(fd, key)
            public = subprocess.check_output(["/usr/bin/openssl", "pkey", "-inform", "DER",
                                              "-in", f"/proc/self/fd/{fd}", "-pubout", "-outform", "DER"],
                                             pass_fds=(fd,))
            payload = b"independent verification"
            signature = subprocess.check_output(["/usr/bin/openssl", "dgst", "-sha256", "-keyform", "DER",
                                                 "-sign", f"/proc/self/fd/{fd}"], input=payload, pass_fds=(fd,))
            point = public[-65:]
            PROVIDER.verify_signature(point, payload, signature)
            digest = PROVIDER.hashlib.sha256(payload).digest()
            # An ECDSA-SHA256(message) signature also verifies directly over
            # SHA256(message), but must fail if that digest is hashed again.
            PROVIDER.verify_signature(point, digest, signature, prehashed=True)
            with self.assertRaises(OSError):
                PROVIDER.verify_signature(point, digest, signature)
            with self.assertRaises(OSError):
                PROVIDER.verify_signature(point, bytes(32), signature, prehashed=True)
            with self.assertRaises(OSError):
                PROVIDER.verify_signature(point, payload + b"changed", signature)
        finally:
            os.close(fd)

    @unittest.skipUnless(os.geteuid() == 0 and hasattr(socket, "SO_PEERCRED"), "root Linux integration check")
    def test_isolated_fake_socket_permissions_and_symlink_refusal(self):
        with tempfile.TemporaryDirectory(prefix="provider-test-") as root:
            parent = Path(root) / "socket-parent"
            parent.mkdir(mode=0o755)
            path = parent / "sep.sock"
            allowed_uid = 1000
            process = multiprocessing.get_context("fork").Process(target=fake_server,
                                                                  args=(str(path), allowed_uid))
            process.start()
            try:
                deadline = time.monotonic() + 2
                while not path.exists() and time.monotonic() < deadline:
                    time.sleep(0.01)
                self.assertTrue(path.exists())
                # Wait for post-bind ownership before inspecting it.
                while path.stat().st_uid != allowed_uid and time.monotonic() < deadline:
                    time.sleep(0.01)
                info = path.stat()
                self.assertTrue(stat.S_ISSOCK(info.st_mode))
                self.assertEqual((info.st_uid, stat.S_IMODE(info.st_mode)), (allowed_uid, 0o600))
                with socket.socket(socket.AF_UNIX) as client:
                    client.settimeout(1)
                    client.connect(str(path))
                    client.sendall(PROVIDER.HEADER.pack(1, 3) + b"abc")
                    self.assertEqual(client.recv(80), PROVIDER.HEADER.pack(0, 8) + SIGNATURE)
            finally:
                process.terminate()
                process.join(2)
            link = Path(root) / "alias"
            link.symlink_to(parent, target_is_directory=True)
            with self.assertRaises(OSError):
                PROVIDER.socket_parent(link / "other.sock")


if __name__ == "__main__":
    unittest.main()
