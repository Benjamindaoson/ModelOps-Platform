"""Argo Workflow ownership verification, state reporting and retry naming.

An HTTP 200 from Kubernetes is never treated as proof that training has
finished. Workflow state always comes from the observed Argo status.
"""
from __future__ import annotations

from fastapi import HTTPException

TERMINAL = frozenset(("Succeeded", "Failed", "Error", "Terminated", "COMPLETED", "FAILED", "CANCELLED"))


def terminal_job_phase(phase: str) -> bool:
    return phase in TERMINAL


def retry_workflow_name(name: str, random_suffix: str) -> str:
    if len(random_suffix) != 8 or any(ch not in "0123456789abcdef" for ch in random_suffix):
        raise ValueError("Retry suffix must be eight random hex characters")
    # A trailing -ft suffix is added to Argo workflows; both must fit DNS-63.
    prefix = name[:49].rstrip("-")
    if not prefix:
        raise ValueError("Cannot retry a job without a valid name")
    return prefix + "-r-" + random_suffix


def check_job_identity(workflow: dict, job) -> None:
    metadata = workflow.get("metadata") if isinstance(workflow, dict) else None
    if not isinstance(metadata, dict):
        raise HTTPException(status_code=502, detail="Argo returned invalid Workflow metadata")
    labels = metadata.get("labels") or {}
    if (metadata.get("namespace") != "modelops-" + job.tenant or
        metadata.get("name") != job.workflow_name or
        labels.get("modelops.io/tenant") != job.tenant or
        labels.get("modelops.io/job-id") != job.id):
        raise HTTPException(status_code=502, detail="Argo Workflow ownership does not match tenant/job")


def observed_job(workflow: dict) -> dict:
    status = workflow.get("status") or {}
    metadata = workflow.get("metadata") or {}
    spec = workflow.get("spec") or {}
    phase = status.get("phase") or "Pending"
    if not isinstance(phase, str):
        raise HTTPException(status_code=502, detail="Argo returned invalid Workflow phase")
    return {
        "observed_phase": phase,
        "runtime_verified": True,
        "workflow_uid": metadata.get("uid"),
        "started_at": status.get("startedAt"),
        "finished_at": status.get("finishedAt"),
        "progress": status.get("progress"),
        "cancel_requested": spec.get("shutdown") == "Terminate",
        # A model's logs and raw Argo errors may contain prompts, private
        # dataset rows, or credentials: never reflect those as status text.
        "message": "Workflow " + phase if phase != "Pending" else "Waiting for Argo scheduling",
    }
