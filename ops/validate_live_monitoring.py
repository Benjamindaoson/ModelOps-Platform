"""Bounded actual GPU serving + native monitoring check; no training or benchmark rerun."""
import json, os, subprocess, time
from pathlib import Path
import httpx, psutil
from ops.run_model_comparison import (comparison_environment, available, wait_ready, stop_owned, ROOT, E, UPSTREAM, PROXY)
from ops.model_release_gate.__main__ import run as release_gate
from pipelines.training.data_contract import write_json

def main():
    folder=E/"monitoring";folder.mkdir(exist_ok=True)
    if (folder/"live-validation.json").exists():
        old=json.loads((folder/"live-validation.json").read_text())
        if old.get("status")=="PASS":
            print("Completed actual live monitoring evidence reused");return
    train=json.loads((ROOT/"Evidence/llm-production-validation/training-finished.json").read_text())["result"]
    life=json.loads((ROOT/"Evidence/llm-production-validation/lifecycle.json").read_text())
    modelid=life["candidate"]["id"]
    env=comparison_environment(ROOT,Path(train["checkpoint"]).parent,modelid,train["checkpoint_sha256"])
    available(19782);available(19780)
    log=(folder/"live-serving.log").open("ab");proxy=None
    p=subprocess.Popen([str(ROOT/".gpu-venv/bin/python"),"-m","ops.locked_exec","--",str(ROOT/".gpu-venv/bin/python"),"-m","ops.platform_serving"],
                       cwd=ROOT,env=env,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
    owned={"pid":p.pid,"create_time":psutil.Process(p.pid).create_time()}
    start=time.perf_counter()
    try:
        load_s=wait_ready(p,UPSTREAM,modelid)
        proxylog=(folder/"live-proxy.log").open("ab")
        proxy=subprocess.Popen([str(ROOT/".venv/bin/python"),"-m","ops.observability.server","--upstream",UPSTREAM,"--port","19780","--version","trained-monitoring"],
                               cwd=ROOT,env=env,stdout=proxylog,stderr=subprocess.STDOUT,start_new_session=True)
        proxyowned={"pid":proxy.pid,"create_time":psutil.Process(proxy.pid).create_time()}
        wait_ready(proxy,PROXY,modelid)
        responses=[]
        for prompt in ["What is the capital of France? Answer briefly.","Name a primary color."]:
            payload={"model":modelid,"messages":[{"role":"user","content":prompt}],"temperature":0,"max_tokens":24,"stream":True,"stream_options":{"include_usage":True}}
            with httpx.stream("POST",PROXY+"/v1/chat/completions",json=payload,timeout=60) as r:
                r.raise_for_status();body=b"".join(r.iter_bytes()).decode()
            if '"completion_tokens"' not in body:raise ValueError("Actual usage missing")
            responses.append({"prompt":prompt,"sse":body})
        write_json(folder/"live-api-response.json",{"scope":"Actual GPU model inference","model":modelid,"responses":responses})
        (folder/"live-metrics.txt").write_text(httpx.get(PROXY+"/metrics",timeout=10).text)
        queries={}
        names=["modelops_inference_requests_total","modelops_inference_ttft_seconds_count","modelops_gpu_utilization_percent","modelops_gpu_memory_used_bytes","modelops_gpu_temperature_celsius"]
        for _ in range(6):
            for name in names:
                r=httpx.get("http://127.0.0.1:19790/api/v1/query",params={"query":name},timeout=10);r.raise_for_status()
                queries[name]=r.json()
            if all(x["data"]["result"] for x in queries.values()):break
            time.sleep(10)
        if not all(x["data"]["result"] for x in queries.values()):raise ValueError("Prometheus scrape missing actual metrics")
        health=httpx.get("http://127.0.0.1:19791/api/health",timeout=10);health.raise_for_status()
        dashboard=httpx.get("http://127.0.0.1:19791/api/dashboards/uid/modelops-production",timeout=10)
        if dashboard.status_code!=200:
            uid=json.loads((ROOT/"deploy/monitoring/modelops-dashboard.json").read_text())["uid"]
            dashboard=httpx.get("http://127.0.0.1:19791/api/dashboards/uid/"+uid,timeout=10)
        dashboard.raise_for_status()
        decision=release_gate("ModelOps-Qwen2.5-3B",1,PROXY,E/"comparison/progress.json",E/"release_decision.json")
        if decision["status"]!="PASS":raise ValueError("Real release gate failed")
        write_json(folder/"live-validation.json",{"status":"PASS","scope":"Native CPU Prometheus/Grafana + actual GPU vLLM; not Docker",
            "model":modelid,"checkpoint_sha256":train["checkpoint_sha256"],"actual_requests":2,"model_load_s":load_s,
            "wall_s":time.perf_counter()-start,"queries":queries,"grafana_health":health.json(),
            "dashboard_uid":dashboard.json()["dashboard"]["uid"],"release_gate":decision["status"]})
        print("Actual GPU monitoring and release validation PASS",flush=True)
    finally:
        if proxy:stop_owned(proxy,proxyowned,"ops.observability.server")
        stop_owned(p,owned,"ops.platform_serving")
        log.close()

if __name__=="__main__":main()
