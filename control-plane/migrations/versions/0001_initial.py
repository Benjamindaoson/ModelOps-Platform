"""Pinned ModelOps v0.1 PostgreSQL schema, independent of future ORM changes.

Revision ID: 0001_initial
Revises:
Create Date: 2026-10-11

DO NOT import Base.metadata.create_all here: later ORM additions must never
change the historical baseline used to provision new databases. New columns
belong in independent forward Alembic revisions.
"""
from alembic import op
import sqlalchemy as sa

revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "tenants",
        sa.Column("slug", sa.String(40), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "model_artifacts",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("tenant", sa.String(40), sa.ForeignKey("tenants.slug"), nullable=False),
        sa.Column("name", sa.String(80), nullable=False),
        sa.Column("version", sa.Integer, nullable=False),
        sa.Column("source", sa.String(300), nullable=False),
        sa.Column("revision", sa.String(140), nullable=False),
        sa.Column("digest", sa.String(64), nullable=False),
        sa.Column("digest_verified", sa.Boolean, nullable=False),
        sa.Column("family", sa.String(15), nullable=False),
        sa.Column("created_by", sa.String(150), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("tenant", "name", "version"),
    )
    op.create_index("ix_model_artifacts_tenant", "model_artifacts", ["tenant"])
    op.create_index("ix_model_artifacts_name", "model_artifacts", ["name"])
    op.create_table(
        "dataset_versions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("tenant", sa.String(40), sa.ForeignKey("tenants.slug"), nullable=False),
        sa.Column("name", sa.String(80), nullable=False),
        sa.Column("version", sa.Integer, nullable=False),
        sa.Column("uri", sa.String(500), nullable=False),
        sa.Column("digest", sa.String(64), nullable=False),
        sa.Column("train_count", sa.Integer, nullable=False),
        sa.Column("heldout_count", sa.Integer, nullable=False),
        sa.Column("created_by", sa.String(150), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("tenant", "name", "version"),
    )
    op.create_index("ix_dataset_versions_tenant", "dataset_versions", ["tenant"])
    op.create_table(
        "deployments",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("tenant", sa.String(40), sa.ForeignKey("tenants.slug"), nullable=False),
        sa.Column("name", sa.String(63), nullable=False),
        sa.Column("artifact_id", sa.String(36), sa.ForeignKey("model_artifacts.id"), nullable=False),
        sa.Column("engine", sa.String(20), nullable=False),
        sa.Column("replicas", sa.Integer, nullable=False),
        sa.Column("gpu", sa.Integer, nullable=False),
        sa.Column("generation", sa.Integer, nullable=False),
        sa.Column("intent", sa.String(25), nullable=False),
        sa.Column("created_by", sa.String(150), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("tenant", "name"),
    )
    op.create_index("ix_deployments_tenant", "deployments", ["tenant"])
    op.create_table(
        "deployment_revisions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("deployment_id", sa.String(36), sa.ForeignKey("deployments.id"), nullable=False),
        sa.Column("generation", sa.Integer, nullable=False),
        sa.Column("artifact_id", sa.String(36), sa.ForeignKey("model_artifacts.id"), nullable=False),
        sa.Column("operation", sa.String(20), nullable=False),
        sa.Column("requested_by", sa.String(150), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("deployment_id", "generation"),
    )
    op.create_index("ix_deployment_revisions_deployment_id", "deployment_revisions", ["deployment_id"])
    op.create_table(
        "finetune_jobs",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("tenant", sa.String(40), sa.ForeignKey("tenants.slug"), nullable=False),
        sa.Column("name", sa.String(63), nullable=False),
        sa.Column("artifact_id", sa.String(36), sa.ForeignKey("model_artifacts.id"), nullable=False),
        sa.Column("dataset_id", sa.String(36), sa.ForeignKey("dataset_versions.id"), nullable=False),
        sa.Column("method", sa.String(10), nullable=False),
        sa.Column("parameters_json", sa.Text, nullable=False),
        sa.Column("workflow_name", sa.String(100), nullable=False),
        sa.Column("intent", sa.String(25), nullable=False),
        sa.Column("created_by", sa.String(150), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("tenant", "name"),
    )
    op.create_index("ix_finetune_jobs_tenant", "finetune_jobs", ["tenant"])
    op.create_table(
        "audit_events",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("tenant", sa.String(40), nullable=False),
        sa.Column("actor", sa.String(150), nullable=False),
        sa.Column("action", sa.String(70), nullable=False),
        sa.Column("object_kind", sa.String(30), nullable=False),
        sa.Column("object_id", sa.String(80), nullable=False),
        sa.Column("detail", sa.Text, nullable=False),
        sa.Column("at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_audit_events_tenant", "audit_events", ["tenant"])
    op.create_table(
        "evaluation_records",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("tenant", sa.String(40), sa.ForeignKey("tenants.slug"), nullable=False),
        sa.Column("artifact_id", sa.String(36), sa.ForeignKey("model_artifacts.id"), nullable=False),
        sa.Column("dataset_id", sa.String(36), sa.ForeignKey("dataset_versions.id"), nullable=False),
        sa.Column("report_sha256", sa.String(64), nullable=False),
        sa.Column("metrics_json", sa.Text, nullable=False),
        sa.Column("verified", sa.Boolean, nullable=False),
        sa.Column("passed", sa.Boolean, nullable=False),
        sa.Column("submitted_by", sa.String(150), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_evaluation_records_tenant", "evaluation_records", ["tenant"])
    op.create_table(
        "release_approvals",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("tenant", sa.String(40), sa.ForeignKey("tenants.slug"), nullable=False),
        sa.Column("artifact_id", sa.String(36), sa.ForeignKey("model_artifacts.id"), nullable=False),
        sa.Column("evaluation_id", sa.String(36), sa.ForeignKey("evaluation_records.id"), nullable=False),
        sa.Column("approver", sa.String(150), nullable=False),
        sa.Column("reason", sa.String(1000), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_release_approvals_tenant", "release_approvals", ["tenant"])


def downgrade() -> None:
    op.drop_index("ix_release_approvals_tenant", table_name="release_approvals")
    op.drop_table("release_approvals")
    op.drop_index("ix_evaluation_records_tenant", table_name="evaluation_records")
    op.drop_table("evaluation_records")
    op.drop_index("ix_audit_events_tenant", table_name="audit_events")
    op.drop_table("audit_events")
    op.drop_index("ix_finetune_jobs_tenant", table_name="finetune_jobs")
    op.drop_table("finetune_jobs")
    op.drop_index("ix_deployment_revisions_deployment_id", table_name="deployment_revisions")
    op.drop_table("deployment_revisions")
    op.drop_index("ix_deployments_tenant", table_name="deployments")
    op.drop_table("deployments")
    op.drop_index("ix_dataset_versions_tenant", table_name="dataset_versions")
    op.drop_table("dataset_versions")
    op.drop_index("ix_model_artifacts_name", table_name="model_artifacts")
    op.drop_index("ix_model_artifacts_tenant", table_name="model_artifacts")
    op.drop_table("model_artifacts")
    op.drop_table("tenants")
