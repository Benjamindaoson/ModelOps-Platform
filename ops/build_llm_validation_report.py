"""Audit complete real results and generate public aggregate evidence, never synthetic metrics."""
from pathlib import Path
from datetime import datetime
import json,statistics,csv,hashlib
ROOT=Path(__file__).resolve().parents[1];E=ROOT/"Evidence/llm-production-validation"
def main():
    matrix=json.loads((E/"benchmark/progress.json").read_text())
    if matrix["status"]!="PASS":raise RuntimeError("Real matrix not complete")
    trials=[x for x in matrix["trials"] if x["status"]=="PASS"]
    keys={(x["profile"],x["repeat"],x["concurrency"]) for x in trials}
    expected={(p,r,c) for p in ("baseline","batching-token-budget","kv-memory-budget") for r in range(3) for c in (1,4,8,16,32)}
    if keys!=expected or len(trials)!=45:raise RuntimeError("Missing/duplicate matched point")
    from ops.benchmark_llm_validation import read_trial
    for trial in trials:
        current=read_trial(Path(trial["artifact_root"]))
        if current["raw_sha256"]!=trial["result"]["raw_sha256"]:raise RuntimeError("Raw timing evidence changed")
    grouped=[]
    for profile in ("baseline","batching-token-budget","kv-memory-budget"):
      for c in (1,4,8,16,32):
        data=[x["result"] for x in trials if x["profile"]==profile and x["concurrency"]==c]
        row={"profile":profile,"concurrency":c,"repeats":3,"requests":sum(x["completed_requests"] for x in data)}
        for metric in ("requests_per_s","output_tokens_per_s","wall_s"):
            vals=[x[metric] for x in data];row[metric+"_mean"]=statistics.mean(vals);row[metric+"_std"]=statistics.stdev(vals)
        row["latency_ms"]={key:{"mean_of_trial_percentiles":statistics.mean(x["latency_ms"][key] for x in data)} for key in data[0]["latency_ms"]}
        row["peak_gpu_used_mib"]=max(x["gpu"]["peak_used_mib"] for x in data)
        row["mean_gpu_utilization_percent"]=statistics.mean(x["gpu"]["mean_utilization_percent"] for x in data)
        row["mean_gpu_power_w"]=statistics.mean(x["gpu"]["mean_power_w"] for x in data)
        grouped.append(row)
    seals=[]
    for trial in trials:
      path=Path(trial["artifact_root"])
      for name in ("raw-benchmark.json","status.json","manifest.json","gpu-telemetry.csv"):
        f=path/name;seals.append({"trial":trial["run_id"],"file":str(f.relative_to(ROOT)),"sha256":hashlib.sha256(f.read_bytes()).hexdigest(),"bytes":f.stat().st_size})
    result={"status":"PASS","valid_points":45,"valid_requests":sum(x["result"]["completed_requests"] for x in trials),
        "protocol":matrix["protocol"],"groups":grouped,"excluded_measurements":[x for x in matrix["trials"] if x["status"]=="EXCLUDED_SMOKE_OVERLAP"],
        "controller_errors_retained":len([x for x in matrix["trials"] if x["status"]=="FAIL"]),
        "interpretation":"Three repeated synthetic trials per cell; mean of trial percentiles, not pooled percentiles or production SLO. No AWQ inference comparison claimed.",
        "gpu_scope":"Whole GPU sampled per official CLI subprocess including client initialization"}
    out=ROOT/"benchmark";out.mkdir(exist_ok=True)
    (out/"report.json").write_text(json.dumps(result,indent=2))
    doc=ROOT/"docs/evidence/llm-validation/benchmark";doc.mkdir(exist_ok=True)
    (doc/"result.json").write_text(json.dumps(result,indent=2));(doc/"validation.json").write_text(json.dumps({"status":"PASS","points":45,"requests":5760,"unique_keys":45,"file_hashes":seals},indent=2))
    lines=["# Real Qwen2.5-3B serving benchmark","",
        "45 valid points and 5,760 real streamed requests; three repeats at concurrency 1/4/8/16/32 for each FP16 profile. Input budget 256, forced output 64, context bound 2048, same checkpoint and seeds.","",
        "| Profile | C | Requests/s | Output tokens/s | TTFT P50/P95/P99 ms | TPOT P50/P95/P99 ms | E2E P95 ms | Peak MiB | Mean GPU % | Mean power W |",
        "|---|---:|---:|---:|---|---|---:|---:|---:|---:|"]
    for x in grouped:
        lat=x["latency_ms"];q=lambda key:lat[key]["mean_of_trial_percentiles"]
        lines.append(f"| {x['profile']} | {x['concurrency']} | {x['requests_per_s_mean']:.3f} | {x['output_tokens_per_s_mean']:.2f} | {q('p50_ttft_ms'):.2f}/{q('p95_ttft_ms'):.2f}/{q('p99_ttft_ms'):.2f} | {q('p50_tpot_ms'):.2f}/{q('p95_tpot_ms'):.2f}/{q('p99_tpot_ms'):.2f} | {q('p95_e2el_ms'):.2f} | {x['peak_gpu_used_mib']:.0f} | {x['mean_gpu_utilization_percent']:.2f} | {x['mean_gpu_power_w']:.2f} |")
    lines += ["","Percentile entries are means of three independently measured trial percentiles, not a pooled 384-request percentile. Synthetic traffic does not establish a business workload SLO or maximum capacity.",
      "vLLM already uses continuous batching; the batching profile changes token budget only. KV tuning raises GPU reservation from 0.90 to 0.95. Any difference is descriptive for this bounded workload.",
      "The already successful first C1 point was reused after a summarizer-path repair. One overlapping validation curl point is retained and excluded; only that point was rerun. Negative quality results and all measurement attempts remain traceable.",
      "Detailed request timings, outputs, CPU-controller logs and GPU power/utilization/memory samples remain in the private cloud evidence directory; file hashes are published in validation.json."]
    text="\n".join(lines)+"\n";(out/"report.md").write_text(text);(doc/"report.md").write_text(text)
    import matplotlib;matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig,axes=plt.subplots(1,2,figsize=(12,4.5))
    for profile in ("baseline","batching-token-budget","kv-memory-budget"):
      rows=[x for x in grouped if x["profile"]==profile]
      axes[0].errorbar([x["concurrency"] for x in rows],[x["output_tokens_per_s_mean"] for x in rows],yerr=[x["output_tokens_per_s_std"] for x in rows],marker="o",label=profile,capsize=3)
      axes[1].plot([x["concurrency"] for x in rows],[x["latency_ms"]["p95_e2el_ms"]["mean_of_trial_percentiles"] for x in rows],marker="o",label=profile)
    axes[0].set(xlabel="Concurrency",ylabel="Output tokens/s",title="Mean +/- SD across 3 actual trials")
    axes[1].set(xlabel="Concurrency",ylabel="Mean trial E2E P95 (ms)",title="Descriptive tail latency")
    for a in axes:a.grid(alpha=.2);a.legend(fontsize=8)
    fig.tight_layout();fig.savefig(doc/"throughput_latency.png",dpi=160);plt.close(fig)
    print(json.dumps({"valid_points":45,"requests":5760,"baseline_c32":[x for x in grouped if x["profile"]=="baseline" and x["concurrency"]==32][0]}),flush=True)
if __name__=="__main__":main()
