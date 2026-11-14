#!/usr/bin/env python3
"""Synthetic log contracts: phase separation, attempt bounds, and no raw output."""

import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


SOURCE = Path(__file__).resolve().parents[1] / "share" / "omvm-auth-phase.py"
SPEC = importlib.util.spec_from_file_location("auth_phase", SOURCE)
PHASE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(PHASE)
SINCE = "2030-02-03T10:00:00Z"
SECRET = "PLANTED_PRIVATE_ACCOUNT_TOKEN@example.invalid"


def record(template, message=None, timestamp=SINCE, **extra):
    return {"formatString": template, "eventMessage": message,
            "timestamp": timestamp, **extra}


def observe(records):
    return PHASE.observe(records, PHASE.parse_timestamp(SINCE))


class PhaseTests(unittest.TestCase):
    def test_account_auth_success_and_later_cdp_recovery_remain_separate(self):
        records = [
            record("Successfully obtained new CK from secondary auth"),
            record("Completed Apple Account Auth, starting service sign in"),
            record(PHASE.AUTHENTICATED, "AppleAccount Authenticated: 1"),
            record("Showing LocalAuthentication password prompt.",
                   timestamp="2030-02-03T10:01:00Z"),
            record("Proceeding with backup recovery attempt now that the local secret is known...",
                   timestamp="2030-02-03T10:02:00Z"),
            record(PHASE.COLLECTION_FAILED,
                   'Secret collection failed with error: Error Domain=com.example.CDP Code=-7035 "failure"',
                   timestamp="2030-02-03T10:03:00Z"),
        ]
        result = observe(records)
        summary = result["summary"]
        self.assertTrue(summary["secondary_auth_success_observed"])
        self.assertTrue(summary["account_auth_success_observed"])
        self.assertTrue(summary["local_recovery_observed"])
        self.assertTrue(summary["collection_failure_observed"])
        self.assertFalse(summary["current_attempt_confirmed"])
        self.assertFalse(summary["automatic_mfa_resend"])
        self.assertEqual(result["events"][-1]["status_codes"], [-7035])

    def test_textual_no_error_is_recovery_success_without_account_auth_success(self):
        result = observe([record(PHASE.ACCOUNT_INFO,
                                 "getAccountInfoWithRequest came back with no error")])
        self.assertEqual(result["events"][0]["label"], "recovery_account_info_succeeded")
        self.assertTrue(result["summary"]["local_recovery_observed"])
        self.assertFalse(result["summary"]["account_auth_success_observed"])
        for suffix in ["<private>", "(null)", "no error " + SECRET, 'Error Domain=x Code=0 "no error"']:
            with self.subTest(suffix=suffix):
                self.assertEqual(observe([record(PHASE.ACCOUNT_INFO,
                    "getAccountInfoWithRequest came back with " + suffix)])["events"], [])

    def test_boolean_parser_cannot_treat_truthy_strings_or_payloads_as_success(self):
        for value in ["1", "true", "YES", "0", "false", "NO"]:
            result = observe([record(PHASE.AUTHENTICATED, "AppleAccount Authenticated: " + value)])
            expected = value in {"1", "true", "YES"}
            self.assertEqual(result["summary"]["account_auth_success_observed"], expected)
            self.assertEqual(result["summary"]["not_authenticated_observed"], not expected)
        for value in ["<private>", SECRET, "1 " + SECRET, "false but success", "2", "%@"]:
            self.assertEqual(observe([record(PHASE.AUTHENTICATED,
                "AppleAccount Authenticated: " + value)])["events"], [])

    def test_historical_success_missing_timezone_and_bad_timestamps_are_excluded(self):
        records = [record("Successfully obtained new CK from secondary auth", timestamp=t)
                   for t in ["2030-02-03T09:59:59.999999Z", None, SECRET,
                             "2030-02-03T10:01:00", "2030-99-03T10:01:00Z"]]
        records.append(record("Showing LocalAuthentication password prompt."))
        result = observe(records)
        self.assertFalse(result["summary"]["secondary_auth_success_observed"])
        self.assertEqual([event["label"] for event in result["events"]], ["local_approval_prompt"])

    def test_boundary_is_inclusive_timezone_normalized_and_events_sorted(self):
        records = [record("Showing LocalAuthentication password prompt.",
                          timestamp="2030-02-03 03:00:01.000001-0700"),
                   record("Successfully obtained new CK from secondary auth",
                          timestamp="2030-02-03T11:00:00+01:00")]
        result = observe(records)
        self.assertEqual(result["events"][0]["label"], "secondary_auth_succeeded")
        self.assertEqual(result["events"][0]["timestamp"], SINCE)
        self.assertEqual(result["events"][1]["timestamp"], "2030-02-03T10:00:01.000001Z")

    def test_static_templates_are_exact_and_unrecognized_messages_cannot_trigger_success(self):
        result = observe([
            record("Successfully obtained new CK from secondary auth " + SECRET),
            record(None, "Successfully obtained new CK from secondary auth"),
            record(SECRET, "Completed Apple Account Auth, starting service sign in"),
            record([SECRET], SECRET),
        ])
        self.assertEqual(result["events"], [])
        self.assertFalse(result["summary"]["account_auth_success_observed"])

    def test_only_outer_typed_nserror_code_is_extracted(self):
        messages = [
            ('Error Domain=com.example.CDP Code=-7035 "' + SECRET +
             ' Error Domain=nested Code=999" UserInfo={' + SECRET + '}', [-7035]),
            (SECRET + " Code=123456", None),
            ('Error Domain=com.example.CDP Code=1234567890123456 "' + SECRET + '"', None),
            ('Error Domain=com.example.CDP Code=-7035' + SECRET, None),
            ('Error Domain=com.example.CDP Code=1.5 "' + SECRET + '"', None),
        ]
        for error, codes in messages:
            result = observe([record(PHASE.COLLECTION_FAILED,
                "Secret collection failed with error: " + error,
                explicit_error_codes=[123456], account=SECRET)])
            self.assertEqual(result["events"][0].get("status_codes"), codes)
            self.assertFalse(result["summary"]["account_auth_success_observed"])
            self.assertNotIn(SECRET, json.dumps(result))


class CliTests(unittest.TestCase):
    def run_cli(self, payload="", args=None):
        return subprocess.run([sys.executable, str(SOURCE), *(args if args is not None else
                              ["--since", SINCE])], input=payload,
                              capture_output=True, text=True, check=False)

    def test_array_ndjson_and_file_have_same_allowlisted_output(self):
        records = [record("Successfully obtained new CK from secondary auth", SECRET,
                          account=SECRET, activityIdentifier=SECRET),
                   record(PHASE.COLLECTION_FAILED,
                          'Secret collection failed with error: Error Domain=com.example.CDP Code=-7035 "' + SECRET + '"'),
                   record(SECRET, SECRET)]
        array = json.dumps(records, indent=2)
        ndjson = "\n".join(json.dumps(row) for row in records)
        outputs = [self.run_cli(array), self.run_cli(ndjson)]
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "synthetic.json"
            path.write_text(array)
            outputs.append(self.run_cli(args=["--since", SINCE, str(path)]))
        for completed in outputs:
            self.assertEqual(completed.returncode, 0)
            self.assertEqual(completed.stderr, "")
            self.assertNotIn(SECRET, completed.stdout)
            result = json.loads(completed.stdout)
            for event in result["events"]:
                self.assertLessEqual(set(event), {"timestamp", "label", "status_codes"})
        self.assertTrue(all(json.loads(item.stdout) == json.loads(outputs[0].stdout)
                            for item in outputs))

    def test_parser_failures_never_echo_payload_arguments_paths_or_tracebacks(self):
        cases = [
            (SECRET, ["--since", SINCE]),
            ('[{"eventMessage":"' + SECRET + '"}', ["--since", SINCE]),
            (json.dumps([SECRET]), ["--since", SINCE]),
            (json.dumps(record("Begin present server UI.")) + "\n" + SECRET,
             ["--since", SINCE]),
            ("", []), ("", ["--since", SECRET]),
            ("", ["--since", "2030-02-03T10:00:00"]),
            ("", ["--since", "0001-01-01T00:00:00+01:00"]),
            ("", ["--since", SINCE, "--" + SECRET]),
            ("", ["--since", SINCE, "/missing/" + SECRET]),
        ]
        for payload, args in cases:
            completed = self.run_cli(payload, args)
            self.assertNotEqual(completed.returncode, 0)
            self.assertEqual(completed.stdout, "")
            self.assertNotIn(SECRET, completed.stderr)
            self.assertNotIn("Traceback", completed.stderr)

    def test_empty_input_is_undetermined_and_help_is_available(self):
        result = self.run_cli()
        self.assertEqual(result.returncode, 0)
        summary = json.loads(result.stdout)["summary"]
        self.assertFalse(summary["current_attempt_confirmed"])
        self.assertFalse(summary["automatic_mfa_resend"])
        self.assertEqual(summary["phase"], "undetermined")
        self.assertEqual(self.run_cli(args=["--help"]).returncode, 0)


if __name__ == "__main__":
    unittest.main()
