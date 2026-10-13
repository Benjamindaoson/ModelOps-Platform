"""Reuse native ModelOps release APIs for the real 3B checkpoint; no Kubernetes."""
from pathlib import Path
from datetime import datetime,timedelta,timezone
import os,json,secrets,time,hashlib,hmac
import httpx,jwt
from ops.dev_control import control_session
from ops.run_llm_validation import register
from ops.mlflow_validation import tracking_client
from pipelines.training.data_contract import sha256,write_json
ROOT=Path(__file__).resolve().parents[1];E=ROOT/"Evidence/llm-production-validation"
def main():
    target=E/"lifecycle.json"
    if target.exists() and json.loads(target.read_text()).get("status")=="PASS":
        print("Existing real lifecycle retained; no duplicate GPU deployment");return
    training=json.loads((E/"training-finished.json").read_text())
    report=json.loads((E/"evaluation/evaluation.json").read_text())
    key=secrets.token_urlsafe(48);previous=os.environ.get("MODELOPS_ATTESTATION_KEY")
    os.environ["MODELOPS_ATTESTATION_KEY"]=key
    record={"status":"RUNNING","scope":"Native Linux development validation; Kubernetes explicitly out of scope","events":[]}
    deployment=None
    try:
      with control_session(ROOT,"llm-evaluation-controller","Evidence/llm-production-validation") as c:
        def call(method,path,body=None,headers=None):
            r=c.request(method,path,json=body,headers=headers);r.raise_for_status();return r.json() if r.content else {}
        def auth(subject):
            now=datetime.now(timezone.utc)
            token=jwt.encode({"iss":"modelops-local","aud":"modelops-dev","sub":subject,"tenant":"lab","role":"admin","iat":now,"exp":now+timedelta(hours=2)},os.environ["MODELOPS_JWT_SECRET"],algorithm="HS256")
            return {"Authorization":"Bearer "+token}
        def ready(identity,label):
            tick=time.perf_counter()
            for _ in range(180):
                d=call("GET","/api/v1/deployments/"+identity)
                if d["runtime_verified"]:
                    record["events"].append({"event":label,"generation":d["generation"],"artifact_id":d["artifact_id"],"load_wall_s":time.perf_counter()-tick})
                    write_json(target,record);return d
                time.sleep(2)
            raise RuntimeError("Real vLLM readiness timed out")
        def chat(d):
            r=httpx.post(d["endpoint"]+"/v1/chat/completions",timeout=90,json={"model":d["artifact_id"],"messages":[{"role":"user","content":"What is the capital of France? Answer with one city name."}],"max_tokens":16,"temperature":0})
            r.raise_for_status();x=r.json()
            if x["model"]!=d["artifact_id"] or not x["choices"][0]["message"]["content"]:raise ValueError("Model identity/output mismatch")
            return x
        candidate=register(c,"/api/v1/models",{"name":"qwen2-5-3b-qlora","version":2,"source":training["config"]["model"],
            "revision":training["config"]["revision"],"digest":report["artifact_sha256"],"model_type":"llm","framework":"transformers",
            "task_type":"short_answer","base_model":training["base"]["id"],"adapter_type":"qlora",
            "adapter_uri":Path(training["result"]["adapter"]).as_uri(),"artifact_uri":Path(report["candidate_path"]).as_uri(),"training_run_id":training["job"]["id"]})
        data=register(c,"/api/v1/datasets",{"name":"dolly-shortqa-3b-heldout","version":1,"uri":(E/"evaluation/heldout.jsonl").as_uri(),
            "digest":report["heldout_sha256"],"train_count":0,"heldout_count":24})
        from modelops.evidence import digest_report
        signature=hmac.new(key.encode(),digest_report(report).encode(),hashlib.sha256).hexdigest()
        evaluation=call("POST","/api/v1/evaluations/attest",{"artifact_id":candidate["id"],"dataset_id":data["id"],"report":report},{"X-ModelOps-Attestation":signature})
        record.update(base=training["base"],candidate=candidate,heldout=data,evaluation=evaluation,training_run_id=training["job"]["id"])
        m,_=tracking_client();rid=training["tracking"]["run_id"]
        for k,v in report["metrics"].items():m.log_metric(rid,"evaluation."+k,float(v))
        m.set_tag(rid,"modelops.evaluation_id",evaluation["id"])
        m.set_model_version_tag(training["mlflow_model"]["name"],training["mlflow_model"]["version"],"evaluation_passed",str(evaluation["passed"]).lower())
        m.set_model_version_tag(training["mlflow_model"]["name"],training["mlflow_model"]["version"],"modelops.serving_artifact_id",candidate["id"])
        write_json(target,record)
        if not evaluation["passed"]:raise RuntimeError("Unchanged quality gate rejected candidate; no promotion")
        approval=call("POST","/api/v1/approvals",{"artifact_id":candidate["id"],"evaluation_id":evaluation["id"],"reason":"Frozen independent heldout gate passed for bounded native validation"},auth("llm-release-controller"))
        record["approval"]=approval
        d=call("POST","/api/v1/deployments",{"name":"qwen3b-validation-v1","artifact_id":training["base"]["id"],"engine":"vllm","replicas":1,"gpu":1})
        deployment=d["id"];record["deployment_id"]=deployment;write_json(target,record)
        d=ready(deployment,"base_ready");record["base_api"]=chat(d)
        d=call("POST","/api/v1/deployments/"+deployment+"/promote",{"artifact_id":candidate["id"],"approval_id":approval["id"],"expected_generation":d["generation"]},auth("llm-release-controller"))
        d=ready(deployment,"trained_candidate_ready");record["candidate_api"]=chat(d)
        write_json(E/"api_response.json",record["candidate_api"])
        m.set_registered_model_alias(training["mlflow_model"]["name"],"validated-candidate",training["mlflow_model"]["version"])
        d=call("POST","/api/v1/deployments/"+deployment+"/rollback",{"replicas":1,"expected_generation":d["generation"]},auth("llm-release-controller"))
        d=ready(deployment,"rollback_base_ready");record["rollback_api"]=chat(d)
        if d["artifact_id"]!=training["base"]["id"]:raise ValueError("Rollback did not restore base model identity")
        record.update(status="PASS",finished=datetime.now(timezone.utc).isoformat(),modelops_models_api=call("GET","/api/v1/models"))
        write_json(target,record)
        call("DELETE","/api/v1/deployments/"+deployment);deployment=None
        print("REAL_3B_REGISTER_EVALUATE_SERVE_ROLLBACK_PASS",flush=True)
    finally:
        if previous is None:os.environ.pop("MODELOPS_ATTESTATION_KEY",None)
        else:os.environ["MODELOPS_ATTESTATION_KEY"]=previous
if __name__=="__main__":main()
