#!/usr/bin/env python3
"""Produce a real, loadable fine-tuned checkpoint for promotion.

LoRA/QLoRA: merge adapter into the original full-precision base on CPU
using PEFT. Full fine-tuning: validate and atomically copy checkpoint.
Outputs a model directory and a receipt; never claims a merge happened
unless weight/config files were actually produced.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path


class MergeError(ValueError):
    pass


def _weight_files(path: Path) -> list[Path]:
    return sorted([p for p in path.rglob("*")
                   if p.is_file() and p.suffix in (".safetensors", ".bin")
                   and ("model" in p.name or "adapter" in p.name)])


def verify_checkpoint(path: Path, *, adapter: bool = False) -> None:
    if not path.is_dir() or path.is_symlink():
        raise MergeError("checkpoint directory missing")
    config = "adapter_config.json" if adapter else "config.json"
    if not (path / config).is_file() or not _weight_files(path):
        raise MergeError(f"checkpoint missing {config} or weight files")
    if any(p.is_symlink() for p in path.rglob("*")):
        raise MergeError("checkpoint contains a symlink")


def merge_checkpoint(base: Path, trained: Path, output: Path,
                     method: str) -> dict:
    if method not in ("full", "lora", "qlora"):
        raise MergeError("method must be full, lora or qlora")
    if base.resolve() == output.resolve() or trained.resolve() == output.resolve():
        raise MergeError("output must differ from source checkpoints")
    if output.exists():
        raise MergeError("output already exists, refusing to overwrite")
    verify_checkpoint(trained, adapter=method != "full")
    if method != "full":
        verify_checkpoint(base)

    output.parent.mkdir(parents=True, exist_ok=True)
    tmp = Path(tempfile.mkdtemp(prefix=".modelops-merge-", dir=str(output.parent)))
    try:
        if method == "full":
            # No adapter to merge: copy actual fine-tuned full weights.
            shutil.copytree(trained, tmp, dirs_exist_ok=True, symlinks=False)
        else:
            try:
                import torch
                from peft import PeftModel
                from transformers import AutoModelForCausalLM, AutoTokenizer
            except ImportError as exc:
                raise MergeError("install torch, transformers and peft for a real adapter merge") from exc
            # A QLoRA adapter must be merged into *unquantized* base weights;
            # merging directly into 4-bit weights is not equivalent.
            original = AutoModelForCausalLM.from_pretrained(
                str(base), local_files_only=True, trust_remote_code=False,
                torch_dtype=torch.float32, device_map="cpu",
                low_cpu_mem_usage=True,
            )
            adapter = PeftModel.from_pretrained(original, str(trained), is_trainable=False,
                                               local_files_only=True)
            merged = adapter.merge_and_unload(safe_merge=True)
            merged.save_pretrained(str(tmp), safe_serialization=True)
            tokenizer = AutoTokenizer.from_pretrained(
                str(base), trust_remote_code=False, local_files_only=True)
            tokenizer.save_pretrained(str(tmp))
        verify_checkpoint(tmp)
        # POSIX rename in same directory is atomic. Gate only accepts this output.
        tmp.rename(output)
    except Exception:
        shutil.rmtree(tmp, ignore_errors=True)
        raise
    return {"schema":"modelops.merge.v1", "method":method,
            "base":str(base), "trained":str(trained), "merged":str(output),
            "merged_at_utc":datetime.now(timezone.utc).isoformat(),
            "weight_files":len(_weight_files(output)), "completed":True}


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--base", type=Path, required=True)
    p.add_argument("--trained", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--method", choices=("lora","qlora","full"), required=True)
    p.add_argument("--receipt", type=Path, required=True)
    a=p.parse_args(argv)
    try:
        r=merge_checkpoint(a.base,a.trained,a.output,a.method)
        a.receipt.parent.mkdir(parents=True,exist_ok=True)
        a.receipt.write_text(json.dumps(r,indent=2)+"\n")
        print(json.dumps({"status":"MERGED","weight_files":r["weight_files"]}))
        return 0
    except (MergeError,OSError,RuntimeError,ValueError) as exc:
        print(f"ModelOps merge blocked: {exc}",file=sys.stderr)
        return 1


if __name__=="__main__":
    raise SystemExit(main())
