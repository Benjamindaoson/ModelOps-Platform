"""Simulation-only SmolVLA serving from qualified immutable ModelOps versions."""
import argparse
import fcntl
import json
from pathlib import Path

from pipelines.robotics.adapter import Registry


def qualified_versions(registry):
    path = registry.root / "deployments.jsonl"
    if not path.is_file():
        raise ValueError("No real M05 development evaluation has qualified a version")
    deployments = [json.loads(line) for line in path.read_text().splitlines() if line]
    versions, evaluations, contracts = {}, {}, set()
    for deployment in deployments:
        version = deployment["version"]
        record = registry.resolve(version)
        evaluation = deployment["evaluation"]
        if evaluation.get("scope") != "M05-development" or not evaluation.get("passed"):
            continue
        contracts.add((record["processor_sha256"], record.get("normalizer_sha256")))
        versions[version] = None if record.get("model_kind") == "base" else str(Path(record["checkpoint"]).parent)
        evaluations[version] = evaluation
    if not versions or len(contracts) != 1:
        raise ValueError("No compatible, evaluated policy/processor contract")
    return versions, evaluations


def create_managed_app(registry_root, backend, log_path):
    from robot_vla.m05_serving import PolicyEngine, create_app

    registry = Registry(registry_root)
    active = json.loads((registry.root / "active.json").read_text())
    versions, evaluations = qualified_versions(registry)
    version = active["version"]
    if version not in versions:
        raise ValueError("Active policy was not qualified by M05 development evaluation")
    engine = PolicyEngine(version, versions[version], backend)

    def activate(next_version, rollback):
        if rollback:
            return registry.rollback(next_version)
        return registry.deploy(next_version, evaluations[next_version])

    app = create_app(engine, versions, log_path, activate=activate)

    @app.get("/modelops/active")
    def modelops_active():
        current = json.loads((registry.root / "active.json").read_text())
        return {"version": current["version"], "revision": current["revision"], "scope": current["scope"]}

    return app


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--registry", type=Path, required=True)
    parser.add_argument("--backend", choices=("eager", "cuda_graph", "bf16", "fp16", "tf32", "compile"), default="eager")
    parser.add_argument("--log", type=Path, required=True)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=18767)
    parser.add_argument("--gpu-lock", type=Path, default=Path("/data/VLA-Forge/Evidence/M05/gpu.lock"))
    args = parser.parse_args()
    if args.host not in ("127.0.0.1", "localhost"):
        raise ValueError("M05 policy serving is authorized only on loopback")
    import uvicorn

    args.gpu_lock.parent.mkdir(parents=True, exist_ok=True)
    with args.gpu_lock.open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        app = create_managed_app(args.registry, args.backend, args.log)
        uvicorn.run(app, host="127.0.0.1", port=args.port, log_level="info")

if __name__ == "__main__":
    main()
