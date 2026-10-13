"""MLflow lineage for real completed ModelOps jobs; no fixture results are exported."""
from pathlib import Path
import json, time
from pipelines.training.data_contract import sha256
ROOT=Path(__file__).resolve().parents[1]
E=ROOT/"Evidence/llm-production-validation"

def verified_training_artifacts(result,evidence):
    if result.get("status")!="COMPLETED" or not result.get("run_id") or result.get("steps",0)<=0 or result.get("parameter_delta_linf",0)<=0:
        raise ValueError("No real completed weight update")
    owned=(Path(evidence).resolve()/"runtime").resolve()
    paths={"adapter":Path(result["adapter"]).resolve()/"adapter_model.safetensors","checkpoint":Path(result["checkpoint"]).resolve()}
    for kind,p in paths.items():
        if not p.is_relative_to(owned) or not p.is_file():raise ValueError("Unowned or missing "+kind)
        if sha256(p)!=result[kind+"_sha256"]:raise ValueError("Changed "+kind)
    return paths

def tracking_client():
    from mlflow import MlflowClient
    E.mkdir(parents=True,exist_ok=True)
    uri="sqlite:///"+str(E/"mlflow.sqlite")
    return MlflowClient(tracking_uri=uri,registry_uri=uri),uri

def create_training_run(config):
    client,uri=tracking_client()
    name="ModelOps LLM Production Validation"
    experiment=client.get_experiment_by_name(name)
    exp_id=experiment.experiment_id if experiment else client.create_experiment(name,artifact_location=(E/"mlflow-artifacts").as_uri())
    run=client.create_run(exp_id,tags={"mlflow.runName":"Qwen2.5-3B true managed QLoRA","evidence_scope":"single-host engineering validation","modelops.training_started":"false"})
    for key,value in config.items():
        if isinstance(value,(str,int,float,bool)):client.log_param(run.info.run_id,key,str(value))
    return {"run_id":run.info.run_id,"experiment_id":exp_id,"tracking_uri":uri}

def log_steps(run_id,path,last_step=0):
    client,_=tracking_client()
    if not Path(path).exists():return last_step
    for line in Path(path).read_text().splitlines():
        event=json.loads(line)
        if event["step"]<=last_step:continue
        for key in ("loss","gradient_norm","lr","forward_s","backward_s","optimizer_s","wall_s","gpu_allocated_bytes","gpu_reserved_bytes"):
            client.log_metric(run_id,key,float(event[key]),int(time.time()*1000),step=event["step"])
        last_step=event["step"]
    return last_step

def register_training(result,tracking):
    paths=verified_training_artifacts(result,E)
    client,_=tracking_client();run_id=tracking["run_id"]
    client.log_artifacts(run_id,str(paths["adapter"].parent),artifact_path="model")
    info=E/"checkpoint_info.json";info.write_text(json.dumps(result,indent=2))
    client.log_artifact(run_id,str(info),artifact_path="model")
    steps=paths["adapter"].parent.parent/"steps.jsonl"
    if steps.exists():client.log_artifact(run_id,str(steps),artifact_path="training")
    for key in ("steps","model_load_s","training_wall_s","wall_s","trainable_parameters","parameter_delta_linf","gpu_peak_allocated_bytes"):
        client.log_metric(run_id,key,float(result[key]))
    client.set_tag(run_id,"modelops.training_run_id",result["run_id"])
    client.set_tag(run_id,"adapter_sha256",result["adapter_sha256"])
    client.set_tag(run_id,"checkpoint_sha256",result["checkpoint_sha256"])
    name="ModelOps-Qwen2.5-3B"
    registered=client.get_registered_model(name) if client.search_registered_models(filter_string="name='"+name+"'") else client.create_registered_model(name)
    versions=client.search_model_versions("name='"+name+"'")
    matches=[v for v in versions if v.run_id==run_id]
    if matches:
        version=matches[0]
        if version.tags.get("checkpoint_sha256")!=result["checkpoint_sha256"]:raise ValueError("Immutable MLflow version conflict")
    else:
        version=client.create_model_version(name,source="runs:/"+run_id+"/model",run_id=run_id,tags={
            "modelops.training_run_id":result["run_id"],"checkpoint_sha256":result["checkpoint_sha256"],
            "adapter_sha256":result["adapter_sha256"],"artifact_kind":"PEFT adapter and verified merged checkpoint reference",
            "evaluation_status":"pending"})
    client.set_terminated(run_id,status="FINISHED")
    return {"name":name,"version":version.version,"run_id":run_id,"source":version.source,"status":version.status,
            "checkpoint_sha256":result["checkpoint_sha256"],"adapter_sha256":result["adapter_sha256"]}
