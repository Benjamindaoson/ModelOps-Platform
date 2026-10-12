"""Add recoverable canary desired state with PostgreSQL/SQLite safe DDL.

Revision ID: 0003_canary_desired_state
Revises: 0002_train_job_lifecycle

Alembic batch mode ensures SQLite safely copies existing rows while adding
the foreign-key constraint. PostgreSQL applies ordinary ALTER TABLE.
Do not use the *current* ORM metadata as a historical DDL baseline.
"""
from alembic import op
import sqlalchemy as sa

revision = "0003_canary_desired_state"
down_revision = "0002_train_job_lifecycle"
branch_labels = None
depends_on = None


def _columns() -> set[str]:
    return {col["name"] for col in sa.inspect(op.get_bind()).get_columns("deployments")}


def upgrade() -> None:
    columns = _columns()
    if {"canary_artifact_id", "canary_weight"} <= columns:
        return
    with op.batch_alter_table("deployments", recreate="auto") as batch:
        if "canary_artifact_id" not in columns:
            batch.add_column(sa.Column(
                "canary_artifact_id", sa.String(36),
                sa.ForeignKey("model_artifacts.id"), nullable=True,
            ))
        if "canary_weight" not in columns:
            batch.add_column(sa.Column("canary_weight", sa.Integer(), nullable=True))


def downgrade() -> None:
    columns = _columns()
    if "canary_weight" not in columns and "canary_artifact_id" not in columns:
        return
    with op.batch_alter_table("deployments", recreate="auto") as batch:
        if "canary_weight" in columns:
            batch.drop_column("canary_weight")
        if "canary_artifact_id" in columns:
            batch.drop_column("canary_artifact_id")
