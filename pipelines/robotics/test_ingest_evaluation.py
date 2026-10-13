import json

from pipelines.robotics.adapter import Registry, sha256_file
from pipelines.robotics.ingest_evaluation import admit


def test_development_ingest_requires_exact_coverage_and_hashed_actions(tmp_path):
    weight = tmp_path / "model.safetensors"
    weight.write_bytes(b"frozen")
    registry_root = tmp_path / "registry"
    Registry(registry_root).register({
        "version": "frozen", "run_id": "run-1", "checkpoint": str(weight),
        "checkpoint_sha256": sha256_file(weight), "processor_sha256": "a" * 64,
        "dataset_sha256": "b" * 64, "base_sha256": "c" * 64,
    })
    protocol = tmp_path / "protocol.json"
    cases = [{"suite": "goal", "task": 0, "init": i} for i in range(10, 18)]
    protocol.write_text(json.dumps({
        "scope": "M05-development-only", "development": cases,
        "formal_test_forbidden_init_ids": list(range(40, 50)),
    }))
    receipts = tmp_path / "receipts"
    receipts.mkdir()
    for case in cases:
        case_id = f"frozen_goal_t00_i{case['init']:02d}"
        video = receipts / f"{case_id}.mp4"
        video.write_bytes(b"fixture-video")
        trajectory = receipts / f"{case_id}.npz"
        trajectory.write_bytes(b"fixture-trajectory")
        actions = receipts / f"{case_id}.jsonl"
        actions.write_text(json.dumps([{"executed": [0.0] * 7}]))
        (receipts / f"{case_id}.json").write_text(json.dumps({
            "suite": "goal", "task": 0, "init": case["init"],
            "condition": "frozen", "checkpoint_sha256": sha256_file(weight),
            "status": "complete", "success": False, "steps": 1,
            "chunk_mean_ms": 5.0, "gpu_peak_allocated": 0,
            "video": {"path": str(video), "sha256": sha256_file(video)},
            "trajectory": {"path": str(trajectory), "sha256": sha256_file(trajectory)},
            "action_trace": {"path": str(actions), "sha256": sha256_file(actions)},
        }))
    args = (registry_root, "frozen", "frozen", protocol, receipts)
    assert admit(*args)["passed"]
    extra = receipts / "frozen_duplicate.json"
    extra.write_bytes((receipts / "frozen_goal_t00_i10.json").read_bytes())
    assert not admit(*args)["passed"]
    extra.unlink()
    trace = receipts / "frozen_goal_t00_i10.jsonl"
    trace.write_text(json.dumps([{"executed": [1.5] * 7}]))
    row = receipts / "frozen_goal_t00_i10.json"
    data = json.loads(row.read_text())
    data["action_trace"]["sha256"] = sha256_file(trace)
    row.write_text(json.dumps(data))
    assert not admit(*args)["passed"]
