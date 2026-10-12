#!/usr/bin/env python3
"""Sign a real ModelOps held-out report inside an isolated evaluation Worker.

Only the worker may read this private key; neither the API nor Console has
signing credentials. The base64 signature signs ASCII SHA-256 of canonical JSON.
Never include raw training rows, model weights or private keys in stdout.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import re
import stat
import sys
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey


def canonical_digest(report: dict) -> bytes:
    return hashlib.sha256(
        json.dumps(report, sort_keys=True, separators=(",", ":"),
                   allow_nan=False).encode("utf-8")
    ).hexdigest().encode("ascii")


def sign(report: dict, private_key_pem: bytes) -> str:
    if (report.get("schema") != "modelops.heldout.v1"
        or report.get("proof_type") != "real_checkpoint_holdout"
        or type(report.get("num_samples")) is not int
        or report["num_samples"] < 20
        or report.get("train_overlap_count") != 0
        or report.get("generation_success_rate") != 1.0
        or not isinstance(report.get("metrics"), dict)
        or any(not re.fullmatch(r"[a-f0-9]{64}", str(report.get(field, "")))
               for field in ("artifact_sha256", "heldout_sha256"))):
        raise ValueError("The evaluation report is incomplete or not a valid heldout proof")
    key = serialization.load_pem_private_key(private_key_pem, password=None)
    if not isinstance(key, Ed25519PrivateKey):
        raise ValueError("Only Ed25519 worker private keys are supported")
    return base64.b64encode(key.sign(canonical_digest(report))).decode("ascii")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--private-key-file", type=Path, required=True)
    parser.add_argument("--signature-output", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        # Worker-only key files must be owner-readable, not world/group.
        if os.name == "posix" and stat.S_IMODE(args.private_key_file.stat().st_mode) & 0o077:
            raise ValueError("Worker signing private key file must have 0600 permissions")
        if args.signature_output.resolve() == args.private_key_file.resolve():
            raise ValueError("Refusing to overwrite the evaluation private key")
        report = json.loads(args.report.read_text(encoding="utf-8"))
        if not isinstance(report, dict):
            raise ValueError("Report must be a JSON object")
        signature = sign(report, args.private_key_file.read_bytes())
        # A detached signature is public and may be attached to the API
        # request X-ModelOps-Attestation. Never write the private key.
        args.signature_output.write_text(signature + "\n", encoding="ascii")
    except (OSError, ValueError, TypeError) as exc:
        print("Worker attestation failed: " + type(exc).__name__, file=sys.stderr)
        return 2
    print("Ed25519 report signature written (no private key exposed)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
