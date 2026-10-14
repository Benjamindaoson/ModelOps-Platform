from pathlib import Path
import json
import pytest
from ops.gpu_runtime_validation import host_probe, validate_probe_url

def test_host_gpu_does_not_pass_missing_docker(tmp_path):
    result = host_probe(tmp_path, docker_command="definitely-missing-docker-command")
    assert result["status"] == "SKIPPED"
    assert result["checks"]["container_cuda"] is None
    assert json.loads((tmp_path/"api-response.json").read_text())["response"] is None

def test_container_probe_rejects_external_or_credential_url():
    for url in ["http://example.com:8000", "http://root:secret@127.0.0.1:8000", "file:///tmp/x"]:
        with pytest.raises(ValueError):
            validate_probe_url(url)

def test_container_probe_accepts_only_loopback_http():
    assert validate_probe_url("http://127.0.0.1:8000") == "http://127.0.0.1:8000"
