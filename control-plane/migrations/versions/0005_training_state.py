"""Persistent canonical training state alongside legacy Argo identity."""
from alembic import op
import sqlalchemy as sa

revision = "0005_training_state"
down_revision = "0004_model_artifact"
branch_labels = None
depends_on = None

def upgrade():
    op.add_column("finetune_jobs", sa.Column("worker", sa.String(20), nullable=False, server_default="argo"))
    op.add_column("finetune_jobs", sa.Column("state", sa.String(20), nullable=False, server_default="QUEUED"))
    op.add_column("finetune_jobs", sa.Column("runtime_run_id", sa.String(128), nullable=True))

def downgrade():
    with op.batch_alter_table("finetune_jobs") as batch:
        batch.drop_column("runtime_run_id")
        batch.drop_column("state")
        batch.drop_column("worker")
