"""Add hibernation strategy columns and org automation config

Revision ID: 20260210_hib_strategies
Revises: 20260210_rename
Create Date: 2026-02-10
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers
revision = '20260210_hib_strategies'
down_revision = '20260210_rename'
branch_labels = None
depends_on = None


def upgrade():
    # Hibernation schedule: strategy + state tracking columns
    op.add_column('hibernation_schedules',
        sa.Column('strategy', sa.String(20), server_default='NAMESPACE_SLEEP'))
    op.add_column('hibernation_schedules',
        sa.Column('saved_state', sa.JSON, server_default='{}'))
    op.add_column('hibernation_schedules',
        sa.Column('az_affinity', sa.JSON, server_default='{}'))
    op.add_column('hibernation_schedules',
        sa.Column('last_action', sa.String(20), nullable=True))
    op.add_column('hibernation_schedules',
        sa.Column('last_action_at', sa.DateTime, nullable=True))

    # Organization: automation config for hibernation defaults
    op.add_column('organizations',
        sa.Column('automation_config', sa.JSON, server_default='{}'))


def downgrade():
    op.drop_column('hibernation_schedules', 'strategy')
    op.drop_column('hibernation_schedules', 'saved_state')
    op.drop_column('hibernation_schedules', 'az_affinity')
    op.drop_column('hibernation_schedules', 'last_action')
    op.drop_column('hibernation_schedules', 'last_action_at')
    op.drop_column('organizations', 'automation_config')
