"""Bounded recipe-driven native training. Completed runs are verified and reused."""
from pathlib import Path
import argparse,json,time
import yaml
from ops.dev_control import control_session
from pipelines.training.data_contract import sha256,validate_manifest
ROOT=Path(__file__).resolve().parents[1]
E=ROOT/"Evidence/v1"
def main():
    p=argparse.ArgumentParser();p.add_argument("--dataset",choices=["broad","shortqa"],default="broad")
    a=p.parse_args()
    target=E/("native-qa-training-finished.json" if a.dataset=="shortqa" else "native-training-finished.json")
    if target.exists():
        records=json.loads(target.read_text())
        for item in records["jobs"]:
            result=json.loads((E/"runtime/lab"/item["job_id"]/"artifacts/result.json").read_text())
            if result["status"]!="COMPLETED" or sha256(result["checkpoint"])!=result["checkpoint_sha256"]:
                raise RuntimeError("Existing completion receipt does not verify")
        print("Existing real GPU runs verified; no duplicate training");return 0
    dataset_name="dolly-shortqa-v1" if a.dataset=="shortqa" else "dolly-v1"
    manifest=E/"datasets/public"/dataset_name/"manifest.json"
    train,heldout=validate_manifest(manifest,sha256(manifest))
    methods=["lora"] if a.dataset=="shortqa" else ["lora","qlora"]
    records={"scope":"single-host development; frozen bounded recipes","jobs":[]}
    with control_session(ROOT,"v1-training-controller") as c:
        def register(url,body):
            found=[x for x in c.get(url).json() if x["name"]==body["name"] and x["version"]==body["version"]]
            if found:
                if found[0]["digest"]!=body["digest"]:raise RuntimeError("Registry identity conflict")
                return found[0]
            r=c.post(url,json=body);r.raise_for_status();return r.json()
        path=ROOT/".tools/assets/qwen-base/model.safetensors"
        base=register("/api/v1/models",{"name":"qwen-base","version":1,"model_type":"llm","framework":"transformers",
            "source":"Qwen/Qwen2.5-0.5B-Instruct","revision":"7ae557604adf67be50417f59c2c2f167def9a775",
            "digest":sha256(path),"artifact_uri":path.as_uri()})
        dataset=register("/api/v1/datasets",{"name":dataset_name,"version":1,"uri":manifest.as_uri(),
            "digest":sha256(manifest),"train_count":len(train),"heldout_count":len(heldout)})
        records.update(base=base,dataset=dataset)
        for method in methods:
            recipe=ROOT/"pipelines/training"/("qwen_sft.yaml" if method=="lora" else "qwen_qlora.yaml")
            config=yaml.safe_load(recipe.read_text())
            name="qwen-"+method+("-shortqa-v1" if a.dataset=="shortqa" else "-v1")
            payload={k:v for k,v in config.items() if k not in ["model","revision"]}
            payload.update(name=name,artifact_id=base["id"],dataset_id=dataset["id"],output_name=name,
                gpu=1,gradient_accumulation_steps=1)
            r=c.post("/api/v1/train-jobs",json=payload);r.raise_for_status();job=r.json()
            record={"method":method,"job_id":job["id"],"job":job,"recipe_sha256":sha256(recipe)}
            records["jobs"].append(record)
            for _ in range(900):
                r=c.get("/api/v1/train-jobs/"+job["id"]);r.raise_for_status();observed=r.json()
                record["observed"]=observed
                (E/("native-qa-lifecycle.json" if a.dataset=="shortqa" else "native-lifecycle.json")).write_text(json.dumps(records,indent=2))
                if observed["state"] in ["COMPLETED","FAILED","CANCELLED"]:break
                time.sleep(1)
            if observed["state"]!="COMPLETED" or not observed["artifact_verified"]:raise RuntimeError("GPU job did not complete with valid checkpoint")
    target.write_text(json.dumps(records,indent=2));print("REAL_GPU_TRAINING_COMPLETE")
    return 0
if __name__=="__main__":raise SystemExit(main())
