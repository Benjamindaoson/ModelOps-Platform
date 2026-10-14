"""Owned single-host GPU jobs. This backend is explicitly not Kubernetes."""
from __future__ import annotations
import hashlib
import json
import os
import signal
import subprocess
import time
from pathlib import Path
from urllib.parse import unquote, urlsplit
import psutil
from .runtime import RuntimeFailure, RuntimeNotFound, RuntimeUnavailable, namespace_for

def digest(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()

def save(path, body):
    import uuid
    path = Path(path)
    temp = path.with_name(path.name + "." + uuid.uuid4().hex + ".tmp")
    temp.write_text(json.dumps(body, indent=2))
    os.replace(temp, path)

class LinuxRuntime:
    connected = True
    kind = "linux"

    def __init__(self, repo_root, gpu_python, worker_root):
        self.repo = Path(repo_root).resolve()
        self.python = Path(gpu_python)
        self.root = Path(worker_root).resolve()
        if not self.root.is_relative_to(self.repo):
            raise ValueError("Worker root must stay in this project")
        self.root.mkdir(parents=True, exist_ok=True)
        from .native_serving import NativeServing
        self.serving = NativeServing(self.repo, self.python, self.root)

    def directory(self, row):
        path = (self.root / row.tenant / row.id).resolve()
        if not path.is_relative_to(self.root):
            raise RuntimeFailure("Invalid worker identity")
        return path

    def _owned_input(self, uri, row, dataset=False):
        parsed = urlsplit(uri or "")
        if parsed.scheme != "file" or parsed.netloc not in {"", "localhost"}:
            raise RuntimeFailure("Native jobs require an owned local artifact URI")
        path = Path(unquote(parsed.path)).resolve()
        public = self.repo / ("Evidence/v1/datasets/public" if dataset else ".tools/assets")
        owned = self.root / row.tenant
        if not (path.is_relative_to(public) or path.is_relative_to(owned)):
            raise RuntimeFailure("Artifact belongs to another tenant or unapproved root")
        if not path.is_file():
            raise RuntimeFailure("Artifact file is unavailable")
        return path

    def build_training_config(self, row, artifact, dataset, parameters):
        if artifact.model_type != "llm" or parameters.get("framework", "transformers") != "transformers":
            raise RuntimeFailure("Use the authoritative robotics adapter or Argo LLaMA-Factory backend for this job type")
        if row.method not in {"lora","qlora"}:raise RuntimeFailure("Native training method only supports validated LoRA/QLoRA; use Argo for full SFT")
        weight = self._owned_input(artifact.artifact_uri, row)
        manifest = self._owned_input(dataset.uri, row, dataset=True)
        if digest(weight) != artifact.digest or digest(manifest) != dataset.digest:
            raise RuntimeFailure("Frozen model or dataset hash mismatch")
        steps = parameters.get("steps", 32)
        if not 1 <= steps <= 1000:
            raise RuntimeFailure("Native update budget exceeded")
        return {
            "run_id": row.id, "run_name": row.name, "tenant": row.tenant,
            "base_model": str(weight.parent), "base_sha256": artifact.digest,
            "dataset_manifest": str(manifest), "dataset_sha256": dataset.digest,
            "method": row.method, "steps": steps, "seed": parameters.get("seed", 9101),
            "batch_size": parameters.get("batch_size", 2),
            "lr": parameters.get("lr", 0.00001),
            "lora_rank": parameters.get("lora_rank", 8),
            "lora_alpha": parameters.get("lora_alpha", 16),
            "max_seq_length": parameters.get("max_seq_length", 256),
            "gradient_accumulation_steps": parameters.get("gradient_accumulation_steps", 1),
            "gradient_checkpointing": parameters.get("gradient_checkpointing", False),
            "output": str(self.directory(row) / "artifacts"),
        }

    def training_contract(self, row, artifact, dataset, parameters):
        return {"apiVersion": "modelops.local/v1", "kind": "ModelOpsTrainingRun",
                "runtime_kind": "linux",
                "metadata": {"name": row.workflow_name, "namespace": namespace_for(row.tenant),
                    "labels": {"modelops.io/tenant": row.tenant, "modelops.io/job-id": row.id}},
                "spec": {"artifact_id": artifact.id, "artifact_digest": artifact.digest,
                         "dataset_id": dataset.id, "dataset_digest": dataset.digest,
                         "parameters": parameters}}

    def submit_finetune(self, row, artifact, dataset, parameters):
        config = self.build_training_config(row, artifact, dataset, parameters)
        directory = self.directory(row)
        directory.mkdir(parents=True, exist_ok=True)
        with (directory / "intent.json").open("x") as stream:
            json.dump(self.training_contract(row, artifact, dataset, parameters), stream)
        save(directory / "config.json", config)
        self._launch(row)

    def _launch(self, row, resume=False):
        directory = self.directory(row)
        old = directory / "process.json"
        if old.exists() and self._alive(json.loads(old.read_text())):
            raise RuntimeFailure("Worker is already active")
        env = {k: v for k, v in os.environ.items()
               if not any(word in k.upper() for word in ("TOKEN", "PASSWORD", "SECRET"))}
        env.update(HF_HUB_OFFLINE="1", TOKENIZERS_PARALLELISM="false")
        args = [str(self.python), "-m", "pipelines.training.sft_worker",
                "--config", str(directory / "config.json")]
        if resume:
            args.append("--resume")
        with (directory / "process.log").open("ab") as log:
            process = subprocess.Popen(args, cwd=self.repo, env=env, stdout=log,
                                       stderr=subprocess.STDOUT, start_new_session=True)
        save(old, {"pid": process.pid, "create_time": psutil.Process(process.pid).create_time(),
                   "started": time.time(), "resume": resume, "cancel_requested": False})

    def _alive(self, record):
        try:
            p = psutil.Process(record["pid"])
            return p.create_time() == record["create_time"] and p.status() != psutil.STATUS_ZOMBIE
        except (psutil.NoSuchProcess, KeyError):
            return False

    def get_finetune(self, row):
        directory = self.directory(row)
        if not (directory / "intent.json").is_file():
            raise RuntimeNotFound("Native training intent absent")
        body = json.loads((directory / "intent.json").read_text())
        process = json.loads((directory / "process.json").read_text())
        phase = "RUNNING" if self._alive(process) else "FAILED"
        receipt_path = directory / "artifacts/result.json"
        if not self._alive(process) and receipt_path.exists() and receipt_path.stat().st_mtime >= process["started"]:
            receipt = json.loads(receipt_path.read_text())
            phase = receipt.get("status", "FAILED")
            body["artifact_receipt"] = receipt
        if process.get("cancel_requested") and not self._alive(process):
            phase = "CANCELLED"
        body["metadata"].update(uid=row.id, resourceVersion=str(process["started"]))
        body["status"] = {"phase": phase}
        return body

    def cancel_finetune(self, row, resource_version):
        directory = self.directory(row)
        record = json.loads((directory / "process.json").read_text())
        if str(record["started"]) != resource_version:
            raise RuntimeFailure("Native job version changed")
        if self._alive(record):self._signal(record, directory)
        elif self.get_finetune(row).get("status",{}).get("phase")!="PAUSED":
            raise RuntimeFailure("Cannot cancel a terminal native worker")
        record["cancel_requested"] = True
        save(directory / "process.json", record)

    def _signal(self, record, directory):
        if not self._alive(record):
            raise RuntimeFailure("Worker is not active")
        process = psutil.Process(record["pid"])
        if str(directory / "config.json") not in process.cmdline():
            raise RuntimeFailure("Worker command identity mismatch")
        process.send_signal(signal.SIGTERM)

    def pause_finetune(self, row):
        directory = self.directory(row)
        self._signal(json.loads((directory / "process.json").read_text()), directory)

    def resume_finetune(self, row):
        if not (self.directory(row) / "artifacts/resume.pt").is_file():
            raise RuntimeFailure("No resumable optimizer/RNG checkpoint")
        self._launch(row, resume=True)

    def create_deployment(self, row, artifact):
        self.serving.start(row, artifact)
    def patch_deployment(self, row, artifact):
        self.serving.start(row, artifact)
    def get_deployment(self, row):
        return self.serving.get(row)
    def delete_deployment(self, row):
        self.serving.delete(row)
    def patch_canary(self, *args, **kwargs):
        raise RuntimeUnavailable("Native backend has no Gateway canary; use Kubernetes")
