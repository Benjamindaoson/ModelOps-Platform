"""Bounded real GPU pause/resume test; never modifies formal checkpoints."""
from pathlib import Path
import json,time,traceback,shutil
from ops.dev_control import control_session
ROOT=Path(__file__).resolve().parents[1]
E=ROOT/"Evidence/v1"
def main():
    output=E/"resume-validation.json"
    if output.exists() and json.loads(output.read_text()).get("status")=="PASS":return 0
    result={"status":"RUNNING","scope":"one short recoverable validation job; no quality selection"}
    def save():output.write_text(json.dumps(result,indent=2))
    def call(client,url,body=None,method="POST"):
        r=client.request(method,url,json=body);r.raise_for_status();return r.json()
    try:
        with control_session(ROOT,"v1-recovery-validator") as client:
            history=json.loads((E/"native-lifecycle.json").read_text())
            job=call(client,"/api/v1/train-jobs",{"name":"v1-resume-validation","artifact_id":history["base"]["id"],
                "dataset_id":history["dataset"]["id"],"method":"lora","framework":"transformers",
                "steps":64,"seed":9101,"batch_size":2,"gradient_accumulation_steps":1,"lr":1e-5,
                "max_seq_length":256,"output_name":"v1-resume-validation"})
            result["job_id"]=job["id"];save()
            directory=E/"runtime/lab"/job["id"];steps=directory/"artifacts/steps.jsonl"
            started=time.monotonic()
            while time.monotonic()-started<120:
                if steps.exists() and steps.stat().st_size>0:break
                time.sleep(.02)
            else:raise RuntimeError("Worker did not produce real training steps")
            result["pause_requested"]=call(client,"/api/v1/train-jobs/"+job["id"]+"/pause")
            for _ in range(180):
                row=call(client,"/api/v1/train-jobs/"+job["id"],method="GET")
                if row["state"] in ["PAUSED","FAILED","COMPLETED"]:break
                time.sleep(.2)
            if row["state"]!="PAUSED":raise RuntimeError("Pause did not reach PAUSED: "+row["state"])
            paused=json.loads((directory/"artifacts/result.json").read_text())
            if not 0<paused["steps"]<64:raise RuntimeError("Pause occurred outside useful recovery interval")
            archive=directory/"pause-snapshot";archive.mkdir()
            shutil.copy2(directory/"artifacts/result.json",archive/"result.json")
            shutil.copy2(directory/"artifacts/resume.pt",archive/"resume.pt")
            shutil.copytree(directory/"artifacts/adapter-latest",archive/"adapter-latest")
            result["paused"]=paused;save()
            result["resume_requested"]=call(client,"/api/v1/train-jobs/"+job["id"]+"/resume")
            for _ in range(600):
                row=call(client,"/api/v1/train-jobs/"+job["id"],method="GET")
                if row["state"] in ["COMPLETED","FAILED"]:break
                time.sleep(.2)
            if row["state"]!="COMPLETED" or not row["artifact_verified"]:raise RuntimeError("Resume checkpoint did not verify")
            events=[json.loads(l) for l in steps.read_text().splitlines()]
            if [x["step"] for x in events]!=list(range(1,65)):raise RuntimeError("Lost or duplicated updates")
            result.update(status="PASS",completed=row,steps=64,paused_at_step=paused["steps"],
                checkpoint_verified=True,update_numbers_exact=True,wall_s=time.monotonic()-started)
            save();print("REAL_GPU_RESUME_PASS",paused["steps"],flush=True);return 0
    except Exception as exc:
        result.update(status="FAILED",error=type(exc).__name__+": "+str(exc));save();traceback.print_exc();return 1
if __name__=="__main__":raise SystemExit(main())
