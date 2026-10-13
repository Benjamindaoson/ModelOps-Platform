"""Sequential native inference validation for LLM, Embedding and frozen simulation VLA."""
from pathlib import Path
import argparse,json,time,subprocess,os,shutil,base64,io,traceback,hashlib
import httpx
from ops.dev_control import control_session
ROOT=Path(__file__).resolve().parents[1]
E=ROOT/"Evidence/v1"
def sha(path):
    h=hashlib.sha256()
    with Path(path).open("rb") as f:
        for b in iter(lambda:f.read(1048576),b""):h.update(b)
    return h.hexdigest()
def call(client,method,path,body=None):
    r=client.request(method,path,json=body);r.raise_for_status()
    return r.json() if r.content else {}
def register(client,body):
    rows=call(client,"GET","/api/v1/models")
    found=[x for x in rows if x["name"]==body["name"] and x["version"]==body["version"]]
    if found:
        if len(found)!=1 or found[0]["digest"]!=body["digest"]:raise RuntimeError("Registry hash conflict")
        return found[0]
    return call(client,"POST","/api/v1/models",body)
def ready(client,key):
    for _ in range(120):
        row=call(client,"GET","/api/v1/deployments/"+key)
        if row["runtime_verified"]:return row
        time.sleep(2)
    raise RuntimeError("Native server readiness deadline exceeded")
def main():
    parser=argparse.ArgumentParser();parser.add_argument("--kind",choices=["llm","embedding","vla"],required=True)
    args=parser.parse_args();output=E/f"inference-{args.kind}.json"
    if output.exists() and json.loads(output.read_text()).get("status")=="PASS":
        print(args.kind,"already validated; no duplicate run");return 0
    if output.exists():
        attempt=E/"attempts";attempt.mkdir(exist_ok=True)
        stamp=str(time.time_ns());shutil.copy2(output,attempt/(output.stem+"-"+stamp+".json"))
        old=json.loads(output.read_text());old_id=old.get("cleanup",{}).get("id")
        if old_id:
            for name in ["server.log","requests.jsonl"]:
                src=E/"runtime/deployments/lab"/old_id/name
                if src.exists():shutil.copy2(src,attempt/(args.kind+"-"+stamp+"-"+name))
    records={"status":"RUNNING","kind":args.kind,"scope":"single-host development; simulation only for VLA"}
    deployment=None
    def save():output.write_text(json.dumps(records,indent=2))
    try:
        with control_session(ROOT) as client:
            try:
                if args.kind=="llm":
                    original=json.loads((E/"llm-lifecycle.json").read_text())
                    model=original["candidate"]
                elif args.kind=="embedding":
                    path=ROOT/".tools/assets/embedding-base/model.safetensors"
                    model=register(client,{"name":"minilm-embedding","version":1,"model_type":"embedding",
                        "framework":"transformers","task_type":"embedding","source":"sentence-transformers/all-MiniLM-L6-v2",
                        "revision":"1110a243fdf4706b3f48f1d95db1a4f5529b4d41","digest":sha(path),"artifact_uri":path.as_uri()})
                else:
                    original=Path("/data/VLA-Forge/Evidence/M05/modelops/registry")
                    snapshot=E/"vla-registry";snapshot.mkdir(exist_ok=True)
                    hashes={}
                    for p in original.glob("*"):
                        if p.suffix in [".json",".jsonl"]:
                            hashes[p.name]=sha(p)
                            dst=snapshot/p.name
                            if not dst.exists():shutil.copy2(p,dst)
                            if sha(dst)!=hashes[p.name]:raise RuntimeError("Frozen VLA registry snapshot drift")
                    records["original_registry_hashes"]=hashes
                    path=Path("/data/VLA-Forge/Assets/models/smolvla_libero/model.safetensors")
                    model=register(client,{"name":"smolvla-frozen","version":1,"model_type":"vla",
                        "framework":"lerobot","task_type":"action-prediction","source":"lerobot/smolvla_libero",
                        "revision":"m05-base-frozen","digest":sha(path),"artifact_uri":path.as_uri()})
                records["model"]=model
                deployment=call(client,"POST","/api/v1/deployments",{"name":"v1-infer-"+args.kind+"-r2",
                    "artifact_id":model["id"],"engine":"vllm" if args.kind=="llm" else "custom",
                    "replicas":1,"gpu":0 if args.kind=="embedding" else 1})
                save();d=ready(client,deployment["id"]);records["ready"]=d;save()
                if args.kind=="llm":
                    request={"messages":[{"role":"user","content":"What is the capital of France? Answer briefly."}],"max_tokens":16,"temperature":0}
                    value=call(client,"POST","/api/v1/deployments/"+d["id"]+"/infer",request)
                    assert value["model"]==model["id"] and value["choices"][0]["message"]["content"]
                    records["managed_api"]=value
                    env=os.environ.copy();env["PATH"]=str(ROOT/".gpu-venv/bin")+":"+env["PATH"];env.pop("LD_LIBRARY_PATH",None)
                    cmd=[str(ROOT/".gpu-venv/bin/python"),"benchmarks/inference/run.py","--base-url",d["endpoint"],
                        "--model",model["id"],"--tokenizer",str(ROOT/".tools/assets/qwen-base"),"--cli-profile","v0.10",
                        "--prompts","40","--concurrency","4","--request-rate","8","--input-len","64","--output-len","32",
                        "--warmups","0","--gpu-poll-s","0.25","--timeout-s","180",
                        "--output-root",str(E/"benchmark"),"--run-id","qwen-qa-fixed-v1"]
                    with (E/"benchmark-fixed-controller.log").open("w") as log:
                        result=subprocess.run(cmd,cwd=ROOT,env=env,stdout=log,stderr=subprocess.STDOUT,timeout=220)
                    records["benchmark_exit"]=result.returncode
                    if result.returncode:raise RuntimeError("Real benchmark did not pass")
                elif args.kind=="embedding":
                    value=call(client,"POST","/api/v1/deployments/"+d["id"]+"/infer",{
                        "input":["robot learning","robot learning","enterprise model lifecycle"]})
                    vectors=[x["embedding"] for x in value["data"]]
                    import math
                    assert len(vectors)==3 and all(len(v)==384 and all(math.isfinite(x) for x in v) for v in vectors)
                    assert vectors[0]==vectors[1]
                    records.update(dimensions=384,vectors=3,duplicate_input_exact=True,
                        l2_norms=[math.sqrt(sum(x*x for x in v)) for v in vectors],response_sha256=hashlib.sha256(json.dumps(value,sort_keys=True).encode()).hexdigest())
                else:
                    import numpy as np
                    from PIL import Image
                    source=Path("/data/VLA-Forge/Evidence/M05/training_perf/data_pipeline/observation-corrective-0.npz")
                    z=np.load(source,allow_pickle=False)
                    records["observation_source"]=str(source);records["observation_sha256"]=sha(source)
                    def image(value):
                        stream=io.BytesIO();Image.fromarray(value.astype(np.uint8)).save(stream,format="PNG")
                        return base64.b64encode(stream.getvalue()).decode()
                    state=np.asarray(z["state"]).reshape(-1).tolist()
                    task=str(z["task"].item())
                    payload={"image1":image(z["image1"]),"image2":image(z["image2"]),"state":state,"task":task,"scope":"simulation",
                        "seed":5501,"version":"m05-base-frozen","observation_id":"v1-real-observation-0","observed_at":time.time(),"timeout_s":30}
                    value=call(client,"POST","/api/v1/deployments/"+d["id"]+"/infer",payload)
                    (E/"vla-action-response.json").write_text(json.dumps(value,indent=2))
                    actions=np.asarray(value["actions"])
                    assert actions.shape==(50,7) and np.isfinite(actions).all()
                    assert value["model_sha256"]==model["digest"]
                    records.update(action_shape=list(actions.shape),input_state_dimensions=len(state),
                        chunk_s=value["chunk_s"],model_sha256=value["model_sha256"],
                        action_response_sha256=sha(E/"vla-action-response.json"))
                    records["original_registry_unchanged"]=all(sha(original/k)==v for k,v in hashes.items())
                    assert records["original_registry_unchanged"]
                metrics=client.get("/metrics");metrics.raise_for_status()
                (E/f"metrics-{args.kind}.prom").write_text(metrics.text)
                records.update(status="PASS",completed_at=time.time());save();print(args.kind,"PASS",flush=True)
                return 0
            finally:
                if deployment:
                    records["cleanup"]=call(client,"DELETE","/api/v1/deployments/"+deployment["id"]);save()
    except Exception as exc:
        records.update(status="FAILED",error=type(exc).__name__+": "+str(exc));save();traceback.print_exc();return 1
if __name__=="__main__":raise SystemExit(main())
