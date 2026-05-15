"""Add pod-level visibility columns and retry_count for PlacementController.

Adds:
  - rebalancing_actions.migration_type  VARCHAR(20)  DEFAULT 'node_level'
  - rebalancing_actions.source          VARCHAR(30)  DEFAULT 'auto_rebalancer'
  - rebalancing_actions.agent_action_id VARCHAR(36)  FK -> agent_actions.id (nullable)
  - agent_actions.retry_count           SMALLINT     DEFAULT 0

Revision ID: 20260423_pod_level_visibility_and_retry
Revises: 20260416_add_agent_action_types
Create Date: 2026-04-23
"""

from alembic import op
import sqlalchemy as sa

revision = '20260423_pod_level_cols'
down_revision = '20260416_add_agent_action_types'
branch_labels = None
depends_on = None


def upgrade():
    # ── rebalancing_actions: pod-level visibility columns ────────────────────
    op.add_column(
        'rebalancing_actions',
        sa.Column('migration_type', sa.String(20), nullable=False, server_default='node_level'),
    )
    op.add_column(
        'rebalancing_actions',
        sa.Column('source', sa.String(30), nullable=False, server_default='auto_rebalancer'),
    )
    op.add_column(
        'rebalancing_actions',
        sa.Column(
            'agent_action_id',
            sa.String(36),
            sa.ForeignKey('agent_actions.id', ondelete='SET NULL'),
            nullable=True,
        ),
    )
    op.create_index(
        'idx_rebalancing_actions_source',
        'rebalancing_actions',
        ['source'],
    )
    op.create_index(
        'idx_rebalancing_actions_migration_type',
        'rebalancing_actions',
        ['migration_type'],
    )
    op.create_index(
        'idx_rebalancing_actions_agent_action_id',
        'rebalancing_actions',
        ['agent_action_id'],
    )

    # ── agent_actions: retry_count for post-eviction validation ─────────────
    op.add_column(
        'agent_actions',
        sa.Column('retry_count', sa.SmallInteger(), nullable=False, server_default='0'),
    )


def downgrade():
    op.drop_column('agent_actions', 'retry_count')
    op.drop_index('idx_rebalancing_actions_agent_action_id', 'rebalancing_actions')
    op.drop_index('idx_rebalancing_actions_migration_type', 'rebalancing_actions')
    op.drop_index('idx_rebalancing_actions_source', 'rebalancing_actions')
    op.drop_column('rebalancing_actions', 'agent_action_id')
    op.drop_column('rebalancing_actions', 'source')
    op.drop_column('rebalancing_actions', 'migration_type')
