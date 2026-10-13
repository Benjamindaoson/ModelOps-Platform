"""Unified serving configuration, preserving legacy deployments."""
from alembic import op
import sqlalchemy as sa
revision="0006_serving_configuration"
down_revision="0005_training_state"
branch_labels=None
depends_on=None
def upgrade():
    with op.batch_alter_table("deployments") as batch:
        batch.add_column(sa.Column("quantization",sa.String(20),nullable=False,server_default="none"))
        batch.add_column(sa.Column("cache",sa.Boolean(),nullable=False,server_default=sa.false()))
        batch.add_column(sa.Column("custom_json",sa.Text(),nullable=True))
def downgrade():
    with op.batch_alter_table("deployments") as batch:
        batch.drop_column("custom_json");batch.drop_column("cache");batch.drop_column("quantization")
