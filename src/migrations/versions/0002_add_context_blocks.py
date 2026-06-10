"""add context_blocks to files

Revision ID: 0002
Revises:
Create Date: 2026-06-10

"""
from alembic import op

revision = "0002"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE files ADD COLUMN IF NOT EXISTS context_blocks TEXT")


def downgrade() -> None:
    op.execute("ALTER TABLE files DROP COLUMN IF EXISTS context_blocks")
