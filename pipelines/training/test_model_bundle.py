import json, hashlib
from pathlib import Path
import pytest
from pipelines.training import data_contract as d

def verify(root,expected):
    fn=getattr(d,"verify_model_bundle",None)
    assert fn is not None, "Sharded frozen model verification missing"
    return fn(root,expected)

def bundle(root):
    files=[]
    for name,data in [("model-1.safetensors",b"part1"),("model-2.safetensors",b"part2"),("config.json",b"{}")]:
        (root/name).write_bytes(data);files.append({"name":name,"sha256":d.sha256(root/name),"bytes":len(data)})
    p=root/"modelops-files.json";p.write_text(json.dumps({"files":files}))
    return d.sha256(p)

def test_all_weight_shards_verified(tmp_path):
    sha=bundle(tmp_path)
    verify(tmp_path,sha)
    (tmp_path/"model-2.safetensors").write_bytes(b"changed")
    with pytest.raises(ValueError,match="changed"):
        verify(tmp_path,sha)

def test_missing_second_weight_shard_rejected(tmp_path):
    sha=bundle(tmp_path);(tmp_path/"model-2.safetensors").unlink()
    with pytest.raises(ValueError):
        verify(tmp_path,sha)

def test_single_weight_backward_compatibility(tmp_path):
    p=tmp_path/"model.safetensors";p.write_bytes(b"legacy")
    verify(tmp_path,d.sha256(p))
    with pytest.raises(ValueError):verify(tmp_path,"0"*64)

def test_bundle_cannot_escape_root(tmp_path):
    p=tmp_path/"modelops-files.json"
    p.write_text(json.dumps({"files":[{"name":"../outside","sha256":"0"*64,"bytes":1}]}))
    with pytest.raises(ValueError):verify(tmp_path,d.sha256(p))
