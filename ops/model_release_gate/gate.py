"""Fail-closed release predicates; CLI resolves and verifies real external evidence."""
from dataclasses import dataclass, asdict
import hashlib
import math
from pathlib import Path


@dataclass(frozen=True)
class GatePolicy:
    min_f1: float = 0.55
    min_delta: float = -0.02
    min_samples: int = 20
    concurrency: int = 4
    repeats: int = 3
    requests_per_repeat: int = 128
    min_output_tokens_s: float = 250
    max_ttft_p95_ms: float = 200
    max_latency_p95_ms: float = 1200


def sha256(path):
    p = Path(path)
    if p.is_symlink() or not p.is_file(): raise ValueError("Not a regular immutable artifact")
    digest = hashlib.sha256()
    with p.open("rb") as stream:
        for chunk in iter(lambda: stream.read(2 ** 20), b""): digest.update(chunk)
    return digest.hexdigest()


def finite(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def decide(identity, training, evaluation, benchmark, serving, policy=None):
    policy = policy or GatePolicy()
    checks = {"artifact": False, "evaluation": False, "serving": False, "benchmark": False}
    errors = {}
    try:
        checks["artifact"] = (
            training["status"] == "COMPLETED" and training["steps"] > 0 and training["parameter_delta_linf"] > 0
            and identity["run_id"] == training["mlflow_run_id"]
            and identity["checkpoint_sha256"] == training["checkpoint_sha256"] == sha256(training["checkpoint"])
            and identity["adapter_sha256"] == training["adapter_sha256"] == sha256(Path(training["adapter"]) / "adapter_model.safetensors")
        )
    except (KeyError, OSError, ValueError, TypeError) as exc: errors["artifact"] = type(exc).__name__
    try:
        f1 = evaluation["metrics"]["candidate_token_f1"]; delta = evaluation["metrics"]["delta_token_f1"]
        checks["evaluation"] = (
            evaluation["proof_type"] == "real_checkpoint_holdout" and evaluation["num_samples"] >= policy.min_samples
            and evaluation["train_overlap_count"] == 0
            and finite(f1) and 0 <= f1 <= 1 and f1 >= policy.min_f1
            and finite(delta) and -1 <= delta <= 1 and delta >= policy.min_delta
        )
    except (KeyError, ValueError, TypeError) as exc: errors["evaluation"] = type(exc).__name__
    checks["serving"] = (
        serving.get("healthy") is True and bool(serving.get("expected_model"))
        and serving.get("expected_model") in serving.get("loaded_models", [])
    )
    try:
        tps = benchmark["output_tokens_s"]; ttft = benchmark["ttft_p95_ms"]; latency = benchmark["latency_p95_ms"]
        checks["benchmark"] = (
            benchmark["model_sha256"] == identity["checkpoint_sha256"]
            and benchmark["concurrency"] == policy.concurrency and benchmark["repeats"] == policy.repeats
            and benchmark["requests"] == policy.repeats * policy.requests_per_repeat
            and all(finite(x) and x >= 0 for x in (tps, ttft, latency))
            and tps >= policy.min_output_tokens_s and ttft <= policy.max_ttft_p95_ms and latency <= policy.max_latency_p95_ms
        )
    except (KeyError, ValueError, TypeError) as exc: errors["benchmark"] = type(exc).__name__
    return {"model": identity.get("model"), "version": identity.get("version"), "run_id": identity.get("run_id"),
            "status": "PASS" if all(checks.values()) else "FAIL", "checks": checks, "errors": errors, "policy": asdict(policy)}
