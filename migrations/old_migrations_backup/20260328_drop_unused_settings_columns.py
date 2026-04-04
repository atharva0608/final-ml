"""Drop unused settings columns: conservative_mode_enabled, optimization_target, show_ondemand_only

These columns were never read by the ranking or rebalancing logic and are now removed
as part of the unified pool-ranking refactor.

Revision ID: drop_unused_settings_columns
Revises: 20260328_add_drain_timeout_minutes
Create Date: 2026-03-28
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'drop_unused_settings_columns'
down_revision = '20260328_add_drain_timeout_minutes'
branch_labels = None
depends_on = None


def upgrade():
    # cluster_optimization_settings
    op.drop_column('cluster_optimization_settings', 'conservative_mode_enabled')
    op.drop_column('cluster_optimization_settings', 'optimization_target')

    # stateful_rules
    op.drop_column('stateful_rules', 'show_ondemand_only')


def downgrade():
    # stateful_rules
    op.add_column('stateful_rules',
        sa.Column('show_ondemand_only', sa.Boolean(), nullable=True, server_default='true'))

    # cluster_optimization_settings
    op.add_column('cluster_optimization_settings',
        sa.Column('optimization_target', sa.String(20), nullable=True, server_default='spot'))
    op.add_column('cluster_optimization_settings',
        sa.Column('conservative_mode_enabled', sa.Boolean(), nullable=True, server_default='true'))
