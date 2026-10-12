import hashlib
import json
from pathlib import Path
import pytest

from loader import ModelLoadError, load, sha256_checkpoint, check_source

REVISION = "a"*40

def sample_model(target: Path):
    target.mkdir(parents=True, exist_ok=True)
    (target / "config.json").write_text('{"model_type":"test"}')
    (target / "model.safetensors").write_bytes(b"synthetic contract-test bytes")
    return sha256_checkpoint(target)

def test_real_files_get_hashed_and_cache_reused(tmp_path):
    source = tmp_path / "fixture"
    checksum = sample_model(source)
    calls=[]
    def copy(_, revision, directory):
        calls.append(revision)
        import shutil
        shutil.copytree(source, directory, dirs_exist_ok=True)
    root = tmp_path / "models"
    first = load("Qwen/SmallModel", REVISION, checksum, "Qwen--SmallModel", root, hf_fetch=copy)
    assert first["status"]=="MODEL_VERIFIED"
    assert calls==[REVISION]
    second = load("Qwen/SmallModel", REVISION, checksum, "Qwen--SmallModel", root, hf_fetch=copy)
    assert second["status"]=="CACHE_VERIFIED"
    assert len(calls)==1
    assert (root/"Qwen--SmallModel/.modelops-provenance.json").exists()

def test_tampered_cache_never_serves(tmp_path):
    source = tmp_path/"source"
    checksum = sample_model(source)
    def fetch(_, __, where):
        import shutil
        shutil.copytree(source, where, dirs_exist_ok=True)
    load("Qwen/SmallModel", REVISION, checksum, "cache", tmp_path/"models", hf_fetch=fetch)
    (tmp_path/"models/cache/model.safetensors").write_bytes(b"tampered")
    with pytest.raises(ModelLoadError, match="existing model cache"):
        load("Qwen/SmallModel", REVISION, checksum, "cache", tmp_path/"models", hf_fetch=fetch)

def test_incorrect_artifact_digest_rejected(tmp_path):
    def fetch(_, __, where):
        sample_model(where)
    with pytest.raises(ModelLoadError, match="downloaded model SHA-256"):
        load("Qwen/SmallModel", REVISION, "e"*64, "model", tmp_path/"models", hf_fetch=fetch)
    assert not (tmp_path/"models/model").exists()

def test_unpinned_hf_model_rejected():
    with pytest.raises(ModelLoadError, match="40-character"):
        check_source("Qwen/SmallModel","main","a"*64,"qwen")

def test_symlink_and_traversal_forbidden(tmp_path):
    with pytest.raises(ModelLoadError):
        check_source("Qwen/SmallModel", REVISION, "a"*64, "../secret")
    root = tmp_path/"checkpoint"
    sample_model(root)
    (root/"escape").symlink_to(tmp_path/"somewhere")
    with pytest.raises(ModelLoadError, match="symlink"):
        sha256_checkpoint(root)

def test_missing_files_rejected(tmp_path):
    f = tmp_path/"empty"
    f.mkdir()
    with pytest.raises(ModelLoadError):
        sha256_checkpoint(f)
