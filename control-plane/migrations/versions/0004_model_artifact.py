"""Unified model artifact metadata; retain legacy columns and identities."""
from alembic import op
import sqlalchemy as sa

revision = "0004_model_artifact"
down_revision = "0003_canary_desired_state"
branch_labels = None
depends_on = None

OPTIONAL = {
    "task_type": 80, "framework": 80, "base_model": 300, "adapter_type": 20,
    "adapter_uri": 500, "artifact_uri": 500, "training_run_id": 128, "evaluation_id": 128,
}


def upgrade():
    op.add_column("model_artifacts", sa.Column("model_type", sa.String(15), nullable=False, server_default="llm"))
    for name, length in OPTIONAL.items():
        op.add_column("model_artifacts", sa.Column(name, sa.String(length), nullable=True))
    op.add_column("model_artifacts", sa.Column("deployment_status", sa.String(25), nullable=False, server_default="registered"))
    op.execute("UPDATE model_artifacts SET model_type = family")
    # Missing historical metadata stays null; registration is not serving validation.


def downgrade():
    with op.batch_alter_table("model_artifacts") as batch:
        batch.drop_column("deployment_status")
        for name in reversed(list(OPTIONAL)):
            batch.drop_column(name)
        batch.drop_column("model_type")
