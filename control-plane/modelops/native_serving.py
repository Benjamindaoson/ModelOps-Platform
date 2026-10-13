"""Owned single-host development serving. No Kubernetes/Gateway claim."""
from __future__ import annotations
import json,os,socket,subprocess,signal,time
from pathlib import Path
from urllib.parse import urlsplit,unquote
import httpx,psutil
from .linux_runtime import digest,save
from .runtime import RuntimeFailure,RuntimeNotFound,deployment_body

class NativeServing:
    kind="linux"
    def __init__(self,repo_root,gpu_python,worker_root):
        self.repo=Path(repo_root).resolve();self.python=Path(gpu_python);self.root=Path(worker_root).resolve()
    def directory(self,row):
        p=(self.root/"deployments"/row.tenant/row.id).resolve()
        if not p.is_relative_to(self.root):raise RuntimeFailure("Invalid serving identity")
        return p
    def validate_budget(self,row):
        if getattr(row,"quantization","none")!="none":raise RuntimeFailure("Native validation requires unquantized merged weights")
        if row.replicas not in [0,1]:raise RuntimeFailure("Native backend supports one replica")
    def validate_model_engine(self,row,artifact):
        if artifact.model_type not in {"llm","embedding","vla"}:raise RuntimeFailure("Native model type not validated")
        if artifact.model_type=="vla" and row.engine!="custom":raise RuntimeFailure("VLA needs continuous-action custom serving")
        if artifact.model_type=="embedding" and row.engine!="custom":raise RuntimeFailure("Native embedding is Transformers; TEI is Kubernetes-only")
        if artifact.model_type=="llm" and row.engine!="vllm":raise RuntimeFailure("Native LLM validation supports vLLM")
    def stop_owned(self,record):
        try:
            p=psutil.Process(record["pid"])
            if p.create_time()!=record["create_time"] or record["command_marker"] not in p.cmdline():
                raise RuntimeFailure("Serving process identity mismatch")
        except psutil.NoSuchProcess:return
        if os.getpgid(p.pid) != p.pid:
            raise RuntimeFailure("Serving process group identity mismatch")
        os.killpg(p.pid, signal.SIGTERM)
        try:
            p.wait(15)
        except psutil.TimeoutExpired:
            os.killpg(p.pid, signal.SIGKILL)
            p.wait(10)
        # The wrapper and all inference workers share this owned session.
        time.sleep(1)
    def model_directory(self,row,artifact):
        parsed=urlsplit(artifact.artifact_uri or "")
        if parsed.scheme!="file" or parsed.netloc not in ["","localhost"]:raise RuntimeFailure("Owned local artifact required")
        path=Path(unquote(parsed.path)).resolve()
        if artifact.model_type=="vla":
            expected=Path("/data/VLA-Forge/Assets/models/smolvla_libero/model.safetensors")
            if path!=expected or digest(path)!=artifact.digest:raise RuntimeFailure("Only approved frozen VLA base permitted")
            return path.parent
        if not any(path.is_relative_to(p) for p in [self.repo/".tools/assets",self.root/row.tenant]):
            raise RuntimeFailure("Cross-tenant serving artifact")
        if path.is_file():actual=digest(path);directory=path.parent
        elif path.is_dir():
            from pipelines.evaluation.run import sha256_artifact
            actual=sha256_artifact(path);directory=path
        else:raise RuntimeFailure("Artifact unavailable")
        if actual!=artifact.digest:raise RuntimeFailure("Serving artifact digest drift")
        return directory
    def start(self,row,artifact):
        self.validate_budget(row);self.validate_model_engine(row,artifact)
        directory=self.directory(row);directory.mkdir(parents=True,exist_ok=True)
        prior=directory/"process.json"
        if prior.exists():self.stop_owned(json.loads(prior.read_text()))
        model=self.model_directory(row,artifact)
        body=deployment_body(row,artifact)
        body.update(kind="ModelOpsDeployment",apiVersion="modelops.local/v1",runtime_kind="linux")
        body["metadata"].update(generation=row.generation,uid=row.id)
        save(directory/"intent.json",body)
        (directory/"deleted.json").unlink(missing_ok=True)
        if row.replicas==0:return
        with socket.socket() as sock:sock.bind(("127.0.0.1",0));port=sock.getsockname()[1]
        env={k:v for k,v in os.environ.items() if not any(w in k.upper() for w in ["SECRET","TOKEN","PASSWORD"])}
        env.update(HF_HUB_OFFLINE="1",TOKENIZERS_PARALLELISM="false",PYTHONPATH=str(self.repo))
        env.pop("LD_LIBRARY_PATH",None)
        if artifact.model_type=="llm":
            marker=str(model)
            cmd=[str(self.python),"-m","ops.locked_exec","--",str(self.python),
                 "-m","vllm.entrypoints.openai.api_server","--model",str(model),
                 "--served-model-name",artifact.id,"--dtype","bfloat16","--enforce-eager",
                 "--max-model-len","1024","--gpu-memory-utilization","0.40",
                 "--enable-prefix-caching" if getattr(row,"cache",False) else "--no-enable-prefix-caching",
                 "--host","127.0.0.1","--port",str(port)]
            ready="/v1/models"
        elif artifact.model_type=="embedding":
            marker=str(model)
            cmd=[str(self.python),"-m","ops.custom_server","--model-root",str(model),
                 "--model-id",artifact.id,"--host","127.0.0.1","--port",str(port)]
            ready="/health"
        else:
            marker=str(self.repo/"Evidence/v1/vla-registry")
            if not Path(marker).is_dir():raise RuntimeFailure("Frozen owned VLA registry snapshot required")
            cmd=["/data/VLA-Forge/project/robot-vla/.venv/bin/python","-m","pipelines.robotics.serve",
                 "--registry",marker,"--backend","eager","--log",str(directory/"requests.jsonl"),
                 "--host","127.0.0.1","--port",str(port)]
            ready="/ready"
        with (directory/"server.log").open("ab") as log:
            process=subprocess.Popen(cmd,cwd=self.repo,env=env,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
        save(prior,{"pid":process.pid,"create_time":psutil.Process(process.pid).create_time(),
            "command_marker":marker,"endpoint":f"http://127.0.0.1:{port}","ready_path":ready,
            "artifact_id":artifact.id,"model_type":artifact.model_type,"checkpoint_sha256":artifact.digest})
    def get(self,row):
        directory=self.directory(row)
        if (directory/"deleted.json").exists():raise RuntimeNotFound("Native deployment deleted")
        if not (directory/"intent.json").exists():raise RuntimeNotFound("Native deployment absent")
        body=json.loads((directory/"intent.json").read_text());healthy=False;endpoint=None
        if (directory/"process.json").exists():
            record=json.loads((directory/"process.json").read_text());endpoint=record["endpoint"]
            try:
                p=psutil.Process(record["pid"])
                owned=p.create_time()==record["create_time"] and record["command_marker"] in p.cmdline()
                if owned and p.status()!=psutil.STATUS_ZOMBIE:
                    response=httpx.get(endpoint+record["ready_path"],timeout=2)
                    healthy=response.status_code==200
                    if healthy and record["model_type"]=="llm":
                        healthy=record["artifact_id"] in {x["id"] for x in response.json().get("data",[])}
                    if healthy and record["model_type"]=="vla":
                        healthy=response.json().get("ready") is True and response.json().get("model_sha256")==record["checkpoint_sha256"]
            except (psutil.NoSuchProcess,httpx.HTTPError,ValueError,KeyError):pass
        generation=body["metadata"]["generation"]
        body["status"]={"phase":"Ready" if healthy else "Starting","readyReplicas":int(healthy),
            "endpoint":endpoint,"conditions":[{"type":key,"status":"True" if healthy else "False",
            "observedGeneration":generation} for key in ["Ready","ModelReady"]]}
        return body
    def delete(self,row):
        path=self.directory(row)/"process.json"
        if path.exists():self.stop_owned(json.loads(path.read_text()))
        save(self.directory(row)/"deleted.json",{"deployment_id":row.id,"deleted":True})
