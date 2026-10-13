"""SFT input alignment and leakage gates; no GPU or model fixtures."""
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace
import pytest
from pipelines.training.data_contract import encode_sample, validate_manifest

class Tokenizer:
    eos_token_id = 10
    def apply_chat_template(self, messages, **kwargs):
        return [11, 22, 33]
    def __call__(self, text, **kwargs):
        return SimpleNamespace(input_ids=[7, 8, 9])

def test_only_assistant_tokens_are_supervised():
    row = encode_sample(Tokenizer(), {"prompt": "Hello", "reference": "world"}, 32)
    assert row["input_ids"] == [11, 22, 33, 7, 8, 9, 10]
    assert row["labels"] == [-100, -100, -100, 7, 8, 9, 10]
    assert row["attention_mask"] == [1] * 7

def manifest(tmp_path, overlap=False):
    train = [{"id": "train-1", "prompt": "Explain gravity", "reference": "A force"}]
    heldout = [{"id": f"test-{i}", "prompt": f"Question {i}", "reference": "Answer"} for i in range(20)]
    if overlap:heldout[0]["prompt"] = "  explain   GRAVITY "
    files={}
    for name,rows in [("train.jsonl",train),("heldout.jsonl",heldout)]:
        text="".join(json.dumps(x)+"\n" for x in rows)
        (tmp_path/name).write_text(text)
        files[name]=hashlib.sha256(text.encode()).hexdigest()
    body={"train_file":"train.jsonl","heldout_file":"heldout.jsonl",
          "train_sha256":files["train.jsonl"],"heldout_sha256":files["heldout.jsonl"]}
    path=tmp_path/"manifest.json"
    path.write_text(json.dumps(body))
    return path,hashlib.sha256(path.read_bytes()).hexdigest()

def test_verified_manifest_returns_independent_rows(tmp_path):
    path,sha=manifest(tmp_path)
    train,test=validate_manifest(path,sha)
    assert len(train)==1
    assert len(test)==20

def test_training_holdout_overlap_is_rejected(tmp_path):
    path,sha=manifest(tmp_path,True)
    with pytest.raises(ValueError,match="overlap"):
        validate_manifest(path,sha)

def test_modified_training_rows_are_rejected(tmp_path):
    path,sha=manifest(tmp_path)
    (tmp_path/"train.jsonl").write_text("corrupted")
    with pytest.raises(ValueError,match="hash"):
        validate_manifest(path,sha)
