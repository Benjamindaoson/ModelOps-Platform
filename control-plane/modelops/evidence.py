"""HMAC check of independent evaluation evidence from trusted training worker.

This does not prove benchmark generalization; it prevents ordinary API
clients from self-declaring a model as passing without a privileged report.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import math
from typing import Any


class EvidenceError(ValueError):
    pass


def digest_report(data: dict) -> str:
    return hashlib.sha256(json.dumps(data, sort_keys=True, separators=(",", ":"),
                             allow_nan=False).encode()).hexdigest()


def verify_report(data: dict, signature: str, secret: str, artifact, dataset) -> tuple[bool, dict]:
    if len(secret) < 32:
        raise EvidenceError("Server evidence signing key not configured")
    expected = hmac.new(secret.encode(), digest_report(data).encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, signature):
        raise EvidenceError("Invalid independent worker signature")
    if data.get("schema") != "modelops.heldout.v1" or data.get("proof_type") != "real_checkpoint_holdout":
        raise EvidenceError("Wrong evidence schema")
    if not isinstance(data.get("num_samples"), int) or data["num_samples"] < 20:
        raise EvidenceError("Insufficient heldout evidence")
    if data.get("artifact_sha256") != artifact.digest or data.get("heldout_sha256") != dataset.digest:
        raise EvidenceError("Model/dataset digests do not match registered versions")
    if data.get("generation_success_rate") != 1.0 or data.get("train_overlap_count") != 0:
        raise EvidenceError("Incomplete generations or overlapping prompts")
    metrics = data.get("metrics")
    if not isinstance(metrics, dict):
        raise EvidenceError("No metrics")
    keys = ("base_token_f1", "candidate_token_f1", "delta_token_f1")
    if any(isinstance(metrics.get(k), bool) or not isinstance(metrics.get(k), (float, int)) or
           not math.isfinite(metrics[k]) for k in keys):
        raise EvidenceError("Non-finite/missing evaluation metrics")
    if not math.isclose(metrics["candidate_token_f1"] - metrics["base_token_f1"],
                        metrics["delta_token_f1"], abs_tol=1e-6):
        raise EvidenceError("Evidence metric arithmetic mismatch")
    passed = metrics["candidate_token_f1"] >= 0.55 and metrics["delta_token_f1"] >= -0.02
    return passed, metrics
