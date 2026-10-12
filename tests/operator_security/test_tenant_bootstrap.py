from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
SCRIPT=ROOT/"ops/provision-tenant.sh"
WORKFLOW=ROOT/"charts/kube-llmops-stack/charts/finetune/templates/workflow-dynamic.yaml"

def test_tenant_bootstrap_requires_secret_and_namespaced_helm():
    contents=SCRIPT.read_text()
    for marker in ("modelops-$TENANT","kind: ResourceQuota","kind: LimitRange",
                   'get secret modelops-objectstore',"--set mlflow.enabled=false",
                   "--set staticTemplate.enabled=false","can-i get secrets"):
        assert marker in contents
    assert "kubectl create secret" not in contents
    assert "cluster-admin" not in contents

def test_dynamic_mlflow_supports_real_external_service():
    assert ".Values.dynamicTemplate.mlflowTrackingURI" in WORKFLOW.read_text()
