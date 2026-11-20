#!/usr/bin/env python3
"""Automatic login: kcpassword encoding, and `omvm autologin` end to end with
ssh and the guest's tools stubbed (the generated script runs under bash)."""

import base64
import importlib.util
import os
from pathlib import Path
import stat
import subprocess
import tempfile
import textwrap
import unittest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("kcpassword", ROOT / "share" / "kcpassword.py")
KC = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(KC)


class KcpasswordTests(unittest.TestCase):
    def test_known_vector(self):
        # "test" + 8 NULs, XORed with the cyclic 11-byte key.
        self.assertEqual(KC.encode("test").hex(), "09ec2157d2bcddeaa3b91f7d")

    def test_padding_is_a_multiple_of_12_with_a_terminator(self):
        for n, size in [(1, 12), (11, 12), (12, 24), (13, 24), (24, 36), (64, 72)]:
            self.assertEqual(len(KC.encode("x" * n)), size, n)

    def test_round_trip(self):
        for pw in ["macos", "elephant", "a b$c\\d\"e", "x" * 64]:
            self.assertEqual(KC.decode(KC.encode(pw)), pw)

    def test_cli_reads_the_first_line_of_a_file(self):
        with tempfile.NamedTemporaryFile("w", delete=False) as f:
            f.write("macos\n")
        try:
            out = subprocess.run(["python3", "-I", str(ROOT / "share" / "kcpassword.py"), f.name],
                                 check=True, capture_output=True, text=True).stdout.strip()
        finally:
            os.unlink(f.name)
        self.assertEqual(base64.b64decode(out), KC.encode("macos"))


def stub(path, body):
    path.write_text("#!/bin/bash\n" + textwrap.dedent(body))
    path.chmod(path.stat().st_mode | stat.S_IEXEC)


class AutologinTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.bin = self.tmp / "bin"
        self.bin.mkdir()
        self.log = self.tmp / "calls.log"
        self.out = self.tmp / "out"
        self.out.mkdir()
        data = self.tmp / "data"
        (data / "upstream" / "artifacts" / "runs" / "vm1").mkdir(parents=True)
        (data / "upstream" / "artifacts" / "runs" / "vm1" / "ssh_port").write_text("2222\n")
        (data / "upstream" / "artifacts" / "runs" / "vm1" / "guest_user").write_text("izzy\n")
        (data / "guest-password").write_text("macos\n")
        self.env = {
            "PATH": f"{self.bin}:/usr/bin:/bin",
            "HOME": str(self.tmp),
            "XDG_CONFIG_HOME": str(self.tmp / "config"),
            "OMVM_DATA": str(data),
            "OMVM_KEY": str(self.tmp / "key"),
            "LOG": str(self.log),
            "OUT": str(self.out),
        }
        # ssh: run what the guest would get on stdin under bash, with the guest's tools stubbed.
        stub(self.bin / "ssh", """
            echo "ssh $*" >> "$LOG"
            cat > "$OUT/script.sh"
            exec bash "$OUT/script.sh"
        """)
        stub(self.bin / "sudo", """
            [ "$1" = -n ] && shift
            echo "sudo $*" >> "$LOG"
            exec "$@"
        """)
        stub(self.bin / "tee", 'cat > "$OUT/$(basename "$1")"\n')
        stub(self.bin / "base64", 'exec python3 -c "import base64,sys;sys.stdout.buffer.write(base64.b64decode(sys.stdin.read()))"\n')
        stub(self.bin / "defaults", 'echo "defaults $*" >> "$LOG"\n')
        stub(self.bin / "sw_vers", '[ "$1" = -productVersion ] && echo 26.4 || echo 25E246\n')
        stub(self.bin / "id", '[ "${2:-}" = izzy ] && { echo 501; exit; }; exec /usr/bin/id "$@"\n')
        for tool in ("chown", "chmod", "mkdir"):
            stub(self.bin / tool, f'echo "{tool} $*" >> "$LOG"\n')

    def run_omvm(self, *args):
        return subprocess.run(["bash", str(ROOT / "bin" / "omvm"), *args], env=self.env,
                              capture_output=True, text=True)

    def test_autologin_writes_kcpassword_and_loginwindow(self):
        r = self.run_omvm("autologin", "vm1")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(KC.decode((self.out / "kcpassword").read_bytes()), "macos")
        self.assertEqual((self.out / "kcpassword").read_bytes(), KC.encode("macos"))
        calls = self.log.read_text()
        self.assertIn("izzy@127.0.0.1 bash -s", calls)
        self.assertIn("sudo chown root:wheel /etc/kcpassword", calls)
        self.assertIn("sudo chmod 600 /etc/kcpassword", calls)
        self.assertIn("defaults write /Library/Preferences/com.apple.loginwindow autoLoginUser -string izzy", calls)

    def test_setup_assistant_panes_are_marked_seen(self):
        r = self.run_omvm("autologin", "vm1")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        calls = self.log.read_text()
        for line in [
            "defaults write com.apple.SetupAssistant DidSeeCloudSetup -bool true",
            "defaults write com.apple.SetupAssistant DidSeePrivacy -bool true",
            "defaults write com.apple.SetupAssistant SkipFirstLoginOptimization -bool true",
            "defaults write com.apple.SetupAssistant LastSeenCloudProductVersion -string 26.4",
            "defaults write com.apple.SetupAssistant LastSeenBuddyBuildVersion -string 25E246",
            "defaults write /Library/Managed Preferences/com.apple.SetupAssistant.managed SkipSetupItems -array",
            "defaults write /Library/Managed Preferences/izzy/com.apple.SetupAssistant.managed SkipSetupItems -array",
            "defaults write /Library/Preferences/com.apple.SoftwareUpdate AutomaticallyInstallMacOSUpdates -bool false",
        ]:
            self.assertIn(line, calls)
        self.assertRegex(calls, r"SkipSetupItems -array [^\n]*\bSoftwareUpdate\b")

    def test_password_never_in_argv_or_plain_in_the_script(self):
        r = self.run_omvm("autologin", "vm1")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertNotIn("macos", (self.out / "script.sh").read_text().split("LOGIN_USER=")[1].split("\n", 2)[1])
        for line in self.log.read_text().splitlines():
            if line.startswith("ssh "):
                self.assertNotIn("KCPASSWORD", line)

    def test_no_password_file_fails_before_ssh(self):
        os.unlink(Path(self.env["OMVM_DATA"]) / "guest-password")
        r = self.run_omvm("autologin", "vm1")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("no password", r.stderr)
        self.assertFalse(self.log.exists() and "ssh" in self.log.read_text())


if __name__ == "__main__":
    unittest.main()
