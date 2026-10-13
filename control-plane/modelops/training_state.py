"""Canonical job state backed by runtime ownership and checkpoint receipts."""
from __future__ import annotations
import hashlib
from pathlib import Path

STATES = frozenset({"QUEUED", "RUNNING", "PAUSED", "COMPLETED", "FAILED", "CANCELLED"})
PHASES = {"Pending": "QUEUED", "Running": "RUNNING", "Suspended": "PAUSED",
          "Succeeded": "COMPLETED", "Failed": "FAILED", "Error": "FAILED",
          "Terminated": "CANCELLED", "CREATED": "QUEUED", **{s: s for s in STATES}}

class TrainingStateReconciler:
    def __init__(self, artifact_root=None):
        self.root = Path(artifact_root).resolve() if artifact_root else None

    def reconcile(self, db_state, runtime_state, receipt=None, run_id=None):
        previous = db_state if db_state in STATES else "QUEUED"
        out = {"state": previous, "runtime_verified": False, "artifact_verified": False,
               "reconciliation_issue": None}
        if runtime_state not in PHASES:
            out["reconciliation_issue"] = "runtime_unavailable"
            return out
        out.update(state=PHASES[runtime_state], runtime_verified=True)
        if out["state"] != "COMPLETED":
            return out
        if receipt is None:
            out.update(state="RUNNING", reconciliation_issue="awaiting_checkpoint_receipt")
            return out
        if not isinstance(receipt, dict) or receipt.get("run_id") != run_id or receipt.get("status") != "COMPLETED":
            out.update(state="FAILED", reconciliation_issue="completion_receipt_identity_mismatch")
            return out
        try:
            path = Path(receipt["checkpoint"]).resolve()
            if self.root is None or not path.is_relative_to(self.root) or not path.is_file():
                raise ValueError("Untrusted artifact")
            digest = hashlib.sha256()
            with path.open("rb") as stream:
                for block in iter(lambda: stream.read(1024 * 1024), b""):
                    digest.update(block)
            if digest.hexdigest() != receipt.get("checkpoint_sha256"):
                raise ValueError("Checkpoint drift")
        except (KeyError, TypeError, ValueError, OSError):
            out.update(state="FAILED", reconciliation_issue="checkpoint_integrity_failure")
            return out
        out["artifact_verified"] = True
        return out
