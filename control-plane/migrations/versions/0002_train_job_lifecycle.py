"""Add per-run immutable retry ancestry and attempt counters.

Revision ID: 0002_train_job_lifecycle
Revises: 0001_initial
"""
from alembic import op
import sqlalchemy as sa

revision = "0002_train_job_lifecycle"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


def _has_column(inspector, column: str) -> bool:
    return any(item["name"] == column for item in inspector.get_columns("finetune_jobs"))


def upgrade() -> None:
    connection = op.get_bind()
    inspector = sa.inspect(connection)
    # Earlier migration 0001 creates tables from ORM metadata. Therefore a
    # new database can already have these columns; old installations cannot.
    if not _has_column(inspector, "parent_job_id"):
        op.add_column("finetune_jobs", sa.Column("parent_job_id", sa.String(36), nullable=True))
    if not _has_column(inspector, "attempt"):
        op.add_column("finetune_jobs", sa.Column("attempt", sa.Integer(),
                                                server_default="1", nullable=False))
    indexes = {item["name"] for item in sa.inspect(connection).get_indexes("finetune_jobs")}
    if "ix_finetune_jobs_parent_job_id" not in indexes:
        op.create_index("ix_finetune_jobs_parent_job_id", "finetune_jobs", ["parent_job_id"])


def downgrade() -> None:
    connection = op.get_bind()
    indexes = {item["name"] for item in sa.inspect(connection).get_indexes("finetune_jobs")}
    if "ix_finetune_jobs_parent_job_id" in indexes:
        op.drop_index("ix_finetune_jobs_parent_job_id", table_name="finetune_jobs")
    if _has_column(sa.inspect(connection), "parent_job_id"):
        op.drop_column("finetune_jobs", "parent_job_id")
    if _has_column(sa.inspect(connection), "attempt"):
        op.drop_column("finetune_jobs", "attempt")
