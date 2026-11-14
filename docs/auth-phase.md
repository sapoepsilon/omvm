# Observing Apple sign-in phases

`share/omvm-auth-phase.py` is a read-only diagnostic for saved macOS unified-log
JSON. It distinguishes secondary/account authentication from subsequent local
password approval and encrypted-data recovery. A later recovery failure does
not establish that an earlier Apple password or MFA code was wrong.

Run it on a bounded capture from the relevant attempt:

```sh
python3 share/omvm-auth-phase.py --since 2030-02-03T10:00:00Z trace.json
```

The timestamp must include a timezone. Input may be a JSON array or NDJSON;
omit the filename, or use `-`, to read stdin. Sanitized report wrappers are not
input records: extract their event array first. Templates alone cannot establish
rendered boolean values or textual `no error` results.

Output contains only recognized event labels, normalized timestamps, selected
outer numeric status codes, and conservative guidance. Unknown templates and raw
messages are omitted. Parse errors do not echo input, arguments, or file paths.
Treat input logs and resulting timing/status evidence as private operational data.

Always correlate observations with the current native screen and request. A
shared time window does not prove events belong to the same account or attempt;
missing events do not prove failure. Authentication success followed by a code
error on screen calls for fresh evidence before further MFA input. The tool
cannot validate a code, submit input, resend MFA, or establish current sign-in
state. `current_attempt_confirmed` and `automatic_mfa_resend` remain false.

This diagnostic is not an authentication repair or proof of first-attempt
success. That requires an observed clean flow and a fresh authenticated service
request. Preserve functioning account state while diagnosing.

Run the focused synthetic contracts with:

```sh
python3 -m unittest discover -s tests -p test_auth_phase.py -v
```
