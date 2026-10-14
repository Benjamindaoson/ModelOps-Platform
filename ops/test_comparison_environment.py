import os
import shutil
from ops.run_model_comparison import comparison_environment

def test_official_benchmark_finds_cli_in_the_selected_gpu_environment(tmp_path,monkeypatch):
    cli=tmp_path/".gpu-venv/bin/vllm";cli.parent.mkdir(parents=True);cli.write_text("#!/bin/sh\nexit 0\n");cli.chmod(0o755)
    monkeypatch.setenv("PATH","/usr/bin")
    env=comparison_environment(tmp_path,tmp_path/"model","unit-id","a"*64)
    assert shutil.which("vllm",path=env["PATH"])==str(cli)
    assert env["SERVING_HOST"]=="127.0.0.1"

def test_inference_child_does_not_inherit_provider_credentials(tmp_path,monkeypatch):
    monkeypatch.setenv("UNIT_PROVIDER_API_KEY","unit-fixture")
    env=comparison_environment(tmp_path,tmp_path/"model","unit-id","a"*64)
    assert "UNIT_PROVIDER_API_KEY" not in env
