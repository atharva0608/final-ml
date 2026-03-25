"""Add launch_outcomes table, RebalancingAction state columns, unique constraints, and indexes

Revision ID: 20260323_launch_outcomes
Revises: 20260320_current_state
Create Date: 2026-03-23

Covers Steps 14, 15, 16 from changes.md:
  - launch_outcomes table (Step 14)
  - RebalancingAction: state_entered_at, state_history, lock_version (Step 16)
  - Unique constraints: instances.instance_id, spot_advisor_rates(region, instance_type)
  - Missing indexes: idx_launch_outcomes_pool_key, idx_active_rebalancing_actions,
                     idx_rebalancing_actions_source
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = '20260323_launch_outcomes'
down_revision = '20260320_current_state'
branch_labels = None
depends_on = None


def upgrade():
    # ---------------------------------------------------------------
    # 1. Create launch_outcomes table
    # ---------------------------------------------------------------
    op.create_table(
        'launch_outcomes',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('pool_key', sa.String(100), nullable=False),
        sa.Column('cluster_id', sa.String(100), nullable=False),
        sa.Column('instance_type', sa.String(50), nullable=False),
        sa.Column('az', sa.String(50), nullable=False),
        sa.Column('region', sa.String(50), nullable=False),
        sa.Column('outcome', sa.String(20), nullable=False),
        sa.Column('actual_spot_price_hr', sa.Float(), nullable=True),
        sa.Column('uptime_hours', sa.Float(), nullable=True),
        sa.Column('launched_at', sa.DateTime(), nullable=False),
        sa.Column('resolved_at', sa.DateTime(), nullable=True),
        sa.Column('failure_reason', sa.Text(), nullable=True),
        sa.Column('rebalancing_action_id', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now()),
    )
    op.create_index('idx_launch_outcomes_pool_key', 'launch_outcomes', ['pool_key', 'launched_at'])
    op.create_index('idx_launch_outcomes_cluster', 'launch_outcomes', ['cluster_id', 'launched_at'])
    op.create_index('idx_launch_outcomes_action', 'launch_outcomes', ['rebalancing_action_id'])

    # ---------------------------------------------------------------
    # 2. Add missing columns to rebalancing_actions (Step 16)
    # ---------------------------------------------------------------
    op.add_column(
        'rebalancing_actions',
        sa.Column('state_entered_at', sa.DateTime(), nullable=True),
    )
    op.add_column(
        'rebalancing_actions',
        sa.Column('state_history', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )
    op.add_column(
        'rebalancing_actions',
        sa.Column('lock_version', sa.Integer(), nullable=True, server_default='0'),
    )

    # ---------------------------------------------------------------
    # 3. Add source_instance_id column if missing (referenced in indexes)
    #    (Only add if it does not already exist — guard via try/except)
    # ---------------------------------------------------------------
    try:
        op.add_column(
            'rebalancing_actions',
            sa.Column('source_instance_id', sa.String(50), nullable=True),
        )
        op.create_index(
            'idx_rebalancing_actions_source',
            'rebalancing_actions',
            ['source_instance_id', 'current_state'],
        )
    except Exception:
        # Column already exists from a previous migration — skip silently
        pass

    # ---------------------------------------------------------------
    # 4. Partial index for active rebalancing actions
    # ---------------------------------------------------------------
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_active_rebalancing_actions
        ON rebalancing_actions (cluster_id, source_instance_id)
        WHERE current_state NOT IN ('COMPLETED', 'FAILED')
        """
    )

    # ---------------------------------------------------------------
    # 5. Unique constraint on instances.instance_id
    #    (instances model already has unique=True; guard with IF NOT EXISTS
    #     so the migration is idempotent whether the constraint exists or not)
    # ---------------------------------------------------------------
    # Dedup: keep only the most recently updated row per instance_id
    # (instances.private_ip does NOT exist — skip IP-based dedup)
    op.execute(
        """
        DELETE FROM instances
        WHERE id IN (
          SELECT id FROM (
            SELECT id,
                   ROW_NUMBER() OVER (
                     PARTITION BY instance_id
                     ORDER BY updated_at DESC NULLS LAST
                   ) AS rn
            FROM instances
          ) t WHERE rn > 1
        )
        """
    )
    # Add constraint only if it doesn't already exist
    op.execute(
        """
        DO $$
        BEGIN
          IF NOT EXISTS (
            SELECT 1 FROM information_schema.table_constraints
            WHERE table_name = 'instances'
              AND constraint_name = 'uq_instances_instance_id'
          ) THEN
            ALTER TABLE instances ADD CONSTRAINT uq_instances_instance_id
              UNIQUE (instance_id);
          END IF;
        END$$;
        """
    )

    # ---------------------------------------------------------------
    # 6. Unique constraint on spot_advisor_rates (region, instance_type)
    # ---------------------------------------------------------------
    # Keep the most recently inserted row per (region, instance_type)
    op.execute(
        """
        DELETE FROM spot_advisor_rates
        WHERE id NOT IN (
          SELECT MAX(id)
          FROM spot_advisor_rates
          GROUP BY region, instance_type
        )
        """
    )
    op.create_unique_constraint(
        'uq_spot_advisor_region_type', 'spot_advisor_rates', ['region', 'instance_type']
    )

    # ---------------------------------------------------------------
    # 7. Index on rebalancing_actions (cluster_id, current_state, created_at)
    # ---------------------------------------------------------------
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_rebalancing_actions_cluster_state
        ON rebalancing_actions (cluster_id, current_state, created_at)
        """
    )


def downgrade():
    op.execute("DROP INDEX IF EXISTS idx_rebalancing_actions_cluster_state")
    op.execute("DROP INDEX IF EXISTS idx_active_rebalancing_actions")
    try:
        op.drop_constraint('uq_spot_advisor_region_type', 'spot_advisor_rates', type_='unique')
    except Exception:
        pass
    try:
        op.drop_constraint('uq_instances_instance_id', 'instances', type_='unique')
    except Exception:
        pass
    try:
        op.drop_index('idx_rebalancing_actions_source', table_name='rebalancing_actions')
        op.drop_column('rebalancing_actions', 'source_instance_id')
    except Exception:
        pass
    op.drop_column('rebalancing_actions', 'lock_version')
    op.drop_column('rebalancing_actions', 'state_history')
    op.drop_column('rebalancing_actions', 'state_entered_at')
    op.drop_index('idx_launch_outcomes_action', table_name='launch_outcomes')
    op.drop_index('idx_launch_outcomes_cluster', table_name='launch_outcomes')
    op.drop_index('idx_launch_outcomes_pool_key', table_name='launch_outcomes')
    op.drop_table('launch_outcomes')
