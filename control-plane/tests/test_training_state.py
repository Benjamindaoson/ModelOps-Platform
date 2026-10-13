"""Contract tests; fixture bytes are not model-training evidence."""
import hashlib
from pathlib import Path
import pytest
from modelops.training_state import TrainingStateReconciler

@pytest.mark.parametrize("phase,want", [
    ("Pending", "QUEUED"), ("Running", "RUNNING"), ("Suspended", "PAUSED"),
    ("Failed", "FAILED"), ("Terminated", "CANCELLED"),
])
def test_runtime_overrides_stale_database_state(phase, want):
    assert TrainingStateReconciler().reconcile("COMPLETED", phase, run_id="run-1")["state"] == want

def test_runtime_completion_without_checkpoint_does_not_complete():
    result = TrainingStateReconciler().reconcile("RUNNING", "Succeeded", run_id="run-1")
    assert result["state"] == "RUNNING"
    assert result["artifact_verified"] is False
    assert result["reconciliation_issue"] == "awaiting_checkpoint_receipt"

def receipt(tmp_path):
    artifact = tmp_path / "contract.bin"
    artifact.write_bytes(b"unit-test-only-hash-contract")
    return {"run_id": "run-1", "status": "COMPLETED", "checkpoint": str(artifact),
            "checkpoint_sha256": hashlib.sha256(artifact.read_bytes()).hexdigest()}

def test_completed_checkpoint_is_verified_against_runtime(tmp_path):
    result = TrainingStateReconciler(tmp_path).reconcile("RUNNING", "Succeeded", receipt(tmp_path), "run-1")
    assert result["state"] == "COMPLETED"
    assert result["artifact_verified"] is True

def test_corruption_and_cross_run_receipts_fail_closed(tmp_path):
    row = receipt(tmp_path)
    Path(row["checkpoint"]).write_bytes(b"corrupted")
    result = TrainingStateReconciler(tmp_path).reconcile("RUNNING", "Succeeded", row, "run-1")
    assert result["state"] == "FAILED"
    assert result["artifact_verified"] is False
    result = TrainingStateReconciler(tmp_path).reconcile("RUNNING", "Succeeded", receipt(tmp_path), "other-run")
    assert result["state"] == "FAILED"

def test_unreachable_runtime_preserves_state_without_claiming_verification():
    result = TrainingStateReconciler().reconcile("RUNNING", None, run_id="run-1")
    assert result["state"] == "RUNNING"
    assert result["runtime_verified"] is False

def test_receipt_outside_worker_root_is_rejected(tmp_path):
    row = receipt(tmp_path)
    allowed = tmp_path / "worker"
    allowed.mkdir()
    assert TrainingStateReconciler(allowed).reconcile("RUNNING", "Succeeded", row, "run-1")["state"] == "FAILED"
