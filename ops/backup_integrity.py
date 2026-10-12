#!/usr/bin/env python3
"""SHA-256 sealed ModelOps backup manifests, with strict path validation.

Backups are incomplete until the manifest is atomically written. Before a
restore, verify every file digest and refuse missing/extra files, links or
unsafe paths. This utility never calls a database or object storage client.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath


class BackupIntegrityError(ValueError):
    pass


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def manifest_files(root: Path) -> dict[str, dict]:
    result = {}
    for file in sorted(root.rglob("*")):
        if file.is_symlink():
            raise BackupIntegrityError("Backup contains a symlink")
        if not file.is_file():
            continue
        relative = file.relative_to(root).as_posix()
        if relative in ("manifest.json", ".manifest.tmp"):
            continue
        if not is_safe_name(relative):
            raise BackupIntegrityError("Invalid backup entry path")
        result[relative] = {"sha256": sha256_file(file), "bytes": file.stat().st_size}
    return result


def is_safe_name(raw: str) -> bool:
    if not raw or "\\" in raw:
        return False
    rel = PurePosixPath(raw)
    return not rel.is_absolute() and ".." not in rel.parts and rel.as_posix() == raw


def generate(root: Path, namespace: str, source_bucket: str) -> dict:
    if not re.fullmatch(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?", namespace):
        raise BackupIntegrityError("Invalid namespace")
    if not re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9._-]{1,62}", source_bucket):
        raise BackupIntegrityError("Invalid S3 bucket")
    root = root.resolve(strict=True)
    files = manifest_files(root)
    for needed in ("postgresql/modelops.dump", "kubernetes/modeldeployments.json", "objects/.objects-marker"):
        if needed not in files or files[needed]["bytes"] == 0:
            raise BackupIntegrityError("Required backup component missing or empty: " + needed)
    if not any(p.startswith("objects/") and p != "objects/.objects-marker" for p in files):
        raise BackupIntegrityError("Object-store snapshot contains no artifacts")
    result = {
        "schema": "modelops.backup.v1",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "namespace": namespace, "source_bucket": source_bucket,
        "files": files, "verified": True,
    }
    fd, temp_path = tempfile.mkstemp(prefix=".manifest-", dir=str(root))
    try:
        with os.fdopen(fd, "w") as stream:
            json.dump(result, stream, indent=2, sort_keys=True)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp_path, root / "manifest.json")
    finally:
        if os.path.exists(temp_path):
            os.unlink(temp_path)
    return result


def verify(root: Path) -> dict:
    root = root.resolve(strict=True)
    manifest = root / "manifest.json"
    if manifest.is_symlink() or not manifest.is_file():
        raise BackupIntegrityError("Sealed manifest.json missing")
    try:
        data = json.loads(manifest.read_text())
    except (ValueError, UnicodeError) as exc:
        raise BackupIntegrityError("Malformed manifest JSON") from exc
    if data.get("schema") != "modelops.backup.v1" or data.get("verified") is not True:
        raise BackupIntegrityError("Unknown/incomplete backup manifest")
    expected = data.get("files")
    if not isinstance(expected, dict) or not expected:
        raise BackupIntegrityError("Backup manifest has no hashed files")
    actual = manifest_files(root)
    if set(expected) != set(actual):
        raise BackupIntegrityError("Missing or unexpected backup files")
    for relative, info in expected.items():
        if not is_safe_name(relative) or not isinstance(info, dict):
            raise BackupIntegrityError("Invalid manifest path")
        if actual[relative] != info:
            raise BackupIntegrityError("Backup SHA-256 or byte-size mismatch: " + relative)
    return data


def main(argv=None) -> int:
    p = argparse.ArgumentParser()
    p.add_argument("operation", choices=("seal", "verify"))
    p.add_argument("directory", type=Path)
    p.add_argument("--namespace")
    p.add_argument("--source-bucket")
    args = p.parse_args(argv)
    try:
        if args.operation == "seal":
            if not args.namespace or not args.source_bucket:
                raise BackupIntegrityError("Seal needs namespace and source bucket")
            data = generate(args.directory, args.namespace, args.source_bucket)
        else:
            data = verify(args.directory)
        print(json.dumps({"status": "VERIFIED" if args.operation == "verify" else "SEALED",
                          "namespace": data["namespace"], "files": len(data["files"])}))
        return 0
    except (BackupIntegrityError, OSError) as exc:
        print("ModelOps backup integrity error: " + str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
