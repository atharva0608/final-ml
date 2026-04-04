"""Add Task-4.2 savings columns to rebalancing_actions

Revision ID: 20260320_savings_columns
Revises: 20260320_node_coverage_tables
Create Date: 2026-03-20
"""
from alembic import op
import sqlalchemy as sa

revision = '20260320_savings_columns'
down_revision = '20260320_node_coverage_tables'
branch_labels = None
depends_on = None


def upgrade():
    # Decision-time columns (written when action is created)
    op.add_column('rebalancing_actions', sa.Column('source_od_price_hr', sa.Float(), nullable=True))
    op.add_column('rebalancing_actions', sa.Column('target_spot_price_hr', sa.Float(), nullable=True))
    op.add_column('rebalancing_actions', sa.Column('estimated_savings_hr', sa.Float(), nullable=True))
    op.add_column('rebalancing_actions', sa.Column('estimated_savings_mo', sa.Float(), nullable=True))

    # Completion-time columns (written when action completes)
    op.add_column('rebalancing_actions', sa.Column('actual_instance_type', sa.String(50), nullable=True))
    op.add_column('rebalancing_actions', sa.Column('actual_az', sa.String(50), nullable=True))
    op.add_column('rebalancing_actions', sa.Column('actual_spot_price_hr', sa.Float(), nullable=True))
    op.add_column('rebalancing_actions', sa.Column('realized_savings_hr', sa.Float(), nullable=True))
    op.add_column('rebalancing_actions', sa.Column('realized_savings_mo', sa.Float(), nullable=True))
    op.add_column('rebalancing_actions', sa.Column('realized_savings_pct', sa.Float(), nullable=True))
    op.add_column('rebalancing_actions', sa.Column('savings_gap_hr', sa.Float(), nullable=True))


def downgrade():
    op.drop_column('rebalancing_actions', 'savings_gap_hr')
    op.drop_column('rebalancing_actions', 'realized_savings_pct')
    op.drop_column('rebalancing_actions', 'realized_savings_mo')
    op.drop_column('rebalancing_actions', 'realized_savings_hr')
    op.drop_column('rebalancing_actions', 'actual_spot_price_hr')
    op.drop_column('rebalancing_actions', 'actual_az')
    op.drop_column('rebalancing_actions', 'actual_instance_type')
    op.drop_column('rebalancing_actions', 'estimated_savings_mo')
    op.drop_column('rebalancing_actions', 'estimated_savings_hr')
    op.drop_column('rebalancing_actions', 'target_spot_price_hr')
    op.drop_column('rebalancing_actions', 'source_od_price_hr')
