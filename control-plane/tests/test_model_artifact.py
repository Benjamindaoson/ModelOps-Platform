"""Real API/SQLite contracts for unified immutable artifact metadata."""
import pytest
import importlib.util
from pathlib import Path

_spec = importlib.util.spec_from_file_location("v1_api_fixtures", Path(__file__).with_name("test_api.py"))
_fixture_module = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_fixture_module)
api = _fixture_module.api
headers = _fixture_module.headers
model_payload = _fixture_module.model_payload


def create(client, **extra):
    return client.post("/api/v1/models", headers=headers(), json={**model_payload(), **extra})


def test_legacy_artifact_derives_type_and_remains_readable(api):
    client, _ = api
    response = create(client)
    assert response.status_code == 201
    row = response.json()
    assert row["family"] == row["model_type"] == "llm"
    assert row["deployment_status"] == "registered"
    assert row["adapter_uri"] is None
    assert client.get("/api/v1/models/" + row["id"], headers=headers()).json()["digest"] == row["digest"]


@pytest.mark.parametrize("kind,framework,task", [
    ("llm", "transformers", "text-generation"),
    ("vlm", "transformers", "vision-language"),
    ("vla", "lerobot", "action-prediction"),
    ("embedding", "transformers", "embedding"),
])
def test_typed_artifacts_preserve_training_lineage(api, kind, framework, task):
    client, _ = api
    body = model_payload()
    body.pop("family")
    body.update(model_type=kind, framework=framework, task_type=task,
                base_model="Qwen/Qwen2.5-0.5B-Instruct", adapter_type="lora",
                adapter_uri="file:///data/ModelOps-Platform/private/adapter",
                artifact_uri="file:///data/ModelOps-Platform/private/weights",
                training_run_id="v1-sft-001")
    response = client.post("/api/v1/models", headers=headers(), json=body)
    assert response.status_code == 201, response.text
    row = response.json()
    assert row["family"] == row["model_type"] == kind
    assert row["training_run_id"] == "v1-sft-001"
    assert row["adapter_type"] == "lora"
    assert row["framework"] == framework
    assert client.get("/api/v1/models/" + row["id"], headers=headers("beta")).status_code == 404


def test_conflicting_legacy_family_is_rejected(api):
    client, _ = api
    assert create(client, model_type="vla").status_code == 422


@pytest.mark.parametrize("uri", [
    "file:///data/../etc/shadow",
    "https://user:password@example.com/model",
    "file:///data/model\nother",
])
def test_unsafe_artifact_uri_is_rejected(api, uri):
    client, _ = api
    assert create(client, artifact_uri=uri).status_code == 422


def test_client_cannot_claim_deployment_by_registering_metadata(api):
    client, _ = api
    assert create(client, deployment_status="deployed").status_code == 422


def test_adapter_location_requires_adapter_type(api):
    client, _ = api
    assert create(client, adapter_uri="file:///data/ModelOps-Platform/private/adapter").status_code == 422


def test_unified_artifact_migration_preserves_legacy_rows(tmp_path, monkeypatch):
    from pathlib import Path
    from alembic import command
    from alembic.config import Config
    from sqlalchemy import create_engine, inspect, text
    root = Path(__file__).resolve().parents[1]
    url = "sqlite:///" + str(tmp_path / "legacy.sqlite")
    monkeypatch.setenv("MODELOPS_DATABASE_URL", url)
    cfg = Config(str(root / "alembic.ini"))
    command.upgrade(cfg, "0003_canary_desired_state")
    engine = create_engine(url)
    with engine.begin() as conn:
        conn.execute(text("INSERT INTO tenants (slug,created_at) VALUES ('alpha','2026-10-13')"))
        conn.execute(text("INSERT INTO model_artifacts "
            "(id,tenant,name,version,source,revision,digest,digest_verified,family,created_by,created_at) "
            "VALUES ('legacy','alpha','qwen',1,'Qwen/base','abcdef0123',:digest,0,'llm','test','2026-10-13')"),
            {"digest": "a" * 64})
    command.upgrade(cfg, "head")
    assert "model_type" in {col["name"] for col in inspect(engine).get_columns("model_artifacts")}
    with engine.connect() as conn:
        row = conn.execute(text("SELECT model_type,deployment_status FROM model_artifacts WHERE id='legacy'")).one()
        assert tuple(row) == ("llm", "registered")
    command.downgrade(cfg, "0003_canary_desired_state")
    with engine.connect() as conn:
        assert conn.scalar(text("SELECT name FROM model_artifacts WHERE id='legacy'")) == "qwen"
    command.upgrade(cfg, "head")
    engine.dispose()
