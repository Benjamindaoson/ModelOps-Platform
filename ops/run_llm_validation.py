"""Existing ModelOps native job + true PEFT training + MLflow; restart avoids duplicate GPU work."""
from pathlib import Path
from datetime import datetime,timezone
import argparse,fcntl,json,time,subprocess,sys
import yaml
from ops.dev_control import control_session
from ops.mlflow_validation import create_training_run,log_steps,register_training,tracking_client
from pipelines.training.data_contract import sha256,validate_manifest,write_json
ROOT=Path(__file__).resolve().parents[1]
E=ROOT/"Evidence/llm-production-validation"

def register(client,url,body):
    response=client.get(url);response.raise_for_status()
    matches=[x for x in response.json() if x["name"]==body["name"] and x["version"]==body["version"]]
    if matches:
        if len(matches)!=1 or matches[0]["digest"]!=body["digest"]:raise ValueError("Immutable registry conflict")
        return matches[0]
    response=client.post(url,json=body);response.raise_for_status();return response.json()

def training():
    E.mkdir(parents=True,exist_ok=True)
    with (E/"controller.lock").open("a") as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        done=E/"training-finished.json"; state=E/"training-state.json"
        if done.exists():
            record=json.loads(done.read_text())
            from ops.mlflow_validation import verified_training_artifacts
            verified_training_artifacts(record["result"],E)
            print("Existing true QLoRA checkpoint verified; no repeated training",flush=True);return record
        if not (E/"asset-validation.json").exists():raise RuntimeError("Complete official weight verification required")
        config=yaml.safe_load((ROOT/"experiments/training/config.yaml").read_text())
        config["code_revision"]=subprocess.check_output(["git","rev-parse","HEAD"],cwd=ROOT,text=True).strip()
        record=json.loads(state.read_text()) if state.exists() else {"status":"PREPARING","config":config,"tracking":create_training_run(config)}
        model=ROOT/".tools/assets/qwen3b-base/modelops-files.json"
        manifest=ROOT/"Evidence/v1/datasets/public/dolly-shortqa-v1/manifest.json"
        train,test=validate_manifest(manifest,sha256(manifest))
        with control_session(ROOT,"llm-training-controller","Evidence/llm-production-validation") as c:
            base=register(c,"/api/v1/models",{"name":"qwen2-5-3b-base","version":1,"model_type":"llm","framework":"transformers",
                "source":config["model"],"revision":config["revision"],"digest":sha256(model),"artifact_uri":model.as_uri(),"base_model":config["model"]})
            data=register(c,"/api/v1/datasets",{"name":"dolly-shortqa-3b-v1","version":1,"uri":manifest.as_uri(),"digest":sha256(manifest),
                "train_count":len(train),"heldout_count":len(test)})
            record.update(base=base,dataset=data)
            if "job" not in record:
                keys=("framework","method","steps","seed","batch_size","max_seq_length","lr","lora_rank","lora_alpha","gpu")
                payload={k:config[k] for k in keys}
                payload.update(name="qwen3b-qlora-validation-v1",artifact_id=base["id"],dataset_id=data["id"],
                    output_name="qwen3b-qlora-validation-v1",epochs=1,gradient_accumulation_steps=1)
                response=c.post("/api/v1/train-jobs",json=payload);response.raise_for_status();record["job"]=response.json()
                m,_=tracking_client();m.set_tag(record["tracking"]["run_id"],"modelops.training_run_id",record["job"]["id"])
                m.set_tag(record["tracking"]["run_id"],"modelops.training_started","true")
            write_json(state,record)
            output=E/"runtime/lab"/record["job"]["id"]/"artifacts"
            last=0;started=time.time()
            for _ in range(1800):
                response=c.get("/api/v1/train-jobs/"+record["job"]["id"]);response.raise_for_status()
                observed=response.json();record["observed"]=observed
                last=log_steps(record["tracking"]["run_id"],output/"steps.jsonl",last)
                write_json(state,record)
                if observed["state"] in {"COMPLETED","FAILED","CANCELLED"}:break
                time.sleep(1)
            if observed["state"]!="COMPLETED" or not observed["artifact_verified"]:
                client,_=tracking_client();client.set_terminated(record["tracking"]["run_id"],status="FAILED")
                raise RuntimeError("Managed GPU job failed; inspect retained real worker log")
            result=json.loads((output/"result.json").read_text())
            record.update(result=result,status="PASS",finished=datetime.now(timezone.utc).isoformat(),controller_wall_s=time.time()-started)
            record["mlflow_model"]=register_training(result,record["tracking"])
            candidate=register(c,"/api/v1/models",{"name":"qwen2-5-3b-qlora","version":1,"model_type":"llm","framework":"transformers",
                "source":config["model"],"revision":config["revision"],"digest":result["checkpoint_sha256"],
                "artifact_uri":Path(result["checkpoint"]).as_uri(),"base_model":base["id"],"adapter_type":"qlora",
                "adapter_uri":Path(result["adapter"]).as_uri(),"training_run_id":record["job"]["id"],"task_type":"short_answer"})
            record["candidate"]=candidate
            m,_=tracking_client();m.set_tag(record["tracking"]["run_id"],"modelops.artifact_id",candidate["id"])
            m.set_model_version_tag(record["mlflow_model"]["name"],record["mlflow_model"]["version"],"modelops.artifact_id",candidate["id"])
            write_json(done,record)
            write_json(ROOT/"experiments/training/metrics.json",{**result,"modelops_training_run_id":record["job"]["id"],
                "mlflow_run_id":record["tracking"]["run_id"],"scope":"Actual 32-update bounded GPU QLoRA; not task-general quality proof"})
            print(json.dumps({"REAL_3B_TRAINING":"PASS","run_id":record["job"]["id"],"mlflow_run_id":record["tracking"]["run_id"],
                "mlflow_model_version":record["mlflow_model"]["version"],"adapter_sha256":result["adapter_sha256"]}),flush=True)
            return record

def main():
    p=argparse.ArgumentParser();p.add_argument("--phase",choices=["training"],default="training");p.parse_args()
    training()
if __name__=="__main__":main()
