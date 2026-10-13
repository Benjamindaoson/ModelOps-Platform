"""Bounded real matched vLLM matrix using the existing official-CLI benchmark runner."""
from pathlib import Path
from datetime import datetime,timezone
import argparse,json,os,socket,subprocess,time,signal,fcntl
import httpx,psutil
from pipelines.training.data_contract import sha256,write_json
ROOT=Path(__file__).resolve().parents[1];E=ROOT/"Evidence/llm-production-validation"
PROFILES=[("baseline",{}),("batching-token-budget",{"MAX_NUM_BATCHED_TOKENS":"4096"}),("kv-memory-budget",{"GPU_MEMORY_UTILIZATION":"0.95"})]
CONCURRENCY=[1,4,8,16,32]
def stop(record):
    p=psutil.Process(record["pid"])
    if p.create_time()!=record["create_time"] or "ops.vllm_start" not in p.cmdline() or os.getpgid(p.pid)!=p.pid:
        raise RuntimeError("GPU process ownership mismatch")
    os.killpg(p.pid,signal.SIGTERM)
    try:p.wait(30)
    except psutil.TimeoutExpired:os.killpg(p.pid,signal.SIGKILL);p.wait(15)
    time.sleep(2)


def read_trial(path):
    import csv,math
    path=Path(path)
    status=json.loads((path/"status.json").read_text())
    raw=json.loads((path/"raw-benchmark.json").read_text())
    manifest=json.loads((path/"manifest.json").read_text())
    if status.get("status")!="PASS" or raw.get("completed")!=manifest["prompts"]:raise ValueError("Incomplete official benchmark")
    if len(raw.get("output_lens",[]))!=raw["completed"] or any(x!=manifest["output_len_tokens"] for x in raw["output_lens"]):
        raise ValueError("Fixed output protocol not satisfied")
    if raw["total_output_tokens"]!=raw["completed"]*manifest["output_len_tokens"]:raise ValueError("Output accounting mismatch")
    rows=list(csv.DictReader((path/"gpu-telemetry.csv").open()))
    values=lambda key:[float(x[key]) for x in rows if x.get(key) not in (None,"","N/A")]
    util=values("utilization_percent");memory=values("memory_used_mib");power=values("power_w")
    gpu={"samples":len(rows),"mean_utilization_percent":sum(util)/len(util) if util else None,
         "peak_utilization_percent":max(util) if util else None,"peak_used_mib":max(memory) if memory else None,
         "mean_power_w":sum(power)/len(power) if power else None,"peak_power_w":max(power) if power else None,
         "scope":"Whole GPU sampled during official CLI subprocess, including client initialization"}
    return {"status":"PASS","completed_requests":raw["completed"],"output_tokens":raw["total_output_tokens"],
        "wall_s":raw["duration"],"requests_per_s":raw["request_throughput"],"output_tokens_per_s":raw["output_throughput"],
        "latency_ms":{k:raw[k] for k in raw if k.startswith(("p50_","p95_","p99_"))},"gpu":gpu,
        "raw_sha256":sha256(path/"raw-benchmark.json"),"status_sha256":sha256(path/"status.json")}

def main():
    parser=argparse.ArgumentParser();parser.add_argument("--prompts",type=int,default=128);parser.add_argument("--repeats",type=int,default=3);args=parser.parse_args()
    if args.prompts!=128 or args.repeats!=3:raise ValueError("Frozen protocol requires 128 requests and three repeats")
    E.mkdir(parents=True,exist_ok=True);folder=E/"benchmark";folder.mkdir(exist_ok=True)
    with (E/"benchmark-controller.lock").open("a") as lock:
      fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
      train=json.loads((E/"training-finished.json").read_text());life=json.loads((E/"lifecycle.json").read_text())
      if life["status"]!="PASS" or not life["evaluation"]["passed"]:raise RuntimeError("Real lifecycle and quality gate required")
      model=Path(train["result"]["checkpoint"]).parent;model_id=life["candidate"]["id"]
      if sha256(model/"model.safetensors")!=train["result"]["checkpoint_sha256"]:raise ValueError("Frozen serving weights changed")
      records=json.loads((folder/"progress.json").read_text()) if (folder/"progress.json").exists() else {
          "status":"RUNNING","protocol":{"profiles":[p[0] for p in PROFILES],"concurrency":CONCURRENCY,"requests_per_point":128,"repeats":3,
          "input_tokens":256,"output_tokens":64,"ignore_eos":True,"precision":"fp16","context_bound":2048,"vllm":"0.10.2",
          "seed_per_repeat":[8100,8101,8102],"checkpoint_sha256":train["result"]["checkpoint_sha256"],"modelops_artifact":model_id,
          "baseline_note":"vLLM default scheduling/KV options with common explicit precision/context/network bounds; continuous batching already enabled"},
          "trials":[],"scope":"Bounded synthetic native GPU experiments; not production capacity/SLO or Kubernetes"}
      for name,extra in PROFILES:
        needed=[(rep,c) for rep in range(3) for c in CONCURRENCY if not any(x["profile"]==name and x["repeat"]==rep and x["concurrency"]==c and x["status"]=="PASS" for x in records["trials"])]
        if not needed:continue
        with socket.socket() as sock:sock.bind(("127.0.0.1",0));port=sock.getsockname()[1]
        env={k:v for k,v in os.environ.items() if not any(x in k.upper() for x in ("TOKEN","SECRET","PASSWORD"))}
        env.update(MODEL_PATH=str(model),MODEL_SHA256=train["result"]["checkpoint_sha256"],SERVED_MODEL_NAME=model_id,
            SERVING_HOST="127.0.0.1",SERVING_PORT=str(port),HF_HUB_OFFLINE="1",TOKENIZERS_PARALLELISM="false",
            PATH=str(ROOT/".gpu-venv/bin")+os.pathsep+env.get("PATH",""),PYTHONPATH=str(ROOT))
        env.pop("LD_LIBRARY_PATH",None);env.update(extra)
        env.update(VLLM_CACHE_ROOT=str(ROOT/".tools/vllm-cache"),XDG_CACHE_HOME=str(ROOT/".tools/cache"))
        log=(folder/(name+"-server.log")).open("ab")
        cmd=[str(ROOT/".gpu-venv/bin/python"),"-m","ops.locked_exec","--",str(ROOT/".gpu-venv/bin/python"),"-m","ops.vllm_start"]
        began=time.perf_counter();p=subprocess.Popen(cmd,cwd=ROOT,env=env,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
        owned={"pid":p.pid,"create_time":psutil.Process(p.pid).create_time(),"profile":name,"endpoint":f"http://127.0.0.1:{port}","extra":extra}
        write_json(folder/"active-server.json",owned)
        try:
          ready=False
          for _ in range(240):
            if p.poll() is not None:raise RuntimeError("Real vLLM startup failed; retained server log")
            try:
                r=httpx.get(owned["endpoint"]+"/v1/models",timeout=2)
                ready=r.status_code==200 and model_id in {x["id"] for x in r.json()["data"]}
            except (httpx.HTTPError,KeyError,ValueError):pass
            if ready:break
            time.sleep(2)
          if not ready:raise RuntimeError("Real vLLM startup budget exceeded")
          owned["model_load_wall_s"]=time.perf_counter()-began;write_json(folder/"active-server.json",owned)
          for rep,c in needed:
            run_id=name+"-r"+str(rep)+"-c"+str(c)
            path=folder/run_id
            if path.exists():
                run_id+="-retry-"+str(int(time.time()));path=folder/run_id
            # Warmups are independent of measured 128-request result. Clear default prefix cache where supported.
            cache_reset=httpx.post(owned["endpoint"]+"/reset_prefix_cache",timeout=10)
            for _ in range(3):
                r=httpx.post(owned["endpoint"]+"/v1/chat/completions",timeout=60,json={"model":model_id,"messages":[{"role":"user","content":"Name one city."}],"temperature":0,"max_tokens":8})
                r.raise_for_status()
            bench=[str(ROOT/".gpu-venv/bin/python"),"benchmarks/inference/run.py","--base-url",owned["endpoint"],"--model",model_id,
              "--tokenizer",str(model),"--cli-profile","v0.10","--prompts","128","--concurrency",str(c),"--request-rate","10000",
              "--input-len","256","--output-len","64","--warmups","0","--fixed-lengths","--ignore-eos","--save-detailed",
              "--seed",str(8100+rep),"--gpu-poll-s","0.25","--timeout-s","600","--output-root",str(folder),"--run-id",run_id]
            with (folder/(run_id+"-controller.log")).open("wb") as output:
                result=subprocess.run(bench,cwd=ROOT,env=env,stdout=output,stderr=subprocess.STDOUT,timeout=650)
            normalized=read_trial(path) if (path/"status.json").exists() else {"status":"FAIL"}
            item={"profile":name,"repeat":rep,"concurrency":c,"run_id":run_id,"status":normalized.get("status"),"exit":result.returncode,
                  "result":normalized,"artifact_root":str(path),"cache_reset_status":cache_reset.status_code,"model_load_wall_s":owned["model_load_wall_s"]}
            records["trials"].append(item);write_json(folder/"progress.json",records)
            print(json.dumps({"completed_trial":run_id,"status":item["status"],"requests":normalized.get("completed_requests")}),flush=True)
            if result.returncode!=0 or item["status"]!="PASS":raise RuntimeError("Real benchmark failed; record retained")
        finally:
          if p.poll() is None:stop(owned)
          log.close()
      records.update(status="PASS",finished=datetime.now(timezone.utc).isoformat());write_json(folder/"progress.json",records)
      print("REAL_MATCHED_3B_BENCHMARK_MATRIX_PASS",flush=True)
if __name__=="__main__":main()
