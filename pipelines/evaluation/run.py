#!/usr/bin/env python3
"""Fail-closed held-out model evaluation and promotion gate.

Two CLI stages:
  run  --base-model LOCAL --candidate LOCAL --train-data TRAIN.json[l]
       --heldout HOLDOUT.jsonl --output report.json
  gate --report report.json --candidate LOCAL --train-data TRAIN.json[l]
       --heldout HOLDOUT.jsonl --approval approval.json

Only the run stage loads Transformers weights. The gate stage uses stdlib
only, verifies every artifact/dataset digest and enforces independent holdout
quality thresholds. No prompts, generations, API keys or weights are logged.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

SCHEMA = "modelops.heldout.v1"


class EvaluationError(ValueError):
    """Invalid data, provenance or model-quality evidence."""


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(2**20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def sha256_artifact(path: Path) -> str:
    """Hash complete model contents; include relative names, reject symlinks."""
    if path.is_file() and not path.is_symlink():
        return sha256_file(path)
    if not path.is_dir() or path.is_symlink():
        raise EvaluationError("trained artifact path missing or is a symlink")
    files = sorted(p for p in path.rglob("*") if p.is_file())
    if not files:
        raise EvaluationError("trained artifact directory is empty")
    digest = hashlib.sha256()
    for item in files:
        if item.is_symlink():
            raise EvaluationError("model artifact contains a symlink")
        rel = item.relative_to(path).as_posix().encode()
        digest.update(len(rel).to_bytes(4, "big"))
        digest.update(rel)
        digest.update(bytes.fromhex(sha256_file(item)))
    return digest.hexdigest()


def load_records(path: Path) -> list[dict]:
    if not path.is_file() or path.is_symlink():
        raise EvaluationError("data path missing or not a regular file")
    try:
        if path.suffix == ".jsonl":
            rows = [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
        elif path.suffix == ".json":
            rows = json.loads(path.read_text())
        else:
            raise EvaluationError("data must be JSON or JSONL")
    except (json.JSONDecodeError, UnicodeError) as exc:
        raise EvaluationError("invalid dataset JSON") from exc
    if not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows):
        raise EvaluationError("dataset must contain an array of records")
    return rows


def normalized_prompt(row: dict) -> str:
    prompt = row.get("prompt", row.get("instruction", ""))
    if not isinstance(prompt, str):
        raise EvaluationError("prompt/instruction must be a string")
    extra = row.get("input", "")
    if extra:
        if not isinstance(extra, str):
            raise EvaluationError("input must be a string")
        prompt = prompt + "\n" + extra
    if not prompt.strip():
        raise EvaluationError("empty prompt")
    return prompt.strip()


def prompt_digest(prompt: str) -> str:
    return hashlib.sha256(" ".join(prompt.casefold().split()).encode()).hexdigest()


def prepare_heldout(heldout: Path, train_data: Path, min_samples: int) -> tuple[list[dict], dict]:
    if heldout.resolve() == train_data.resolve():
        raise EvaluationError("heldout file and training file must differ")
    train_rows = load_records(train_data)
    train_hashes = {prompt_digest(normalized_prompt(r)) for r in train_rows}
    if not train_hashes:
        raise EvaluationError("training dataset empty: independence cannot be checked")
    rows = load_records(heldout)
    if len(rows) < min_samples:
        raise EvaluationError("insufficient independent heldout samples")
    seen = set()
    prepared = []
    for i, row in enumerate(rows):
        if row.get("split") not in ("heldout", "test", "validation"):
            raise EvaluationError("each heldout record needs an explicit heldout/test/validation split")
        prompt = normalized_prompt(row)
        reference = row.get("reference")
        if not isinstance(reference, str) or not reference.strip():
            raise EvaluationError("heldout record missing reference")
        key = prompt_digest(prompt)
        if key in seen:
            raise EvaluationError("duplicate heldout prompt")
        if key in train_hashes:
            raise EvaluationError("train/heldout prompt overlap detected")
        seen.add(key)
        prepared.append({"id": str(row.get("id", f"sample-{i}")), "prompt": prompt,
                         "reference": reference.strip(), "prompt_sha256": key})
    if len({r["id"] for r in prepared}) != len(prepared):
        raise EvaluationError("duplicate heldout IDs")
    return prepared, {"heldout_sha256": sha256_file(heldout),
                      "train_sha256": sha256_file(train_data),
                      "num_training_prompts": len(train_hashes)}


def score(reference: str, prediction: str) -> tuple[float, float]:
    """Unambiguous reproducible normalized exact match and token overlap F1.
    Neither value is a faithfulness metric or a semantic quality score.
    """
    def tokens(text: str) -> list[str]:
        return re.findall(r"\w+", text.casefold(), re.UNICODE)
    want, got = tokens(reference), tokens(prediction)
    em = float(bool(want) and want == got)
    if not want or not got:
        return em, 0.0
    from collections import Counter
    overlap = sum((Counter(want) & Counter(got)).values())
    f1 = 2 * overlap / (len(want) + len(got))
    return em, f1


def transformers_predictor(model_path: Path, max_new_tokens: int, *,
                           tokenizer_path: Path | None = None) -> Callable[[str], str]:
    try:
        import torch
        from transformers import AutoModelForCausalLM, AutoTokenizer
    except ImportError as exc:
        raise EvaluationError("real evaluation requires torch and transformers") from exc
    if not model_path.is_dir():
        raise EvaluationError("model checkpoint directory not found")
    tokenizer = AutoTokenizer.from_pretrained(str(tokenizer_path or model_path),
                                              local_files_only=True, trust_remote_code=False)
    model = AutoModelForCausalLM.from_pretrained(
        str(model_path), torch_dtype="auto", device_map="auto" if torch.cuda.is_available() else None,
        local_files_only=True, trust_remote_code=False,
    )
    model.eval()
    def predict(prompt: str) -> str:
        if getattr(tokenizer, "chat_template", None):
            ids = tokenizer.apply_chat_template(
                [{"role": "user", "content": prompt}], tokenize=True,
                add_generation_prompt=True, return_tensors="pt")
        else:
            ids = tokenizer(prompt, return_tensors="pt")["input_ids"]
        ids = ids.to(next(model.parameters()).device)
        with torch.inference_mode():
            output = model.generate(ids, max_new_tokens=max_new_tokens,
                                    do_sample=False, pad_token_id=tokenizer.eos_token_id)
        return tokenizer.decode(output[0][ids.shape[-1]:], skip_special_tokens=True)
    return predict


def calculate(rows: list[dict], base_predict: Callable[[str], str],
              candidate_predict: Callable[[str], str]) -> tuple[dict, list[dict]]:
    per_sample = []
    sums = {"base_exact_match": 0., "base_token_f1": 0.,
            "candidate_exact_match": 0., "candidate_token_f1": 0.}
    for row in rows:
        # A missing/failed generation is a hard error, never a quietly skipped sample.
        try:
            baseline = base_predict(row["prompt"])
            candidate = candidate_predict(row["prompt"])
        except Exception as exc:
            raise EvaluationError("model generation failed; refusing quality PASS") from exc
        if not isinstance(baseline, str) or not isinstance(candidate, str):
            raise EvaluationError("model predictor must return text")
        be, bf = score(row["reference"], baseline)
        ce, cf = score(row["reference"], candidate)
        sums["base_exact_match"] += be
        sums["base_token_f1"] += bf
        sums["candidate_exact_match"] += ce
        sums["candidate_token_f1"] += cf
        per_sample.append({"id": row["id"], "prompt_sha256": row["prompt_sha256"],
                           "baseline_em": be, "candidate_em": ce,
                           "baseline_f1": bf, "candidate_f1": cf})
    n = len(rows)
    metrics = {key: value/n for key, value in sums.items()}
    metrics["delta_token_f1"] = metrics["candidate_token_f1"] - metrics["base_token_f1"]
    metrics["delta_exact_match"] = metrics["candidate_exact_match"] - metrics["base_exact_match"]
    return metrics, per_sample


def evaluate(heldout: Path, train_data: Path, base_model: Path,
             candidate: Path, output: Path, min_samples: int, max_new_tokens: int,
             predictor_factory: Callable[[Path, int], Callable[[str], str]] = transformers_predictor) -> dict:
    if min_samples < 1 or max_new_tokens < 1:
        raise EvaluationError("invalid sample or token budget")
    rows, provenance = prepare_heldout(heldout, train_data, min_samples)
    artifact_sha = sha256_artifact(candidate)
    # Base and candidate are evaluated under the same tokenizer and decoding
    # settings; they are loaded one at a time to reduce GPU peak memory.
    base_predictor = predictor_factory(base_model, max_new_tokens)
    base_outputs = []
    for row in rows:
        try:
            base_outputs.append(base_predictor(row["prompt"]))
        except Exception as exc:
            raise EvaluationError("baseline inference failed") from exc
    del base_predictor
    try:
        import gc
        gc.collect()
        import torch
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
    except ImportError:
        pass
    candidate_predictor = predictor_factory(candidate, max_new_tokens)
    by_index = {i: base_outputs[i] for i in range(len(rows))}
    counter = iter(range(len(rows)))
    metrics, details = calculate(rows, lambda _prompt: by_index[next(counter)],
                                 candidate_predictor)
    report = {
        "schema": SCHEMA, "proof_type": "real_checkpoint_holdout",
        "evaluated_at_utc": datetime.now(timezone.utc).isoformat(),
        "base_model_path": str(base_model), "candidate_path": str(candidate),
        "artifact_sha256": artifact_sha, "model_evaluator": "transformers_greedy",
        "max_new_tokens": max_new_tokens, "num_samples": len(rows),
        "generation_success_rate": 1.0, "train_overlap_count": 0,
        **provenance, "metrics": metrics, "samples": details,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    # Checkpoints and heldout data are intentionally not included in report.
    output.write_text(json.dumps(report, indent=2, sort_keys=True)+"\n")
    return report


def quality_gate(report_path: Path, candidate: Path, heldout: Path, train_data: Path,
                 approval: Path, min_samples: int, min_f1: float,
                 min_delta: float) -> dict:
    """Recompute hashes and verify structural evidence before authorizing deploy."""
    if approval.exists():
        approval.unlink()
    try:
        report = json.loads(report_path.read_text())
    except (OSError, ValueError) as exc:
        raise EvaluationError("quality report is unavailable or invalid") from exc
    if report.get("schema") != SCHEMA or report.get("proof_type") != "real_checkpoint_holdout":
        raise EvaluationError("untrusted evaluation report schema or proof type")
    n = report.get("num_samples")
    samples = report.get("samples")
    if not isinstance(n, int) or n < min_samples or not isinstance(samples, list) or len(samples) != n:
        raise EvaluationError("incomplete heldout evaluation evidence")
    if report.get("train_overlap_count") != 0 or report.get("generation_success_rate") != 1.0:
        raise EvaluationError("overlap or failed generations")
    rows, provenance = prepare_heldout(heldout, train_data, min_samples)
    if len(rows) != n or any(a["prompt_sha256"] != b.get("prompt_sha256")
                             or a["id"] != b.get("id") for a,b in zip(rows,samples)):
        raise EvaluationError("heldout sample evidence mismatch")
    for k,v in provenance.items():
        if report.get(k) != v:
            raise EvaluationError(f"dataset provenance mismatch: {k}")
    if report.get("artifact_sha256") != sha256_artifact(candidate):
        raise EvaluationError("artifact bytes changed after evaluation")
    metrics = report.get("metrics")
    if not isinstance(metrics, dict):
        raise EvaluationError("metrics missing")
    required = ("base_token_f1", "candidate_token_f1", "base_exact_match",
                "candidate_exact_match", "delta_token_f1", "delta_exact_match")
    if any(not isinstance(metrics.get(k), (int,float)) or
           not math.isfinite(metrics[k]) for k in required):
        raise EvaluationError("non-finite or missing model metrics")
    if any(not (0. <= metrics[k] <= 1.) for k in required[:4]):
        raise EvaluationError("invalid metric range")
    if any(not math.isclose(metrics[k], sum(s[metric] for s in samples) / n, abs_tol=1e-8)
           for k,metric in (("base_token_f1","baseline_f1"),
                            ("candidate_token_f1","candidate_f1"),
                            ("base_exact_match","baseline_em"),
                            ("candidate_exact_match","candidate_em"))):
        raise EvaluationError("reported metrics do not match per-sample scores")
    if not math.isclose(metrics["delta_token_f1"],
                        metrics["candidate_token_f1"]-metrics["base_token_f1"], abs_tol=1e-8):
        raise EvaluationError("candidate delta does not match baseline")
    if not (metrics["candidate_token_f1"] >= min_f1 and
            metrics["delta_token_f1"] >= min_delta):
        raise EvaluationError("candidate is below absolute or non-regression quality gate")
    approval_record = {
        "gate_schema": "modelops.approval.v1", "report_sha256": sha256_file(report_path),
        "artifact_sha256": report["artifact_sha256"], "heldout_sha256": report["heldout_sha256"],
        "approved_at_utc": datetime.now(timezone.utc).isoformat(),
        "min_samples": min_samples, "min_token_f1": min_f1, "min_delta_token_f1": min_delta,
    }
    approval.parent.mkdir(parents=True, exist_ok=True)
    approval.write_text(json.dumps(approval_record, indent=2)+"\n")
    return approval_record


def cli(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)
    for action in ("run","gate","check-data"):
        p = sub.add_parser(action)
        if action != "check-data":
            p.add_argument("--candidate", type=Path, required=True)
        p.add_argument("--train-data", type=Path, required=True)
        p.add_argument("--heldout", type=Path, required=True)
        p.add_argument("--min-samples", type=int, default=20)
        if action == "run":
            p.add_argument("--base-model", type=Path, required=True)
            p.add_argument("--output", type=Path, required=True)
            p.add_argument("--max-new-tokens", type=int, default=128)
        else:
            p.add_argument("--report", type=Path, required=True)
            p.add_argument("--approval", type=Path, required=True)
            p.add_argument("--min-f1", type=float, default=0.55)
            p.add_argument("--min-delta", type=float, default=-0.02)
    args = parser.parse_args(argv)
    try:
        if args.cmd == "check-data":
            records, data = prepare_heldout(args.heldout,args.train_data,args.min_samples)
            print(json.dumps({"status":"DATASET_VALIDATED","heldout_samples":len(records),
                              "train_prompts":data["num_training_prompts"],
                              "heldout_sha256":data["heldout_sha256"]}))
        elif args.cmd == "run":
            r = evaluate(args.heldout, args.train_data, args.base_model, args.candidate,
                         args.output, args.min_samples, args.max_new_tokens)
            print(json.dumps({"status":"EVALUATED_NOT_APPROVED","samples":r["num_samples"],
                              "metrics":r["metrics"]}))
        else:
            r = quality_gate(args.report, args.candidate, args.heldout, args.train_data,
                             args.approval, args.min_samples, args.min_f1, args.min_delta)
            print(json.dumps({"status":"APPROVED","report_sha256":r["report_sha256"]}))
        return 0
    except (EvaluationError, OSError, KeyError, TypeError) as exc:
        print(f"ModelOps evaluation blocked: {exc}",file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(cli())
