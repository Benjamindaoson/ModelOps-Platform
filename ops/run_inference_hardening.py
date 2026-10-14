"""Resume-safe staged native GPU experiments; no generated results in CPU mode."""
import argparse,asyncio,fcntl,hashlib,json,os,time,traceback
from pathlib import Path
from ops.inference_hardening.runtime import ROOT,E,Server
from ops.inference_hardening.contracts import digest,resume_valid
from ops.inference_hardening.resume import valid_receipt
from ops.inference_hardening.benchmark import measure

def run_engines(engines):
    model=ROOT/".tools/assets/qwen3b-base";model_sha=digest(model/"modelops-files.json")
    data=json.loads((E/"prompts.json").read_text())
    protocol={"model_sha":model_sha,"prompt_sha":digest(E/"prompts.json"),"precision":"fp16","prefix_cache":False,"workloads":{"A":[256,64],"B":[2048,128],"C":[512,512]},
              "concurrency":[1,4,8,16,32],"repeats":3,"requests":32,"warmup":3,"seed":8700,"hardware_sha":digest(E/"environment.json")}
    ps=hashlib.sha256(json.dumps(protocol,sort_keys=True).encode()).hexdigest()
    files=["ops/inference_hardening/benchmark.py","ops/inference_hardening/contracts.py","ops/observability/stream_metrics.py"]
    source={p:digest(ROOT/p) for p in files};ss=hashlib.sha256(json.dumps(source,sort_keys=True).encode()).hexdigest()
    (E/"protocol.json").write_text(json.dumps(protocol,indent=2)+"\n");(E/"measurement-source.json").write_text(json.dumps(source,indent=2)+"\n")
    snapshot=E/"measured-source";snapshot.mkdir(exist_ok=True)
    for p in files:(snapshot/Path(p).name).write_bytes((ROOT/p).read_bytes())
    progress=E/"engine-progress.json";records=json.loads(progress.read_text()) if progress.exists() else {"status":"RUNNING","trials":[],"failures":[]}
    for engine in engines:
        todo=[]
        for label in ("A","B","C"):
            for c in [1,4,8,16,32]:
                for rep in range(3):
                    ident=f"{engine}-{label}-c{c}-r{rep}";folder=E/"engine-comparison"/ident
                    rp=folder/"receipt.json"
                    prior=next((r for r in reversed(records["trials"]) if r["id"]==ident and valid_receipt(r,Path(r["path"]),ss,ps)),None)
                    if prior or (rp.exists() and valid_receipt(json.loads(rp.read_text()),folder,ss,ps)):continue
                    todo.append((ident,label,c,rep))
        if not todo:continue
        config={"engine":engine,"model":str(model),"model_sha":model_sha,"name":"modelops-frozen-qwen3b","label":engine+"-baseline",
                "port":19801,"memory_fraction":.7,"max_context":4096,"max_sequences":64,"batch_tokens":2048,"prefix_cache":False}
        if engine=="sglang":config.update(attention_backend="triton",sampling_backend="pytorch")
        try:
            with Server(config) as server:
                for ident,label,c,rep in todo:
                    folder=E/"engine-comparison"/ident
                    if folder.exists():folder=folder.with_name(ident+"-retry-"+str(int(time.time())))
                    record=asyncio.run(measure(server,data[label]["prompts"][rep*32:(rep+1)*32],data[label]["output_tokens"],c,8700+rep,folder,ps,ss))
                    row={"id":ident,"engine":engine,"workload":label,"concurrency":c,"repeat":rep,"path":str(folder),**record}
                    records["trials"].append(row);records["status"]="RUNNING";progress.write_text(json.dumps(records,indent=2)+"\n")
                    print(json.dumps({"id":ident,"status":record["status"],"output_tokens_s":record["output_tokens_s"]}),flush=True)
                    if record["status"]!="PASS":raise RuntimeError("Real benchmark failed; all requests retained")
        except Exception as exc:
            records["failures"].append({"engine":engine,"error":type(exc).__name__+": "+str(exc),"time":time.time()});progress.write_text(json.dumps(records,indent=2)+"\n")
            print("ENGINE_FAILURE "+engine+" "+str(exc),flush=True)
            (E/("failure-"+engine+".log")).write_text(traceback.format_exc())
            continue
    valid=[r for r in records["trials"] if r["status"]=="PASS"]
    records["status"]="PASS" if len({r["id"] for r in valid})==90 else "BLOCKED" if records["failures"] else "RUNNING"
    progress.write_text(json.dumps(records,indent=2)+"\n")

def main():
    p=argparse.ArgumentParser();p.add_argument("--stage",choices=["engines","profiling","faults","quantization","training"],default="engines");p.add_argument("--engines",nargs="+",choices=["vllm","sglang"],default=["vllm","sglang"])
    a=p.parse_args();E.mkdir(exist_ok=True)
    with (E/"controller.lock").open("a") as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        if a.stage=="engines":run_engines(a.engines)
        else:
            from importlib import import_module
            modules={"profiling":"profiling_stage","faults":"fault_stage","quantization":"quantization_stage","training":"training_stage"}
            import_module("ops.inference_hardening."+modules[a.stage]).main()

if __name__=="__main__":main()
