"""CPU-only API tests use an explicit recording FakeRuntime, never production Kubernetes."""
import hashlib
import hmac
import os
import json
from datetime import datetime, timedelta, timezone

os.environ.setdefault("MODELOPS_AUTH_MODE", "dev")
os.environ.setdefault("MODELOPS_ENV", "test")
os.environ.setdefault("MODELOPS_JWT_SECRET", "only-for-tests-32-chars-plus-000000000")
os.environ["MODELOPS_ATTESTATION_KEY"] = "only-for-tests-32-chars-plus-sign-key"

import jwt
import pytest
from fastapi.testclient import TestClient

from modelops.auth import Verifier
from modelops.config import Settings
from modelops.db import ModelArtifact
from modelops.evidence import digest_report
from modelops.main import create_app
from modelops.runtime import DisabledRuntime, deployment_body, fine_tune_workflow_body


class RecordingRuntime:
    connected = True
    def __init__(self):
        self.deployments = {}
        self.jobs = {}
        self.last_workflow = None
        self.fail_next = False

    def create_deployment(self, row, artifact):
        if self.fail_next:
            self.fail_next = False
            from modelops.runtime import RuntimeFailure
            raise RuntimeFailure("Injected Kubernetes outage")
        self.deployments[(row.tenant, row.name)] = deployment_body(row, artifact)

    def get_deployment(self, row):
        if (row.tenant, row.name) not in self.deployments:
            raise AssertionError("test runtime not populated")
        return {"status": {"phase": "Ready", "readyReplicas": row.replicas}}

    def patch_deployment(self, row, artifact):
        self.deployments[(row.tenant, row.name)] = deployment_body(row, artifact)

    def delete_deployment(self, row):
        self.deployments.pop((row.tenant, row.name), None)

    def submit_finetune(self, row, artifact, dataset, parameters):
        self.last_workflow = fine_tune_workflow_body(row, artifact, dataset, parameters)
        self.jobs[row.workflow_name] = self.last_workflow

    def get_finetune(self, row):
        return {"status": {"phase": "Pending"}}


@pytest.fixture
def api(tmp_path):
    settings = Settings(database_url="sqlite:///" + str(tmp_path / "db.sqlite"),
                        environment="test", runtime="disabled", auth_mode="dev",
                        jwt_secret="only-for-tests-32-chars-plus-000000000")
    runtime = RecordingRuntime()
    client = TestClient(create_app(settings, runtime=runtime))
    return client, runtime


def token(tenant="alpha", role="admin", sub="operator"):
    now = datetime.now(timezone.utc)
    return jwt.encode({"iss": "modelops-local", "aud": "modelops-dev",
                       "sub": sub, "tenant": tenant, "role": role,
                       "iat": now, "exp": now + timedelta(minutes=10)},
                      "only-for-tests-32-chars-plus-000000000", algorithm="HS256")


def headers(tenant="alpha", role="admin", sub="operator"):
    return {"Authorization": "Bearer " + token(tenant, role, sub)}


def model_payload(name="qwen", version=1):
    return {"name": name, "version": version, "source": "Qwen/Qwen2.5-0.5B-Instruct",
            "revision": "9abcdef012345678901234567890123456789abcdef",
            "digest": "a" * 64, "family": "llm"}


def dataset_payload(name="fine-tune", version=1):
    return {"name": name, "version": version, "uri": "s3://modelops/datasets/alpha/v1/",
            "digest": "b" * 64, "train_count": 80, "heldout_count": 20}


def register(client):
    m = client.post("/api/v1/models", json=model_payload(), headers=headers())
    assert m.status_code == 201, m.text
    d = client.post("/api/v1/datasets", json=dataset_payload(), headers=headers())
    assert d.status_code == 201, d.text
    return m.json(), d.json()


def test_health_public_but_metadata_requires_auth(api):
    c, _ = api
    assert c.get("/healthz").status_code == 200
    assert c.get("/api/v1/models").status_code == 401
    assert c.get("/api/v1/models", headers={"Authorization": "Bearer not-a-jwt"}).status_code == 401


def test_metadata_crud_and_tenant_isolation(api):
    c, _ = api
    m, d = register(c)
    assert c.get("/api/v1/models", headers=headers()).json()[0]["id"] == m["id"]
    assert c.get("/api/v1/models", headers=headers("beta")).json() == []
    assert c.get("/api/v1/datasets", headers=headers()).json()[0]["id"] == d["id"]
    assert c.get("/api/v1/overview", headers=headers()).json()["models"] == 1
    assert c.get("/api/v1/audit", headers=headers()).json()[0]["actor"] == "operator"


def test_viewer_cannot_mutate(api):
    c, _ = api
    assert c.post("/api/v1/models", json=model_payload(), headers=headers(role="viewer")).status_code == 403


def test_model_version_immutable_and_duplicates_blocked(api):
    c, _ = api
    register(c)
    bad = c.post("/api/v1/models", json=model_payload(), headers=headers())
    assert bad.status_code == 409
    next_version = c.post("/api/v1/models", json=model_payload(version=2), headers=headers())
    assert next_version.status_code == 201


def test_deployment_produces_real_runtime_contract_in_test(api):
    c, runtime = api
    model, _ = register(c)
    resp = c.post("/api/v1/deployments", json={"name": "qwen-api", "artifact_id": model["id"],
        "engine": "vllm", "replicas": 1, "gpu": 1}, headers=headers())
    assert resp.status_code == 201, resp.text
    data = resp.json()
    assert data["observed_phase"] == "Ready"  # Explicit test-only FakeRuntime
    body = runtime.deployments[("alpha", "qwen-api")]
    assert body["metadata"]["namespace"] == "modelops-alpha"
    assert body["spec"]["engineArgs"]["--revision"] == model["revision"]
    r = c.get("/api/v1/deployments/" + data["id"] + "/revisions", headers=headers())
    assert len(r.json()) == 1
    return data


def test_scale_revisions_and_cas(api):
    c, runtime = api
    m, _ = register(c)
    r = c.post("/api/v1/deployments", json={"name": "qwen-api", "artifact_id": m["id"],
        "engine": "vllm"}, headers=headers()).json()
    path = "/api/v1/deployments/" + r["id"] + "/scale"
    assert c.patch(path, json={"replicas": 3, "expected_generation": 1}, headers=headers()).status_code == 200
    assert c.patch(path, json={"replicas": 2, "expected_generation": 1}, headers=headers()).status_code == 409
    rows = c.get("/api/v1/deployments/" + r["id"] + "/revisions", headers=headers()).json()
    assert rows[0]["generation"] == 2


def test_runtime_failure_does_not_register_fake_deployment(api):
    c, runtime = api
    m, _ = register(c)
    runtime.fail_next = True
    response = c.post("/api/v1/deployments", json={"name": "broken", "artifact_id": m["id"],
        "engine": "vllm"}, headers=headers())
    assert response.status_code == 502
    assert c.get("/api/v1/deployments", headers=headers()).json() == []


def test_production_offline_writes_are_denied(tmp_path):
    settings = Settings(database_url="sqlite:///" + str(tmp_path / "dev.sqlite"), environment="test",
                        auth_mode="dev", jwt_secret="only-for-tests-32-chars-plus-000000000")
    client = TestClient(create_app(settings, DisabledRuntime()))
    model = client.post("/api/v1/models", json=model_payload(), headers=headers()).json()
    assert client.post("/api/v1/deployments", json={"name": "no-simulation",
        "artifact_id": model["id"], "engine": "vllm"}, headers=headers()).status_code == 503
    assert client.get("/api/v1/deployments", headers=headers()).json() == []


def test_train_job_parameterization_isolation(api):
    c, runtime = api
    m, d = register(c)
    p = {"name": "job-one", "artifact_id": m["id"], "dataset_id": d["id"],
         "method": "qlora", "output_name": "model-finetuned",
         "epochs": 2, "lr": 0.0001, "gpu": 1}
    r = c.post("/api/v1/train-jobs", json=p, headers=headers())
    assert r.status_code == 201, r.text
    assert runtime.last_workflow["spec"]["workflowTemplateRef"]["name"] == "modelops-finetune-dynamic"
    vals = {x["name"]: x["value"] for x in runtime.last_workflow["spec"]["arguments"]["parameters"]}
    assert vals["epochs"] == "2"
    assert vals["method"] == "qlora"
    assert vals["dataset_sha256"] == "b" * 64
    assert len(c.get("/api/v1/train-jobs", headers=headers()).json()) == 1


def test_signed_holdout_evidence_and_two_person_approval(api):
    c, _ = api
    m, d = register(c)
    report = {"schema": "modelops.heldout.v1", "proof_type": "real_checkpoint_holdout",
              "num_samples": 20, "train_overlap_count": 0, "generation_success_rate": 1.0,
              "artifact_sha256": m["digest"], "heldout_sha256": d["digest"],
              "metrics": {"base_token_f1": 0.60, "candidate_token_f1": 0.72, "delta_token_f1": 0.12}}
    signature = hmac.new(os.environ["MODELOPS_ATTESTATION_KEY"].encode(),
                         digest_report(report).encode(), hashlib.sha256).hexdigest()
    auth = headers(sub="evaluator")
    auth["X-ModelOps-Attestation"] = signature
    r = c.post("/api/v1/evaluations/attest", json={"artifact_id": m["id"],
        "dataset_id": d["id"], "report": report}, headers=auth)
    assert r.status_code == 201, r.text
    evid = r.json()
    assert evid["verified"] is True and evid["passed"] is True
    approval = {"artifact_id": m["id"], "evaluation_id": evid["id"],
                "reason": "Independent verification and review passed"}
    assert c.post("/api/v1/approvals", json=approval, headers=headers(sub="evaluator")).status_code == 409
    good = c.post("/api/v1/approvals", json=approval, headers=headers(sub="release-manager"))
    assert good.status_code == 201, good.text


def test_bad_evidence_signature_and_roles(api):
    c, _ = api
    m, d = register(c)
    report = {"not": "evidence"}
    result = c.post("/api/v1/evaluations/attest", json={"artifact_id": m["id"],
        "dataset_id": d["id"], "report": report}, headers={
            **headers(role="editor"), "X-ModelOps-Attestation": "wrong"})
    assert result.status_code == 422


def test_cross_tenant_reference_is_404(api):
    c, _ = api
    m, d = register(c)
    result = c.post("/api/v1/deployments", json={"name": "stolen", "artifact_id": m["id"],
        "engine": "vllm"}, headers=headers("beta"))
    assert result.status_code == 404


def test_configuration_fails_closed():
    with pytest.raises(ValueError):
        Settings(auth_mode="dev", environment="production", jwt_secret="x" * 40).validate()
    with pytest.raises(ValueError):
        Settings(auth_mode="oidc", environment="production", runtime="kubernetes").validate()
