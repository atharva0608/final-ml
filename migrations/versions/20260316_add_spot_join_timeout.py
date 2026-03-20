"""add spot_join_timeout_minutes to cluster_optimization_settings

Revision ID: 20260316_spot_join_timeout
Revises: ed7f8dd2b28e
Create Date: 2026-03-16

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '20260316_spot_join_timeout'
down_revision = 'ed7f8dd2b28e'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        'cluster_optimization_settings',
        sa.Column('spot_join_timeout_minutes', sa.Integer(), nullable=True)
    )


def downgrade() -> None:
    op.drop_column('cluster_optimization_settings', 'spot_join_timeout_minutes')
