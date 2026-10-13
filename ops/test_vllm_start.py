import importlib,hashlib
import pytest

def module():
    try:m=importlib.import_module("ops.vllm_start")
    except ModuleNotFoundError:m=None
    assert m is not None, "Pinned vLLM startup contract missing"
    return m

def test_command_uses_owned_model_and_explicit_version():
    args=module().build_args({"MODEL_PATH":"/model","SERVED_MODEL_NAME":"modelops-qwen3b","MAX_MODEL_LEN":"2048"})
    assert args[args.index("--model")+1]=="/model"
    assert args[args.index("--served-model-name")+1]=="modelops-qwen3b"
    assert args[args.index("--dtype")+1]=="half"

def test_invalid_memory_budget_is_rejected():
    with pytest.raises(ValueError):module().build_args({"GPU_MEMORY_UTILIZATION":"1.2"})

def test_missing_or_changed_checkpoint_rejected(tmp_path):
    p=tmp_path/"model.safetensors";p.write_bytes(b"integrity-contract-fixture")
    env={"MODEL_PATH":str(tmp_path),"MODEL_SHA256":hashlib.sha256(p.read_bytes()).hexdigest()}
    module().verify_checkpoint(env)
    p.write_bytes(b"changed")
    with pytest.raises(ValueError):module().verify_checkpoint(env)
