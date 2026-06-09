"""add org person to files

Revision ID: 0001
Revises:
Create Date: 2026-06-09

"""
from alembic import op
import sqlalchemy as sa

revision = '0001'
down_revision = '80825cc4b41f'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('files', sa.Column('org', sa.String(length=128), nullable=True))
    op.add_column('files', sa.Column('person', sa.String(length=256), nullable=True))


def downgrade() -> None:
    op.drop_column('files', 'person')
    op.drop_column('files', 'org')
