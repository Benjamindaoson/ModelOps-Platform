"""Single-host SmolVLA control plane. No Kubernetes scheduling is implied."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import signal
import subprocess
import time
from pathlib import Path


def sha256_file(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as f:
        for b in iter(lambda: f.read(2**20), b""):
            h.update(b)
    return h.hexdigest()


def identity(value):
    if not re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9_.-]{0,100}", value):
        raise ValueError("Invalid identity")
    return value


def write(path, obj):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(".tmp")
    temp.write_text(json.dumps(obj, indent=2, sort_keys=True) + "\n")
    os.replace(temp, path)


def verify_bound_files(record):
    """Reject drift in a registered VLA processor, normalizer, data or base."""
    for path_field, digest_field in (
        ("processor_file", "processor_sha256"),
        ("normalizer_file", "normalizer_sha256"),
        ("dataset_manifest", "dataset_sha256"),
        ("base_file", "base_sha256"),
    ):
        if path_field in record:
            path = Path(record[path_field])
            if not path.is_file() or sha256_file(path) != record.get(digest_field):
                raise ValueError(f"{path_field} artifact integrity failure")


class Registry:
    def __init__(self, root):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def register(self, record):
        key = identity(record["version"])
        p = self.root / (key + ".json")
        for field in [
            "checkpoint_sha256",
            "processor_sha256",
            "dataset_sha256",
            "base_sha256",
        ]:
            if not re.fullmatch("[a-f0-9]{64}", record.get(field, "")):
                raise ValueError("Missing digest")
        if (
            not record.get("run_id")
            or sha256_file(record["checkpoint"]) != record["checkpoint_sha256"]
        ):
            raise ValueError("Artifact integrity failure")
        verify_bound_files(record)
        if p.exists():
            if json.loads(p.read_text()) != record:
                raise ValueError("Immutable version already exists")
            return record
        # Exclusive creation protects immutable registration across processes.
        with p.open("x") as f:
            json.dump(record, f, indent=2, sort_keys=True)
        return record

    def resolve(self, version):
        r = json.loads((self.root / (identity(version) + ".json")).read_text())
        if sha256_file(r["checkpoint"]) != r["checkpoint_sha256"]:
            raise ValueError("Registered artifact mutated")
        verify_bound_files(r)
        return r

    def deploy(self, version, evaluation):
        record = self.resolve(version)
        if evaluation.get("scope") != "M05-development" or not evaluation.get("passed"):
            raise ValueError(
                "Only qualified M05 simulation development revisions can deploy"
            )
        if evaluation.get("checkpoint_sha256") != record["checkpoint_sha256"]:
            raise ValueError("Evaluation/checkpoint mismatch")
        if evaluation.get("total", 0) < 1 or evaluation.get("illegal_actions", 1) != 0:
            raise ValueError("Missing actual robot evaluation")
        p = self.root / "deployments.jsonl"
        entries = (
            [json.loads(x) for x in p.read_text().splitlines()] if p.exists() else []
        )
        r = {
            "revision": len(entries) + 1,
            "version": version,
            "previous": entries[-1]["version"] if entries else None,
            "evaluation": evaluation,
            "time": time.time(),
            "scope": "simulation_only",
        }
        with p.open("a") as f:
            f.write(json.dumps(r) + "\n")
        write(self.root / "active.json", r)
        return r

    def rollback(self, version):
        self.resolve(version)
        entries = [
            json.loads(x)
            for x in (self.root / "deployments.jsonl").read_text().splitlines()
        ]
        prior = next((r for r in reversed(entries) if r["version"] == version), None)
        if prior is None:
            raise ValueError("Version was never qualified")
        return self.deploy(version, prior["evaluation"])


class Jobs:
    def __init__(self, root, vla_root):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.vla = Path(vla_root).resolve()
        self.entry = (
            self.vla / "benchmarks/robot-vla-engine/scripts/run_m05_training.py"
        )
        self.python = self.vla / ".venv/bin/python"
        if not self.entry.is_file() or not self.python.exists():
            raise ValueError("VLA runner unavailable")

    def directory(self, run_id):
        return self.root / identity(run_id)

    def create(self, config):
        run_id = identity(config["run_id"])
        d = self.directory(run_id)
        if d.exists():
            raise FileExistsError("Run already exists")
        if config.get("dataset") not in ["corrective", "standard", "replay"]:
            raise ValueError("Not a SmolVLA dataset type")
        if not 1 <= config.get("steps", 0) <= 1000:
            raise ValueError("Run exceeds bounded update budget")
        d.mkdir()
        config = dict(config)
        config["output"] = str(d / "artifacts")
        write(d / "config.json", config)
        write(
            d / "job.json",
            {
                "schema": "modelops.smolvla-linux.v1",
                "run_id": run_id,
                "state": "CREATED",
                "runner": str(self.entry),
                "runner_sha256": sha256_file(self.entry),
                "created": time.time(),
                "attempts": [],
            },
        )
        return self.query(run_id)

    def start(self, run_id, resume=False):
        import fcntl

        d = self.directory(run_id)
        with (d / "control.lock").open("a") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            r = self.query(run_id)
            if r["state"] == "RUNNING":
                raise ValueError("Run already active")
            j = json.loads((d / "job.json").read_text())
            if sha256_file(self.entry) != j["runner_sha256"]:
                raise ValueError("Pinned runner changed")
            c = json.loads((d / "config.json").read_text())
            if resume:
                ck = d / "artifacts/resume.pt"
                if not ck.exists():
                    raise ValueError("No resumable checkpoint")
                c["resume"] = str(ck)
                c.pop("stop_after", None)
            elif j["attempts"]:
                raise ValueError("Use explicit resume after an attempt")
            write(d / "config.json", c)
            with (d / "process.log").open("ab") as log:
                env = os.environ.copy()
                env.pop("LD_LIBRARY_PATH", None)
                env["MODEL_OPS_RUN_ID"] = run_id
                proc = subprocess.Popen(
                    [
                        str(self.python),
                        str(self.entry),
                        "--config",
                        str(d / "config.json"),
                    ],
                    cwd=self.vla,
                    env=env,
                    stdout=log,
                    stderr=subprocess.STDOUT,
                    start_new_session=True,
                )
            import psutil

            j["attempts"].append(
                {
                    "pid": proc.pid,
                    "create_time": psutil.Process(proc.pid).create_time(),
                    "started": time.time(),
                    "resume": resume,
                }
            )
            j["state"] = "RUNNING"
            write(d / "job.json", j)
            return j

    def query(self, run_id):
        import psutil

        d = self.directory(run_id)
        j = json.loads((d / "job.json").read_text())
        if j["attempts"]:
            a = j["attempts"][-1]
            alive = False
            try:
                p = psutil.Process(a["pid"])
                alive = (
                    p.create_time() == a["create_time"]
                    and p.status() != psutil.STATUS_ZOMBIE
                )
            except psutil.NoSuchProcess:
                pass
            result = d / "artifacts/result.json"
            if alive:
                j["state"] = "RUNNING"
            elif result.exists() and result.stat().st_mtime >= a["started"]:
                j["result"] = json.loads(result.read_text())
                j["state"] = j["result"]["status"]
            else:
                j["state"] = "FAILED"
                j["failure_reason"] = (
                    "Worker exited without a current completion receipt; inspect process.log"
                )
        return j

    def stop(self, run_id):
        import psutil

        j = self.query(run_id)
        if j["state"] != "RUNNING":
            raise ValueError("Run is not active")
        a = j["attempts"][-1]
        p = psutil.Process(a["pid"])
        if p.create_time() != a["create_time"] or str(self.entry) not in p.cmdline():
            raise ValueError("Process identity mismatch; refusing signal")
        p.send_signal(signal.SIGTERM)
        return {"run_id": run_id, "state": "STOP_REQUESTED"}


def export_tracking(job_dir, tracking_uri):
    import mlflow

    p = Path(job_dir)
    config = json.loads((p / "config.json").read_text())
    info = json.loads((p / "artifacts/identity.json").read_text())
    mlflow.set_tracking_uri(tracking_uri)
    mlflow.set_experiment("VLA-Forge-M05")
    with mlflow.start_run(run_name=config["run_id"]) as run:
        mlflow.log_params(
            {k: str(v) for k, v in info.items() if k != "trainable_names"}
        )
        for line in (p / "artifacts/steps.jsonl").read_text().splitlines():
            row = json.loads(line)
            mlflow.log_metrics(
                {k: v for k, v in row.items() if isinstance(v, (int, float))},
                step=row["step"],
            )
        # Metrics only: no private images or model weights are copied.
        for file in [
            "config.json",
            "identity.json",
            "result.json",
            "steps.jsonl",
            "resources.jsonl",
        ]:
            source = p / file if file == "config.json" else p / "artifacts" / file
            if source.exists():
                mlflow.log_artifact(str(source))
        write(
            p / "mlflow.json",
            {
                "run_id": config["run_id"],
                "mlflow_run_id": run.info.run_id,
                "tracking_uri": tracking_uri,
            },
        )
        return run.info.run_id


def main():
    a = argparse.ArgumentParser()
    a.add_argument(
        "operation", choices=["create", "start", "stop", "resume", "query", "track"]
    )
    a.add_argument("--root", required=True)
    a.add_argument("--vla-root", required=True)
    a.add_argument("--run-id")
    a.add_argument("--config")
    a.add_argument("--tracking-uri")
    x = a.parse_args()
    j = Jobs(x.root, x.vla_root)
    if x.operation == "create":
        r = j.create(json.loads(Path(x.config).read_text()))
    elif x.operation == "start":
        r = j.start(x.run_id)
    elif x.operation == "resume":
        r = j.start(x.run_id, True)
    elif x.operation == "stop":
        r = j.stop(x.run_id)
    elif x.operation == "track":
        r = export_tracking(j.directory(x.run_id), x.tracking_uri)
    else:
        r = j.query(x.run_id)
    print(json.dumps(r, indent=2))


if __name__ == "__main__":
    main()
