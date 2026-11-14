"""Concurrent Unix-socket clients use one fake SEP worker, with isolated replies."""

import importlib.util
import multiprocessing
import os
from pathlib import Path
import socket
import sys
import tempfile
import threading
import time
import unittest


SOURCE = Path(__file__).resolve().parents[1] / "share/sep-identity-provider.py"
SPEC = importlib.util.spec_from_file_location("sep_concurrency_provider", SOURCE)
PROVIDER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(PROVIDER)


class ObservedFakeSigner:
    def __init__(self, active, maximum, calls):
        self.active, self.maximum, self.calls = active, maximum, calls

    def sign(self, payload):
        with self.active.get_lock():
            self.active.value += 1
            self.maximum.value = max(self.maximum.value, self.active.value)
        try:
            time.sleep(0.03)
            with self.calls.get_lock():
                self.calls.value += 1
            return payload[:8]
        finally:
            with self.active.get_lock():
                self.active.value -= 1

    sign_digest = sign

    def close(self):
        pass


def serve_fake(path, active, maximum, calls):
    signer = PROVIDER.BoundedSigner(ObservedFakeSigner(active, maximum, calls), timeout=1)
    try:
        PROVIDER.serve(Path(path), 0, signer)
    finally:
        signer.close()


def receive_exact(connection, count):
    result = bytearray()
    while len(result) < count:
        part = connection.recv(count - len(result))
        if not part:
            raise EOFError("fake SEP response was truncated")
        result.extend(part)
    return bytes(result)


@unittest.skipUnless(sys.platform == "linux" and os.geteuid() == 0,
                     "root Linux Unix-socket ownership integration check")
class ConcurrentClientsTests(unittest.TestCase):
    def test_two_clients_keep_responses_distinct_and_share_one_worker(self):
        context = multiprocessing.get_context("fork")
        active, maximum, calls = (context.Value("i", 0) for _ in range(3))
        with tempfile.TemporaryDirectory(dir="/run", prefix="omvm-sep-test-") as directory:
            path = Path(directory) / "server" / "provider.sock"
            server = context.Process(target=serve_fake,
                                     args=(str(path), active, maximum, calls))
            server.start()
            try:
                deadline = time.monotonic() + 3
                while not path.exists() and time.monotonic() < deadline:
                    self.assertTrue(server.is_alive())
                    time.sleep(0.01)
                self.assertTrue(path.exists())
                barrier = threading.Barrier(2, timeout=2)
                answers, errors = {}, []

                def client(label, operation, payload):
                    try:
                        with socket.socket(socket.AF_UNIX) as connection:
                            connection.settimeout(3)
                            connection.connect(str(path))
                            barrier.wait()
                            connection.sendall(PROVIDER.HEADER.pack(operation, len(payload)) + payload)
                            status, count = PROVIDER.HEADER.unpack(
                                receive_exact(connection, PROVIDER.HEADER.size))
                            answers[label] = status, receive_exact(connection, count)
                    except BaseException as error:
                        errors.append(error)

                payloads = {"one": b"client-A" + bytes(24), "two": b"client-B" + bytes(24)}
                threads = [
                    threading.Thread(target=client, args=("one", PROVIDER.OP_SIGN, payloads["one"])),
                    threading.Thread(target=client, args=("two", PROVIDER.OP_SIGN_DIGEST, payloads["two"])),
                ]
                for thread in threads:
                    thread.start()
                for thread in threads:
                    thread.join(4)
                    self.assertFalse(thread.is_alive(), "fake client did not finish")
                self.assertEqual(errors, [])
                self.assertEqual(answers, {name: (0, value[:8]) for name, value in payloads.items()})
                self.assertEqual(calls.value, 2)
                self.assertEqual(maximum.value, 1)
                self.assertEqual(active.value, 0)
                self.assertTrue(server.is_alive())
            finally:
                server.terminate()
                server.join(3)
                self.assertFalse(server.is_alive(), "fake server did not terminate")


if __name__ == "__main__":
    unittest.main()
