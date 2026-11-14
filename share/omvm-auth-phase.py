#!/usr/bin/env python3
"""Read-only, allowlisted observations from macOS unified-log JSON.

This does not correlate accounts, requests, or attempts and cannot validate a
password or MFA code. Raw messages and identifiers never enter the output.
"""

import argparse
from datetime import datetime, timezone
import json
import re
import sys


STATIC_EVENTS = {
    "Successfully obtained new CK from secondary auth": "secondary_auth_succeeded",
    "Completed Apple Account Auth, starting service sign in": "account_auth_completed",
    "Showing LocalAuthentication password prompt.": "local_approval_prompt",
    "Proceeding with backup recovery attempt now that the local secret is known...":
        "local_approval_accepted",
    "Begin present server UI.": "auth_ui_presented",
}
AUTHENTICATED = "AppleAccount Authenticated: %@"
COLLECTION_FAILED = "Secret collection failed with error: %@"
ACCOUNT_INFO = "getAccountInfoWithRequest came back with %@"
SUCCESS_EVENTS = {
    "secondary_auth_succeeded", "account_auth_completed", "account_authenticated",
}
RECOVERY_EVENTS = {
    "local_approval_prompt", "local_approval_accepted",
    "recovery_account_info_succeeded",
}
TIMESTAMP = re.compile(
    r"\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?"
    r"(?:Z|[+-]\d{2}:?\d{2})\Z", re.ASCII,
)
# Only the outer, typed NSError code is eligible. Never search descriptions,
# UserInfo, nested errors, arbitrary numbers, or input-provided parsed fields.
NSERROR = re.compile(
    r'Error Domain=[A-Za-z0-9_.-]+ Code=(-?[0-9]{1,10})(?= |$)', re.ASCII,
)


def parse_timestamp(value):
    if not isinstance(value, str) or not TIMESTAMP.fullmatch(value):
        raise ValueError("a timestamp with an explicit timezone is required")
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)
    except OverflowError:
        raise ValueError("timestamp is outside the supported range") from None


def timestamp_text(value):
    return value.isoformat().replace("+00:00", "Z")


def read_records(stream):
    """Accept one JSON array or one JSON object per nonempty line."""
    for first in stream:
        if first.strip():
            break
    else:
        return
    if first.lstrip().startswith("["):
        records = json.loads(first + stream.read())
        if not isinstance(records, list):
            raise ValueError("expected an array")
        for record in records:
            if not isinstance(record, dict):
                raise ValueError("expected log objects")
            yield record
    else:
        def decode(line):
            record = json.loads(line)
            if not isinstance(record, dict):
                raise ValueError("expected log objects")
            return record

        yield decode(first)
        for line in stream:
            if line.strip():
                yield decode(line)


def classify(record):
    template = record.get("formatString")
    if not isinstance(template, str):
        return None
    label = STATIC_EVENTS.get(template)
    if label:
        return {"label": label}
    message = record.get("eventMessage")
    if template == COLLECTION_FAILED:
        event = {"label": "collection_failed"}
        prefix = "Secret collection failed with error: "
        if isinstance(message, str) and message.startswith(prefix):
            error = NSERROR.match(message[len(prefix):])
            if error:
                code = int(error.group(1))
                if -(2 ** 31) <= code < 2 ** 31:
                    event["status_codes"] = [code]
        return event
    if not isinstance(message, str):
        return None
    if template == AUTHENTICATED:
        prefix = "AppleAccount Authenticated: "
        if message.startswith(prefix):
            value = message[len(prefix):].casefold()
            if value in {"1", "true", "yes"}:
                return {"label": "account_authenticated"}
            if value in {"0", "false", "no"}:
                return {"label": "account_not_authenticated"}
    if template == ACCOUNT_INFO and message == (
        "getAccountInfoWithRequest came back with no error"
    ):
        return {"label": "recovery_account_info_succeeded"}
    return None


def summarize(events):
    labels = {event["label"] for event in events}
    success = bool(labels & SUCCESS_EVENTS)
    recovery = bool(labels & RECOVERY_EVENTS)
    if success and recovery:
        phase = "auth_success_and_local_recovery_observed"
    elif recovery:
        phase = "local_recovery_observed"
    elif success:
        phase = "auth_success_observed"
    elif "auth_ui_presented" in labels:
        phase = "auth_ui_observed"
    elif "collection_failed" in labels:
        phase = "collection_failure_observed"
    else:
        phase = "undetermined"
    return {
        "phase": phase,
        "secondary_auth_success_observed": "secondary_auth_succeeded" in labels,
        "account_auth_success_observed": bool(
            labels & {"account_auth_completed", "account_authenticated"}
        ),
        "not_authenticated_observed": "account_not_authenticated" in labels,
        "local_recovery_observed": recovery,
        "collection_failure_observed": "collection_failed" in labels,
        "current_attempt_confirmed": False,
        "automatic_mfa_resend": False,
        "guidance": [
            "Correlate these observations with the current native screen and attempt; "
            "a shared time window does not link events to one account or request.",
            "After observed secondary or account authentication success, further MFA "
            "requires a fresh challenge and a current request. Stale incorrect-code "
            "UI alone does not justify resending MFA.",
            "Secret collection failure is not necessarily a wrong-code result. "
            "Local/CDP recovery failure does not establish an invalid Apple password.",
            "Only allowlisted templates with valid timestamps at or after --since "
            "are included. Absence of an observation does not establish failure.",
        ],
    }


def observe(records, since):
    events = []
    for record in records:
        try:
            timestamp = parse_timestamp(record.get("timestamp"))
        except (ValueError, OverflowError):
            continue
        if timestamp < since:
            continue
        event = classify(record)
        if event:
            events.append((timestamp, {"timestamp": timestamp_text(timestamp), **event}))
    events.sort(key=lambda item: item[0])
    safe_events = [event for _, event in events]
    return {
        "since": timestamp_text(since),
        "events": safe_events,
        "summary": summarize(safe_events),
    }


class SafeArgumentParser(argparse.ArgumentParser):
    def error(self, message):
        # argparse's usual errors echo command arguments, potentially secrets.
        self.exit(2, "Invalid arguments; use --help for input requirements.\n")


def main(argv=None):
    parser = SafeArgumentParser(
        description="Observe Apple sign-in phases without emitting raw log content. "
        "Read-only diagnostic; no account access, input automation, or MFA resend.",
        epilog="Example: omvm-auth-phase.py --since 2030-02-03T10:00:00Z trace.json\n"
        "Output is JSON. Correlate events with the current native screen/attempt; "
        "this tool does not prove first-attempt sign-in success or validate passwords.",
    )
    parser.add_argument("--since", required=True, type=parse_timestamp, metavar="TIMESTAMP",
                        help="inclusive attempt boundary with explicit timezone "
                        "(ISO 8601; for example 2030-02-03T10:00:00Z)")
    parser.add_argument("input", nargs="?", default="-", metavar="FILE",
                        help="macOS unified-log JSON array or NDJSON; default/-: stdin")
    args = parser.parse_args(argv)
    try:
        if args.input == "-":
            result = observe(read_records(sys.stdin), args.since)
        else:
            with open(args.input, encoding="utf-8") as stream:
                result = observe(read_records(stream), args.since)
        json.dump(result, sys.stdout, indent=2, allow_nan=False)
        sys.stdout.write("\n")
    except (OSError, ValueError, RecursionError, OverflowError):
        sys.stderr.write("Cannot read valid unified-log JSON; no raw records are emitted.\n")
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
