import json
from pathlib import Path
import pytest

def check(result,root):
    import importlib
    try:m=importlib.import_module("ops.mlflow_validation")
    except ModuleNotFoundError:m=None
    assert m is not None, "MLflow completed-artifact integrity gate missing"
    return m.verified_training_artifacts(result,root)

def test_failed_run_never_registered(tmp_path):
    with pytest.raises(ValueError):
        check({"status":"FAILED"},tmp_path)

def test_changed_adapter_never_registered(tmp_path):
    from pipelines.training.data_contract import sha256
    ad=tmp_path/"runtime/lab/test/adapter-latest";ad.mkdir(parents=True)
    cp=tmp_path/"runtime/lab/test/model.safetensors";cp.write_bytes(b"checkpoint-contract-fixture")
    a=ad/"adapter_model.safetensors";a.write_bytes(b"adapter-contract-fixture")
    result={"status":"COMPLETED","run_id":"test","steps":1,"parameter_delta_linf":0.1,"adapter":str(ad),"adapter_sha256":sha256(a),"checkpoint":str(cp),"checkpoint_sha256":sha256(cp)}
    check(result,tmp_path)
    a.write_bytes(b"corruption")
    with pytest.raises(ValueError):check(result,tmp_path)

def test_foreign_checkpoint_never_registered(tmp_path):
    with pytest.raises(ValueError):
        check({"status":"COMPLETED","run_id":"test","steps":1,"parameter_delta_linf":0.1,"adapter":"/foreign","checkpoint":"/foreign"},tmp_path)
