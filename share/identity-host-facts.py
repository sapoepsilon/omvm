#!/usr/bin/env python3
"""Collect physical-host identity facts from the validated, read-only boot ADT.

Requires aurora-adt-extract.py from the host SEP tools. No keys, identifiers, or
raw ADT data are printed. This does not request Apple certificate issuance.
"""
import argparse
import importlib.util
import json
import os
from pathlib import Path


def collect(parser, device):
    spec = importlib.util.spec_from_file_location("omvm_boot_adt", parser)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    host = module.Host()
    binding = module.check_binding(str(device), host)
    root, _, _, _ = module.parse_adt(module.read_device(binding, host))
    nodes = dict(module.walk(root))

    def property_at(path, name, size=None):
        values = [p for p in nodes[path].props if p.name == name]
        if len(values) != 1 or values[0].placeholder:
            raise ValueError(f"missing, duplicate, or placeholder ADT property {path}:{name}")
        value = values[0].value
        if size is not None and len(value) != size:
            raise ValueError(f"unexpected ADT property size for {name}")
        return value

    fields = {}
    for key, name, size in [
        ("UniqueChipID", "unique-chip-id", 8),
        ("ChipID", "chip-id", 4),
        ("BoardId", "board-id", 4),
        ("SecurityDomain", "security-domain", 4),
    ]:
        fields[key] = int.from_bytes(property_at("/chosen", name, size), "little")
    manifest = "/chosen/manifest-properties"
    if manifest not in nodes:
        raise ValueError("boot ADT has no manifest properties to corroborate ECID")
    ecid = int.from_bytes(property_at(manifest, "ECID", 8), "little")
    if not fields["UniqueChipID"] or ecid != fields["UniqueChipID"]:
        raise ValueError("boot manifest ECID does not match boot chosen ECID")
    raw = property_at("/", "serial-number")
    serial = raw.split(b"\0", 1)[0].decode("ascii")
    if not serial or len(serial) > 32 or not all(0x21 <= ord(c) <= 0x7e for c in serial):
        raise ValueError("invalid boot ADT serial-number encoding")
    # The live Linux DT's physical serial is independent corroboration of the
    # original boot ADT source; never substitute another Mac's or a VM's facts.
    dt_serial = Path(host.dt_root, "serial-number").read_bytes().split(b"\0", 1)[0]
    if dt_serial != serial.encode("ascii"):
        raise ValueError("boot ADT and current Linux DT serial numbers disagree")
    fields["SerialNumber"] = serial
    return {"format_version": 1, "source": "validated-readonly-boot-adt",
            "manifest_ecid_matches": True, "linux_dt_serial_matches": True,
            "RKProperties": fields}


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--adt-parser", required=True, type=Path,
                    help="trusted local aurora-adt-extract.py parser")
    ap.add_argument("--device", type=Path, required=True,
                    help="read-only ADT MTD node, such as /dev/mtd1ro")
    ap.add_argument("--output", required=True, type=Path,
                    help="new 0600 JSON file; existing files are refused")
    args = ap.parse_args()
    try:
        facts = collect(args.adt_parser, args.device)
        data = (json.dumps(facts, indent=2) + "\n").encode()
        fd = os.open(args.output, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_CLOEXEC, 0o600)
        with os.fdopen(fd, "wb") as out:
            out.write(data)
            out.flush()
            os.fsync(out.fileno())
    except (OSError, ValueError, KeyError, ImportError) as error:
        # Parser diagnostics include paths/property names, never property values.
        print(f"Host facts collection failed: {error}", file=__import__("sys").stderr)
        return 1
    print("Collected five physical-host facts; manifest ECID and Linux DT serial match.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
