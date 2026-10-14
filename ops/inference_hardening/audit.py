"""Reconstruct saved benchmark/QA metrics without new inference or training."""
import json,statistics,math
from pathlib import Path
from .runtime import ROOT,E
from .contracts import digest
from .report import verify
from .quality import quality_rows
from pipelines.evaluation.run import score
from pipelines.training.data_contract import verify_model_bundle
from ops.mlflow_validation import verified_training_artifacts,tracking_client

def read(path):return json.loads(Path(path).read_text())
def audit_quality(folder,receipt):
    raw=folder/"outputs.jsonl";errors=[]
    if digest(raw)!=receipt["raw_sha"]:errors.append("quality hash")
    rows=[json.loads(x) for x in raw.read_text().splitlines()]
    expected={(r["group"],r["id"]):r for r in quality_rows()}
    if len(rows)!=152 or len({(r["group"],r["id"]) for r in rows})!=152:errors.append("quality coverage")
    recomputed={}
    for row in rows:
        identity=(row["group"],row["id"])
        source=expected.get(identity)
        if not source or row.get("error") or source["prompt"]!=row["prompt"] or source["references"]!=row["references"]:errors.append("quality input/generation");continue
        values=[score(r,row["output"]) for r in source["references"]]
        em=max(v[0] for v in values);f1=max(v[1] for v in values)
        if not math.isclose(em,row["em"],abs_tol=1e-12) or not math.isclose(f1,row["f1"],abs_tol=1e-12):errors.append("quality scoring")
        recomputed.setdefault(row["group"],[]).append((em,f1))
    for group,values in recomputed.items():
        saved=receipt["groups"][group]
        if len(values)!=saved["samples"] or not math.isclose(statistics.mean(x[1] for x in values),saved["token_f1"],abs_tol=1e-12) or not math.isclose(statistics.mean(x[0] for x in values),saved["exact_match"],abs_tol=1e-12):errors.append("quality aggregate")
    return errors

def main():
    (E/"independent-audit.json").write_text(json.dumps({"status":"BLOCKED","reason":"Fresh audit started; no stale pass reused"}))
    failures=[];counts={};engine=read(E/"engine-progress.json")
    rows=engine["trials"];counts["engine_trials"]=len({r["id"] for r in rows if verify(r)})
    if counts["engine_trials"]!=90:failures.append("engine coverage")
    q=read(E/"quantization/progress.json")
    for name,model in q["models"].items():
        valid=[r for r in model["trials"] if verify(r)];counts[name+"_quant_trials"]=len({r["id"] for r in valid})
        if counts[name+"_quant_trials"]!=21:failures.append(name+" performance coverage")
        failures += [name+":"+s for s in audit_quality(E/"quantization"/name/"quality",model["quality"])]
        folder=ROOT/".tools/assets/qwen3b-base" if name=="fp16" else E/"quantization"/name/"model"
        verify_model_bundle(folder,digest(folder/"modelops-files.json"))
    tuning=read(E/"tuning/progress.json");counts["tuning_trials"]=len({(r["engine"],r["variant"],r["repeat"]) for r in tuning["trials"] if verify(r)})
    if counts["tuning_trials"]!=18:failures.append("tuning coverage")
    failures+=["sglang baseline:"+s for s in audit_quality(E/"tuning/sglang-quality",tuning["baseline_quality"])]
    profile=read(E/"profiling/progress.json");counts["prefix_trials"]=len(profile["trials"])
    if counts["prefix_trials"]!=6 or not all(verify(r) for r in profile["trials"]):failures.append("prefix coverage/hash")
    for p in profile["trace"]["traces"]:
        if digest(p["path"])!=p["sha256"]:failures.append("trace changed")
    trained=read(E/"training/progress.json")
    for label,r in trained["runs"].items():
        verified_training_artifacts(r["result"],E)
        steps=[json.loads(x) for x in (Path(r["result"]["adapter"]).parent/"steps.jsonl").read_text().splitlines()]
        if [x["step"] for x in steps]!=list(range(1,65)):failures.append(label+" step continuity")
        failures += [label+":"+s for s in audit_quality(E/"training"/label/"quality",r["quality"])]
        client,_=tracking_client();v=client.get_model_version(r["mlflow_model"]["name"],r["mlflow_model"]["version"])
        if v.run_id!=r["tracking"]["run_id"] or v.tags["checkpoint_sha256"]!=r["result"]["checkpoint_sha256"]:failures.append(label+" registry binding")
        if r["online_version_binding"]["status"]!="PASS" or not r["evaluation_attestation"]["verified"]:failures.append(label+" online/attestation")
    counts["training_updates"]=sum(r["result"]["steps"] for r in trained["runs"].values())
    counts["formal_benchmark_requests"]=(counts["engine_trials"]+sum(counts[n+"_quant_trials"] for n in q["models"])+counts["tuning_trials"]+counts["prefix_trials"])*32
    counts["quality_requests"]=152*(len(q["models"])+len(trained["runs"])+1)
    result={"status":"PASS" if not failures else "FAIL","counts":counts,"failures":failures,"scope":"Separate reconstruction of private raw data, no new GPU experiment","source_sha":digest(Path(__file__)),"same_merged_checkpoint_sha":len({r["result"]["checkpoint_sha256"] for r in trained["runs"].values()})==1,"quality_variation_note":"Identical checkpoint SHA still produced minor Dolly24 score differences. Cause not independently isolated; do not interpret as training improvement."}
    (E/"independent-audit.json").write_text(json.dumps(result,indent=2)+"\n");print(json.dumps(result),flush=True)
if __name__=="__main__":main()
