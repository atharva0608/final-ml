"""Add max_concurrent_rebalance_actions column and cluster_cooldown_states table

Revision ID: 20260325_max_concurrent_cooldown
Revises: 20260325_state_entered_at_trigger
Create Date: 2026-03-25

Issue 12: Add max_concurrent_rebalance_actions to cluster_optimization_settings.
  - Default NULL (treated as 1) preserves existing one-at-a-time behavior.
  - Set to >1 for clusters that can safely handle parallel node replacements.

Issue 13: Add cluster_cooldown_states table for DB-backed stabilization lock.
  - Survives Redis restarts — auto_rebalancer re-hydrates Redis key from this table.
  - cooldown_controller.acquire_stabilization_lock() writes here after acquiring Redis lock.
"""
from alembic import op
import sqlalchemy as sa


revision = '20260325_max_concurrent_cooldown'
down_revision = '20260325_state_entered_at_trigger'
branch_labels = None
depends_on = None


def upgrade():
    # ---------------------------------------------------------------
    # Issue 12: Add max_concurrent_rebalance_actions column
    # ---------------------------------------------------------------
    try:
        op.add_column(
            'cluster_optimization_settings',
            sa.Column('max_concurrent_rebalance_actions', sa.Integer(), nullable=True),
        )
    except Exception:
        # Column already exists (e.g. created manually or by a previous session)
        pass

    # ---------------------------------------------------------------
    # Issue 13: Create cluster_cooldown_states table
    # ---------------------------------------------------------------
    op.create_table(
        'cluster_cooldown_states',
        sa.Column('cluster_id', sa.String(36), sa.ForeignKey('clusters.id', ondelete='CASCADE'),
                  primary_key=True, nullable=False),
        sa.Column('stabilization_until', sa.DateTime(), nullable=True),
        sa.Column('last_action_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.func.now(), onupdate=sa.func.now(), nullable=True),
    )


def downgrade():
    op.drop_table('cluster_cooldown_states')
    try:
        op.drop_column('cluster_optimization_settings', 'max_concurrent_rebalance_actions')
    except Exception:
        pass
