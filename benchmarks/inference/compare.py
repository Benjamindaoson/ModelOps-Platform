#!/usr/bin/env python3
"""Check measurement integrity and fair workload parity before A/B reporting.

Reports actual vLLM result JSON, never fabricated performance observations.
Results may still be confounded by hidden engine/hardware differences: a
matching manifest is necessary, not sufficient, for causal claims.
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path


class ComparisonError(ValueError):
    pass


def _number(value, name: str, *, positive: bool = False) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ComparisonError(f"{name}: missing numeric measurement")
    if not math.isfinite(value) or (positive and value <= 0) or value < 0:
        raise ComparisonError(f"{name}: nonfinite/invalid measurement")
    return float(value)


def load_run(folder: Path) -> tuple[dict, dict]:
    try:
        manifest=json.loads((folder/"manifest.json").read_text())
        status=json.loads((folder/"status.json").read_text())
        raw=json.loads((folder/"raw-benchmark.json").read_text())
    except (OSError, ValueError) as exc:
        raise ComparisonError(f"missing or invalid benchmark evidence in {folder}") from exc
    if not isinstance(raw,dict) or not isinstance(manifest,dict):
        raise ComparisonError("invalid evidence schema")
    if status.get("status") != "PASS":
        raise ComparisonError("benchmark must pass real request and SLO checks")
    if (status.get("measurements_valid") is not True
        or status.get("tool_exit_code") != 0
        or status.get("benchmark_timed_out") is not False
        or status.get("raw_results_exist") is not True):
        raise ComparisonError("benchmark status lacks verified process and measurement evidence")
    wanted=manifest.get("prompts")
    if not isinstance(wanted,int) or wanted<1 or raw.get("completed")!=wanted:
        raise ComparisonError("incomplete requests: all scheduled prompts must succeed for comparison")
    if raw.get("failed",0) != 0:
        raise ComparisonError("benchmark reported failed requests")
    if (status.get("successful_requests") != wanted
        or status.get("failed_requests") != 0
        or status.get("observed_success_rate") != 1.0):
        raise ComparisonError("status and raw requests disagree")
    _number(raw.get("duration"),"duration",positive=True)
    _number(raw.get("request_throughput"),"request_throughput",positive=True)
    _number(raw.get("output_throughput"),"output_throughput",positive=True)
    if manifest.get("backend")!="openai-embeddings":
        for k in ("p95_ttft_ms","p95_tpot_ms","p95_e2el_ms"):
            _number(raw.get(k),k)
    return manifest,raw


def parity(left: dict, right: dict) -> None:
    # Deliberately strict: different declared model alias/hardware/seed/lengths
    # means the result is not comparable. Server settings are the independent
    # variable and must be documented in each run's external deployment config.
    for k in ("model","backend","dataset","prompts","concurrency",
              "request_rate_per_sec","input_len_tokens","output_len_tokens","seed"):
        if left.get(k) != right.get(k):
            raise ComparisonError(f"workload parity failure: {k}")
    if not left.get("gpu_snapshot") or left.get("gpu_snapshot")!=right.get("gpu_snapshot"):
        raise ComparisonError("GPU metadata absent or inconsistent across runs")
    if left.get("git_sha")!=right.get("git_sha"):
        raise ComparisonError("different benchmark runner commits")


def compare(left_folder: Path, right_folder: Path) -> dict:
    lm,lr=load_run(left_folder)
    rm,rr=load_run(right_folder)
    parity(lm,rm)
    metrics=["request_throughput","output_throughput"]
    if lm["backend"]!="openai-embeddings":
        metrics.extend(["p50_ttft_ms","p95_ttft_ms","p99_ttft_ms",
                        "p50_tpot_ms","p95_tpot_ms","p99_tpot_ms",
                        "p50_e2el_ms","p95_e2el_ms","p99_e2el_ms"])
    else:
        metrics.extend(["p50_e2el_ms","p95_e2el_ms","p99_e2el_ms"])
    observations={}
    for k in metrics:
        old=_number(lr.get(k),k,positive=True)
        new=_number(rr.get(k),k,positive=True)
        change=(new/old-1)*100.0
        good=(k in ("request_throughput","output_throughput"))
        observations[k]={"baseline":old,"candidate":new,"change_pct":change,
                         "improvement_pct":change if good else -change}
    return {"schema":"modelops.ab.v1","evidence":"real_benchmark_runs_only",
            "baseline":str(left_folder),"candidate":str(right_folder),
            "model":lm["model"],"backend":lm["backend"],
            "hardware":lm["gpu_snapshot"],"metrics":observations,
            "limitations":"Same benchmark runner, workload and GPU fingerprint. "
                          "Server settings and model files still need separate verification; "
                          "single-run differences are not statistically significant."}


def render_markdown(report: dict) -> str:
    rows=["# ModelOps inference A/B comparison","",
          "Engine performance from actual server requests; higher improvement_pct means better.",
          "",
          "| Metric | Baseline | Candidate | Improvement |","|---|---:|---:|---:|"]
    for k,v in report["metrics"].items():
        rows.append(f"| {k} | {v['baseline']:.3f} | {v['candidate']:.3f} | {v['improvement_pct']:+.2f}% |")
    rows.extend(["","**Limitations:** "+report["limitations"],""])
    return "\n".join(rows)


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--baseline",type=Path,required=True)
    p.add_argument("--candidate",type=Path,required=True)
    p.add_argument("--output",type=Path,required=True)
    a=p.parse_args(argv)
    try:
        report=compare(a.baseline,a.candidate)
        a.output.parent.mkdir(parents=True,exist_ok=True)
        a.output.write_text(json.dumps(report,indent=2)+"\n")
        a.output.with_suffix(".md").write_text(render_markdown(report))
        print(json.dumps({"status":"COMPARED","metrics":len(report["metrics"])}))
        return 0
    except (ComparisonError,OSError) as exc:
        print(f"ModelOps comparison blocked: {exc}",file=sys.stderr)
        return 1


if __name__=="__main__":
    raise SystemExit(main())
