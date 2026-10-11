#!/usr/bin/env python3
"""Download immutable HF base and vetted S3/HF dataset, verifying manifest and split hashes.

Secrets only from environment; an unavailable object store or digest mismatch
aborts before a GPU training Pod can reserve resources.
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
from pathlib import Path, PurePosixPath
from urllib.parse import urlparse


class PreparationError(ValueError):
    pass


ROOT = Path("/workspace")


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def verify_dataset(path: Path, expected_digest: str) -> dict:
    if not path.is_dir() or len(expected_digest) != 64:
        raise PreparationError("Missing dataset directory or invalid manifest digest")
    manifest_path = path / "dataset_manifest.json"
    if not manifest_path.is_file() or sha256(manifest_path) != expected_digest:
        raise PreparationError("Dataset manifest SHA-256 does not match the registered version")
    manifest = json.loads(manifest_path.read_text())
    checks = manifest.get("files", {})
    if not isinstance(checks, dict) or not {"train.json", "heldout.jsonl"} <= checks.keys():
        raise PreparationError("Manifest must hash the train and heldout split files")
    for name, digest in checks.items():
        rel = PurePosixPath(name)
        if rel.is_absolute() or ".." in rel.parts or rel.as_posix() != name:
            raise PreparationError("Unsafe dataset filename")
        file = (path / name)
        if not file.is_file() or file.is_symlink() or sha256(file) != digest:
            raise PreparationError("Dataset split SHA-256 mismatch: " + name)
    train = json.loads((path / "train.json").read_text())
    heldout = [json.loads(line) for line in (path / "heldout.jsonl").read_text().splitlines() if line.strip()]
    if not isinstance(train, list) or len(train) == 0 or len(heldout) < 20:
        raise PreparationError("Invalid train set or fewer than 20 heldout samples")
    return {"train_rows": len(train), "heldout_rows": len(heldout)}


def fetch_minio_dataset(uri: str, target: Path):
    from minio import Minio
    parsed = urlparse(uri)
    if parsed.scheme != "s3" or not parsed.netloc:
        raise PreparationError("Dataset URI must be s3://bucket/prefix")
    endpoint = os.environ["MODELOPS_S3_ENDPOINT"]
    access = os.environ["MODELOPS_S3_ACCESS_KEY"]
    secret = os.environ["MODELOPS_S3_SECRET_KEY"]
    client = Minio(endpoint.removeprefix("https://").removeprefix("http://"),
                   access_key=access, secret_key=secret, secure=endpoint.startswith("https://"))
    prefix = parsed.path.lstrip("/")
    if prefix and not prefix.endswith("/"):
        prefix += "/"
    count = 0
    for obj in client.list_objects(parsed.netloc, prefix=prefix, recursive=True):
        rel = obj.object_name[len(prefix):]
        parts = PurePosixPath(rel)
        if not rel or parts.is_absolute() or ".." in parts.parts:
            continue
        destination = target / rel
        destination.parent.mkdir(parents=True, exist_ok=True)
        client.fget_object(parsed.netloc, obj.object_name, str(destination))
        count += 1
    if count == 0:
        raise PreparationError("Object store did not return dataset files")


def fetch_hf_dataset(uri: str, target: Path):
    from huggingface_hub import snapshot_download
    if not uri.startswith("hf://"):
        raise PreparationError("Expected hf://dataset/repo@revision")
    spec = uri.removeprefix("hf://")
    if "@" not in spec:
        raise PreparationError("HuggingFace dataset URI must be revision pinned")
    repo, revision = spec.rsplit("@", 1)
    if not repo or len(revision) < 7:
        raise PreparationError("HuggingFace dataset identifier/revision missing")
    snapshot_download(repo_id=repo, repo_type="dataset", revision=revision,
                      local_dir=str(target), token=os.getenv("HF_TOKEN") or None)


def main():
    from huggingface_hub import snapshot_download
    model = os.environ["MODELOPS_BASE_MODEL"]
    revision = os.environ["MODELOPS_BASE_REVISION"]
    dataset_uri = os.environ["MODELOPS_DATASET_URI"]
    dataset_digest = os.environ["MODELOPS_DATASET_SHA256"]
    if len(revision) < 7 or len(dataset_digest) != 64:
        raise PreparationError("Source model revision or data manifest SHA missing")
    model_dir = ROOT / "base-model"
    data_dir = ROOT / "data"
    model_dir.mkdir(parents=True, exist_ok=True)
    data_dir.mkdir(parents=True, exist_ok=True)
    snapshot_download(repo_id=model, revision=revision, local_dir=str(model_dir),
                      token=os.getenv("HF_TOKEN") or None)
    if not (model_dir / "config.json").is_file():
        raise PreparationError("Model config.json is absent after download")
    if dataset_uri.startswith("s3://"):
        fetch_minio_dataset(dataset_uri, data_dir)
    elif dataset_uri.startswith("hf://"):
        fetch_hf_dataset(dataset_uri, data_dir)
    else:
        raise PreparationError("Only versioned s3:// and hf:// datasets supported")
    info = verify_dataset(data_dir, dataset_digest)
    (data_dir / "dataset_info.json").write_text(json.dumps({
        "train": {"file_name": "train.json"},
    }, indent=2) + "\n")
    print(json.dumps({"status": "DATA_PREPARED_AND_HASHED", **info,
                      "dataset_manifest_sha256": dataset_digest}))


if __name__ == "__main__":
    main()
