"""Actual fail-closed loading/API faults and regressions against saved measurements."""
import json,time,copy
from pathlib import Path
from .runtime import ROOT,E,Server
from .contracts import digest
from pipelines.training.data_contract import verify_model_bundle
from ops.dev_control import control_session
from ops.model_release_gate.hardening import validate_observed_trial,quality_decision,version_decision

def main():
    folder=E/"release";folder.mkdir(exist_ok=True);out=folder/"regression.json";spec={"source_sha":digest(Path(__file__)),"model_sha":digest(ROOT/".tools/assets/qwen3b-base/modelops-files.json")}
    if out.exists():
        old=json.loads(out.read_text())
        if old.get("status")=="PASS" and old.get("identity")==spec:return
    records=[]
    measured=json.loads((E/"engine-progress.json").read_text());row=next(r for r in measured["trials"] if r["id"]=="vllm-A-c4-r0")
    for label,bad in [("missing-telemetry",{**row,"gpu_samples":0}),("latency-regression",{**row,"latency":{**row["latency"],"ttft_ms":{**row["latency"]["ttft_ms"],"p95":row["latency"]["ttft_ms"]["p95"]*3}}}),("throughput-regression",{**row,"output_tokens_s":row["output_tokens_s"]*.5}),("wrong-loaded-version",{**row,"config":{**row["config"],"model_sha":"intentional-wrong-expected"}})]:
        decision=validate_observed_trial(bad,spec["model_sha"],row)
        records.append({"case":label,"status":"PASS" if decision["status"]=="FAIL" else "FAIL","scope":"Faulted audit input against real saved GPU trial","decision":decision})
    baseline=json.loads((E/"quantization/progress.json").read_text()).get("models",{}).get("fp16",{}).get("quality",{})
    q=copy.deepcopy(baseline)
    if "groups" in q:
        q["groups"]["squad128"]["token_f1"]=max(0,q["groups"]["squad128"]["token_f1"]-.1)
        decision=quality_decision(baseline,q)
        records.append({"case":"quality-regression","status":"PASS" if decision["status"]=="FAIL" else "FAIL","scope":"Faulted metric input, not a fabricated model result","decision":decision})
    try:
        with control_session(ROOT,"hardening-negative-rollback","Evidence/inference-hardening") as c:
            models=c.get("/api/v1/models");models.raise_for_status();base=next(x for x in models.json() if x["name"]=="hardening-qwen3b-base")
            existing=c.get("/api/v1/deployments");existing.raise_for_status()
            match=next((x for x in existing.json() if x["name"]=="hardening-rollback-negative" and x.get("intent")!="deleted"),None)
            if match:d=match
            else:
                r=c.post("/api/v1/deployments",json={"name":"hardening-rollback-negative","artifact_id":base["id"],"engine":"vllm","replicas":0,"gpu":1});r.raise_for_status();d=r.json()
            statuses=[]
            for _ in range(2):statuses.append(c.post("/api/v1/deployments/"+d["id"]+"/rollback",json={"replicas":0,"expected_generation":d["generation"]}).status_code)
            records.append({"case":"rollback-target-unavailable","status":"PASS" if statuses==[409,409] else "FAIL","http_status":statuses,"scope":"Actual control-plane API; replicas0, no GPU deployment"})
            r=c.delete("/api/v1/deployments/"+d["id"]);r.raise_for_status()
    except Exception as exc:records.append({"case":"rollback-target-unavailable","status":"FAIL","error":str(exc)})
    cfg={**row["config"],"label":"fault-incompatible-gptq","quantization":"gptq","kv_cache_bytes":3*1024**3}
    try:
        with Server(cfg):records.append({"case":"incompatible-model-load","status":"FAIL","reason":"Incorrect GPTQ declaration unexpectedly loaded FP16 package"})
    except Exception as exc:
        log=E/"servers/fault-incompatible-gptq/server.log";text=log.read_text() if log.exists() else ""
        expected=any(x in text.lower() for x in ["quantization","gptq","quantize"])
        records.append({"case":"incompatible-model-load","status":"PASS" if expected else "FAIL","actual_error":str(exc),"log":str(log),"log_sha":digest(log) if log.exists() else None,"scope":"Real native loader rejects wrong quantization metadata; official weights unchanged"})
    # Manifest hash fault verifies real official bytes, without copying/corrupting model weights.
    actual=digest(ROOT/".tools/assets/qwen3b-base/modelops-files.json")
    try:
        verify_model_bundle(ROOT/".tools/assets/qwen3b-base","fault-injected-wrong-hash");rejected=False
    except ValueError:rejected=True
    records.append({"case":"artifact-hash-mismatch","status":"PASS" if rejected else "FAIL","actual":actual,"expected":"fault-injected-wrong-hash","scope":"Actual immutable loader rejects bad manifest identity; original artifact unchanged"})
    result={"identity":spec,"status":"PASS" if len(records)==8 and all(r["status"]=="PASS" for r in records) else "FAIL","cases":records,"threshold_scope":"Engineering baseline regression15%, bounded QA delta-.02; no production business SLO"}
    out.write_text(json.dumps(result,indent=2));print("RELEASE_REGRESSIONS "+result["status"],flush=True)
if __name__=="__main__":main()
