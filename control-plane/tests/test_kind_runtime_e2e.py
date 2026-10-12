"""Real CPU Kubernetes ModelOps API -> CRD -> Operator integration.

Requires an externally bootstrapped kind cluster and tenant-local Operator.
No mock runtime, fake GPU measurements, or simulated model inference occurs.
The model Pod is intentionally unready on the CPU-only runner.
"""
from __future__ import annotations

import os
import time
from datetime import datetime, timedelta, timezone

import pytest

pytestmark = pytest.mark.skipif(
    os.environ.get("MODELOPS_KIND_E2E") != "1",
    reason="Requires kind + real tenant-scoped ModelDeployment Operator",
)


def _headers(tenant="ci"):
    import jwt

    now = datetime.now(timezone.utc)
    claims = {
        "iss": "modelops-local", "aud": "modelops-dev", "sub": "kind-ci",
        "tenant": tenant, "role": "admin", "iat": now,
        "exp": now + timedelta(minutes=10),
    }
    token = jwt.encode(claims, os.environ["MODELOPS_JWT_SECRET"], algorithm="HS256")
    return {"Authorization": "Bearer " + token}


def _wait(label, predicate, timeout=120):
    end = time.monotonic() + timeout
    last_error = "not observed"
    while time.monotonic() < end:
        try:
            if predicate():
                return
        except Exception as exc:
            last_error = repr(exc)
        time.sleep(2)
    pytest.fail(f"Timed out waiting for {label}: {last_error}")


def test_real_api_kubernetes_operator_lifecycle(tmp_path):
    from fastapi.testclient import TestClient
    from kubernetes import client
    from modelops.config import Settings
    from modelops.main import create_app
    from modelops.runtime import KubernetesRuntime

    namespace = "modelops-ci"  # Fixed from tenant, never user-supplied in a request.
    runtime = KubernetesRuntime()
    settings = Settings(
        database_url="sqlite:///" + str(tmp_path / "kind.sqlite"),
        runtime="kubernetes", environment="test", auth_mode="dev",
        jwt_secret=os.environ["MODELOPS_JWT_SECRET"],
    )
    api = TestClient(create_app(settings, runtime=runtime))
    objects = client.CustomObjectsApi()
    deployments = client.AppsV1Api()
    core = client.CoreV1Api()
    auth = _headers()

    model = api.post("/api/v1/models", json={
        "name": "kind-qwen", "version": 1,
        "source": "Qwen/Qwen2.5-0.5B-Instruct",
        "revision": "9abcdef012345678901234567890123456789abcdef",
        "digest": "a" * 64, "family": "llm",
    }, headers=auth)
    assert model.status_code == 201, model.text
    model_id = model.json()["id"]
    created = api.post("/api/v1/deployments", json={
        "name": "modelops-api-kind", "artifact_id": model_id,
        "engine": "vllm", "replicas": 1, "gpu": 1,
    }, headers=auth)
    assert created.status_code == 201, created.text
    deployment_id = created.json()["id"]
    assert created.json()["runtime_verified"] is False  # no GPU: NOT served
    assert api.get("/api/v1/deployments/" + deployment_id,
                   headers=_headers("foreign")).status_code == 404

    cr = objects.get_namespaced_custom_object(
        "llmops.kubellmops.io", "v1alpha1", namespace,
        "modeldeployments", "modelops-api-kind",
    )
    assert cr["metadata"]["annotations"]["modelops.io/artifact-id"] == model_id
    assert cr["spec"]["source"] == "Qwen/Qwen2.5-0.5B-Instruct"
    assert cr["spec"]["resources"]["gpu"] == 1
    _wait("real Operator creates Deployment, Service and PVC", lambda: (
        deployments.read_namespaced_deployment("modelops-api-kind", namespace)
        and core.read_namespaced_service("modelops-api-kind", namespace)
        and core.read_namespaced_persistent_volume_claim(
            "modelops-api-kind-cache", namespace)
    ))

    # This is a real Kubernetes spec change, not a stubbed client:
    scale = api.patch("/api/v1/deployments/" + deployment_id + "/scale", json={
        "replicas": 2, "expected_generation": 1,
    }, headers=auth)
    assert scale.status_code == 200, scale.text
    cr = objects.get_namespaced_custom_object(
        "llmops.kubellmops.io", "v1alpha1", namespace,
        "modeldeployments", "modelops-api-kind",
    )
    assert cr["spec"]["replicas"] == 2
    assert api.patch("/api/v1/deployments/" + deployment_id + "/scale", json={
        "replicas": 3, "expected_generation": 1,
    }, headers=auth).status_code == 409
    observed = api.get("/api/v1/deployments/" + deployment_id, headers=auth)
    assert observed.status_code == 200
    assert observed.json()["runtime_verified"] is False  # no GPU
    assert observed.json()["ready_replicas"] in (0, None)

    deleted = api.delete("/api/v1/deployments/" + deployment_id, headers=auth)
    assert deleted.status_code == 200, deleted.text
    assert deleted.json()["status"] == "deletion_requested"
    _wait("real Kubernetes CR deletion", lambda: not any(
        obj["metadata"]["name"] == "modelops-api-kind"
        for obj in objects.list_namespaced_custom_object(
            "llmops.kubellmops.io", "v1alpha1", namespace, "modeldeployments"
        ).get("items", [])
    ))
    assert api.get("/api/v1/deployments/" + deployment_id,
                   headers=auth).json()["intent"] == "deleted"
