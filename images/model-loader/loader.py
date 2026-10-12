#!/usr/bin/env python3
"""ModelOps model-loader: fetch a pinned checkpoint into the shared PVC.

Actual model bytes are retrieved from Hugging Face or S3/MinIO. A declared
SHA-256 must match the complete tree of model files before serving proceeds.
No fake checkpoint creation, unpinned revisions or secret disclosure.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import tempfile
from pathlib import Path, PurePosixPath
from urllib.parse import urlparse


class ModelLoadError(ValueError):
    pass


def sha256_file(path: Path) -> str:
    checksum = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            checksum.update(chunk)
    return checksum.hexdigest()


def sha256_checkpoint(path: Path) -> str:
    """Same deterministic model hash as pipelines/evaluation before loader receipt.

    HuggingFace local_dir creates an internal .cache used for download metadata;
    it is not part of model weights. A loader provenance receipt is also
    excluded because it is derived from the files whose hash it records.
    """
    if not path.is_dir() or path.is_symlink():
        raise ModelLoadError("missing model directory or forbidden symlink")
    files = sorted(p for p in path.rglob("*") if p.is_file() and ".cache" not in p.relative_to(path).parts
                   and p.name != ".modelops-provenance.json")
    if not files:
        raise ModelLoadError("download produced no model files")
    digest = hashlib.sha256()
    for f in files:
        if f.is_symlink():
            raise ModelLoadError("model files may not contain symlinks")
        rel = f.relative_to(path).as_posix().encode()
        digest.update(len(rel).to_bytes(4, "big"))
        digest.update(rel)
        digest.update(bytes.fromhex(sha256_file(f)))
    return digest.hexdigest()


def check_source(source: str, revision: str, checksum: str, slug: str) -> None:
    if not re.fullmatch(r"[A-Za-z0-9._-]{1,180}", slug) or slug.startswith(".") or ".." in slug:
        raise ModelLoadError("invalid model cache slug")
    if not re.fullmatch(r"[a-f0-9]{64}", checksum):
        raise ModelLoadError("verified deployment needs a full artifact SHA-256")
    if source.startswith("s3://"):
        parsed = urlparse(source)
        if not parsed.netloc or not parsed.path.strip("/"):
            raise ModelLoadError("S3 object prefix required")
        if not revision or len(revision) < 7:
            raise ModelLoadError("S3 artifact needs a pinned registry version")
    else:
        if not re.fullmatch(r"[\w.-]+/[\w.-]+", source):
            raise ModelLoadError("model source must be a Hugging Face repo ID or s3 URI")
        if not re.fullmatch(r"[a-f0-9]{40}", revision):
            raise ModelLoadError("Hugging Face model revision must be a 40-character git commit")


def download_hf(source: str, revision: str, directory: Path) -> None:
    try:
        from huggingface_hub import snapshot_download
    except ImportError as exc:
        raise ModelLoadError("huggingface_hub dependency unavailable") from exc
    snapshot_download(repo_id=source, revision=revision, local_dir=str(directory),
                      token=os.environ.get("HF_TOKEN") or None, local_files_only=False)


def download_s3(source: str, revision: str, directory: Path) -> None:
    try:
        from minio import Minio
    except ImportError as exc:
        raise ModelLoadError("minio client dependency unavailable") from exc
    endpoint = os.environ.get("MODELOPS_S3_ENDPOINT", "")
    access = os.environ.get("MODELOPS_S3_ACCESS_KEY", "")
    secret = os.environ.get("MODELOPS_S3_SECRET_KEY", "")
    if not endpoint or not access or not secret:
        raise ModelLoadError("S3 endpoint and Secret-backed credentials are required")
    url = urlparse(endpoint)
    if url.scheme not in {"http", "https"} or not url.netloc or url.username or url.password:
        raise ModelLoadError("invalid configured S3 endpoint")
    object_url = urlparse(source)
    prefix = object_url.path.lstrip("/").rstrip("/") + "/"
    store = Minio(url.netloc, access_key=access, secret_key=secret, secure=url.scheme == "https")
    count = 0
    for entry in store.list_objects(object_url.netloc, prefix=prefix, recursive=True):
        if not entry.object_name.startswith(prefix):
            raise ModelLoadError("storage object does not match allowed prefix")
        relative = entry.object_name[len(prefix):]
        p = PurePosixPath(relative)
        if not relative or p.is_absolute() or ".." in p.parts or "\\" in relative:
            raise ModelLoadError("unsafe remote object path")
        destination = directory.joinpath(*p.parts)
        destination.parent.mkdir(parents=True, exist_ok=True)
        store.fget_object(object_url.netloc, entry.object_name, str(destination))
        count += 1
    if count == 0:
        raise ModelLoadError("S3 model version contains no files")


def load(source: str, revision: str, expected_sha256: str, slug: str, root: Path,
         hf_fetch=download_hf, s3_fetch=download_s3) -> dict:
    check_source(source, revision, expected_sha256, slug)
    root.mkdir(parents=True, exist_ok=True)
    destination = root / slug
    if destination.exists():
        actual = sha256_checkpoint(destination)
        if actual != expected_sha256:
            raise ModelLoadError("existing model cache bytes do not match registered model")
        return {"status": "CACHE_VERIFIED", "model_sha256": actual, "revision": revision}
    tmp = Path(tempfile.mkdtemp(prefix=".modelops-pull-", dir=str(root)))
    try:
        if source.startswith("s3://"):
            s3_fetch(source, revision, tmp)
        else:
            hf_fetch(source, revision, tmp)
        if not (tmp / "config.json").is_file():
            raise ModelLoadError("checkpoint config.json is missing")
        actual = sha256_checkpoint(tmp)
        if actual != expected_sha256:
            raise ModelLoadError("downloaded model SHA-256 differs from the registered version")
        receipt = {"schema": "modelops.model-loader.v1", "status": "MODEL_VERIFIED",
                   "revision": revision, "model_sha256": actual, "source": source}
        (tmp / ".modelops-provenance.json").write_text(json.dumps(receipt, sort_keys=True) + "\n")
        tmp.rename(destination)
        return receipt
    finally:
        if tmp.exists():
            shutil.rmtree(tmp)


def main():
    source = os.environ.get("MODEL_SOURCE", "")
    revision = os.environ.get("MODEL_REVISION", "")
    expected = os.environ.get("MODEL_ARTIFACT_SHA256", "")
    slug = os.environ.get("MODEL_SLUG", "")
    result = load(source, revision, expected, slug, Path("/models"))
    # Avoid logging JWTs, access tokens, model text or private request data.
    print(json.dumps({"status": result["status"], "revision": result["revision"],
                      "verified_sha256": result["model_sha256"]}))


if __name__ == "__main__":
    main()
