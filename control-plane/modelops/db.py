"""SQL metadata and immutable audit rows. Kubernetes is the only runtime authority."""
from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, create_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker


def now() -> datetime:
    return datetime.now(timezone.utc)


def uid() -> str:
    return str(uuid4())


class Base(DeclarativeBase):
    pass


class TenantRecord(Base):
    __tablename__ = "tenants"
    slug: Mapped[str] = mapped_column(String(40), primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class ModelArtifact(Base):
    __tablename__ = "model_artifacts"
    __table_args__ = (UniqueConstraint("tenant", "name", "version"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    tenant: Mapped[str] = mapped_column(String(40), ForeignKey("tenants.slug"), index=True)
    name: Mapped[str] = mapped_column(String(80), index=True)
    version: Mapped[int] = mapped_column(Integer)
    source: Mapped[str] = mapped_column(String(300))
    revision: Mapped[str] = mapped_column(String(140))
    digest: Mapped[str] = mapped_column(String(64))
    digest_verified: Mapped[bool] = mapped_column(default=False)
    family: Mapped[str] = mapped_column(String(15))
    created_by: Mapped[str] = mapped_column(String(150))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class DatasetVersion(Base):
    __tablename__ = "dataset_versions"
    __table_args__ = (UniqueConstraint("tenant", "name", "version"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    tenant: Mapped[str] = mapped_column(String(40), ForeignKey("tenants.slug"), index=True)
    name: Mapped[str] = mapped_column(String(80))
    version: Mapped[int] = mapped_column(Integer)
    uri: Mapped[str] = mapped_column(String(500))
    digest: Mapped[str] = mapped_column(String(64))
    train_count: Mapped[int] = mapped_column(Integer)
    heldout_count: Mapped[int] = mapped_column(Integer)
    created_by: Mapped[str] = mapped_column(String(150))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class Deployment(Base):
    __tablename__ = "deployments"
    __table_args__ = (UniqueConstraint("tenant", "name"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    tenant: Mapped[str] = mapped_column(String(40), ForeignKey("tenants.slug"), index=True)
    name: Mapped[str] = mapped_column(String(63))
    artifact_id: Mapped[str] = mapped_column(String(36), ForeignKey("model_artifacts.id"))
    engine: Mapped[str] = mapped_column(String(20))
    replicas: Mapped[int] = mapped_column(Integer)
    gpu: Mapped[int] = mapped_column(Integer)
    generation: Mapped[int] = mapped_column(Integer, default=1)
    canary_artifact_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("model_artifacts.id"), nullable=True)
    canary_weight: Mapped[int | None] = mapped_column(Integer, nullable=True)
    intent: Mapped[str] = mapped_column(String(25), default="requested")
    created_by: Mapped[str] = mapped_column(String(150))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class DeploymentRevision(Base):
    __tablename__ = "deployment_revisions"
    __table_args__ = (UniqueConstraint("deployment_id", "generation"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    deployment_id: Mapped[str] = mapped_column(String(36), ForeignKey("deployments.id"), index=True)
    generation: Mapped[int] = mapped_column(Integer)
    artifact_id: Mapped[str] = mapped_column(String(36), ForeignKey("model_artifacts.id"))
    operation: Mapped[str] = mapped_column(String(20))
    requested_by: Mapped[str] = mapped_column(String(150))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class FineTuneJob(Base):
    __tablename__ = "finetune_jobs"
    __table_args__ = (UniqueConstraint("tenant", "name"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    tenant: Mapped[str] = mapped_column(String(40), ForeignKey("tenants.slug"), index=True)
    name: Mapped[str] = mapped_column(String(63))
    artifact_id: Mapped[str] = mapped_column(String(36), ForeignKey("model_artifacts.id"))
    dataset_id: Mapped[str] = mapped_column(String(36), ForeignKey("dataset_versions.id"))
    method: Mapped[str] = mapped_column(String(10))
    parameters_json: Mapped[str] = mapped_column(Text)
    workflow_name: Mapped[str] = mapped_column(String(100))
    parent_job_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True, unique=True)
    attempt: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    intent: Mapped[str] = mapped_column(String(25), default="requested")
    created_by: Mapped[str] = mapped_column(String(150))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class AuditEvent(Base):
    __tablename__ = "audit_events"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    tenant: Mapped[str] = mapped_column(String(40), index=True)
    actor: Mapped[str] = mapped_column(String(150))
    action: Mapped[str] = mapped_column(String(70))
    object_kind: Mapped[str] = mapped_column(String(30))
    object_id: Mapped[str] = mapped_column(String(80))
    detail: Mapped[str] = mapped_column(Text, default="{}")
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


def make_session_factory(url: str):
    opts = {"check_same_thread": False} if url.startswith("sqlite") else {}
    engine = create_engine(url, connect_args=opts, pool_pre_ping=True)
    return engine, sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)

class EvaluationRecord(Base):
    __tablename__ = "evaluation_records"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    tenant: Mapped[str] = mapped_column(String(40), ForeignKey("tenants.slug"), index=True)
    artifact_id: Mapped[str] = mapped_column(String(36), ForeignKey("model_artifacts.id"))
    dataset_id: Mapped[str] = mapped_column(String(36), ForeignKey("dataset_versions.id"))
    report_sha256: Mapped[str] = mapped_column(String(64))
    metrics_json: Mapped[str] = mapped_column(Text)
    verified: Mapped[bool] = mapped_column(default=False)
    passed: Mapped[bool] = mapped_column(default=False)
    submitted_by: Mapped[str] = mapped_column(String(150))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class ReleaseApproval(Base):
    __tablename__ = "release_approvals"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    tenant: Mapped[str] = mapped_column(String(40), ForeignKey("tenants.slug"), index=True)
    artifact_id: Mapped[str] = mapped_column(String(36), ForeignKey("model_artifacts.id"))
    evaluation_id: Mapped[str] = mapped_column(String(36), ForeignKey("evaluation_records.id"))
    approver: Mapped[str] = mapped_column(String(150))
    reason: Mapped[str] = mapped_column(String(1000))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
