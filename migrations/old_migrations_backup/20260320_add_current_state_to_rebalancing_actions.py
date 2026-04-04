"""Add Pillar-1 current_state column to rebalancing_actions

Revision ID: 20260320_current_state
Revises: 20260320_savings_columns
Create Date: 2026-03-20

Adds the declarative state-machine column to rebalancing_actions.
States: CREATED → POOL_SELECTED → SOURCE_CORDONED → SOURCE_DRAINED
        → REPLACEMENT_LAUNCHING → REPLACEMENT_READY → SOURCE_TERMINATING
        → COMPLETED | FAILED | DRAIN_TIMEOUT
"""
from alembic import op
import sqlalchemy as sa

revision = '20260320_current_state'
down_revision = '20260320_savings_columns'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        'rebalancing_actions',
        sa.Column('current_state', sa.String(30), nullable=True, index=True),
    )
    op.create_index(
        'idx_rebalancing_current_state',
        'rebalancing_actions',
        ['current_state'],
    )


def downgrade():
    op.drop_index('idx_rebalancing_current_state', table_name='rebalancing_actions')
    op.drop_column('rebalancing_actions', 'current_state')
