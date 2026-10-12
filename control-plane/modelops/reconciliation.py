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
