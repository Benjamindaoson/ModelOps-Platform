import hashlib
import json
from pathlib import Path
import pytest
from ops.model_release_gate.gate import decide, GatePolicy

def fixture(tmp_path):
    cp=tmp_path/"model.safetensors";cp.write_bytes(b"unit-test-weight-fixture-not-a-model")
    ap=tmp_path/"adapter_model.safetensors";ap.write_bytes(b"unit-test-adapter-fixture")
    sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
    identity={"model":"unit-model","version":1,"run_id":"run-unit","checkpoint_sha256":sha(cp),"adapter_sha256":sha(ap)}
    training={"status":"COMPLETED","mlflow_run_id":"run-unit","steps":2,"parameter_delta_linf":0.1,"checkpoint":str(cp),"adapter":str(ap.parent),"checkpoint_sha256":sha(cp),"adapter_sha256":sha(ap)}
    evaluation={"proof_type":"real_checkpoint_holdout","num_samples":24,"train_overlap_count":0,"metrics":{"candidate_token_f1":0.75,"delta_token_f1":-0.01}}
    benchmark={"model_sha256":sha(cp),"requests":384,"repeats":3,"concurrency":4,"output_tokens_s":300,"ttft_p95_ms":100,"latency_p95_ms":900}
    serving={"healthy":True,"expected_model":"unit-served-id","loaded_models":["unit-served-id"]}
    return identity,training,evaluation,benchmark,serving

def test_gate_binds_registered_version_to_actual_bytes(tmp_path):
    args=fixture(tmp_path)
    assert decide(*args)["status"]=="PASS"
    Path(args[1]["checkpoint"]).write_bytes(b"swapped")
    decision=decide(*args)
    assert decision["status"]=="FAIL" and not decision["checks"]["artifact"]

def test_healthy_wrong_model_cannot_be_released(tmp_path):
    args=fixture(tmp_path);args[4]["loaded_models"]=["different-version"]
    assert not decide(*args)["checks"]["serving"]

@pytest.mark.parametrize("value", [float("nan"),float("inf"),-1])
def test_invalid_performance_values_fail_closed(tmp_path,value):
    args=fixture(tmp_path);args[3]["output_tokens_s"]=value
    assert not decide(*args)["checks"]["benchmark"]

def test_training_run_or_benchmark_hash_mismatch_fails(tmp_path):
    args=fixture(tmp_path);args[0]["run_id"]="another-run"
    assert decide(*args)["status"]=="FAIL"
    args=fixture(tmp_path);args[3]["model_sha256"]="a"*64
    assert not decide(*args)["checks"]["benchmark"]

def test_incomplete_or_leaked_evaluation_blocks_release(tmp_path):
    args=fixture(tmp_path);args[2]["train_overlap_count"]=1
    assert not decide(*args)["checks"]["evaluation"]
    args=fixture(tmp_path);args[3]["requests"]=128
    assert not decide(*args)["checks"]["benchmark"]

def test_bad_quality_and_missing_checkpoint_fail_without_crashing(tmp_path):
    args=fixture(tmp_path);args[2]["metrics"]["delta_token_f1"]=-0.1
    assert not decide(*args)["checks"]["evaluation"]
    args=fixture(tmp_path);Path(args[1]["checkpoint"]).unlink()
    assert not decide(*args)["checks"]["artifact"]
