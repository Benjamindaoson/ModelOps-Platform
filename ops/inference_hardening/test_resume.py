import json
from pathlib import Path
from .resume import valid_receipt
from .contracts import digest
def test_resume_verifies_gpu_and_requests_hashes(tmp_path):
    raw=tmp_path/"requests.jsonl";raw.write_text("{}\n")
    gpu=tmp_path/"gpu.json";gpu.write_text("[]")
    body={"status":"PASS","raw_sha":digest(raw),"gpu_sha":digest(gpu),"source_sha":"src","protocol_sha":"protocol"}
    assert valid_receipt(body,tmp_path,"src","protocol")
    gpu.write_text("[1]")
    assert not valid_receipt(body,tmp_path,"src","protocol")
def test_resume_missing_partial_or_wrong_identity_rejected(tmp_path):
    assert not valid_receipt({"status":"RUNNING"},tmp_path,"s","p")
