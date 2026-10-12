"""Initial ModelOps metadata schema.

Revision ID: 0001_initial
Revises:
Create Date: 2026-10-11

Schema is derived from pinned ModelOps 0.1 ORM metadata; future revisions
must use explicit Alembic DDL and must not auto-upgrade at runtime.
"""
from alembic import op
from modelops.db import Base

revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None

def upgrade() -> None:
    Base.metadata.create_all(bind=op.get_bind())

def downgrade() -> None:
    # WARNING: destructive. Never run against production without a snapshot.
    Base.metadata.drop_all(bind=op.get_bind())
