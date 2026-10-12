"""Production Helm contract tests. Templates are not a live cluster deployment."""
from __future__ import annotations

import copy
import subprocess
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
CHART = ROOT / "charts" / "modelops-control"
CI_VALUES = CHART / "values-ci.yaml"


def render(extra: list[str] | None = None):
    cmd = [
        "helm", "template", "modelops-control", str(CHART),
        "--namespace", "modelops-system", "-f", str(CI_VALUES),
        *(extra or []),
    ]
    return subprocess.run(cmd, text=True, capture_output=True, check=False)


def test_production_chart_fails_closed_with_no_secrets_or_images():
    result = subprocess.run(
        ["helm", "template", "modelops-control", str(CHART),
         "--namespace", "modelops-system"],
        text=True, capture_output=True, check=False,
    )
    assert result.returncode != 0
    assert "immutable sha256 digest" in result.stderr


@pytest.fixture
def objects():
    rendered = render()
    assert rendered.returncode == 0, rendered.stderr
    docs = list(yaml.safe_load_all(rendered.stdout))
    assert docs and all(isinstance(doc, dict) for doc in docs)
    return docs


def test_chart_has_actual_production_service_resources(objects):
    names = {(x["kind"], x["metadata"]["name"]) for x in objects}
    required = {
        ("Deployment", "modelops-control-api"),
        ("Deployment", "modelops-control-console"),
        ("Service", "modelops-control-api"),
        ("Service", "modelops-control-console"),
        ("ServiceAccount", "modelops-control-api"),
        ("ServiceAccount", "modelops-control-console"),
        ("PodDisruptionBudget", "modelops-control-api"),
        ("PodDisruptionBudget", "modelops-control-console"),
        ("Ingress", "modelops-control-console"),
        ("Job", "modelops-control-migrate-1"),
        ("CronJob", "modelops-ci-recovery"),
        ("Role", "modelops-control-api"),
        ("RoleBinding", "modelops-control-api"),
        ("NetworkPolicy", "modelops-control-api"),
        ("NetworkPolicy", "modelops-control-console"),
    }
    assert required <= names
    assert not any(x["kind"] in {"ClusterRole", "ClusterRoleBinding", "Secret"}
                   for x in objects)
    assert all(x["kind"] != "StatefulSet" for x in objects)  # external PostgreSQL


def test_workloads_use_immutable_images_and_nonroot_readonly_fs(objects):
    for obj in objects:
        if obj["kind"] == "Deployment":
            pod = obj["spec"]["template"]["spec"]
            assert pod["securityContext"]["runAsNonRoot"] is True
            assert pod["securityContext"]["seccompProfile"]["type"] == "RuntimeDefault"
            assert len(pod["containers"]) == 1
            app = pod["containers"][0]
            assert "@sha256:" in app["image"]
            assert app["securityContext"]["readOnlyRootFilesystem"] is True
            assert app["securityContext"]["allowPrivilegeEscalation"] is False
            assert app["securityContext"]["capabilities"]["drop"] == ["ALL"]
            assert "readinessProbe" in app and "livenessProbe" in app
            assert obj["spec"]["replicas"] >= 2
            assert obj["spec"]["strategy"]["rollingUpdate"]["maxUnavailable"] == 0

    api = next(x for x in objects if x["kind"] == "Deployment"
               and x["metadata"]["name"] == "modelops-control-api")
    web = next(x for x in objects if x["kind"] == "Deployment"
               and x["metadata"]["name"] == "modelops-control-console")
    api_env = {v["name"]: v for v in api["spec"]["template"]["spec"]["containers"][0]["env"]}
    web_env = {v["name"]: v for v in web["spec"]["template"]["spec"]["containers"][0]["env"]}
    for secret_var in ("MODELOPS_DATABASE_URL", "MODELOPS_ATTESTATION_KEY"):
        assert "secretKeyRef" in api_env[secret_var]["valueFrom"]
    assert api_env["MODELOPS_AUTH_MODE"]["value"] == "oidc"
    assert api_env["MODELOPS_ENV"]["value"] == "production"
    assert api_env["MODELOPS_RUNTIME"]["value"] == "kubernetes"
    assert web_env["MODELOPS_CONSOLE_AUTH"]["value"] == "oidc"
    assert web["spec"]["template"]["spec"]["automountServiceAccountToken"] is False
    assert web_env["MODELOPS_PUBLIC_ORIGIN"]["value"] == "https://modelops.example.invalid"


def test_namespaced_access_and_negative_capabilities(objects):
    roles = [x for x in objects if x["kind"] == "Role"]
    assert len(roles) == 1
    role = roles[0]
    assert role["metadata"]["namespace"] == "modelops-ci"
    verbs = {v for rule in role["rules"] for v in rule["verbs"]}
    resources = {v for rule in role["rules"] for v in rule["resources"]}
    assert "*" not in verbs and "*" not in resources
    assert "secrets" not in resources
    assert "clusterroles" not in resources
    assert resources == {"modeldeployments", "workflows"}
    binding = next(x for x in objects if x["kind"] == "RoleBinding")
    assert binding["metadata"]["namespace"] == "modelops-ci"
    assert binding["subjects"][0]["namespace"] == "modelops-system"
    assert binding["subjects"][0]["name"] == "modelops-control-api"
    policies = [x for x in objects if x["kind"] == "NetworkPolicy"]
    assert len(policies) == 2
    assert all(x["spec"]["policyTypes"] == ["Ingress", "Egress"] for x in policies)
    assert all(x["spec"]["ingress"] and x["spec"]["egress"] for x in policies)


def test_tls_ingress_and_migration_separate_from_runtime(objects):
    ing = next(x for x in objects if x["kind"] == "Ingress")
    assert ing["spec"]["tls"][0]["secretName"] == "modelops-tls"
    assert ing["spec"]["rules"][0]["host"] == "modelops.example.invalid"
    job = next(x for x in objects if x["kind"] == "Job")
    assert job["metadata"]["annotations"]["helm.sh/hook"] == "pre-install,pre-upgrade"
    pod = job["spec"]["template"]["spec"]
    assert pod["automountServiceAccountToken"] is False
    assert pod["containers"][0]["command"] == ["alembic", "upgrade", "head"]
    assert "secretKeyRef" in pod["containers"][0]["env"][0]["valueFrom"]


@pytest.mark.parametrize("overrides", [
    ["--set", "networkPolicy.enabled=false"],
    ["--set", "oidc.issuer=http://idp.example.invalid"],
    ["--set", "oidc.publicOrigin=https://attacker.example.invalid"],
    ["--set", "ingress.tlsSecret="],
    ["--set", "api.image.digest=latest"],
    ["--set", "api.replicas=1"],
    ["--set", "console.replicas=1"],
    ["--set", "api.egressCidrs={}"],
    ["--set", "secrets.database.name="],
    ["--set", "tenants={../../kube-system}"],
])
def test_unsafe_deploy_values_are_rejected(overrides):
    result = render(overrides)
    assert result.returncode != 0, (overrides, result.stdout)
