#!/usr/bin/env python3
"""Reproducible real-endpoint inference benchmark wrapper.

Delegates requests and measurements to the official vllm bench serve CLI.
Never fabricates latency numbers or stores API secrets in manifests.
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import re
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--base-url", required=True, help="HTTP(S) origin of an OpenAI-compatible server")
    p.add_argument("--model", required=True, help="Served model identifier")
    p.add_argument("--backend", choices=("openai-chat", "openai", "openai-embeddings"), default="openai-chat")
    p.add_argument("--prompts", type=int, default=40)
    p.add_argument("--concurrency", type=int, default=4)
    p.add_argument("--request-rate", type=float, default=4.0)
    p.add_argument("--input-len", type=int, default=512)
    p.add_argument("--output-len", type=int, default=128)
    p.add_argument("--warmups", type=int, default=2)
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--run-id", default=None)
    p.add_argument("--output-root", type=Path, default=Path("benchmarks/results"))
    p.add_argument("--dry-run", action="store_true", help="Print command without invoking a server")
    return p.parse_args(argv)


def validate(a: argparse.Namespace) -> None:
    url = urlparse(a.base_url)
    if (
        url.scheme not in ("http", "https")
        or not url.netloc
        or url.username
        or url.password
        or url.query
        or url.fragment
        or url.path not in ("", "/")
    ):
        raise ValueError("--base-url must be an HTTP(S) origin without credentials, path or query")
    if not a.model.strip():
        raise ValueError("--model must not be empty")
    if a.prompts < 1 or a.concurrency < 1 or a.request_rate <= 0:
        raise ValueError("prompts/concurrency/request-rate must be positive")
    if a.input_len < 1 or a.output_len < 1 or a.warmups < 0:
        raise ValueError("input/output lengths must be positive and warmups nonnegative")
    if a.run_id and not re.fullmatch(r"[A-Za-z0-9_.-]{1,80}", a.run_id):
        raise ValueError("--run-id may contain only ASCII letters, digits, dot, dash, underscore")
    if a.backend == "openai-embeddings" and a.output_len != 128:
        raise ValueError("--output-len has no meaning for embedding benchmarks")


def build_command(a: argparse.Namespace, result_dir: Path) -> list[str]:
    endpoints = {
        "openai-chat": "/v1/chat/completions",
        "openai": "/v1/completions",
        "openai-embeddings": "/v1/embeddings",
    }
    cmd = [
        "vllm", "bench", "serve", "--backend", a.backend,
        "--base-url", a.base_url.rstrip("/"), "--endpoint", endpoints[a.backend],
        "--model", a.model, "--dataset-name", "random",
        "--num-prompts", str(a.prompts), "--max-concurrency", str(a.concurrency),
        "--request-rate", str(a.request_rate), "--input-len", str(a.input_len),
        "--num-warmups", str(a.warmups), "--seed", str(a.seed),
        "--save-result", "--result-dir", str(result_dir),
        "--result-filename", "raw-benchmark.json",
        "--metric-percentiles", "50,95,99",
    ]
    if a.backend != "openai-embeddings":
        cmd += ["--output-len", str(a.output_len), "--percentile-metrics", "ttft,tpot,itl,e2el"]
    else:
        cmd += ["--percentile-metrics", "e2el"]
    return cmd


def _capture(cmd: list[str]) -> str | None:
    if shutil.which(cmd[0]) is None:
        return None
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=6, check=False)
        return (result.stdout or result.stderr).strip()[:2500] or None
    except (OSError, subprocess.TimeoutExpired):
        return None


def metadata(a: argparse.Namespace, cmd: list[str]) -> dict:
    return {
        "schema_version": "1.0",
        "record_type": "planned_or_executed_benchmark",
        "utc": datetime.now(timezone.utc).isoformat(),
        "model": a.model,
        "backend": a.backend,
        "base_url": a.base_url.rstrip("/"),
        "dataset": "random_synthetic_smoke_not_business_distribution",
        "prompts": a.prompts,
        "concurrency": a.concurrency,
        "request_rate_per_sec": a.request_rate,
        "input_len_tokens": a.input_len,
        "output_len_tokens": None if a.backend == "openai-embeddings" else a.output_len,
        "seed": a.seed,
        "python": platform.python_version(),
        "os": platform.platform(),
        "git_sha": os.getenv("GITHUB_SHA") or _capture(["git", "rev-parse", "HEAD"]),
        "gpu_snapshot": _capture(["nvidia-smi", "--query-gpu=name,memory.total,driver_version", "--format=csv,noheader"]),
        "command": cmd,
        "note": "GPU snapshot is metadata only: not peak VRAM. Results are produced exclusively by the real serving endpoint.",
    }


def main(argv: list[str] | None = None) -> int:
    a = parse_args(argv)
    try:
        validate(a)
    except ValueError as exc:
        print(f"Invalid benchmark configuration: {exc}", file=sys.stderr)
        return 2
    run_id = a.run_id or datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    result_dir = a.output_root / run_id
    cmd = build_command(a, result_dir)
    if a.dry_run:
        print(json.dumps({"dry_run": True, "command": cmd}, indent=2))
        return 0
    if not shutil.which("vllm"):
        print("The vllm CLI must be installed to run a real benchmark; use --dry-run to validate configuration.", file=sys.stderr)
        return 3
    result_dir.mkdir(parents=True, exist_ok=False)
    manifest = metadata(a, cmd)
    (result_dir / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(f"Real benchmark starting; evidence directory: {result_dir}")
    with (result_dir / "vllm-bench.log").open("w", encoding="utf-8") as log:
        completed = subprocess.run(cmd, stdout=log, stderr=subprocess.STDOUT, check=False)
    result_file = result_dir / "raw-benchmark.json"
    passed = completed.returncode == 0 and result_file.is_file() and result_file.stat().st_size > 0
    outcome = {
        "tool_exit_code": completed.returncode,
        "raw_results_exist": result_file.is_file() and result_file.stat().st_size > 0,
        "status": "PASS" if passed else "FAIL",
    }
    (result_dir / "status.json").write_text(json.dumps(outcome, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(outcome, indent=2))
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
