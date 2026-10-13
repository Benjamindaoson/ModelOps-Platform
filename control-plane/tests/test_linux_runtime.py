"""Native worker boundary tests; never invoke GPU work here."""
import hashlib
import json
import sys
from types import SimpleNamespace
import pytest
from modelops.linux_runtime import LinuxRuntime
from modelops.runtime import RuntimeFailure

def setup(tmp_path):
    public = tmp_path / ".tools/assets/base"
    public.mkdir(parents=True)
    weight = public / "model.safetensors"
    weight.write_bytes(b"unit-test-only")
    data = tmp_path / "Evidence/v1/datasets/public/manifest.json"
    data.parent.mkdir(parents=True)
    data.write_text("{}")
    runtime = LinuxRuntime(tmp_path, sys.executable, tmp_path / "Evidence/v1/runtime")
    row = SimpleNamespace(id="job-001",tenant="alpha",name="owned-job",
                          workflow_name="owned-job-ft",method="lora")
    artifact = SimpleNamespace(id="base-001",model_type="llm",source="Qwen/base",
        revision="abcdef01",artifact_uri=weight.as_uri(),digest=hashlib.sha256(weight.read_bytes()).hexdigest())
    dataset = SimpleNamespace(id="data-001",uri=data.as_uri(),digest=hashlib.sha256(data.read_bytes()).hexdigest())
    return runtime,row,artifact,dataset

def test_native_recipe_binds_owned_inputs_and_global_run_id(tmp_path):
    runtime,row,artifact,dataset = setup(tmp_path)
    config = runtime.build_training_config(row,artifact,dataset,
        {"framework":"transformers","steps":32,"seed":9101,"batch_size":2,"lora_rank":8,"lora_alpha":16,"lr":0.00001})
    assert config["run_id"] == "job-001"
    assert config["base_sha256"] == artifact.digest
    assert config["dataset_sha256"] == dataset.digest
    assert config["method"] == "lora"
    assert Path(config["output"]).is_relative_to(tmp_path / "Evidence/v1/runtime/alpha")
    assert runtime.training_contract(row,artifact,dataset,{})["kind"] == "ModelOpsTrainingRun"

from pathlib import Path

def test_cross_tenant_model_file_is_rejected_before_loading(tmp_path):
    runtime,row,artifact,dataset = setup(tmp_path)
    foreign = tmp_path / "Evidence/v1/runtime/beta/model.safetensors"
    foreign.parent.mkdir(parents=True)
    foreign.write_bytes(b"private-unit-fixture")
    artifact.artifact_uri = foreign.as_uri()
    with pytest.raises(RuntimeFailure):
        runtime.build_training_config(row,artifact,dataset,{"framework":"transformers","steps":32})

def test_checkpoint_drift_is_rejected(tmp_path):
    runtime,row,artifact,dataset = setup(tmp_path)
    artifact.digest = "0" * 64
    with pytest.raises(RuntimeFailure):
        runtime.build_training_config(row,artifact,dataset,{"framework":"transformers","steps":32})

def test_native_backend_does_not_claim_kubernetes(tmp_path):
    runtime,_,_,_ = setup(tmp_path)
    assert runtime.kind == "linux"

def test_native_full_method_is_not_silently_replaced_with_lora(tmp_path):
    runtime,row,artifact,dataset=setup(tmp_path)
    row.method="full"
    with pytest.raises(RuntimeFailure,match="method"):
        runtime.build_training_config(row,artifact,dataset,{"framework":"transformers","steps":32})
