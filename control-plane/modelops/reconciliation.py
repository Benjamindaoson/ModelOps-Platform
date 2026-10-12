"""Recover deterministic runtime resources from previously committed SQL intent.

This reconciler NEVER deletes foreign objects, guesses a model checkpoint, or
equates successful K8s CREATE with a Ready or Succeeded serving/training status.
"""
from __future__ import annotations

import json

from fastapi import HTTPException

from .job_lifecycle import check_job_identity
from .runtime import (RuntimeFailure, RuntimeNotFound, namespace_for,
                      deployment_body, fine_tune_workflow_body)


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
    expected = deployment_body(record, artifact)["spec"]
    resources = spec.get("resources") or {}
    if (meta.get("namespace") != namespace_for(record.tenant)
        or meta.get("name") != record.name
        or annotations.get("modelops.io/tenant") != record.tenant
        or annotations.get("modelops.io/artifact-id") != artifact.id
        or annotations.get("modelops.io/artifact-revision") != artifact.revision
        or annotations.get("modelops.io/artifact-sha256") != artifact.digest
        or spec.get("source") != expected["source"]
        or spec.get("engine") != expected["engine"]
        or spec.get("replicas") != expected["replicas"]
        or resources.get("gpu") != expected["resources"]["gpu"]):
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

    try:
        check_job_identity(existing, record)
    except HTTPException as exc:
        # Scheduled recovery must report an unadoptable foreign Workflow,
        # not abort the entire tenant batch before the next item is checked.
        raise RuntimeFailure("Existing Argo Workflow ownership mismatch") from exc
    if existing.get("spec", {}).get("workflowTemplateRef", {}).get("name") != "modelops-finetune-dynamic":
        raise RuntimeFailure("Existing Argo Workflow uses an unexpected training template")
    # Every immutable Argo argument matters, not just the source model and
    # dataset. Reusing a Workflow with different LR, batch size, LoRA rank,
    # quality gate or GPU request silently changes the experiment.
    arguments = existing.get("spec", {}).get("arguments", {}).get("parameters")
    expected_items = fine_tune_workflow_body(
        record, artifact, dataset, json.loads(record.parameters_json)
    )["spec"]["arguments"]["parameters"]
    expected = {item["name"]: item["value"] for item in expected_items}
    if (not isinstance(arguments, list)
        or len(arguments) != len(expected)
        or any(not isinstance(item, dict)
               or not isinstance(item.get("name"), str)
               or not isinstance(item.get("value"), str)
               for item in arguments)):
        raise RuntimeFailure("Existing Workflow arguments are incomplete or malformed")
    actual = {item["name"]: item["value"] for item in arguments}
    if len(actual) != len(arguments) or actual != expected:
        raise RuntimeFailure("Existing Workflow arguments disagree with immutable training intent")
    return "adopted"

def ensure_updated_deployment(runtime, record, artifact) -> str:
    """Reconcile an already-created model to a committed SQL desired revision.

    Called after a durable DB commit and by the recovery worker after process
    crashes or ambiguous Kubernetes timeouts. Never adopts a foreign CRD.
    """
    try:
        existing = runtime.get_deployment(record)
    except RuntimeNotFound as exc:
        raise RuntimeFailure("Cannot update a missing ModelDeployment") from exc
    metadata = existing.get("metadata") or {}
    annotations = metadata.get("annotations") or {}
    spec = existing.get("spec") or {}
    if (metadata.get("namespace") != namespace_for(record.tenant)
        or metadata.get("name") != record.name
        or annotations.get("modelops.io/tenant") != record.tenant):
        raise RuntimeFailure("Refusing to patch unowned ModelDeployment")
    desired = deployment_body(record, artifact)
    expected_annotations = desired["metadata"]["annotations"]
    def matches(body: dict) -> bool:
        meta = body.get("metadata") or {}
        ann = meta.get("annotations") or {}
        current = body.get("spec") or {}
        return (
            meta.get("namespace") == namespace_for(record.tenant)
            and meta.get("name") == record.name
            and all(ann.get(k) == value for k, value in expected_annotations.items())
            and current.get("source") == artifact.source
            and current.get("engine") == record.engine
            and current.get("replicas") == record.replicas
            and (current.get("resources") or {}).get("gpu") == record.gpu
        )
    if matches(existing):
        return "adopted"
    runtime.patch_deployment(record, artifact)
    try:
        observed = runtime.get_deployment(record)
    except RuntimeNotFound as exc:
        raise RuntimeFailure("ModelDeployment disappeared after update") from exc
    if not matches(observed):
        raise RuntimeFailure("Kubernetes update did not converge to durable desired revision")
    return "patched"
