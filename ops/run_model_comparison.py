"""Bounded actual base-versus-trained vLLM benchmark through the same telemetry proxy."""
import hashlib
import json
import os
import signal
import socket
import statistics
import subprocess
import time
from pathlib import Path
import fcntl
import httpx
import psutil
from ops.benchmark_llm_validation import read_trial
from pipelines.training.data_contract import sha256, write_json
from ops.model_release_gate.__main__ import run as release_gate

ROOT=Path(__file__).resolve().parents[1]
E=ROOT/"Evidence/llm-platform-finalization"
CONCURRENCY=[4,16]
REPEATS=3
PROMPTS=128
UPSTREAM="http://127.0.0.1:19782"
PROXY="http://127.0.0.1:19780"

def stop_owned(p,owned,marker):
    if p.poll() is not None:return
    process=psutil.Process(p.pid)
    if process.create_time()!=owned["create_time"] or marker not in " ".join(process.cmdline()) or os.getpgid(p.pid)!=p.pid:
        raise RuntimeError("Process ownership mismatch; no unsafe cleanup")
    os.killpg(p.pid,signal.SIGTERM)
    try:p.wait(30)
    except subprocess.TimeoutExpired:
        os.killpg(p.pid,signal.SIGKILL);p.wait(15)

def available(port):
    with socket.socket() as s:
        s.setsockopt(socket.SOL_SOCKET,socket.SO_REUSEADDR,1)
        s.bind(("127.0.0.1",port))

def wait_ready(p,url,model=None):
    start=time.perf_counter()
    while time.perf_counter()-start<240:
        if p.poll() is not None:raise RuntimeError("Owned server exited before readiness")
        try:
            r=httpx.get(url+"/health",timeout=2)
            if r.status_code==200:
                ids=httpx.get(url+"/v1/models",timeout=3).json()["data"]
                if model is None or model in [x["id"] for x in ids]:return time.perf_counter()-start
        except (httpx.HTTPError,ValueError,KeyError):pass
        time.sleep(1)
    raise RuntimeError("Readiness timeout")

def comparison_environment(root,model,modelid,digest):
    env={k:v for k,v in os.environ.items() if not any(x in k.upper() for x in ("TOKEN","PASSWORD","SECRET","API_KEY","PRIVATE_KEY"))}
    env.update(MODEL_PATH=str(model),MODEL_SHA256=digest,SERVED_MODEL_NAME=modelid,SERVING_HOST="127.0.0.1",SERVING_PORT="19782",
               HF_HUB_OFFLINE="1",TOKENIZERS_PARALLELISM="false",PYTHONPATH=str(root),
               VLLM_CACHE_ROOT=str(root/".tools/vllm-cache"),XDG_CACHE_HOME=str(root/".tools/cache"))
    env.pop("LD_LIBRARY_PATH",None)
    env["PATH"]=str(root/".gpu-venv/bin")+os.pathsep+env.get("PATH","")
    return env

def main():
    E.mkdir(parents=True,exist_ok=True);folder=E/"comparison";folder.mkdir(exist_ok=True)
    with (E/"comparison-controller.lock").open("a") as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        train=json.loads((ROOT/"Evidence/llm-production-validation/training-finished.json").read_text())
        life=json.loads((ROOT/"Evidence/llm-production-validation/lifecycle.json").read_text())
        models=[("base",ROOT/".tools/assets/qwen3b-base",train["result"]["base_sha256"],life["base"]["id"]),
                ("trained",Path(train["result"]["checkpoint"]).parent,train["result"]["checkpoint_sha256"],life["candidate"]["id"])]
        protocol={"precision":"fp16","prefix_cache":False,"concurrency":CONCURRENCY,"repeats":REPEATS,"requests_per_point":PROMPTS,
                  "input_tokens":256,"output_tokens":64,"seeds":[8400,8401,8402],"proxy":"same CPU telemetry proxy",
                  "model_identities":{label:digest for label,path,digest,modelid in models}}
        path=folder/"progress.json"
        records=json.loads(path.read_text()) if path.exists() else {"status":"RUNNING","protocol":protocol,"trials":[],"attempts":[]}
        if records["protocol"]!=protocol:raise ValueError("Frozen comparison protocol changed")
        if records["status"]=="PASS":
            for row in records["trials"]:
                if read_trial(Path(row["artifact_root"]))["raw_sha256"]!=row["result"]["raw_sha256"]:raise ValueError("Completed evidence changed")
            print("Verified completed comparison reused");return
        records["status"]="RUNNING";write_json(path,records)
        source={"git":subprocess.check_output(["git","rev-parse","HEAD"],cwd=ROOT,text=True).strip(),
                "files":{n:sha256(ROOT/n) for n in ["ops/run_model_comparison.py","ops/platform_serving.py","ops/observability/server.py","ops/observability/stream_metrics.py"]}}
        write_json(folder/"source.json",source)
        for label,model,digest,modelid in models:
            wanted={(rep,c) for rep in range(REPEATS) for c in CONCURRENCY}
            done={(r["repeat"],r["concurrency"]) for r in records["trials"] if r["model"]==label and r["status"]=="PASS"}
            if done==wanted:continue
            available(19782);available(19780)
            env=comparison_environment(ROOT,model,modelid,digest)
            gpu_log=(folder/(label+"-server.log")).open("ab")
            cmd=[str(ROOT/".gpu-venv/bin/python"),"-m","ops.locked_exec","--",str(ROOT/".gpu-venv/bin/python"),"-m","ops.platform_serving"]
            p=subprocess.Popen(cmd,cwd=ROOT,env=env,stdout=gpu_log,stderr=subprocess.STDOUT,start_new_session=True)
            owned={"pid":p.pid,"create_time":psutil.Process(p.pid).create_time()}
            proxy=None;proxy_log=None
            try:
                model_load=wait_ready(p,UPSTREAM,modelid)
                proxy_log=(folder/(label+"-proxy.log")).open("ab")
                proxy=subprocess.Popen([str(ROOT/".venv/bin/python"),"-m","ops.observability.server","--upstream",UPSTREAM,"--port","19780","--version",label],
                                       cwd=ROOT,env=env,stdout=proxy_log,stderr=subprocess.STDOUT,start_new_session=True)
                proxy_owned={"pid":proxy.pid,"create_time":psutil.Process(proxy.pid).create_time()}
                wait_ready(proxy,PROXY,modelid)
                probes=[]
                for prompt in ["What is the capital of France? Answer briefly.","Name one primary color."]:
                    payload={"model":modelid,"messages":[{"role":"user","content":prompt}],"temperature":0,"max_tokens":16}
                    direct=httpx.post(UPSTREAM+"/v1/chat/completions",json=payload,timeout=60);direct.raise_for_status()
                    through=httpx.post(PROXY+"/v1/chat/completions",json=payload,timeout=60);through.raise_for_status()
                    same=direct.json()["choices"]==through.json()["choices"]
                    probes.append({"model":label,"same_generated_choices":same,"direct":direct.json(),"proxy":through.json()})
                    if not same:raise ValueError("Proxy altered generated output; measurement blocked")
                write_json(folder/(label+"-proxy-correctness.json"),{"status":"PASS","scope":"Actual GPU outputs, not fixtures","cases":probes})
                for rep in range(REPEATS):
                    for c in CONCURRENCY:
                        previous=[r for r in records["trials"] if r["model"]==label and r["repeat"]==rep and r["concurrency"]==c and r["status"]=="PASS"]
                        if previous:
                            if read_trial(Path(previous[0]["artifact_root"]))["raw_sha256"]!=previous[0]["result"]["raw_sha256"]:raise ValueError("Saved trial corrupted")
                            continue
                        runid=f"{label}-r{rep}-c{c}";trial=folder/runid
                        if trial.exists():
                            runid+="-retry-"+str(int(time.time()));trial=folder/runid
                        # Prefix caching is explicitly disabled identically for both conditions.
                        for _ in range(3):
                            r=httpx.post(PROXY+"/v1/chat/completions",timeout=60,json={"model":modelid,"messages":[{"role":"user","content":"Name one city."}],"temperature":0,"max_tokens":8})
                            r.raise_for_status()
                        command=[str(ROOT/".gpu-venv/bin/python"),"benchmarks/inference/run.py","--base-url",PROXY,"--model",modelid,"--tokenizer",str(model),
                                 "--cli-profile","v0.10","--prompts",str(PROMPTS),"--concurrency",str(c),"--request-rate","10000","--input-len","256","--output-len","64",
                                 "--warmups","0","--fixed-lengths","--ignore-eos","--save-detailed","--seed",str(8400+rep),"--gpu-poll-s","0.25","--timeout-s","600",
                                 "--output-root",str(folder),"--run-id",runid]
                        with (folder/(runid+"-controller.log")).open("wb") as out:
                            exitcode=subprocess.run(command,cwd=ROOT,env=env,stdout=out,stderr=subprocess.STDOUT,timeout=650).returncode
                        result=read_trial(trial) if (trial/"status.json").exists() else {"status":"FAIL"}
                        trial.mkdir(exist_ok=True)
                        write_json(trial/"identity.json",{"model":label,"served_model":modelid,"model_sha256":digest,"source":source,"seed":8400+rep})
                        row={"model":label,"repeat":rep,"concurrency":c,"run_id":runid,"status":result["status"],"exit":exitcode,"result":result,"artifact_root":str(trial),"load_s":model_load}
                        records["attempts"].append(row)
                        if exitcode!=0 or result["status"]!="PASS":
                            records.update(status="FAILED");write_json(path,records);raise RuntimeError("Actual benchmark failed; attempt preserved")
                        records["trials"].append(row);write_json(path,records)
                        metrics=httpx.get(PROXY+"/metrics",timeout=5);metrics.raise_for_status()
                        (trial/"prometheus-metrics.txt").write_text(metrics.text)
                        print(json.dumps({"completed":runid,"requests":result["completed_requests"],"output_tokens_s":result["output_tokens_per_s"]}),flush=True)
                if label=="trained":
                    records["status"]="PASS";write_json(path,records)
                    release=release_gate("ModelOps-Qwen2.5-3B",1,PROXY,path,E/"release_decision.json")
                    write_json(folder/"release-health-snapshot.json",{"status":release["status"],"endpoint":PROXY,"model":modelid,"scope":"Actual live GPU serving at release-check time"})
                    print(json.dumps({"release_gate":release["status"]}),flush=True)
                (folder/(label+"-metrics-final.txt")).write_text(httpx.get(PROXY+"/metrics",timeout=5).text)
            finally:
                if proxy:
                    stop_owned(proxy,proxy_owned,"ops.observability.server")
                    if proxy_log:proxy_log.close()
                stop_owned(p,owned,"ops.platform_serving");gpu_log.close()
        records["status"]="PASS";write_json(path,records)
        print(json.dumps({"status":"PASS","trials":len(records["trials"]),"requests":sum(r["result"]["completed_requests"] for r in records["trials"])}),flush=True)

if __name__=="__main__":main()
