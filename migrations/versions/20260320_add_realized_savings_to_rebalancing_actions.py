"""Add realized_savings_hourly_usd and realized_savings_monthly_usd to rebalancing_actions — Issue #25

Revision ID: 20260320_realized_savings
Revises: 20260320_add_instance_cluster_state_index
Create Date: 2026-03-20
"""
from alembic import op
import sqlalchemy as sa

revision = '20260320_realized_savings'
down_revision = '20260320_add_instance_cluster_state_index'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        'rebalancing_actions',
        sa.Column('realized_savings_hourly_usd', sa.Float(), nullable=True)
    )
    op.add_column(
        'rebalancing_actions',
        sa.Column('realized_savings_monthly_usd', sa.Float(), nullable=True)
    )


def downgrade():
    op.drop_column('rebalancing_actions', 'realized_savings_monthly_usd')
    op.drop_column('rebalancing_actions', 'realized_savings_hourly_usd')
