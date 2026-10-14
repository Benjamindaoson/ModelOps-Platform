"""Public aggregates derive only from private raw requests, telemetry and immutable hashes."""
import json,statistics,subprocess
from collections import defaultdict
from pathlib import Path
from .runtime import ROOT,E
from .contracts import digest
from .benchmark import percentile
from ops.model_release_gate.hardening import quality_decision,validate_observed_trial
P=ROOT/"docs/evidence/inference-hardening"
def read(path):
    p=Path(path);return json.loads(p.read_text()) if p.exists() else {"status":"BLOCKED","reason":"No actual completed evidence"}
def save(path,obj):
    p=Path(path);p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(obj,indent=2)+"\n")
def verify(row):
    try:
        d=Path(row["path"]).resolve()
        if not d.is_relative_to(E):return False
        raw=[json.loads(x) for x in (d/"requests.jsonl").read_text().splitlines()];gpu=json.loads((d/"gpu.json").read_text())
        return row["status"]=="PASS" and row["raw_sha"]==digest(d/"requests.jsonl") and row["gpu_sha"]==digest(d/"gpu.json") and len(raw)==32 and len(gpu)>0 and all(r.get("success") and r["input_tokens"]==row["expected_input_tokens"] and r["output_tokens"]==row["expected_output_tokens"] for r in raw)
    except (OSError,KeyError,TypeError,ValueError):return False
def aggregate(rows,keys):
    groups=defaultdict(dict);bad=[]
    for r in rows:
        if verify(r):groups[tuple(r[k] for k in keys)][r.get("id",str(r.get("repeat")))]=r
        else:bad.append(r.get("path"))
    out=[]
    for key,records in sorted(groups.items()):
        rs=list(records.values());raw=[json.loads(x) for r in rs for x in (Path(r["path"])/"requests.jsonl").read_text().splitlines()]
        out.append({**dict(zip(keys,key)),"repeats":len(rs),"requests":len(raw),"errors":sum(r["errors"] for r in rs),
            "output_tokens_s_mean":statistics.mean(r["output_tokens_s"] for r in rs),"output_tokens_s_min":min(r["output_tokens_s"] for r in rs),"output_tokens_s_max":max(r["output_tokens_s"] for r in rs),
            "latency":{k:{f"p{int(q*100)}":percentile([v[k] for v in raw],q) for q in [.5,.95,.99]} for k in ["ttft_ms","tpot_ms","e2e_ms"]},
            "peak_gpu_mib":max(r["gpu"]["peak_used_mib"] for r in rs),"mean_gpu_util_percent":statistics.mean(r["gpu"]["mean_util_percent"] for r in rs),
            "mean_power_w":statistics.mean(r["gpu"]["mean_power_w"] for r in rs),"model_sha":rs[0]["config"]["model_sha"],"config":rs[0]["config"],"receipts":[{k:r[k] for k in ["path","raw_sha","gpu_sha","protocol_sha","source_sha"]} for r in rs]})
    return out,bad
def main():
    P.mkdir(parents=True,exist_ok=True)
    env=read(E/"environment.json");eng=read(E/"engine-progress.json");qraw=read(E/"quantization/progress.json");pr=read(E/"profiling/progress.json");traw=read(E/"training/progress.json");fault=read(E/"faults/actual.json");tu=read(E/"tuning/progress.json")
    groups,bad=aggregate(eng.get("trials",[]),["engine","workload","concurrency"])
    engine={"status":"PASS" if len(groups)==30 and all(g["repeats"]==3 for g in groups) and not bad else "BLOCKED","groups":groups,"actual_formal_requests":sum(g["requests"] for g in groups),"invalid":bad,"failures_retained":eng.get("failures",[]),"hardware":env,"scope":"Exact token-ID synthetic workloads, no chat transformation; isolated native stacks, no historical RTX3090 values pooled."}
    save(P/"engine_comparison.json",engine)
    quant={"status":qraw.get("status","BLOCKED"),"models":{},"failures":qraw.get("failures",[]),"protocol":read(E/"quantization/protocol.json")}
    base=qraw.get("models",{}).get("fp16",{}).get("quality",{})
    for name,r in qraw.get("models",{}).items():
        gs,invalid=aggregate(r.get("trials",[]),["workload","concurrency"])
        quant["models"][name]={"status":r.get("status"),"quality":r.get("quality"),"quality_gate":quality_decision(base,r.get("quality") or {}),"groups":gs,"invalid":invalid,"conversion":qraw.get("conversions",{}).get(name),"max_tested_concurrency":max([g["concurrency"] for g in gs],default=None)}
    save(P/"quantization_comparison.json",quant)
    profile={k:v for k,v in pr.items() if k!="trials"};gs,invalid=aggregate(tu.get("trials",[]),["engine","variant"])
    profile["tuning"]={"status":tu.get("status","BLOCKED"),"groups":gs,"invalid":invalid,"failures":tu.get("failures",[])}
    profile["counter_boundary"]="Nsight unavailable. No measured HBM bandwidth, occupancy or memory-bound certification."
    save(P/"profiling_summary.json",profile)
    training={"status":traw.get("status","BLOCKED"),"protocol":read(E/"training/protocol.json"),"runs":{},"resume_consistency":traw.get("resume_consistency"),"failures":traw.get("failures",[])}
    for label,r in traw.get("runs",{}).items():
        result=r.get("result",{});proof={k:v for k,v in r.items() if k not in ["job","tracking","quality","result"]}
        proof.update(result=result,training_run_id=r.get("job",{}).get("id"),mlflow_run_id=r.get("tracking",{}).get("run_id"),quality=r.get("quality"),quality_gate=quality_decision(base,r.get("quality") or {}))
        if result.get("adapter"):proof["steps_sha"]=digest(Path(result["adapter"]).parent/"steps.jsonl")
        training["runs"][label]=proof
    save(P/"training_optimization.json",training)
    release={"regression":read(E/"release/regression.json"),"gpu_faults":fault,"scope":"Engineering regression/fault predicates; rejected candidate quality is retained","measured_trial_gates":[{"id":r["id"],**validate_observed_trial(r,env["baseline"]["sha256"])} for r in eng.get("trials",[]) if r["status"]=="PASS"]}
    save(P/"release_regression.json",release)
    tp=E/"pytest-final.log" if (E/"pytest-final.log").exists() else E/"pytest-retry.log";tests=tp.read_text().splitlines()[-1] if tp.exists() else "N/A"
    phases={"environment":env.get("status"),"engines":engine["status"],"tuning":tu.get("status","BLOCKED"),"quantization":quant["status"],"profiling":pr.get("status","BLOCKED"),"training":training["status"],"faults":fault.get("status","BLOCKED"),"release":read(E/"release/regression.json").get("status","BLOCKED"),"gpu_docker":"SKIPPED","nsight":"SKIPPED"}
    summary={"status":"PASS" if all(phases[k]=="PASS" for k in ["environment","engines","tuning","quantization","profiling","training","faults","release"]) else "BLOCKED","phases":phases,"tests":tests,"source_revision":subprocess.check_output(["git","rev-parse","HEAD"],cwd=ROOT,text=True).strip(),"measured_sources":read(E/"measurement-source.json"),"private_artifacts":str(E),"scope":"No business SLO, broad quality, Kubernetes GPU or FP8 claims. No main merge."}
    save(E/"validation.json",summary);save(P/"validation.json",summary)
    text=["# Advanced LLM inference and training validation",f"\n**Status: {summary['status']}**\n",f"Hardware: {env.get('gpu_name')}, CC {env.get('compute_capability')}. Old RTX3090 metrics excluded.",f"\nTests: {tests}\n","|Phase|Actual state|","|---|---|"]+[f"|{k}|{v}|" for k,v in phases.items()]
    text+=["\nReproduce in the cloud project environment: python -m ops.run_inference_hardening --stage all. Completed raw/hash-verified points are reused. Private optimizer/RNG state is trusted local input only.","\nRead JSON for exact model/data/source/telemetry identities. Raw generations, calibration, weights and traces stay private. Engineering quality thresholds are fixed before measurement; a runnable candidate can still fail quality admission."]
    (P/"validation_report.md").write_text("\n".join(text)+"\n")
    lines=["# Matched vLLM and SGLang benchmark","\nSame pinned Qwen2.5-3B model/tokenizer, FP16 and synthetic token-ID prompts. Three repeats x32 requests, three genuine warmups. Cache OFF. Sampling and actual usage lengths checked. Percentiles pool96 actual requests; throughput is mean of three trial rates.","\n|Engine|Load|C|Output tokens/s|TTFT P50/P95/P99 ms|TPOT P50 ms|E2E P95 ms|Peak MiB|Errors|","|---|---|---:|---:|---|---:|---:|---:|---:|"]
    for g in groups:
        t=g["latency"]["ttft_ms"];lines.append(f"|{g['engine']}|{g['workload']}|{g['concurrency']}|{g['output_tokens_s_mean']:.2f}|{t['p50']:.2f}/{t['p95']:.2f}/{t['p99']:.2f}|{g['latency']['tpot_ms']['p50']:.2f}|{g['latency']['e2e_ms']['p95']:.2f}|{g['peak_gpu_mib']:.0f}|{g['errors']}|")
    lines+=["\nNative schedulers/KV/CUDA graphs are upstream capabilities. New adapters provide immutable loading, process ownership, resume-safe measurement and evidence. SGLang0.4.10 Torch2.7.1/cu126 uses Triton attention/PyTorch sampling; vLLM0.10.2 Torch2.8/cu128 uses its recorded defaults. Official tagged C++ source repaired the SGLang wheel omission.","\nSeparate one-factor batch-token/sequence/memory experiments and repeated-context prefix-cache A/B are in profiling_summary.json. No general winner or broad quality claim follows from synthetic throughput."]
    (ROOT/"benchmark/engine-comparison.md").write_text("\n".join(lines)+"\n")
    lines=["# Actual AWQ/GPTQ quality and performance","\nFrozen FP16 base,64 calibration records. Expanded128 SQuAD QA plus separate24 Dolly smoke; same scoring/prompt template. Existing normalized token-F1/EM, not official SQuAD leaderboard scoring. Fixed3GiB KV across packages. Capacity means maximum tested, not physical maximum.","\n|Package|Conversion|SQuAD128 F1/EM|Dolly24 F1/EM|Quality gate|Tested C|","|---|---|---|---|---|---|"]
    for name,m in quant["models"].items():
        qq=(m.get("quality") or {}).get("groups",{});a=qq.get("squad128",{});z=qq.get("dolly24",{})
        lines.append(f"|{name}|{(m.get('conversion') or {}).get('status','Original base')}|{a.get('token_f1','N/A')}/{a.get('exact_match','N/A')}|{z.get('token_f1','N/A')}/{z.get('exact_match','N/A')}|{m['quality_gate']['status']}|{m['max_tested_concurrency']}|")
    lines+=["\nHash-bound load/VRAM/throughput/latency/quality: docs/evidence/inference-hardening/quantization_comparison.json. Recommendations apply only to observed configurations that satisfy the fixed quality policy. INT4 speedup is never presumed.","\nSource: https://huggingface.co/datasets/rajpurkar/squad, revision7b6d24c440a36b6815f21b70d25016731768db1f, CC-BY-SA4.0. Dolly calibration retains its CC-BY-SA3.0 provenance. Raw text/outputs and weights are not committed."]
    (ROOT/"benchmark/quantization-comparison.md").write_text("\n".join(lines)+"\n")
    (ROOT/"docs/GPU_PERFORMANCE_PROFILING.md").write_text("# Real GPU profiling\n\n"+json.dumps(profile,indent=2)+"\n\nKernel names/durations are measured. GEMM/GEMV dominance motivates hypotheses, but memory bandwidth/occupancy remain unverified. Prefix A/B applies to repeated long contexts; negative and unique-context results are retained.\n")
    (ROOT/"experiments/training/optimization-report.md").write_text("# Controlled actual QLoRA optimization\n\n"+json.dumps(training,indent=2)+"\n\nSame data/RNG/effective batch/64 updates. Only checkpointing changes for performance comparison. Pause/resume separately verifies optimizer/scheduler/RNG and numeric weights. Not a domain-quality improvement claim.\n")
    print(json.dumps({"status":summary["status"],"phases":phases,"formal_requests":engine["actual_formal_requests"]}),flush=True)
if __name__=="__main__":main()
