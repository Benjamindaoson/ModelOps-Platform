"""Recover deterministic runtime resources from previously committed SQL intent.

This reconciler NEVER deletes foreign objects, guesses a model checkpoint, or
equates successful K8s CREATE with a Ready or Succeeded serving/training status.
"""
from __future__ import annotations

import json

from .job_lifecycle import check_job_identity
from .runtime import RuntimeFailure, RuntimeNotFound, namespace_for


def ensure_deployment(runtime, record, artifact) -> str:
    """Create the exact desired CRD once, or adopt only a matching owned CRD."""
    try:
        existing = runtime.get_deployment(record)
    except RuntimeNotFound:
        runtime.create_deployment(record, artifact)
        return "created"

    meta = existing.get("metadata", {})
    annotations = meta.get("annotations", {})
    spec = existing.get("spec", {})
    if (meta.get("namespace") != namespace_for(record.tenant)
        or meta.get("name") != record.name
        or annotations.get("modelops.io/tenant") != record.tenant
        or annotations.get("modelops.io/artifact-id") != artifact.id
        or annotations.get("modelops.io/artifact-revision") != artifact.revision
        or annotations.get("modelops.io/artifact-sha256") != artifact.digest
        or spec.get("source") != artifact.source
        or spec.get("engine") != record.engine):
        raise RuntimeFailure("Kubernetes ModelDeployment identity/spec drift; refusing adoption")
    return "adopted"


def ensure_training(runtime, record, artifact, dataset) -> str:
    """Never create a second Workflow if the first request succeeded remotely."""
    try:
        existing = runtime.get_finetune(record)
    except RuntimeNotFound:
        params = json.loads(record.parameters_json)
        runtime.submit_finetune(record, artifact, dataset, params)
        return "created"

    check_job_identity(existing, record)
    if existing.get("spec", {}).get("workflowTemplateRef", {}).get("name") != "modelops-finetune-dynamic":
        raise RuntimeFailure("Existing Argo Workflow uses an unexpected training template")
    arguments = existing.get("spec", {}).get("arguments", {}).get("parameters", [])
    actual = {x.get("name"): str(x.get("value")) for x in arguments if isinstance(x, dict)}
    expected = {
        "base_model": artifact.source, "base_revision": artifact.revision,
        "base_sha256": artifact.digest, "dataset_uri": dataset.uri,
        "dataset_sha256": dataset.digest, "method": record.method,
    }
    if any(actual.get(k) != v for k, v in expected.items()):
        raise RuntimeFailure("Existing Workflow input version disagrees with durable training intent")
    return "adopted"
