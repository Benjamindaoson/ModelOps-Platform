"""Bounded real Linux lifecycle validation; private evidence and ephemeral dev credentials."""
from __future__ import annotations
from pathlib import Path
import sys,threading,time,json,secrets,hashlib,hmac,os,subprocess,traceback
from datetime import datetime,timedelta,timezone
import httpx,jwt,uvicorn

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"control-plane"))

def sha(path):
    h=hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda:stream.read(1048576),b""):h.update(block)
    return h.hexdigest()

def main():
    evidence=ROOT/"Evidence/v1"; evidence.mkdir(parents=True,exist_ok=True)
    target=evidence/"llm-lifecycle.json"
    if target.exists() and json.loads(target.read_text()).get("status")=="PASS":
        print("Verified lifecycle already completed; no repeated GPU run.");return 0
    secret=secrets.token_urlsafe(48);signkey=secrets.token_urlsafe(48)
    os.environ.update(MODELOPS_AUTH_MODE="dev",MODELOPS_ENV="development",MODELOPS_RUNTIME="disabled",
      MODELOPS_JWT_SECRET=secret,MODELOPS_ATTESTATION_KEY=signkey,
      MODELOPS_DATABASE_URL="sqlite:///"+str(evidence/"modelops.sqlite"))
    from modelops.config import Settings
    from modelops.main import create_app
    from modelops.evidence import digest_report
    app=create_app(Settings(database_url="sqlite:///"+str(evidence/"modelops.sqlite"),
      runtime="linux",environment="development",auth_mode="dev",jwt_secret=secret,
      artifact_root=str(evidence/"runtime"),gpu_python=str(ROOT/".gpu-venv/bin/python")))
    server=uvicorn.Server(uvicorn.Config(app,host="127.0.0.1",port=18805,log_level="warning",access_log=False))
    threading.Thread(target=server.run,daemon=True).start()
    def auth(subject):
        now=datetime.now(timezone.utc)
        token=jwt.encode({"iss":"modelops-local","aud":"modelops-dev","sub":subject,
          "tenant":"lab","role":"admin","iat":now,"exp":now+timedelta(hours=2)},secret,algorithm="HS256")
        return {"Authorization":"Bearer "+token}
    client=httpx.Client(base_url="http://127.0.0.1:18805",headers=auth("v1-evaluation-controller"),timeout=60)
    records={"status":"RUNNING","runtime":"linux","scope":"single-host development; not Kubernetes or business SLO",
      "approval_scope":"separate development service principals, not independent human production approval",
      "events":[]}; deployment=None
    def save(): target.write_text(json.dumps(records,indent=2))
    def call(method,url,body=None,headers=None):
        response=client.request(method,url,json=body,headers=headers)
        if response.status_code>=400:
            raise RuntimeError(f"{method} {url}: {response.status_code} {response.text[:1000]}")
        return response.json() if response.content else {}
    def register(url,body):
        existing=[x for x in call("GET",url) if x.get("name")==body["name"] and x.get("version")==body["version"]]
        if existing:
            if len(existing)!=1 or existing[0]["digest"]!=body["digest"]:raise RuntimeError("Registry identity conflict")
            return existing[0]
        return call("POST",url,body)
    def wait_ready(key,label):
        started=time.perf_counter()
        for _ in range(120):
            d=call("GET","/api/v1/deployments/"+key)
            if d["runtime_verified"]:
                records["events"].append({"event":label,"generation":d["generation"],
                    "artifact_id":d["artifact_id"],"load_wall_s":time.perf_counter()-started,
                    "observed_phase":d["observed_phase"],"runtime_kind":d["runtime_kind"]})
                save();return d
            time.sleep(2)
        raise RuntimeError("Native model readiness timeout")
    def chat(d,prompt):
        t=time.perf_counter()
        response=httpx.post(d["endpoint"]+"/v1/chat/completions",timeout=60,json={
            "model":d["artifact_id"],"messages":[{"role":"user","content":prompt}],"max_tokens":16,"temperature":0})
        response.raise_for_status();data=response.json()
        if data["model"]!=d["artifact_id"] or not data["choices"][0]["message"]["content"]:raise RuntimeError("Wrong model/output")
        return {"artifact_id":data["model"],"elapsed_s":time.perf_counter()-t,"content":data["choices"][0]["message"]["content"],
            "usage":data.get("usage")}
    try:
        for _ in range(100):
            try:
                if client.get("/healthz").status_code==200:break
            except httpx.HTTPError:pass
            time.sleep(.1)
        history=json.loads((evidence/"native-qa-lifecycle.json").read_text())
        report=json.loads((evidence/"evaluation-shortqa/lora.json").read_text())
        run_id=history["jobs"][0]["job_id"]
        result=json.loads((evidence/"runtime/lab"/run_id/"artifacts/result.json").read_text())
        base=history["base"];candidate=register("/api/v1/models",{
            "name":"qwen-base","version":2,"source":base["source"],
            "revision":"v1qa-"+result["checkpoint_sha256"][:16],"digest":report["artifact_sha256"],
            "model_type":"llm","framework":"transformers","task_type":"short-answer-qa",
            "base_model":base["source"]+"@"+base["revision"],"adapter_type":"lora",
            "adapter_uri":Path(result["adapter"]).as_uri(),
            "artifact_uri":Path(report["candidate_path"]).as_uri(),"training_run_id":run_id})
        heldout=evidence/"evaluation-shortqa/heldout.jsonl"
        dataset=register("/api/v1/datasets",{"name":"dolly-shortqa-heldout","version":1,"uri":heldout.as_uri(),
            "digest":sha(heldout),"train_count":0,"heldout_count":24})
        signature=hmac.new(signkey.encode(),digest_report(report).encode(),hashlib.sha256).hexdigest()
        evaluation=call("POST","/api/v1/evaluations/attest",{
          "artifact_id":candidate["id"],"dataset_id":dataset["id"],"report":report},
          {"X-ModelOps-Attestation":signature,**auth("v1-evaluation-controller")})
        if not evaluation["passed"]:raise RuntimeError("Unchanged release gate rejected candidate")
        approval=call("POST","/api/v1/approvals",{"artifact_id":candidate["id"],"evaluation_id":evaluation["id"],
          "reason":"Bounded heldout gate passed; development lifecycle validation only"},
          auth("v1-release-controller"))
        records.update(training_run_id=run_id,base_model=base,candidate=candidate,dataset=dataset,evaluation=evaluation,approval=approval)
        deployment=call("POST","/api/v1/deployments",{"name":"qwen-lifecycle-v1","artifact_id":base["id"],
            "engine":"vllm","replicas":1,"gpu":1})
        save()
        d=wait_ready(deployment["id"],"base_ready")
        records["base_api"]=chat(d,"What is the capital of France? Answer with one city name.");save()
        d=call("POST","/api/v1/deployments/"+d["id"]+"/promote",{
            "artifact_id":candidate["id"],"approval_id":approval["id"],"expected_generation":d["generation"]})
        d=wait_ready(d["id"],"candidate_ready")
        records["candidate_api"]=chat(d,"What is the capital of France? Answer with one city name.")
        records["candidate_warmup"]=chat(d,"What is the capital of Japan? Answer with one city name.");save()
        env=os.environ.copy();env["PATH"]=str(ROOT/".gpu-venv/bin")+os.pathsep+env.get("PATH","")
        env.pop("LD_LIBRARY_PATH",None)
        benchmark=[str(ROOT/".gpu-venv/bin/python"),"benchmarks/inference/run.py",
            "--base-url",d["endpoint"],"--model",candidate["id"],"--tokenizer",str(ROOT/".tools/assets/qwen-base"),
            "--cli-profile","v0.10","--prompts","40","--concurrency","4","--request-rate","8",
            "--input-len","64","--output-len","32","--warmups","0","--gpu-poll-s","0.25",
            "--timeout-s","300","--output-root",str(evidence/"benchmark"),"--run-id","qwen-qa-v1"]
        with (evidence/"benchmark-controller.log").open("w") as log:
            bench=subprocess.run(benchmark,cwd=ROOT,env=env,stdout=log,stderr=subprocess.STDOUT,timeout=340)
        records["benchmark_exit"]=bench.returncode;save()
        d=call("POST","/api/v1/deployments/"+d["id"]+"/rollback",{"replicas":1,"expected_generation":d["generation"]})
        d=wait_ready(d["id"],"rollback_ready")
        records["rollback_api"]=chat(d,"What is the capital of France? Answer with one city name.")
        if d["artifact_id"]!=base["id"]:raise RuntimeError("Rollback identity mismatch")
        records["status"]="PASS" if bench.returncode==0 else "LIFECYCLE_PASS_BENCHMARK_FAILED"
        records["completed_at_utc"]=datetime.now(timezone.utc).isoformat()
        save();print(records["status"],flush=True)
        return int(bench.returncode!=0)
    except Exception as exc:
        records.update(status="FAILED",error=type(exc).__name__+": "+str(exc))
        save();traceback.print_exc();return 1
    finally:
        if deployment:
            try: records["cleanup"]=call("DELETE","/api/v1/deployments/"+deployment["id"]);save()
            except Exception as exc:records["cleanup_error"]=str(exc);save()
        client.close();server.should_exit=True
if __name__=="__main__":raise SystemExit(main())
