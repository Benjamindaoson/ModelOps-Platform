#!/usr/bin/env python3
"""Generate per-Workflow LLaMA-Factory YAML; never reuse global train_config.yaml.

Each Argo Workflow owns its isolated workspace and full parameter manifest.
This step does not itself invoke training, so CPU tests can inspect exact configs.
"""
from __future__ import annotations

import json
import os
from pathlib import Path


class TrainingConfigError(ValueError):
    pass


def config_from_env(env: dict[str, str]) -> dict:
    method = env["MODELOPS_METHOD"]
    if method not in {"lora", "qlora", "full"}:
        raise TrainingConfigError("Unsupported fine-tuning method")

    def bounded_int(name, lo, hi):
        value = int(env[name])
        if not lo <= value <= hi:
            raise TrainingConfigError("Invalid training parameter: " + name)
        return value

    epochs = bounded_int("MODELOPS_EPOCHS", 1, 30)
    batch = bounded_int("MODELOPS_BATCH_SIZE", 1, 256)
    rank = bounded_int("MODELOPS_LORA_RANK", 1, 256)
    alpha = bounded_int("MODELOPS_LORA_ALPHA", 1, 512)
    grad = bounded_int("MODELOPS_GRAD_ACC", 1, 256)
    gpu = bounded_int("MODELOPS_GPU", 0, 16)
    lr = float(env["MODELOPS_LR"])
    if not 0 < lr <= 0.01:
        raise TrainingConfigError("Invalid learning rate")
    config = {
        "model_name_or_path": "/workspace/base-model",
        "stage": "sft", "do_train": True,
        "finetuning_type": "lora" if method == "qlora" else method,
        "dataset": "train", "dataset_dir": "/workspace/data",
        "template": "default",
        "output_dir": "/workspace/output",
        "overwrite_output_dir": False,
        "per_device_train_batch_size": batch,
        "gradient_accumulation_steps": grad,
        "learning_rate": lr, "num_train_epochs": epochs,
        "lr_scheduler_type": "cosine",
        "warmup_ratio": 0.03,
        "save_steps": 100, "logging_steps": 10,
        "report_to": "none",
        "cutoff_len": 2048,
    }
    if gpu > 0:
        # Runtime will fail if CUDA is unavailable; no CPU fallback labeled GPU.
        config["bf16"] = True
        config["gradient_checkpointing"] = True
    else:
        config.update({"bf16": False, "fp16": False})
    if method in ("lora", "qlora"):
        config.update({"lora_rank": rank, "lora_alpha": alpha, "lora_target": "all"})
    if method == "qlora":
        config.update({"quantization_bit": 4, "quantization_method": "bitsandbytes"})
    return config


def main():
    import yaml
    cfg = config_from_env(dict(os.environ))
    folder = Path("/workspace")
    (folder / "training").mkdir(parents=True, exist_ok=True)
    (folder / "train_config.yaml").write_text(yaml.safe_dump(cfg, sort_keys=True))
    (folder / "training" / "parameters.json").write_text(json.dumps({
        "method": os.environ["MODELOPS_METHOD"],
        "epochs": cfg["num_train_epochs"], "batch_size": cfg["per_device_train_batch_size"],
        "grad_acc": cfg["gradient_accumulation_steps"],
        "lr": cfg["learning_rate"],
        "base_revision": os.environ["MODELOPS_BASE_REVISION"],
        "dataset_sha256": os.environ["MODELOPS_DATASET_SHA256"],
    }, sort_keys=True, indent=2) + "\n")
    print("ModelOps train_config.yaml created; only a subsequent llamafactory-cli invocation trains the model.")


if __name__ == "__main__":
    main()
