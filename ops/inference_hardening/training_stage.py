"""Managed real controlled QLoRA runs; saved RNG/optimizer resume checked numerically."""
import asyncio,json,time,subprocess,traceback,shutil,threading
from pathlib import Path
from ops.dev_control import control_session
from ops.run_llm_validation import register
from ops.mlflow_validation import create_training_run,log_steps,register_training,tracking_client
from pipelines.training.data_contract import sha256,validate_manifest,write_json
from .runtime import ROOT,E,Server
from .benchmark import gpu_poll
from .quality import evaluate

def main():
    folder=E/"training";folder.mkdir(exist_ok=True);sp=folder/"progress.json"
    state=json.loads(sp.read_text()) if sp.exists() else {"runs":{},"failures":[]}
    basepath=ROOT/".tools/assets/qwen3b-base/modelops-files.json";dp=ROOT/"Evidence/v1/datasets/public/dolly-shortqa-v1/manifest.json"
    train,test=validate_manifest(dp,sha256(dp))
    spec={"steps":64,"seed":9102,"batch_size":2,"gradient_accumulation_steps":2,"lr":1e-5,"lora_rank":8,"lora_alpha":16,"max_seq_length":384,"method":"qlora","base_sha":sha256(basepath),"dataset_sha":sha256(dp),"precision":"bf16","comparison":"Only gradient_checkpointing False vs True; resume repeated False","resume_atol":1e-6,"resume_rtol":0}
    specpath=folder/"protocol.json"
    if specpath.exists() and json.loads(specpath.read_text())!=spec:raise ValueError("Training protocol changed")
    write_json(specpath,spec)
    with control_session(ROOT,"hardening-training","Evidence/inference-hardening") as c:
        base=register(c,"/api/v1/models",{"name":"hardening-qwen3b-base","version":1,"model_type":"llm","framework":"transformers","source":"Qwen/Qwen2.5-3B-Instruct","revision":"aa8e72537993ba99e69dfaafa59ed015b17504d1","digest":spec["base_sha"],"artifact_uri":basepath.as_uri()})
        data=register(c,"/api/v1/datasets",{"name":"hardening-dolly-v1","version":1,"uri":dp.as_uri(),"digest":spec["dataset_sha"],"train_count":len(train),"heldout_count":len(test)})
        for label,checkpointing,inject in [("no-checkpoint",False,False),("checkpoint",True,False),("resume",False,True)]:
            rec=state["runs"].setdefault(label,{})
            try:
                if not rec.get("tracking"):
                    rec["tracking"]=create_training_run({**spec,"gradient_checkpointing":checkpointing,"condition":label});write_json(sp,state)
                if not rec.get("job"):
                    payload={k:spec[k] for k in ["steps","seed","batch_size","gradient_accumulation_steps","lr","lora_rank","lora_alpha","max_seq_length","method"]}
                    payload.update(name="hardening-"+label,output_name="hardening-"+label,framework="transformers",artifact_id=base["id"],dataset_id=data["id"],gradient_checkpointing=checkpointing,epochs=1,gpu=1)
                    r=c.post("/api/v1/train-jobs",json=payload);r.raise_for_status();rec["job"]=r.json();write_json(sp,state)
                output=E/"runtime/lab"/rec["job"]["id"]/"artifacts";last=0;start=time.time();stop=threading.Event();samples=[]
                thread=threading.Thread(target=gpu_poll,args=(stop,samples),daemon=True);thread.start()
                try:
                    for _ in range(2400):
                        r=c.get("/api/v1/train-jobs/"+rec["job"]["id"]);r.raise_for_status();obs=r.json()
                        last=log_steps(rec["tracking"]["run_id"],output/"steps.jsonl",last)
                        if inject and not rec.get("pause_requested") and last>=16 and obs["state"]=="RUNNING":
                            paused=c.post("/api/v1/train-jobs/"+rec["job"]["id"]+"/pause");paused.raise_for_status();rec["pause_requested"]=True;rec["pause_requested_after_step"]=last;write_json(sp,state)
                        if obs["state"]=="PAUSED" and inject:
                            if not rec.get("resume_requested"):
                                saved=folder/"resume-snapshot";saved.mkdir(exist_ok=True)
                                shutil.copy2(output/"resume.pt",saved/"resume.pt");shutil.copytree(output/"adapter-latest",saved/"adapter",dirs_exist_ok=True)
                                rec["pause_receipt"]=json.loads((output/"result.json").read_text())
                                r=c.post("/api/v1/train-jobs/"+rec["job"]["id"]+"/resume");r.raise_for_status();rec["resume_requested"]=True;write_json(sp,state)
                            else:raise RuntimeError("Resume returned to PAUSED unexpectedly")
                        if obs["state"] in {"COMPLETED","FAILED","CANCELLED"}:break
                        time.sleep(.25)
                    if obs["state"]!="COMPLETED" or not obs["artifact_verified"]:raise RuntimeError("Managed real training "+obs["state"])
                    rec["result"]=json.loads((output/"result.json").read_text());rec["controller_wall_s"]=time.time()-start
                    rec["mlflow_model"]=register_training(rec["result"],rec["tracking"],E,"ModelOps-Qwen3B-Hardening")
                    rec["candidate"]=register(c,"/api/v1/models",{"name":"hardening-qwen3b-"+label,"version":1,"model_type":"llm","framework":"transformers","source":"Qwen/Qwen2.5-3B-Instruct","digest":rec["result"]["checkpoint_sha256"],"artifact_uri":Path(rec["result"]["checkpoint"]).as_uri(),"base_model":base["id"],"adapter_type":"qlora","adapter_uri":Path(rec["result"]["adapter"]).as_uri(),"training_run_id":rec["job"]["id"],"task_type":"bounded-shortqa"})
                    rec["status"]="PASS"
                finally:
                    stop.set();thread.join(8);write_json(folder/(label+"-telemetry.json"),samples)
            except Exception as exc:
                rec["status"]="FAIL";rec["error"]=str(exc);state["failures"].append({"condition":label,"error":str(exc),"time":time.time()})
                (folder/(label+"-failure.log")).write_text(traceback.format_exc())
            write_json(sp,state);print("TRAINING "+label+" "+rec["status"],flush=True)
    completed={k:r for k,r in state["runs"].items() if r.get("status")=="PASS"}
    if "resume" in completed and "no-checkpoint" in completed:
        a=completed["no-checkpoint"]["result"]["adapter"];b=completed["resume"]["result"]["adapter"]
        program="import json,torch;from safetensors.torch import load_file;a=load_file("+repr(str(Path(a)/"adapter_model.safetensors"))+");b=load_file("+repr(str(Path(b)/"adapter_model.safetensors"))+");keys=set(a)==set(b);err=max(float((a[k]-b[k]).abs().max()) for k in a);print(json.dumps({'same_keys':keys,'max_abs_error':err,'status':'PASS' if keys and err<=1e-6 else 'FAIL'}))"
        p=subprocess.run([str(ROOT/".gpu-venv/bin/python"),"-c",program],cwd=ROOT,capture_output=True,text=True)
        state["resume_consistency"]=json.loads(p.stdout.splitlines()[-1]) if p.returncode==0 else {"status":"FAIL","error":p.stderr}
        for r in completed.values():
            lines=[json.loads(x) for x in (Path(r["result"]["adapter"]).parent/"steps.jsonl").read_text().splitlines()]
            r["step_count"]=len(lines);r["unique_step_count"]=len({x["step"] for x in lines});r["tokens_s"]=sum(x["input_tokens"] for x in lines)/sum(x["wall_s"] for x in lines);r["steps_s"]=len(lines)/sum(x["wall_s"] for x in lines)
        aa=[json.loads(x) for x in (Path(completed["no-checkpoint"]["result"]["adapter"]).parent/"steps.jsonl").read_text().splitlines()]
        bb=[json.loads(x) for x in (Path(completed["resume"]["result"]["adapter"]).parent/"steps.jsonl").read_text().splitlines()]
        state["resume_consistency"]["sample_sequence_equal"]=[x["sample_ids"] for x in aa]==[x["sample_ids"] for x in bb]
        state["resume_consistency"]["max_loss_error"]=max(abs(a["loss"]-b["loss"]) for a,b in zip(aa,bb))
    for label,rec in completed.items():
        result=rec["result"];model=Path(result["checkpoint"]).parent
        mp=model/"modelops-files.json"
        if not mp.exists():write_json(mp,{"files":[{"name":p.name,"sha256":sha256(p),"bytes":p.stat().st_size} for p in sorted(model.iterdir()) if p.is_file()]})
        try:
            with Server({"engine":"vllm","model":str(model),"model_sha":sha256(mp),"name":"modelops-frozen-qwen3b","label":"trained-"+label,"port":19801,"memory_fraction":.7,"max_context":4096,"max_sequences":64,"batch_tokens":2048,"prefix_cache":False,"kv_cache_bytes":3*1024**3}) as server:
                rec["quality"]=asyncio.run(evaluate(server,folder/label/"quality"))
            ml,_=tracking_client();ml.set_model_version_tag(rec["mlflow_model"]["name"],rec["mlflow_model"]["version"],"evaluation_status",rec["quality"]["status"])
        except Exception as exc:rec["quality"]={"status":"FAIL","error":str(exc)}
        write_json(sp,state)
    state["status"]="PASS" if len(completed)==3 and state.get("resume_consistency",{}).get("status")=="PASS" and all(r.get("quality",{}).get("status")=="PASS" for r in completed.values()) else "FAIL"
    write_json(sp,state)
if __name__=="__main__":main()
