"""Export real, hash-checked measured trials; never substitutes fixture or invented values."""
import json, statistics
from pathlib import Path
from ops.run_model_comparison import E, ROOT
from ops.benchmark_llm_validation import read_trial
from pipelines.training.data_contract import sha256, write_json

def main():
    source=E/"comparison/progress.json";records=json.loads(source.read_text())
    if records["status"]!="PASS" or len(records["trials"])!=12:raise ValueError("Incomplete comparison")
    rows=[]
    for row in records["trials"]:
        folder=Path(row["artifact_root"]);actual=read_trial(folder)
        if actual["raw_sha256"]!=row["result"]["raw_sha256"]:raise ValueError("Evidence changed")
        identity=json.loads((folder/"identity.json").read_text())
        if identity["model_sha256"]!=records["protocol"]["model_identities"][row["model"]]:raise ValueError("Wrong model")
        rows.append({**{k:row[k] for k in ("model","repeat","concurrency","run_id","load_s")},**actual,"identity":identity})
    groups=[]
    for model in ["base","trained"]:
        for concurrency in [4,16]:
            selected=[r for r in rows if r["model"]==model and r["concurrency"]==concurrency]
            if len(selected)!=3 or {r["repeat"] for r in selected}!={0,1,2}:raise ValueError("Repeated coverage missing")
            group={"model":model,"concurrency":concurrency,"requests":sum(r["completed_requests"] for r in selected),"repeats":3}
            for label,fn in {"output_tokens_s":lambda r:r["output_tokens_per_s"],"ttft_p95_ms":lambda r:r["latency_ms"]["p95_ttft_ms"],
                             "e2e_p95_ms":lambda r:r["latency_ms"]["p95_e2el_ms"],"peak_gpu_mib":lambda r:r["gpu"]["peak_used_mib"]}.items():
                values=[fn(r) for r in selected];group[label]={"mean":statistics.mean(values),"sample_sd":statistics.stdev(values),"trials":values}
            groups.append(group)
    result={"status":"PASS","scope":"Actual native RTX3090 vLLM inference; not Docker","protocol":records["protocol"],
            "total_requests":sum(r["completed_requests"] for r in rows),"manifest_sha256":sha256(source),"groups":groups,"trials":rows,
            "limitations":["Trial percentiles averaged, not pooled request percentiles","Sequential conditions; no cross-day or hardware stability claim",
                           "Whole-GPU samples include client initialization; no task-attributed GPU cost claim","No quality improvement demonstrated"]}
    write_json(ROOT/"benchmark/model-comparison.json",result)
    lines=["# Base versus fine-tuned serving comparison","","Actual RTX 3090, vLLM 0.10.2, FP16, identical telemetry proxy. Prefix cache **disabled for both**.",
           "256 input / 64 forced output tokens; 128 requests per point; three repeats, seeds 8400–8402; 1,536 valid requests.",
           "Each latency is the mean of three per-trial percentiles, not a pooled percentile. Throughput uses generated output tokens only.","",
           "| Model | Concurrency | Output tokens/s (mean ± sample SD) | TTFT P95 (ms) | E2E P95 (ms) | Peak GPU MiB (max) |",
           "|---|---:|---:|---:|---:|---:|"]
    for g in groups:
        lines.append(f"| {g['model']} | {g['concurrency']} | {g['output_tokens_s']['mean']:.2f} ± {g['output_tokens_s']['sample_sd']:.2f} | {g['ttft_p95_ms']['mean']:.2f} | {g['e2e_p95_ms']['mean']:.2f} | {max(g['peak_gpu_mib']['trials']):.0f} |")
    lines+=["","The fine-tuned checkpoint is slightly slower on this matched workload. This is a serving measurement, not evidence of quality improvement.",
            "The earlier 45-point optimization benchmark is retained separately; it uses a different cache/profile protocol and is not pooled here.","",
            "Failures before measurement (unsupported cache-reset route, missing CLI PATH) and a between-condition TIME_WAIT port check are retained privately. Completed base trials were reused after the port fix.",
            "Every valid point retains its raw/status SHA, exact checkpoint identity and measured-source SHA. The Git revision identifies the base commit; the measured uncommitted source snapshots are archived separately.",
            "","","## Reproduce / resume","","```bash","python -m ops.run_model_comparison","python -m ops.summarize_model_comparison","```",
            "Use the documented project-local CPU/GPU environments and the frozen private asset roots. Completed valid points are verified and reused.",
            "","","## Evidence","","[Machine-readable trial evidence](model-comparison.json). Original cloud records: `Evidence/llm-platform-finalization/comparison/`.",
            "Model, data and weights licensing/access remain governed by the existing training evidence; no model weights are committed."]
    (ROOT/"benchmark/model-comparison.md").write_text("\n".join(lines)+"\n")
    print(json.dumps({"requests":result["total_requests"],"groups":[{"model":g["model"],"c":g["concurrency"],"tps":g["output_tokens_s"]["mean"]} for g in groups]}))

if __name__=="__main__":main()
