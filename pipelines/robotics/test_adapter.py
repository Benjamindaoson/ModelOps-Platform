import importlib.util

import pytest


def module():
    assert importlib.util.find_spec("pipelines.robotics.adapter"), (
        "SmolVLA adapter missing"
    )
    from pipelines.robotics import adapter

    return adapter


def test_registry_rejects_artifact_mutation(tmp_path):
    m = module()
    f = tmp_path / "weight"
    f.write_bytes(b"original")
    registry = m.Registry(tmp_path / "registry")
    r = {
        "version": "v1",
        "checkpoint": str(f),
        "checkpoint_sha256": m.sha256_file(f),
        "processor_sha256": "a" * 64,
        "dataset_sha256": "b" * 64,
        "run_id": "r1",
        "base_sha256": "c" * 64,
    }
    registry.register(r)
    assert registry.resolve("v1")["run_id"] == "r1"
    f.write_bytes(b"tampered")
    with pytest.raises(ValueError):
        registry.resolve("v1")


def test_registry_refuses_redefinition_and_unqualified_deployment(tmp_path):
    m = module()
    f = tmp_path / "weight"
    f.write_bytes(b"original")
    r = m.Registry(tmp_path / "r")
    info = {
        "version": "v1",
        "checkpoint": str(f),
        "checkpoint_sha256": m.sha256_file(f),
        "processor_sha256": "a" * 64,
        "dataset_sha256": "b" * 64,
        "run_id": "r1",
        "base_sha256": "c" * 64,
    }
    r.register(info)
    with pytest.raises(ValueError):
        r.register({**info, "run_id": "other"})
    with pytest.raises(ValueError):
        r.deploy("v1", {"scope": "M06", "passed": True})


def test_reject_path_traversal(tmp_path):
    m = module()
    with pytest.raises(ValueError):
        m.Registry(tmp_path).resolve("../../x")


def test_jobs_bind_runner_and_reject_duplicate_execution(tmp_path):
    m = module()
    v = tmp_path / "vla"
    (v / ".venv/bin").mkdir(parents=True)
    (v / ".venv/bin/python").symlink_to(__import__("sys").executable)
    entry = v / "benchmarks/robot-vla-engine/scripts/run_m05_training.py"
    entry.parent.mkdir(parents=True)
    entry.write_text("import time;time.sleep(2)")
    j = m.Jobs(tmp_path / "jobs", v)
    j.create({"run_id": "unit-worker", "steps": 2, "dataset": "corrective"})
    first = j.start("unit-worker")
    try:
        assert j.query("unit-worker")["state"] == "RUNNING"
        with pytest.raises(ValueError):
            j.start("unit-worker")
        assert j.stop("unit-worker")["state"] == "STOP_REQUESTED"
    finally:
        import os
        import signal

        try:
            os.kill(first["attempts"][-1]["pid"], signal.SIGTERM)
        except ProcessLookupError:
            pass


def test_dev_registration_and_rollback_keep_revision_history(tmp_path):
    m = module()
    r = m.Registry(tmp_path / "registry")
    for version in ["base", "new"]:
        f = tmp_path / version
        f.write_bytes(version.encode())
        h = m.sha256_file(f)
        r.register(
            {
                "version": version,
                "checkpoint": str(f),
                "checkpoint_sha256": h,
                "processor_sha256": "a" * 64,
                "dataset_sha256": "b" * 64,
                "run_id": version,
                "base_sha256": "c" * 64,
            }
        )
        r.deploy(
            version,
            {
                "scope": "M05-development",
                "passed": True,
                "checkpoint_sha256": h,
                "total": 4,
                "success": 2,
                "illegal_actions": 0,
            },
        )
    x = r.rollback("base")
    assert x["revision"] == 3 and x["previous"] == "new" and x["version"] == "base"


def test_serving_lists_only_evaluated_and_compatible_versions(tmp_path):
    from pipelines.robotics.serve import qualified_versions

    m = module()
    registry = m.Registry(tmp_path / "registry")
    for name in ("base", "corrective"):
        model = tmp_path / name
        model.write_bytes(name.encode())
        digest = m.sha256_file(model)
        registry.register({"version": name, "checkpoint": str(model), "checkpoint_sha256": digest, "processor_sha256": "a" * 64, "normalizer_sha256": "b" * 64, "dataset_sha256": "c" * 64, "base_sha256": "d" * 64, "run_id": name, "model_kind": "base" if name == "base" else "adapter"})
    with pytest.raises(ValueError, match="No real"):
        qualified_versions(registry)
    base = registry.resolve("base")
    registry.deploy("base", {"scope": "M05-development", "passed": True, "checkpoint_sha256": base["checkpoint_sha256"], "total": 1, "success": 0, "illegal_actions": 0})
    versions, _ = qualified_versions(registry)
    assert versions == {"base": None}
    corrective = registry.resolve("corrective")
    registry.deploy("corrective", {"scope": "M05-development", "passed": True, "checkpoint_sha256": corrective["checkpoint_sha256"], "total": 1, "success": 0, "illegal_actions": 0})
    versions, _ = qualified_versions(registry)
    assert versions["corrective"] == str((tmp_path / "corrective").parent)
    (tmp_path / "corrective").write_bytes(b"mutated")
    with pytest.raises(ValueError, match="mutated"):
        qualified_versions(registry)


def test_registry_rechecks_processor_and_dataset_contract_files(tmp_path):
    m = module()
    files = {name: tmp_path / name for name in ("weight", "processor", "normalizer", "dataset", "base")}
    for name, path in files.items():
        path.write_bytes(name.encode())
    registry = m.Registry(tmp_path / "registry")
    record = {"version": "bound", "run_id": "run", "checkpoint": str(files["weight"]), "checkpoint_sha256": m.sha256_file(files["weight"]), "processor_file": str(files["processor"]), "processor_sha256": m.sha256_file(files["processor"]), "normalizer_file": str(files["normalizer"]), "normalizer_sha256": m.sha256_file(files["normalizer"]), "dataset_manifest": str(files["dataset"]), "dataset_sha256": m.sha256_file(files["dataset"]), "base_file": str(files["base"]), "base_sha256": m.sha256_file(files["base"])}
    registry.register(record)
    files["dataset"].write_bytes(b"changed")
    with pytest.raises(ValueError, match="Dataset|dataset"):
        registry.resolve("bound")
