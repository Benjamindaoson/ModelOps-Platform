"""Actual conversion + matched fixed-KV quality/performance; resume checks raw hashes."""
import asyncio,json,subprocess,time,hashlib,traceback
from pathlib import Path
from .runtime import ROOT,E,Server
from .contracts import digest,resume_valid
from .benchmark import measure
from .quality import evaluate
from pipelines.training.data_contract import verify_model_bundle

def main():
    folder=E/"quantization";folder.mkdir(exist_ok=True)
    spec={"kv_cache_bytes":3*1024**3,"workloads":["A","B","C"],"concurrency":[1,16,32],"requests":32,"repeats":3,"warmup":3,"base_sha":digest(ROOT/".tools/assets/qwen3b-base/modelops-files.json"),"prompt_sha":digest(E/"prompts.json"),"calibration_sha":digest(E/"calibration.jsonl"),"quality_sha":digest(E/"expanded-heldout.jsonl"),"min_f1_delta":-.02,"min_em_delta":-.02,"quality_scope":"Engineering gate, not a production SLA"}
    specpath=folder/"protocol.json"
    if specpath.exists() and json.loads(specpath.read_text())!=spec:raise ValueError("Quantization protocol changed")
    specpath.write_text(json.dumps(spec,indent=2)+"\n")
    ps=hashlib.sha256(json.dumps(spec,sort_keys=True).encode()).hexdigest()
    ss=hashlib.sha256("".join(digest(ROOT/p) for p in ["ops/inference_hardening/benchmark.py","ops/inference_hardening/contracts.py","ops/observability/stream_metrics.py"]).encode()).hexdigest()
    statepath=folder/"progress.json";state=json.loads(statepath.read_text()) if statepath.exists() else {"conversions":{},"models":{},"failures":[]}
    for method in ["gptq","awq"]:
        cp=folder/method/"conversion.json"
        if cp.exists() and json.loads(cp.read_text()).get("status")=="PASS":
            rec=json.loads(cp.read_text());verify_model_bundle(folder/method/"model",rec["model_sha"]);state["conversions"][method]=rec;continue
        log=folder/(method+"-conversion.log")
        with log.open("ab") as stream:
            proc=subprocess.run([str(ROOT/".quant-venv/bin/python"),"-m","ops.locked_exec","--",str(ROOT/".quant-venv/bin/python"),"-m","ops.inference_hardening.quantize","--method",method],cwd=ROOT,stdout=stream,stderr=subprocess.STDOUT,timeout=2400)
        rec=json.loads(cp.read_text()) if proc.returncode==0 and cp.exists() else {"status":"FAIL","returncode":proc.returncode,"log":str(log)}
        state["conversions"][method]=rec;statepath.write_text(json.dumps(state,indent=2)+"\n")
        print("CONVERSION "+method+" "+rec["status"],flush=True)
    models={"fp16":ROOT/".tools/assets/qwen3b-base",**{m:folder/m/"model" for m,r in state["conversions"].items() if r["status"]=="PASS"}}
    data=json.loads((E/"prompts.json").read_text())
    for name,model in models.items():
        config={"engine":"vllm","model":str(model),"model_sha":digest(model/"modelops-files.json"),"name":"modelops-frozen-qwen3b","label":"quant-"+name,"port":19801,"memory_fraction":.7,"max_context":4096,"max_sequences":64,"batch_tokens":2048,"prefix_cache":False,"kv_cache_bytes":spec["kv_cache_bytes"]}
        result=state["models"].setdefault(name,{"trials":[]})
        try:
            with Server(config) as server:
                result["quality"]=asyncio.run(evaluate(server,folder/name/"quality"))
                for label in spec["workloads"]:
                    for c in spec["concurrency"]:
                        for rep in range(3):
                            ident=f"{name}-{label}-c{c}-r{rep}"
                            prior=next((t for t in reversed(result["trials"]) if t["id"]==ident and t["status"]=="PASS"),None)
                            if prior and resume_valid(prior,Path(prior["path"])/"requests.jsonl",ss,ps):continue
                            target=folder/"performance"/ident
                            if target.exists():target=target.with_name(ident+"-retry-"+str(time.time_ns()))
                            rec=asyncio.run(measure(server,data[label]["prompts"][rep*32:(rep+1)*32],data[label]["output_tokens"],c,8700+rep,target,ps,ss))
                            result["trials"].append({"id":ident,"path":str(target),"workload":label,"concurrency":c,"repeat":rep,**rec})
                            statepath.write_text(json.dumps(state,indent=2)+"\n")
                            print("QUANT_MEASURE "+ident+" "+rec["status"],flush=True)
                            if rec["status"]!="PASS":raise RuntimeError("Actual quantized request failed")
                result["status"]="PASS" if result["quality"]["status"]=="PASS" and len({t["id"] for t in result["trials"] if t["status"]=="PASS"})==27 else "FAIL"
        except Exception as exc:
            result["status"]="FAIL";result["error"]=str(exc);state["failures"].append({"model":name,"error":str(exc),"time":time.time()})
            (folder/(name+"-failure.log")).write_text(traceback.format_exc())
        statepath.write_text(json.dumps(state,indent=2)+"\n")
    state["status"]="PASS" if state["models"].get("fp16",{}).get("status")=="PASS" and any(state["models"].get(m,{}).get("status")=="PASS" for m in ["gptq","awq"]) else "FAIL"
    statepath.write_text(json.dumps(state,indent=2)+"\n")

if __name__=="__main__":main()
