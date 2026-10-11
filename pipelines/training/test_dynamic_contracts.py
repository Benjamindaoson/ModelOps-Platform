"""CPU-only deterministic validation of real dynamic train/data/publish contracts."""
import hashlib
import json
import os
import sys
import tempfile
from pathlib import Path
import pytest

from prepare_dynamic import PreparationError, verify_dataset
from train_dynamic import TrainingConfigError, config_from_env
from publish_dynamic import PublicationError, publication_contract


def params(method="qlora"):
    return {
        "MODELOPS_METHOD": method, "MODELOPS_EPOCHS": "3",
        "MODELOPS_BATCH_SIZE": "1", "MODELOPS_LORA_RANK": "8",
        "MODELOPS_LORA_ALPHA": "16", "MODELOPS_GRAD_ACC": "4",
        "MODELOPS_GPU": "1", "MODELOPS_LR": "0.0002",
        "MODELOPS_BASE_REVISION": "abc123456789",
        "MODELOPS_DATASET_SHA256": "a"*64,
    }


def test_qlora_is_lora_on_4_bit_and_per_run():
    got = config_from_env(params())
    assert got["finetuning_type"] == "lora"
    assert got["quantization_bit"] == 4
    assert got["quantization_method"] == "bitsandbytes"


def test_full_has_no_adapter_or_quantization_config():
    got = config_from_env(params("full"))
    assert got["finetuning_type"] == "full"
    assert "lora_rank" not in got and "quantization_bit" not in got


def test_job_specific_settings_are_not_global():
    one = config_from_env(params())
    changed = params()
    changed["MODELOPS_EPOCHS"] = "7"
    two = config_from_env(changed)
    assert one["num_train_epochs"] == 3 and two["num_train_epochs"] == 7


def test_unsafe_params_rejected():
    d = params(); d["MODELOPS_GPU"] = "18"
    with pytest.raises(TrainingConfigError): config_from_env(d)
    d = params(); d["MODELOPS_LR"] = "0"
    with pytest.raises(TrainingConfigError): config_from_env(d)


def test_dataset_manifest_binds_both_train_and_heldout(tmp_path):
    train = tmp_path/"train.json"
    heldout = tmp_path/"heldout.jsonl"
    train.write_text(json.dumps([{"instruction": "hello", "output": "world"}]))
    heldout.write_text("\n".join(json.dumps({"prompt": "test " + str(i), "reference": "world",
                    "split": "heldout"}) for i in range(20)) + "\n")
    digests = {item.name: hashlib.sha256(item.read_bytes()).hexdigest() for item in (train,heldout)}
    manifest = tmp_path/"dataset_manifest.json"
    manifest.write_text(json.dumps({"files": digests}))
    manifest_hash = hashlib.sha256(manifest.read_bytes()).hexdigest()
    actual = verify_dataset(tmp_path, manifest_hash)
    assert actual["train_rows"] == 1 and actual["heldout_rows"] == 20
    heldout.write_text(heldout.read_text()+"tampered\n")
    with pytest.raises(PreparationError): verify_dataset(tmp_path, manifest_hash)


def test_publication_gate_rejects_artifact_mutation():
    with pytest.raises(PublicationError):
        publication_contract({"schema":"modelops.heldout.v1","artifact_sha256":"a"},
                             {"report_sha256":"x","artifact_sha256":"b"}, "a")
