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
        self.cancel_calls = 0
        self.canaries = {}
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
        candidate = self.canaries.get((row.tenant,row.name))
        return {
            "status": {
                "phase": "Ready", "readyReplicas": row.replicas,
                "canary": {"phase": "Pending", "readyReplicas": 0} if candidate else None,
            },
            "spec": {"canary": candidate},
        }

    def patch_deployment(self, row, artifact):
        self.deployments[(row.tenant, row.name)] = deployment_body(row, artifact)

    def patch_canary(self, row, candidate, weight):
        if self.fail_next:
            self.fail_next = False
            from modelops.runtime import RuntimeFailure
            raise RuntimeFailure("Simulated Kubernetes canary patch failure")
        if (row.tenant,row.name) not in self.deployments:
            raise AssertionError("Cannot patch a missing Kubernetes model")
        if candidate is None:
            self.canaries.pop((row.tenant,row.name),None)
        else:
            self.canaries[(row.tenant,row.name)] = {
                "source":candidate.source,"revision":candidate.revision,
                "digest":candidate.digest,"weight":weight,
            }

    def delete_deployment(self, row):
        self.deployments.pop((row.tenant, row.name), None)

    def submit_finetune(self, row, artifact, dataset, parameters):
        if self.fail_next:
            self.fail_next = False
            from modelops.runtime import RuntimeFailure
            raise RuntimeFailure("Injected Argo submission failure")
        body = fine_tune_workflow_body(row, artifact, dataset, parameters)
        body["metadata"]["resourceVersion"] = "1"
        body["metadata"]["uid"] = "uid-" + row.id
        body["status"] = {"phase": "Pending", "progress": "0/7"}
        self.last_workflow = body
        self.jobs[row.workflow_name] = body

    def get_finetune(self, row):
        return self.jobs[row.workflow_name]

    def cancel_finetune(self, row, resource_version):
        if self.fail_next:
            self.fail_next = False
            from modelops.runtime import RuntimeFailure
            raise RuntimeFailure("Injected Argo PATCH error")
        assert resource_version == self.jobs[row.workflow_name]["metadata"]["resourceVersion"]
        self.cancel_calls += 1
        self.jobs[row.workflow_name]["spec"]["shutdown"] = "Terminate"
        self.jobs[row.workflow_name]["metadata"]["resourceVersion"] = "2"


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
    assert body["spec"]["engineArgs"] == {}
    assert body["metadata"]["annotations"]["modelops.io/artifact-revision"] == model["revision"]
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


def _issue_approved_candidate(client, dataset):
    candidate_payload = model_payload(name="candidate",version=2)
    candidate_payload["revision"] = "c"*40
    candidate_payload["digest"] = "d"*64
    candidate = client.post("/api/v1/models", json=candidate_payload, headers=headers()).json()
    report = {
        "schema":"modelops.heldout.v1","proof_type":"real_checkpoint_holdout",
        "num_samples":20,"train_overlap_count":0,"generation_success_rate":1.0,
        "artifact_sha256":candidate["digest"],"heldout_sha256":dataset["digest"],
        "metrics":{"base_token_f1":0.6,"candidate_token_f1":0.8,"delta_token_f1":0.2},
    }
    signature = hmac.new(os.environ["MODELOPS_ATTESTATION_KEY"].encode(),
                         digest_report(report).encode(), hashlib.sha256).hexdigest()
    ev = client.post("/api/v1/evaluations/attest",json={
        "artifact_id":candidate["id"],"dataset_id":dataset["id"],"report":report,
    },headers={**headers(sub="evaluator"),
              "X-ModelOps-Attestation":signature})
    assert ev.status_code == 201,ev.text
    approval = client.post("/api/v1/approvals",json={
        "artifact_id":candidate["id"],"evaluation_id":ev.json()["id"],
        "reason":"Independent validated model release candidate",
    },headers=headers(sub="security-reviewer"))
    assert approval.status_code == 201,approval.text
    return candidate,approval.json()


def test_canary_requires_independently_approved_new_version(api):
    client, runtime = api
    stable, dataset = register(client)
    deployment = client.post("/api/v1/deployments",json={
        "name":"prod","artifact_id":stable["id"],"engine":"vllm",
        "replicas":1,"gpu":1,
    },headers=headers()).json()
    path="/api/v1/deployments/"+deployment["id"]+"/canary"

    # No approval and no previous successful model evaluation => no route changes.
    without = client.post(path,json={
        "artifact_id":stable["id"],"approval_id":"not-approved",
        "weight":20,"expected_generation":1,
    },headers=headers())
    assert without.status_code==404
    assert runtime.canaries=={}

    candidate,approval=_issue_approved_candidate(client,dataset)
    payload={"artifact_id":candidate["id"],"approval_id":approval["id"],
             "weight":20,"expected_generation":1}
    response=client.post(path,json=payload,headers=headers())
    assert response.status_code==200,response.text
    row=response.json()
    assert row["generation"]==2
    assert row["canary_spec"]["revision"]==candidate["revision"]
    assert row["canary_spec"]["digest"]==candidate["digest"]
    assert row["canary_spec"]["weight"]==20
    # Runtime has not run the candidate model in the fake test; never advertise
    # the candidate Ready. Actual Operator E2E is a separate gate.
    assert row["canary_status"]["phase"]=="Pending"

    stale=client.post(path,json=payload,headers=headers())
    assert stale.status_code==409
    assert client.post(path,json={**payload,"weight":101,"expected_generation":2},
                       headers=headers()).status_code==422
    assert client.post(path,json={**payload,"expected_generation":2},
                       headers=headers("other-tenant")).status_code==404

    stopped=client.post(path+"/stop",json={"expected_generation":2},headers=headers())
    assert stopped.status_code==200,stopped.text
    assert stopped.json()["generation"]==3
    assert stopped.json()["canary_spec"] is None
    operations=client.get("/api/v1/deployments/"+deployment["id"]+"/revisions",
                          headers=headers()).json()
    assert [x["operation"] for x in operations[:3]]==["canary_stop","canary","create"]


def test_canary_cluster_error_must_not_report_success(api):
    client,runtime=api
    stable,data=register(client)
    candidate,approval=_issue_approved_candidate(client,data)
    deployment=client.post("/api/v1/deployments",json={
        "name":"prod","artifact_id":stable["id"],"engine":"vllm"},headers=headers()).json()
    runtime.fail_next=True
    result=client.post("/api/v1/deployments/"+deployment["id"]+"/canary",json={
        "artifact_id":candidate["id"],"approval_id":approval["id"],
        "weight":20,"expected_generation":1,
    },headers=headers())
    assert result.status_code==502
    assert runtime.canaries=={}
    records=client.get("/api/v1/deployments/"+deployment["id"]+"/revisions",
                       headers=headers()).json()
    assert len(records)==1



def test_training_cancel_then_retries_immutable_job(api):
    client, runtime = api
    artifact, dataset = register(client)
    submitted = client.post("/api/v1/train-jobs", json={
        "name": "qwen-domain", "artifact_id": artifact["id"],
        "dataset_id": dataset["id"], "method": "qlora",
        "output_name": "qwen-domain-adapter", "epochs": 4, "lr": 0.0001,
    }, headers=headers())
    assert submitted.status_code == 201, submitted.text
    job = submitted.json()
    path = "/api/v1/train-jobs/" + job["id"]
    detail = client.get(path, headers=headers())
    assert detail.status_code == 200
    assert detail.json()["observed_phase"] == "Pending"
    assert detail.json()["runtime_verified"] is True
    assert detail.json()["attempt"] == 1

    stopped = client.post(path + "/cancel", headers=headers())
    assert stopped.status_code == 200, stopped.text
    assert stopped.json()["cancel_requested"] is True
    assert runtime.cancel_calls == 1
    repeat = client.post(path + "/cancel", headers=headers())
    assert repeat.status_code == 200, repeat.text
    assert runtime.cancel_calls == 1  # repeated requests are idempotent

    active_retry = client.post(path + "/retry", headers=headers())
    assert active_retry.status_code == 409
    runtime.jobs[job["workflow_name"]]["status"]["phase"] = "Failed"
    assert client.post(path + "/cancel", headers=headers()).status_code == 409

    attempted = client.post(path + "/retry", headers=headers())
    assert attempted.status_code == 201, attempted.text
    retry = attempted.json()
    assert retry["parent_job_id"] == job["id"]
    assert retry["attempt"] == 2
    assert retry["id"] != job["id"]
    assert retry["workflow_name"] != job["workflow_name"]
    assert retry["parameters"]["epochs"] == 4
    assert retry["parameters"]["lr"] == 0.0001
    assert retry["artifact_id"] == job["artifact_id"]
    assert retry["dataset_id"] == job["dataset_id"]
    assert client.get(path, headers=headers()).json()["observed_phase"] == "Failed"
    assert client.get("/api/v1/train-jobs", headers=headers()).json()[0]["attempt"] == 2
    assert client.get(path, headers=headers("foreign-tenant")).status_code == 404
    assert client.post(path + "/retry", headers=headers("foreign-tenant")).status_code == 404
    assert client.post(path + "/cancel", headers=headers(role="viewer")).status_code == 403

    actions = [x["action"] for x in client.get("/api/v1/audit", headers=headers()).json()]
    assert "training.cancel" in actions and "training.retry" in actions


def test_training_retry_denied_when_argo_job_succeeded(api):
    client, runtime = api
    artifact, data = register(client)
    result = client.post("/api/v1/train-jobs", json={
        "name": "success", "artifact_id": artifact["id"],
        "dataset_id": data["id"], "output_name": "success-output",
    }, headers=headers()).json()
    runtime.jobs[result["workflow_name"]]["status"]["phase"] = "Succeeded"
    assert client.post("/api/v1/train-jobs/" + result["id"] + "/retry",
                       headers=headers()).status_code == 409


def test_training_cancel_failure_preserves_uncancelled_intent(api):
    client, runtime = api
    artifact, dataset = register(client)
    result = client.post("/api/v1/train-jobs", json={
        "name": "example-job", "artifact_id": artifact["id"],
        "dataset_id": dataset["id"], "output_name": "example-output",
    }, headers=headers()).json()
    runtime.fail_next = True
    path = "/api/v1/train-jobs/" + result["id"]
    response = client.post(path + "/cancel", headers=headers())
    assert response.status_code == 502
    assert client.get(path, headers=headers()).json()["intent"] == "requested"
    assert runtime.jobs[result["workflow_name"]]["spec"].get("shutdown") is None


def test_training_cross_tenant_workflow_collision_fails_closed(api):
    client, runtime = api
    artifact, dataset = register(client)
    result = client.post("/api/v1/train-jobs", json={
        "name": "cross-tenant", "artifact_id": artifact["id"],
        "dataset_id": dataset["id"], "output_name": "output",
    }, headers=headers()).json()
    workflow = runtime.jobs[result["workflow_name"]]
    workflow["metadata"]["labels"]["modelops.io/tenant"] = "foreign"
    result_response = client.get("/api/v1/train-jobs/" + result["id"], headers=headers())
    assert result_response.status_code == 502
    assert client.post("/api/v1/train-jobs/" + result["id"] + "/retry",
                       headers=headers()).status_code == 502


def test_retry_name_is_dns_safe():
    from modelops.job_lifecycle import retry_workflow_name
    name = retry_workflow_name("a" * 63, "12345678")
    assert len(name + "-ft") <= 63
    assert name.endswith("-r-12345678")
