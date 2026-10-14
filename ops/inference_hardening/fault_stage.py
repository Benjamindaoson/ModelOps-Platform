"""Bounded faults against owned actual GPU serving; no formal checkpoint touched."""
import json,os,signal,subprocess,time,traceback
from pathlib import Path
import httpx
from .runtime import ROOT,E,Server
from .contracts import digest

def main():
    folder=E/"faults";folder.mkdir(exist_ok=True);path=folder/"actual.json"
    if path.exists() and json.loads(path.read_text()).get("status")=="PASS":return
    records=[];cfg={"engine":"vllm","model":str(ROOT/".tools/assets/qwen3b-base"),"model_sha":digest(ROOT/".tools/assets/qwen3b-base/modelops-files.json"),"name":"modelops-frozen-qwen3b","label":"fault-owned","port":19801,"memory_fraction":.7,"max_context":4096,"max_sequences":64,"batch_tokens":2048,"prefix_cache":False,"kv_cache_bytes":3*1024**3}
    prompt={"model":cfg["name"],"prompt":"2 + 2 =","max_tokens":8,"temperature":0,"seed":9001}
    original=None
    try:
        with Server(cfg) as server:
            r=httpx.post(server.url+"/v1/completions",json=prompt,timeout=60);r.raise_for_status();original=r.json()["choices"][0]["text"]
            for name,body in [("model-version-mismatch",{**prompt,"model":"not-loaded"}),("invalid-token-budget",{**prompt,"max_tokens":-1})]:
                r=httpx.post(server.url+"/v1/completions",json=body,timeout=10)
                records.append({"fault":name,"status":"PASS" if 400<=r.status_code<500 else "FAIL","http_status":r.status_code})
            try:
                httpx.post(server.url+"/v1/completions",json=prompt,timeout=.000001)
                records.append({"fault":"request-timeout","status":"FAIL"})
            except httpx.TimeoutException as ex:records.append({"fault":"request-timeout","status":"PASS","observed":type(ex).__name__})
            with httpx.stream("POST",server.url+"/v1/completions",json={**prompt,"stream":True,"max_tokens":64},timeout=30) as r:
                r.raise_for_status()
                for line in r.iter_lines():
                    if line.startswith("data:") and "choices" in line:break
            r=httpx.post(server.url+"/v1/completions",json=prompt,timeout=30)
            records.append({"fault":"client-stream-disconnect","status":"PASS" if r.status_code==200 and r.json()["choices"][0]["text"]==original else "FAIL","recovery_http_status":r.status_code})
            # Owned group only: simulate a crashed GPU engine, then rebuild same immutable model.
            os.killpg(os.getpgid(server.p.pid),signal.SIGTERM);time.sleep(3)
            try:r=httpx.get(server.url+"/v1/models",timeout=2);unavailable=r.status_code!=200
            except httpx.HTTPError:unavailable=True
            records.append({"fault":"owned-worker-crash","status":"PASS" if unavailable else "FAIL"})
        with Server({**cfg,"label":"fault-recovered"}) as server:
            r=httpx.post(server.url+"/v1/completions",json=prompt,timeout=60);r.raise_for_status()
            records.append({"fault":"same-version-restart","status":"PASS" if r.json()["choices"][0]["text"]==original else "FAIL","model_sha":cfg["model_sha"]})
        program="import torch,json;\ntry:\n x=torch.empty(torch.cuda.get_device_properties(0).total_memory*2,dtype=torch.uint8,device='cuda');print(json.dumps({'status':'FAIL','reason':'Unexpected allocation'}))\nexcept torch.cuda.OutOfMemoryError as ex:print(json.dumps({'status':'PASS','observed':'CUDA OutOfMemoryError','recovered':bool(torch.isfinite(torch.ones(1,device='cuda')).all())}))"
        p=subprocess.run([str(ROOT/".gpu-venv/bin/python"),"-m","ops.locked_exec","--",str(ROOT/".gpu-venv/bin/python"),"-c",program],cwd=ROOT,capture_output=True,text=True,timeout=60)
        (folder/"oom.log").write_text(p.stdout+p.stderr)
        rec=json.loads(p.stdout.splitlines()[-1]) if p.returncode==0 else {"status":"FAIL","returncode":p.returncode}
        records.append({"fault":"isolated-real-CUDA-OOM",**rec})
    except Exception as exc:
        records.append({"fault":"controller","status":"FAIL","error":str(exc)});(folder/"failure.log").write_text(traceback.format_exc())
    path.write_text(json.dumps({"status":"PASS" if len(records)==7 and all(r["status"]=="PASS" for r in records) else "FAIL","faults":records,"scope":"Actual isolated GPU faults; digest/rollback predicates tested separately on CPU, no business HA claim"},indent=2))
if __name__=="__main__":main()
