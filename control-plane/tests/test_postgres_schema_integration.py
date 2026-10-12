"""Actual PostgreSQL 16 upgrade/downgrade, data preservation and relational gates.

Set MODELOPS_POSTGRES_SCHEMA_TEST=1 and MODELOPS_DATABASE_URL to a dedicated
empty disposable PostgreSQL database. Never execute on a production database.
"""
from __future__ import annotations

import os
from pathlib import Path
from uuid import uuid4

import pytest

pytestmark = pytest.mark.skipif(
    os.getenv("MODELOPS_POSTGRES_SCHEMA_TEST") != "1",
    reason="Requires explicitly isolated PostgreSQL integration service",
)


def test_real_postgres_schema_history_and_row_preservation():
    from alembic import command
    from alembic.config import Config
    from sqlalchemy import create_engine, inspect, text
    from sqlalchemy.exc import IntegrityError

    url = os.environ["MODELOPS_DATABASE_URL"]
    if not url.startswith("postgresql+psycopg://") or "127.0.0.1:5432/modelops_ci" not in url:
        pytest.fail("Only the disposable local modelops_ci PostgreSQL database is allowed")
    engine = create_engine(url, pool_pre_ping=True)
    cfg = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
    try:
        assert "deployments" not in inspect(engine).get_table_names()
        command.upgrade(cfg, "0001_initial")
        first = {x["name"] for x in inspect(engine).get_columns("deployments")}
        assert "canary_artifact_id" not in first
        assert "generation" in first
        initial_jobs = {x["name"] for x in inspect(engine).get_columns("finetune_jobs")}
        assert "parent_job_id" not in initial_jobs
        model_id = str(uuid4())
        deployment_id = str(uuid4())
        with engine.begin() as db:
            db.execute(text(
                "INSERT INTO tenants (slug, created_at) VALUES ('ci', now())"
            ))
            db.execute(text("""
                INSERT INTO model_artifacts
                (id, tenant, name, version, source, revision, digest,
                 digest_verified, family, created_by, created_at)
                VALUES (:id, 'ci', 'qwen', 1, 'Qwen/Qwen2.5-0.5B-Instruct',
                        :revision, :digest, false, 'llm', 'postgres-ci', now())
            """), {"id": model_id, "revision": "a" * 40, "digest": "b" * 64})
            db.execute(text("""
                INSERT INTO deployments
                (id, tenant, name, artifact_id, engine, replicas, gpu,
                 generation, intent, created_by, created_at)
                VALUES (:id, 'ci', 'qwen-prod', :model, 'vllm', 1, 1,
                        1, 'requested', 'postgres-ci', now())
            """), {"id": deployment_id, "model": model_id})

        command.upgrade(cfg, "0002_train_job_lifecycle")
        intermediate_jobs = {x["name"] for x in inspect(engine).get_columns("finetune_jobs")}
        assert {"parent_job_id", "attempt"} <= intermediate_jobs
        assert "canary_weight" not in {x["name"] for x in inspect(engine).get_columns("deployments")}

        command.upgrade(cfg, "head")
        columns = {x["name"] for x in inspect(engine).get_columns("deployments")}
        assert {"canary_artifact_id", "canary_weight"} <= columns
        links = inspect(engine).get_foreign_keys("deployments")
        assert any(fk["referred_table"] == "model_artifacts" and
                   "canary_artifact_id" in fk["constrained_columns"] for fk in links)
        with engine.begin() as db:
            row = db.execute(text("SELECT artifact_id, replicas, intent FROM deployments WHERE id=:id"),
                             {"id": deployment_id}).one()
            assert tuple(row) == (model_id, 1, "requested")
            db.execute(text(
                "UPDATE deployments SET canary_artifact_id=:model, canary_weight=25 WHERE id=:id"
            ), {"model": model_id, "id": deployment_id})
        with pytest.raises(IntegrityError):
            with engine.begin() as db:
                db.execute(text("""
                    INSERT INTO deployments
                    (id, tenant, name, artifact_id, engine, replicas, gpu,
                     generation, intent, created_by, created_at)
                    VALUES (:id, 'ci', 'qwen-prod', :model, 'vllm', 1, 1,
                            1, 'requested', 'postgres-ci', now())
                """), {"id": str(uuid4()), "model": model_id})

        command.downgrade(cfg, "0002_train_job_lifecycle")
        cols_down = {x["name"] for x in inspect(engine).get_columns("deployments")}
        assert "canary_artifact_id" not in cols_down
        assert "canary_weight" not in cols_down
        with engine.connect() as db:
            stable = db.execute(text(
                "SELECT artifact_id, name, generation FROM deployments WHERE id=:id"
            ), {"id": deployment_id}).one()
            assert tuple(stable) == (model_id, "qwen-prod", 1)
        command.upgrade(cfg, "head")
        with engine.connect() as db:
            stable = db.execute(text(
                "SELECT artifact_id, name, canary_artifact_id, canary_weight "
                "FROM deployments WHERE id=:id"
            ), {"id": deployment_id}).one()
            assert tuple(stable) == (model_id, "qwen-prod", None, None)
    finally:
        engine.dispose()
