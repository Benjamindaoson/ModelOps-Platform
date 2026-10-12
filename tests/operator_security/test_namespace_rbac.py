"""Static security contract: runtime Helm chart cannot grant cluster-admin."""
from pathlib import Path
import subprocess
import yaml

ROOT = Path(__file__).resolve().parents[2]
CHART = ROOT / "operator/charts/kube-llmops-operator"

def test_operator_runtime_is_namespace_scoped():
    proc = subprocess.run(["helm", "template", "operator", str(CHART)],
                          capture_output=True,text=True,check=True)
    docs = [x for x in yaml.safe_load_all(proc.stdout) if isinstance(x,dict)]
    kinds = [d.get("kind") for d in docs]
    assert "Role" in kinds and "RoleBinding" in kinds
    assert "ClusterRoleBinding" not in kinds
    assert "ClusterRole" not in kinds
    assert all(d.get("roleRef", {}).get("name") != "cluster-admin" for d in docs)
    assert all(d.get("kind") not in ("ClusterRole", "ClusterRoleBinding") for d in docs)
    dep = next(d for d in docs if d.get("kind") == "Deployment")
    pod = dep["spec"]["template"]["spec"]
    env = {x["name"]:x for x in pod["containers"][0]["env"]}
    assert env["WATCH_NAMESPACE"]["valueFrom"]["fieldRef"]["fieldPath"] == "metadata.namespace"
    assert env["GATEWAY_MASTER_KEY"]["valueFrom"]["secretKeyRef"]["key"] == "master-key"
    assert "value" not in env["GATEWAY_MASTER_KEY"]
    assert pod["containers"][0]["securityContext"]["allowPrivilegeEscalation"] is False


def test_finetune_roles_stay_in_namespace():
    chart = ROOT / "charts/kube-llmops-stack"
    proc = subprocess.run(
        ["helm", "template", "modelops", str(chart),
         "--set", "finetune.enabled=true",
         "--set", "finetune.baseModel=Qwen/Qwen2.5-0.5B-Instruct",
         "--set", "finetune.outputName=release-candidate",
         "--set", "finetune.dataSource.path=s3://datasets/train/"],
        capture_output=True,text=True,check=True)
    docs=[x for x in yaml.safe_load_all(proc.stdout) if isinstance(x,dict)]
    finetune=[x for x in docs if x.get("metadata",{}).get("name")=="modelops-finetune" and
              x.get("kind") in ("Role","RoleBinding","ClusterRole","ClusterRoleBinding")]
    assert {x["kind"] for x in finetune} == {"Role","RoleBinding"}
    assert all(x["metadata"].get("namespace") == "default" for x in finetune)
