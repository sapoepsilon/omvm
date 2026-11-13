#!/usr/bin/env python3
"""Privileged, bounded access to the existing SEP host-identity signing key.

The Unix protocol is network-byte-order u32 operation, u32 payload length,
then payload. Operation 1 signs SHA-256(payload); operation 2 signs an exact
32-byte, already-computed SHA-256 digest without hashing it again. Both use
the same existing, pinned SEP key. Responses contain positive
errno (zero on success), u32 result length, then a DER ECDSA signature.
No certificate issuance, key creation, or replacement is requested here.
"""

import argparse
import errno
import fcntl
import hashlib
import hmac
import os
from pathlib import Path
import queue
import signal
import socket
import stat
import struct
import subprocess
import sys
import threading
import time

HEADER = struct.Struct("!II")
ATTEST = struct.Struct("=I32s65s72s3s")
IOC_ATTEST = 0xC0B0B10A
EXPORT_HEADER = struct.Struct("=II65s7s")
EXPORT_DER_MAX = 4096
EXPORT_SIZE = EXPORT_HEADER.size + EXPORT_DER_MAX
IOC_EXPORT_ATTESTATION = 0x9050B10C
OP_SIGN = 1
OP_SIGN_DIGEST = 2
MAX_PAYLOAD = 65536
MAX_SIGNATURE = 72
IO_TIMEOUT = 5.0
SIGN_TIMEOUT = 15.0
EXISTING_REFERENCE = "/var/lib/aurora-sep-refkey.bin"
# SubjectPublicKeyInfo for id-ecPublicKey / prime256v1, followed by 04 || X || Y.
P256_SPKI_PREFIX = bytes.fromhex("3059301306072a8648ce3d020106082a8648ce3d030107034200")


def open_root_file(path, *, size=None):
    fd = os.open(path, os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW)
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_uid != 0 or info.st_mode & 0o022:
            raise PermissionError(errno.EPERM, "expected a root-owned, non-writable regular file")
        if size is not None and info.st_size != size:
            raise ValueError("incorrect pinned public-key size")
        return fd
    except BaseException:
        os.close(fd)
        raise


def read_pinned_point(path):
    fd = open_root_file(path, size=65)
    try:
        point = os.read(fd, 66)
    finally:
        os.close(fd)
    if len(point) != 65 or point[0] != 4:
        raise ValueError("expected an uncompressed P-256 public point")
    return point


def complete_der_sequence(data):
    """Require complete canonical DER framing; encrypted contents stay opaque."""
    if len(data) < 2 or data[0] != 0x30:
        return False
    first = data[1]
    if first < 0x80:
        header, length = 2, first
    else:
        count = first & 0x7F
        if not 1 <= count <= 2 or len(data) < 2 + count or data[2] == 0:
            return False
        header = 2 + count
        length = int.from_bytes(data[2:header], "big")
        if length < 128:
            return False
    return length > 0 and header + length == len(data)


def verify_signature(point, payload, signature, *, prehashed=False):
    """Independently verify with OpenSSL; public material uses anonymous fds."""
    if prehashed and len(payload) != 32:
        raise OSError(errno.EINVAL, "a SHA-256 digest must be exactly 32 bytes")
    public_fd = os.memfd_create("omvm-public-key", os.MFD_CLOEXEC)
    signature_fd = os.memfd_create("omvm-signature", os.MFD_CLOEXEC)
    try:
        os.write(public_fd, P256_SPKI_PREFIX + point)
        os.write(signature_fd, signature)
        os.lseek(public_fd, 0, os.SEEK_SET)
        os.lseek(signature_fd, 0, os.SEEK_SET)
        if prehashed:
            # pkeyutl without -rawin consumes a digest directly. Using dgst
            # here would hash the supplied digest a second time.
            command = [
                "/usr/bin/openssl", "pkeyutl", "-verify", "-pubin", "-keyform", "DER",
                "-inkey", f"/proc/self/fd/{public_fd}",
                "-sigfile", f"/proc/self/fd/{signature_fd}",
                "-pkeyopt", "digest:sha256",
            ]
        else:
            command = [
                "/usr/bin/openssl", "dgst", "-sha256", "-keyform", "DER",
                "-verify", f"/proc/self/fd/{public_fd}",
                "-signature", f"/proc/self/fd/{signature_fd}",
            ]
        result = subprocess.run(
            command,
            input=payload, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            pass_fds=(public_fd, signature_fd), timeout=3, check=False,
        )
        if result.returncode != 0:
            raise OSError(errno.EIO, "SEP signature verification failed")
    finally:
        os.close(signature_fd)
        os.close(public_fd)


class SepSigner:
    def __init__(self, device, public_key):
        self.point = read_pinned_point(public_key)
        # The legacy signing ioctl has a create-on-missing fallback. Keep the
        # reference path root-owned and populate the driver's cache through the
        # new existing-only export API before allowing any legacy sign request.
        self.reference_fd = open_root_file(EXISTING_REFERENCE)
        self.fd = None
        try:
            size = os.fstat(self.reference_fd).st_size
            if not 1 <= size <= 8192:
                raise ValueError("existing SEP reference has an invalid size")
            self.fd = os.open(device, os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW)
            if not stat.S_ISCHR(os.fstat(self.fd).st_mode):
                raise ValueError("SEP device must be a character device")
            self.verify_existing_key()
        except BaseException:
            self.close()
            raise

    def verify_existing_key(self):
        # This ioctl never creates/replaces a reference. On a fresh boot it
        # strictly loads the persisted reference into the driver's cache, or
        # fails. Holding the device fd keeps that driver instance loaded. An
        # older module or any malformed/mismatched response must fail startup;
        # there is deliberately no fallback to the legacy signing ioctl.
        response = bytearray(EXPORT_SIZE)
        fcntl.ioctl(self.fd, IOC_EXPORT_ATTESTATION, response, True)
        version, length, point, reserved = EXPORT_HEADER.unpack_from(response)
        if version != 1 or reserved != bytes(7) or not 0 < length <= EXPORT_DER_MAX:
            raise OSError(errno.EIO, "malformed existing-key export header")
        if not hmac.compare_digest(point, self.point):
            raise OSError(errno.EKEYREJECTED, "existing SEP key differs from the pinned key")
        der = bytes(response[EXPORT_HEADER.size:EXPORT_HEADER.size + length])
        if (not complete_der_sequence(der)
                or any(response[EXPORT_HEADER.size + length:])):
            raise OSError(errno.EIO, "malformed existing-key attestation export")

    def sign(self, payload):
        if len(payload) > MAX_PAYLOAD:
            raise OSError(errno.EMSGSIZE, "challenge is too large")
        digest = hashlib.sha256(payload).digest()
        signature = self._sign_digest(digest)
        verify_signature(self.point, payload, signature)
        return signature

    def sign_digest(self, digest):
        if len(digest) != 32:
            raise OSError(errno.EINVAL, "a SHA-256 digest must be exactly 32 bytes")
        signature = self._sign_digest(digest)
        verify_signature(self.point, digest, signature, prehashed=True)
        return signature

    def _sign_digest(self, digest):
        response = bytearray(ATTEST.pack(0, digest, bytes(65), bytes(72), bytes(3)))
        fcntl.ioctl(self.fd, IOC_ATTEST, response, True)
        length, actual_digest, point, padded_signature, reserved = ATTEST.unpack(response)
        if (not 8 <= length <= MAX_SIGNATURE or actual_digest != digest
                or reserved != bytes(3) or any(padded_signature[length:])):
            raise OSError(errno.EIO, "malformed SEP signing response")
        if not hmac.compare_digest(point, self.point):
            raise OSError(errno.EKEYREJECTED, "SEP signing key differs from the pinned key")
        return padded_signature[:length]

    def close(self):
        if self.fd is not None:
            os.close(self.fd)
            self.fd = None
        if self.reference_fd is not None:
            os.close(self.reference_fd)
            self.reference_fd = None


class BoundedSigner:
    """One hardware worker; timeouts never spawn another concurrent signer."""
    def __init__(self, signer, timeout=SIGN_TIMEOUT):
        self.signer = signer
        self.timeout = timeout
        self.jobs = queue.Queue(maxsize=1)
        self.lock = threading.Lock()
        self.busy = False
        self.stopping = threading.Event()
        self.thread = threading.Thread(target=self._run, name="sep-signer", daemon=True)
        self.thread.start()

    def _run(self):
        while not self.stopping.is_set():
            try:
                job = self.jobs.get(timeout=0.1)
            except queue.Empty:
                continue
            try:
                if job["operation"] == OP_SIGN_DIGEST:
                    job["result"] = self.signer.sign_digest(job["payload"])
                else:
                    job["result"] = self.signer.sign(job["payload"])
            except OSError as error:
                job["error"] = error.errno or errno.EIO
            except Exception:
                job["error"] = errno.EIO
            finally:
                with self.lock:
                    self.busy = False
                job["done"].set()

    def sign(self, payload):
        return self._submit(OP_SIGN, payload)

    def sign_digest(self, digest):
        if len(digest) != 32:
            raise OSError(errno.EINVAL, "a SHA-256 digest must be exactly 32 bytes")
        return self._submit(OP_SIGN_DIGEST, digest)

    def _submit(self, operation, payload):
        job = {"operation": operation, "payload": payload, "done": threading.Event()}
        with self.lock:
            if self.stopping.is_set() or self.busy:
                raise OSError(errno.EBUSY, "SEP signer is busy")
            self.busy = True
            self.jobs.put_nowait(job)
        if not job["done"].wait(self.timeout):
            raise OSError(errno.ETIMEDOUT, "SEP signing timed out")
        if "error" in job:
            raise OSError(job["error"], "SEP signing failed")
        signature = job["result"]
        if not isinstance(signature, bytes) or not 8 <= len(signature) <= MAX_SIGNATURE:
            raise OSError(errno.EIO, "invalid signature result")
        return signature

    def close(self):
        self.stopping.set()
        self.thread.join(timeout=1)
        # Do not close a descriptor while its worker might still use it.
        # A timed-out worker stays the sole worker until process termination.
        if not self.thread.is_alive():
            self.signer.close()


def read_exact(connection, length, deadline):
    data = bytearray()
    while len(data) < length:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise OSError(errno.ETIMEDOUT, "request timed out")
        connection.settimeout(remaining)
        block = connection.recv(length - len(data))
        if not block:
            raise OSError(errno.EPROTO, "truncated request")
        data.extend(block)
    return bytes(data)


def handle_connection(connection, signer, allow_uid, io_timeout=IO_TIMEOUT):
    status, signature = 0, b""
    try:
        credentials = connection.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, 12)
        _pid, uid, _gid = struct.unpack("=3i", credentials)
        if uid not in (0, allow_uid):
            raise OSError(errno.EACCES, "unauthorised peer")
        deadline = time.monotonic() + io_timeout
        operation, length = HEADER.unpack(read_exact(connection, HEADER.size, deadline))
        if operation not in (OP_SIGN, OP_SIGN_DIGEST):
            raise OSError(errno.EOPNOTSUPP, "unsupported operation")
        if length > MAX_PAYLOAD:
            raise OSError(errno.EMSGSIZE, "challenge is too large")
        if operation == OP_SIGN_DIGEST and length != 32:
            raise OSError(errno.EINVAL, "a SHA-256 digest must be exactly 32 bytes")
        payload = read_exact(connection, length, deadline)
        if operation == OP_SIGN_DIGEST:
            signature = signer.sign_digest(payload)
        else:
            signature = signer.sign(payload)
        if not 8 <= len(signature) <= MAX_SIGNATURE:
            raise OSError(errno.EIO, "invalid signature result")
    except TimeoutError:
        status, signature = errno.ETIMEDOUT, b""
    except OSError as error:
        status, signature = error.errno or errno.EIO, b""
    except Exception:
        status, signature = errno.EIO, b""
    connection.settimeout(io_timeout)
    try:
        connection.sendall(HEADER.pack(status, len(signature)) + signature)
    except OSError:
        pass


def socket_parent(path):
    if not path.is_absolute() or path.name in ("", ".", ".."):
        raise ValueError("socket path must be absolute")
    if len(os.fsencode(path)) > 107 or ".." in path.parts:
        raise ValueError("socket path is too long or contains '..'")
    fd = os.open("/", os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC)
    try:
        parts = path.parent.parts[1:]
        for index, part in enumerate(parts):
            try:
                next_fd = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC
                                  | os.O_NOFOLLOW, dir_fd=fd)
            except FileNotFoundError:
                if index != len(parts) - 1:
                    raise
                os.mkdir(part, 0o755, dir_fd=fd)
                next_fd = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC
                                  | os.O_NOFOLLOW, dir_fd=fd)
                os.fchmod(next_fd, 0o755)
            os.close(fd)
            fd = next_fd
        info = os.fstat(fd)
        if info.st_uid != 0 or stat.S_IMODE(info.st_mode) != 0o755:
            raise PermissionError(errno.EPERM, "socket parent must be root-owned mode 0755")
        return fd
    except BaseException:
        os.close(fd)
        raise


def serve(path, allow_uid, signer):
    parent_fd = socket_parent(path)
    listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    identity = None
    try:
        # Bind through the directory fd so a renamed ancestor cannot redirect
        # a privileged bind. An existing path is deliberately never removed.
        bound_path = f"/proc/self/fd/{parent_fd}/{path.name}"
        previous_umask = os.umask(0o177)
        try:
            listener.bind(bound_path)
        finally:
            os.umask(previous_umask)
        info = os.stat(path.name, dir_fd=parent_fd, follow_symlinks=False)
        identity = info.st_dev, info.st_ino
        os.chown(path.name, allow_uid, -1, dir_fd=parent_fd, follow_symlinks=False)
        os.chmod(path.name, 0o600, dir_fd=parent_fd, follow_symlinks=False)
        listener.listen(8)
        listener.settimeout(1)
        print(f"SEP identity provider listening on {path}; client uid {allow_uid}", flush=True)
        while True:
            try:
                connection, _address = listener.accept()
            except TimeoutError:
                continue
            with connection:
                handle_connection(connection, signer, allow_uid)
    finally:
        listener.close()
        if identity is not None:
            try:
                info = os.stat(path.name, dir_fd=parent_fd, follow_symlinks=False)
                if stat.S_ISSOCK(info.st_mode) and (info.st_dev, info.st_ino) == identity:
                    os.unlink(path.name, dir_fd=parent_fd)
            except FileNotFoundError:
                pass
        os.close(parent_fd)


class Shutdown(BaseException):
    pass


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--socket", required=True, type=Path)
    parser.add_argument("--allow-uid", type=int, required=True)
    parser.add_argument("--public-key", required=True, type=Path)
    parser.add_argument("--device", default="/dev/sep-bio")
    args = parser.parse_args()
    if os.geteuid() != 0:
        parser.error("the SEP provider must run as root")
    if not 0 <= args.allow_uid <= 0x7FFFFFFF:
        parser.error("--allow-uid is outside the supported uid range")
    if not hasattr(socket, "SO_PEERCRED") or not hasattr(os, "memfd_create"):
        parser.error("Linux SO_PEERCRED and anonymous memfds are required")
    def stop(_signum, _frame):
        raise Shutdown()
    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    signer = None
    try:
        signer = BoundedSigner(SepSigner(args.device, args.public_key))
        serve(args.socket, args.allow_uid, signer)
    except Shutdown:
        return 0
    except (OSError, ValueError) as error:
        print(f"SEP identity provider failed: {error}", file=sys.stderr)
        return 1
    finally:
        if signer is not None:
            signer.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
