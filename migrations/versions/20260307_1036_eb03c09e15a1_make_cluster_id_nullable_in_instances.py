"""Make cluster_id nullable in instances

Revision ID: eb03c09e15a1
Revises: 002
Create Date: 2026-03-07 10:36:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'eb03c09e15a1'
down_revision = '002'

def upgrade() -> None:
    # Apply the specific change directly with raw SQL to handle differences
    op.execute("ALTER TABLE instances ALTER COLUMN cluster_id DROP NOT NULL")

def downgrade() -> None:
    op.execute("ALTER TABLE instances ALTER COLUMN cluster_id SET NOT NULL")
