"""Add recoverable canary desired-state fields to ModelOps deployment metadata.

Revision ID: 0003_canary_desired_state
Revises: 0002_train_job_lifecycle

Initial revision 0001 uses ORM metadata: guard columns for fresh installs;
older installations receive exactly the two nullable fields.
"""
from alembic import op
import sqlalchemy as sa

revision = "0003_canary_desired_state"
down_revision = "0002_train_job_lifecycle"
branch_labels = None
depends_on = None


def upgrade() -> None:
    existing = {c["name"] for c in sa.inspect(op.get_bind()).get_columns("deployments")}
    if "canary_artifact_id" not in existing:
        op.add_column("deployments", sa.Column("canary_artifact_id", sa.String(36),
                       sa.ForeignKey("model_artifacts.id"), nullable=True))
    if "canary_weight" not in existing:
        op.add_column("deployments", sa.Column("canary_weight", sa.Integer(), nullable=True))


def downgrade() -> None:
    existing = {c["name"] for c in sa.inspect(op.get_bind()).get_columns("deployments")}
    if "canary_weight" in existing:
        op.drop_column("deployments", "canary_weight")
    if "canary_artifact_id" in existing:
        op.drop_column("deployments", "canary_artifact_id")
