"""Validate real sprint receipts, bytes, registry metadata and public documentation."""
import hashlib
import json
import re
import sqlite3
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
E = ROOT / "Evidence/llm-production-validation"
DOC = ROOT / "docs/evidence/llm-validation"


def read(path):
    return json.loads(Path(path).read_text())


def sha256(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(4 * 1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def main():
    train = read(ROOT / "experiments/training/metrics.json")
    evaluation = read(DOC / "evaluation.json")
    lifecycle = read(DOC / "serving/lifecycle.json")
    registry = read(DOC / "registry/model_artifact.json")
    benchmark = read(DOC / "benchmark/validation.json")
    image = read(DOC / "docker-image-result.json")
    tests = read(E / "final-tests/status.json")
    assert train["status"] == "COMPLETED" and tests["status"] == "PASS"
    assert lifecycle["status"] == "PASS" and len(lifecycle["events"]) == 3
    assert evaluation["num_samples"] == 24 and evaluation["train_overlap_count"] == 0
    assert evaluation["metrics"]["candidate_token_f1"] >= 0.55
    assert evaluation["metrics"]["delta_token_f1"] >= -0.02
    assert lifecycle["candidate"]["digest"] == evaluation["artifact_sha256"]
    assert benchmark["status"] == "PASS" and benchmark["points"] == 45 and benchmark["requests"] == 5760
    assert sha256(train["checkpoint"]) == train["checkpoint_sha256"]
    adapter = Path(train["adapter"]) / "adapter_model.safetensors"
    assert sha256(adapter) == train["adapter_sha256"]
    steps = read(DOC / "training/training_log.json")
    assert [x["step"] for x in steps] == list(range(1, 33))
    assert all(x["run_id"] == train["run_id"] for x in steps)
    assert train["parameter_delta_linf"] > 0
    for item in benchmark["file_hashes"]:
        path = ROOT / item["file"]
        assert path.stat().st_size == item["bytes"] and sha256(path) == item["sha256"], str(path)
    assert registry["mlflow"]["run_id"] == train["mlflow_run_id"]
    assert registry["mlflow"]["checkpoint_sha256"] == train["checkpoint_sha256"]
    with sqlite3.connect("file:" + str(E / "mlflow.sqlite") + "?mode=ro", uri=True) as db:
        version = db.execute("select name,version,status,run_id from model_versions where name=? and version=1", ("ModelOps-Qwen2.5-3B",)).fetchone()
    assert version and version[2] == "READY" and version[3] == train["mlflow_run_id"]
    with urllib.request.urlopen("http://127.0.0.1:18791/health", timeout=5) as response:
        assert response.status == 200
    assert image["build_status"] == "PASS"
    screenshot_validation = read(DOC / "screenshots/validation.json")
    assert screenshot_validation["status"] == "PASS"
    from PIL import Image
    for name in ["screenshots/mlflow-training.png", "screenshots/mlflow-registry.png", "benchmark/throughput_latency.png"]:
        with Image.open(DOC / name) as img:
            img.verify()

    docs = [ROOT / "README.md", ROOT / "README.zh-CN.md", ROOT / "docs/modelops-validation-report.md", ROOT / "experiments/training/README.md"]
    missing = []
    checked = 0
    for path in docs:
        for target in re.findall(r"!?(?:\[[^\]]*\])\(([^)]+)\)", path.read_text()):
            if "://" in target or target.startswith("#"):
                continue
            target = target.split("#", 1)[0].split(":", 1)[0]
            if not target:
                continue
            checked += 1
            if not (path.parent / target).exists():
                missing.append({"document": str(path.relative_to(ROOT)), "target": target})
    assert not [x for x in missing if x != {"document": "docs/modelops-validation-report.md", "target": "evidence/llm-validation/validation.json"}], missing
    check_counts = {"control": 92, "operations": 25, "llm-contracts": 20, "benchmark": 20, "evaluation": 12}
    for key, expected in check_counts.items():
        log = (E / "final-tests" / (key + ".log")).read_text()
        assert (f"{expected} passed" in log) if key in ("control", "llm-contracts") else (f"Ran {expected} tests" in log)
    hashes = []
    for path in sorted(DOC.rglob("*")):
        if path.is_file() and path != DOC / "validation.json":
            hashes.append({"file": str(path.relative_to(ROOT)), "bytes": path.stat().st_size, "sha256": sha256(path)})
    result = {
        "status": "PASS", "scope": "Revised bounded LLM lifecycle sprint",
        "training": {"run_id": train["run_id"], "steps": 32, "actual_checkpoint_rehashed": True, "actual_adapter_rehashed": True},
        "registry": {"name": version[0], "version": version[1], "status": version[2], "run_id": version[3]},
        "evaluation": {"examples": 24, "overlap": 0, "quality_improvement": False, "unchanged_engineering_gate": "PASS"},
        "native_serving": {"revisions": 3, "actual_api_and_rollback": "PASS"},
        "benchmark": {"points": 45, "requests": 5760, "raw_hashes_verified": len(benchmark["file_hashes"])},
        "docker_image_build": "PASS", "gpu_docker_runtime": "NOT_VALIDATED", "kubernetes": "OUT_OF_SCOPE",
        "software_checks": tests["checks"], "software_test_counts": check_counts,
        "software_passed_total": sum(check_counts.values()), "optional_skips": 2,
        "documentation_links_checked": checked, "screenshots_and_chart_decoded": True,
        "review": "Author review plus CI; no independent reviewer agents",
        "public_evidence_file_hashes": hashes,
    }
    (DOC / "validation.json").write_text(json.dumps(result, indent=2) + "\n")
    (E / "final-validation.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps({"status":"PASS", "software_tests":169, "raw_hashes":len(benchmark["file_hashes"]), "documentation_links":checked, "checkpoint_rehashed":True}))


if __name__ == "__main__":
    main()
