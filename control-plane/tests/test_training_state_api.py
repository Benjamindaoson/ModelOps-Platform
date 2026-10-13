"""API reconciliation uses real SQL; runtime transport is an explicit CPU fixture."""
import importlib.util
from pathlib import Path
from dataclasses import replace
import hashlib

_spec = importlib.util.spec_from_file_location("state_api_fixtures", Path(__file__).with_name("test_api.py"))
_module = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_module)
api = _module.api
headers = _module.headers
register = _module.register

def test_api_persists_observed_state_and_verifies_completion(api, tmp_path):
    client, runtime = api
    artifact, dataset = register(client)
    response = client.post("/api/v1/train-jobs", headers=headers(), json={
        "name": "reconciler-case", "artifact_id": artifact["id"],
        "dataset_id": dataset["id"], "output_name": "reconciler-output"})
    assert response.status_code == 201, response.text
    job = response.json()
    raw = runtime.jobs[job["workflow_name"]]
    raw["status"]["phase"] = "Running"
    url = "/api/v1/train-jobs/" + job["id"]
    assert client.get(url, headers=headers()).json()["state"] == "RUNNING"
    raw["status"]["phase"] = "Succeeded"
    waiting = client.get(url, headers=headers()).json()
    assert waiting["state"] == "RUNNING"
    assert waiting["artifact_verified"] is False
    checkpoint = tmp_path / "contract.bin"
    checkpoint.write_bytes(b"unit-test-only")
    client.app.state.settings = replace(client.app.state.settings, artifact_root=str(tmp_path))
    raw["artifact_receipt"] = {
        "run_id": job["name"], "status": "COMPLETED", "checkpoint": str(checkpoint),
        "checkpoint_sha256": hashlib.sha256(checkpoint.read_bytes()).hexdigest()}
    completed = client.get(url, headers=headers()).json()
    assert completed["state"] == "COMPLETED"
    assert completed["artifact_verified"] is True
    from modelops.db import FineTuneJob
    with client.app.state.sessions() as session:
        assert session.get(FineTuneJob, job["id"]).state == "COMPLETED"
    assert client.get(url, headers=headers("beta")).status_code == 404
