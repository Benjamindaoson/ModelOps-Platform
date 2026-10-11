"""Security and QLoRA contracts for the actual rendered Helm objects."""
import subprocess
from pathlib import Path

import yaml

ROOT=Path(__file__).resolve().parents[2]
CHART=ROOT/"charts/kube-llmops-stack"

def _render(*args):
    p=subprocess.run(["helm","template","modelops",str(CHART),
        "-f",str(CHART/"values-ci-finetune.yaml"),
        "--set","finetune.renderWorkflowsWithoutCRD=true",
        *args],text=True,capture_output=True,check=True)
    return [x for x in yaml.safe_load_all(p.stdout) if isinstance(x,dict)]

def test_qlora_is_lora_plus_4bit_config():
    docs=_render("--set","finetune.method=qlora")
    found=[d for d in docs if d.get("kind")=="ConfigMap" and
           d.get("metadata",{}).get("name")=="modelops-finetune-config"]
    assert len(found)==1, "training config must render exactly once"
    text=found[0]["data"]["train_config.yaml"]
    config=yaml.safe_load(text)
    assert config["finetuning_type"]=="lora"
    assert config["quantization_bit"]==4
    assert config["quantization_method"]=="bitsandbytes"

def test_lora_does_not_quantize():
    docs=_render("--set","finetune.method=lora")
    obj=next(x for x in docs if x.get("kind")=="ConfigMap" and
             x.get("metadata",{}).get("name")=="modelops-finetune-config")
    config=yaml.safe_load(obj["data"]["train_config.yaml"])
    assert config["finetuning_type"]=="lora"
    assert "quantization_bit" not in config

def test_gateway_configmap_never_contains_secrets():
    docs=_render()
    config=next(x["data"]["config.yaml"] for x in docs if x.get("kind")=="ConfigMap" and
                x.get("metadata",{}).get("name")=="modelops-litellm-config")
    data=yaml.safe_load(config)
    assert data["general_settings"]["master_key"]=="os.environ/LITELLM_MASTER_KEY"
    assert data["general_settings"]["database_url"]=="os.environ/DATABASE_URL"
    assert "ci-test-pw" not in config and "sk-ci-test-key" not in config

def test_training_cannot_glob_heldout_into_train():
    text=(CHART/"charts/finetune/templates/workflow.yaml").read_text()
    assert "train_file = '/workspace/data/train.json'" in text
    assert "data_files[0]" not in text
