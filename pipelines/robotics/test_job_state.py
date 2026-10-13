"""CPU state persistence tests; fixtures are not GPU experiments."""
import json
import sys
from pathlib import Path
from pipelines.robotics.adapter import Jobs, write, sha256_file

def make_job(tmp_path):
    vla = tmp_path / "vla"
    (vla / ".venv/bin").mkdir(parents=True)
    (vla / ".venv/bin/python").symlink_to(sys.executable)
    entry = vla / "benchmarks/robot-vla-engine/scripts/run_m05_training.py"
    entry.parent.mkdir(parents=True)
    entry.write_text("pass")
    jobs = Jobs(tmp_path / "jobs", vla)
    jobs.create({"run_id": "unit-stale", "steps": 2, "dataset": "corrective"})
    d = jobs.directory("unit-stale")
    row = json.loads((d / "job.json").read_text())
    row["state"] = "RUNNING"
    row["attempts"] = [{"pid": 99999999, "create_time": 0, "started": 0}]
    write(d / "job.json", row)
    return jobs, d

def test_completed_query_persists_terminal_state(tmp_path):
    jobs, d = make_job(tmp_path)
    adapter = d / "artifacts/adapter"
    adapter.mkdir(parents=True)
    (adapter / "adapter_model.safetensors").write_bytes(b"unit-test-only")
    write(d / "artifacts/result.json", {"run_id": "unit-stale", "status": "COMPLETED",
          "adapter": str(adapter), "adapter_sha256": sha256_file(adapter / "adapter_model.safetensors")})
    assert jobs.query("unit-stale")["state"] == "COMPLETED"
    assert json.loads((d / "job.json").read_text())["state"] == "COMPLETED"

def test_query_rejects_receipt_from_another_run(tmp_path):
    jobs, d = make_job(tmp_path)
    write(d / "artifacts/result.json", {"run_id": "foreign", "status": "COMPLETED"})
    assert jobs.query("unit-stale")["state"] == "FAILED"
    assert json.loads((d / "job.json").read_text())["state"] == "FAILED"
