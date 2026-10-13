"""Serving ownership and protocol contracts; not GPU performance tests."""
import sys
from types import SimpleNamespace
import pytest
from modelops.native_serving import NativeServing
from modelops.runtime import RuntimeFailure

def test_backend_identifies_native_serving(tmp_path):
    serving=NativeServing(tmp_path,sys.executable,tmp_path/"Evidence/v1/runtime")
    assert serving.kind=="linux"

def test_refuses_multiple_native_gpu_replicas(tmp_path):
    serving=NativeServing(tmp_path,sys.executable,tmp_path/"Evidence/v1/runtime")
    row=SimpleNamespace(tenant="alpha",id="deployment-1",replicas=2,engine="vllm")
    with pytest.raises(RuntimeFailure,match="replica"):
        serving.validate_budget(row)

def test_foreign_process_is_never_signalled(tmp_path):
    serving=NativeServing(tmp_path,sys.executable,tmp_path/"Evidence/v1/runtime")
    import os
    record={"pid":os.getpid(),"create_time":0,"command_marker":"unrelated"}
    with pytest.raises(RuntimeFailure,match="identity"):
        serving.stop_owned(record)

def test_vla_cannot_use_language_model_engine(tmp_path):
    serving=NativeServing(tmp_path,sys.executable,tmp_path/"Evidence/v1/runtime")
    row=SimpleNamespace(engine="vllm",replicas=1)
    with pytest.raises(RuntimeFailure):
        serving.validate_model_engine(row,SimpleNamespace(model_type="vla"))
