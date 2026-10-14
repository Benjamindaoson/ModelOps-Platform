"""Real vLLM PyTorch/CUDA trace and repeated-context prefix-cache A/B."""
import asyncio,gzip,json,statistics,hashlib,time,traceback
from collections import defaultdict
from pathlib import Path
import httpx
from .runtime import ROOT,E,Server
from .contracts import digest,resume_valid
from .benchmark import measure

def summarize_traces(folder):
    names=defaultdict(float);categories=defaultdict(float);files=[]
    for p in folder.rglob("*"):
        if not p.is_file() or not (p.name.endswith(".json") or p.name.endswith(".json.gz")):continue
        try:
            data=json.loads(gzip.decompress(p.read_bytes()) if p.name.endswith(".gz") else p.read_text())
        except (ValueError,OSError):continue
        if "traceEvents" not in data:continue
        for e in data["traceEvents"]:
            if e.get("ph")=="X" and e.get("dur",0)>0:
                cat=e.get("cat","unknown");categories[cat]+=e["dur"]
                if "kernel" in cat.lower():names[e.get("name","unknown")]+=e["dur"]
        files.append({"path":str(p),"sha256":digest(p),"bytes":p.stat().st_size})
    return {"status":"PASS" if files and names else "FAIL","traces":files,"kernel_duration_us":sorted(names.items(),key=lambda x:-x[1])[:25],"category_sum_us":dict(categories),"scope":"Sum of trace event durations; overlapping GPU kernels are not wall-clock attribution. HBM bandwidth is not measured."}

def main():
    folder=E/"profiling";folder.mkdir(exist_ok=True);statepath=folder/"progress.json"
    state=json.loads(statepath.read_text()) if statepath.exists() else {"trials":[],"failures":[]}
    prompts=json.loads((E/"prompts.json").read_text())["B"]
    config={"engine":"vllm","model":str(ROOT/".tools/assets/qwen3b-base"),"model_sha":digest(ROOT/".tools/assets/qwen3b-base/modelops-files.json"),"name":"modelops-frozen-qwen3b","port":19801,"memory_fraction":.7,"max_context":4096,"max_sequences":64,"batch_tokens":2048,"prefix_cache":False,"kv_cache_bytes":3*1024**3,"label":"profile-fp16","profile":True}
    spec={"model_sha":config["model_sha"],"workload":"2048 input /128 output;32 same exact contexts,C16,3 repeats,3 warmups","cache_only_factor":True,"sampling":"temperature0,ignoreEOS","correctness":"All output texts identical at same request ID","max_tpot_regression":.15}
    ps=hashlib.sha256(json.dumps(spec,sort_keys=True).encode()).hexdigest();ss=hashlib.sha256("".join(digest(ROOT/p) for p in ["ops/inference_hardening/benchmark.py","ops/inference_hardening/contracts.py","ops/observability/stream_metrics.py"]).encode()).hexdigest()
    (folder/"protocol.json").write_text(json.dumps(spec,indent=2))
    if not state.get("trace",{}).get("status")=="PASS":
        try:
            with Server(config) as server:
                r=httpx.post(server.url+"/start_profile",timeout=60);r.raise_for_status()
                try:asyncio.run(measure(server,prompts["prompts"][:32],128,16,8700,folder/"traced-requests",ps,ss))
                finally:
                    r=httpx.post(server.url+"/stop_profile",timeout=180);r.raise_for_status()
            state["trace"]=summarize_traces(folder/"profile-fp16")
        except Exception as exc:
            state["trace"]={"status":"FAIL","error":str(exc)};(folder/"profiler-failure.log").write_text(traceback.format_exc())
        statepath.write_text(json.dumps(state,indent=2))
    # Trace evidence motivates caching repeated long-context prefill; no universal speedup claim.
    for cache in [False,True]:
        cfg={**config,"label":"prefix-"+str(cache).lower(),"profile":False,"prefix_cache":cache}
        todo=[]
        for rep in range(3):
            prior=next((t for t in reversed(state["trials"]) if t["cache"]==cache and t["repeat"]==rep and t["status"]=="PASS"),None)
            if prior and resume_valid(prior,Path(prior["path"])/"requests.jsonl",ss,ps):continue
            todo.append(rep)
        if not todo:continue
        try:
            with Server(cfg) as server:
                for rep in todo:
                    target=folder/f"cache-{cache}-r{rep}"
                    if target.exists():target=target.with_name(target.name+"-retry-"+str(time.time_ns()))
                    rec=asyncio.run(measure(server,[prompts["prompts"][0]]*32,128,16,8700+rep,target,ps,ss))
                    state["trials"].append({"cache":cache,"repeat":rep,"path":str(target),**rec});statepath.write_text(json.dumps(state,indent=2))
                    print("PREFIX_AB "+str(cache)+" "+str(rep)+" "+rec["status"],flush=True)
        except Exception as exc:state["failures"].append({"cache":cache,"error":str(exc)})
    pairs=[]
    for rep in range(3):
        rows={b:next((t for t in reversed(state["trials"]) if t["cache"]==b and t["repeat"]==rep and t["status"]=="PASS"),None) for b in [False,True]}
        if not all(rows.values()):continue
        raw={b:{r["request_id"]:r["text"] for r in [json.loads(x) for x in (Path(rows[b]["path"])/"requests.jsonl").read_text().splitlines()]} for b in rows}
        pairs.append({"repeat":rep,"output_exact":raw[False]==raw[True],"ttft_p50_ratio":rows[True]["latency"]["ttft_ms"]["p50"]/rows[False]["latency"]["ttft_ms"]["p50"],"tpot_p50_ratio":rows[True]["latency"]["tpot_ms"]["p50"]/rows[False]["latency"]["tpot_ms"]["p50"],"output_tps_ratio":rows[True]["output_tokens_s"]/rows[False]["output_tokens_s"]})
    state["pairs"]=pairs;state["nsight"]={"status":"SKIPPED","reason":"nsys/ncu not installed; no GPU counter permission bypass"}
    state["status"]="PASS" if state.get("trace",{}).get("status")=="PASS" and len(pairs)==3 and all(x["output_exact"] for x in pairs) else "FAIL"
    statepath.write_text(json.dumps(state,indent=2))
if __name__=="__main__":main()
