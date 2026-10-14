"""Resolve a real MLflow version and emit a hash-bound release decision."""
import argparse
import hashlib
import json
from pathlib import Path
import statistics
from datetime import datetime, timezone
import httpx
from ops.model_release_gate.gate import decide, GatePolicy, sha256
from ops.gpu_runtime_validation import validate_probe_url
from ops.mlflow_validation import tracking_client
from ops.benchmark_llm_validation import read_trial
from pipelines.evaluation.run import quality_gate

ROOT=Path(__file__).resolve().parents[2]
E=ROOT/"Evidence/llm-platform-finalization"


def benchmark_evidence(path, identity):
    report=json.loads(Path(path).read_text())
    if report["status"]!="PASS":raise ValueError("Comparison not complete")
    rows=[r for r in report["trials"] if r["model"]=="trained" and r["concurrency"]==4 and r["status"]=="PASS"]
    if len(rows)!=3 or {r["repeat"] for r in rows}!={0,1,2}:raise ValueError("Incomplete repeated benchmark")
    measured=[]
    hashes=[]
    for row in rows:
        folder=Path(row["artifact_root"]).resolve()
        if not folder.is_relative_to((E/"comparison").resolve()):raise ValueError("Unowned benchmark")
        frozen=json.loads((folder/"identity.json").read_text())
        if frozen["model_sha256"]!=identity["checkpoint_sha256"]:raise ValueError("Wrong benchmark weights")
        current=read_trial(folder)
        if current["raw_sha256"]!=row["result"]["raw_sha256"]:raise ValueError("Benchmark changed")
        measured.append(current)
        hashes.append({"path":str(folder),"raw_sha256":current["raw_sha256"],"status_sha256":current["status_sha256"]})
    return {"model_sha256":identity["checkpoint_sha256"],"requests":sum(r["completed_requests"] for r in measured),"repeats":3,"concurrency":4,
            "output_tokens_s":statistics.mean(r["output_tokens_per_s"] for r in measured),
            "ttft_p95_ms":statistics.mean(r["latency_ms"]["p95_ttft_ms"] for r in measured),
            "latency_p95_ms":statistics.mean(r["latency_ms"]["p95_e2el_ms"] for r in measured),"raw_evidence":hashes}


def run(model, version, base_url, comparison, output):
    E.mkdir(parents=True,exist_ok=True)
    checks={k:False for k in ("artifact","evaluation","serving","benchmark")}
    evidence={}
    try:
        client,_=tracking_client()
        registered=client.get_model_version(model,str(version))
        if registered.status!="READY":raise ValueError("Registered version not READY")
        training=json.loads((ROOT/"experiments/training/metrics.json").read_text())
        run_record=client.get_run(registered.run_id)
        if run_record.data.tags.get("modelops.training_run_id")!=training["run_id"]:raise ValueError("Training lineage mismatch")
        identity={"model":registered.name,"version":int(registered.version),"run_id":registered.run_id,
                  "checkpoint_sha256":registered.tags["checkpoint_sha256"],"adapter_sha256":registered.tags["adapter_sha256"]}
        folder=ROOT/"Evidence/llm-production-validation/evaluation"
        candidate=Path(training["checkpoint"]).parent
        quality=quality_gate(folder/"evaluation.json",candidate,folder/"heldout.jsonl",folder/"train.jsonl",
                             E/"release-quality-approval.json",24,0.55,-0.02)
        evaluation=json.loads((folder/"evaluation.json").read_text())
        life=json.loads((ROOT/"Evidence/llm-production-validation/lifecycle.json").read_text())
        expected=life["candidate"]["id"]
        if life["training_run_id"]!=training["run_id"]:raise ValueError("Serving lineage mismatch")
        url=validate_probe_url(base_url)
        r=httpx.get(url+"/health",timeout=5)
        models=httpx.get(url+"/v1/models",timeout=5);models.raise_for_status()
        serving={"healthy":r.status_code==200,"expected_model":expected,"loaded_models":[x["id"] for x in models.json()["data"]]}
        benchmark=benchmark_evidence(comparison,identity)
        decision=decide(identity,training,evaluation,benchmark,serving)
        evidence={"checkpoint":training["checkpoint_sha256"],"adapter":training["adapter_sha256"],
                  "evaluation_report":sha256(folder/"evaluation.json"),"quality_approval":quality,
                  "comparison_manifest":sha256(comparison),"benchmark":benchmark,"serving":serving}
        decision.update(evidence=evidence,at_utc=datetime.now(timezone.utc).isoformat(),scope="Development release eligibility; not enterprise OIDC/GPU-Docker approval")
    except Exception as exc:
        decision={"model":model,"version":version,"status":"FAIL","checks":checks,"errors":{"resolution":type(exc).__name__+": "+str(exc)},
                  "scope":"Fail-closed development release eligibility"}
    output=Path(output);output.parent.mkdir(parents=True,exist_ok=True)
    output.write_text(json.dumps(decision,indent=2,allow_nan=False)+"\n")
    if decision["status"]=="PASS":
        client.set_model_version_tag(model,str(version),"modelops.release_gate_status","PASS")
        client.set_model_version_tag(model,str(version),"modelops.release_decision_sha256",sha256(output))
    return decision


def main():
    p=argparse.ArgumentParser()
    p.add_argument("--model",default="ModelOps-Qwen2.5-3B");p.add_argument("--version",type=int,default=1)
    p.add_argument("--base-url",required=True);p.add_argument("--comparison",default=str(E/"comparison/progress.json"))
    p.add_argument("--output",default=str(E/"release_decision.json"))
    a=p.parse_args();r=run(a.model,a.version,a.base_url,a.comparison,a.output)
    print(json.dumps({"model":a.model,"version":a.version,"status":r["status"],"checks":r["checks"]}))
    return 0 if r["status"]=="PASS" else 1


if __name__=="__main__":raise SystemExit(main())
