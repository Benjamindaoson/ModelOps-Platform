from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CHART = ROOT / "charts/kube-llmops-stack/charts/litellm/templates/deployment.yaml"
WF = ROOT / "charts/kube-llmops-stack/charts/finetune/templates/workflow.yaml"

def test_gateway_secret_is_from_k8s():
    text = CHART.read_text()
    after = text.split("- name: LITELLM_MASTER_KEY",1)[1].split("{{- if .Values.postgresql.enabled }}",1)[0]
    assert "valueFrom:" in after and "master-key" in after
    assert "sk-kube-llmops-default" not in after

def test_database_password_does_not_appear_in_deployment_manifest():
    text = CHART.read_text()
    assert "- name: DB_PASSWORD" in text
    assert "key: password" in text
    assert "$(DB_PASSWORD)@" in text
    assert "{{ .Values.postgresql.auth.password }}@" not in text

def test_workflow_uses_independent_checkpoint_evidence():
    text = WF.read_text()
    assert "APPROVED.json" in text
    assert "heldout.jsonl" in text
    assert "modelops-scripts" in text
    assert "token_overlap_f1(" not in text
    assert "What are the benefits of using Kubernetes" not in text
    assert '|| echo "unknown"' not in text

def test_scripts_match_chart_source():
    chart = ROOT / "charts/kube-llmops-stack/charts/finetune"
    assert (chart/"files/modelops_merge.py").read_bytes() == (ROOT/"pipelines/training/merge.py").read_bytes()
    assert (chart/"files/modelops_evaluate.py").read_bytes() == (ROOT/"pipelines/evaluation/run.py").read_bytes()
