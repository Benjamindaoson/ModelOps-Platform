#!/usr/bin/env python3
"""Publish independently approved checkpoint to real object store and MLflow registry.

No model promotion/routing occurs here; human-reviewed release API is separate.
"""
from __future__ import annotations

import json
import os
from pathlib import Path


class PublicationError(ValueError):
    pass


def publication_contract(report: dict, gate: dict, artifact_digest: str) -> None:
    if report.get("schema") != "modelops.heldout.v1" or not gate.get("report_sha256"):
        raise PublicationError("Independent evaluation report and approval missing")
    if report.get("artifact_sha256") != artifact_digest or gate.get("artifact_sha256") != artifact_digest:
        raise PublicationError("Checkpoint was changed after approval")


def main():
    from minio import Minio
    import mlflow
    from evaluate import sha256_artifact, sha256_file

    root = Path("/workspace")
    checkpoint = root / "merged"
    report_file = root / "eval/results.json"
    approval_file = root / "eval/APPROVED.json"
    if not checkpoint.is_dir() or not approval_file.is_file() or not report_file.is_file():
        raise PublicationError("Missing checkpoint or signed evidence gate")
    report = json.loads(report_file.read_text())
    approval = json.loads(approval_file.read_text())
    model_digest = sha256_artifact(checkpoint)
    publication_contract(report, approval, model_digest)
    if approval.get("report_sha256") != sha256_file(report_file):
        raise PublicationError("Approval report checksum invalid")

    endpoint = os.environ["MODELOPS_S3_ENDPOINT"]
    client = Minio(endpoint.removeprefix("https://").removeprefix("http://"),
                   access_key=os.environ["MODELOPS_S3_ACCESS_KEY"],
                   secret_key=os.environ["MODELOPS_S3_SECRET_KEY"],
                   secure=endpoint.startswith("https://"))
    bucket = "models"
    name = os.environ["MODELOPS_OUTPUT_NAME"]
    key_prefix = name + "/" + model_digest + "/"
    if not client.bucket_exists(bucket):
        raise PublicationError("Models bucket must be pre-provisioned by the platform")
    count = 0
    for item in checkpoint.rglob("*"):
        if item.is_file():
            client.fput_object(bucket, key_prefix + item.relative_to(checkpoint).as_posix(), str(item))
            count += 1
    if count < 2:
        raise PublicationError("Incomplete checkpoint upload")
    # Read back a checksum of an uploaded model file for material integrity.
    first = next(p for p in checkpoint.rglob("*") if p.is_file())
    object_name = key_prefix + first.relative_to(checkpoint).as_posix()
    tmp = root / "eval/readback-check.tmp"
    client.fget_object(bucket, object_name, str(tmp))
    if sha256_file(first) != sha256_file(tmp):
        raise PublicationError("Object storage readback integrity mismatch")
    tmp.unlink(missing_ok=True)

    tracking_url = os.environ.get("MLFLOW_TRACKING_URI", "")
    if not tracking_url:
        raise PublicationError("MLflow tracking server not configured")
    mlflow.set_tracking_uri(tracking_url)
    uri = "s3://" + bucket + "/" + key_prefix
    version = mlflow.register_model(uri, name)
    receipt = {"status": "MODEL_REGISTERED_NOT_DEPLOYED", "uri": uri,
               "artifact_sha256": model_digest, "registry_version": version.version}
    (root / "eval/publication_receipt.json").write_text(json.dumps(receipt, indent=2) + "\n")
    print(json.dumps(receipt))


if __name__ == "__main__":
    main()
