"""AtharvaAi Pool Selection & Termination Monitoring - Database Tables

Revision ID: 20260216_atharvaai
Revises:
Create Date: 2026-02-16

Creates tables for:
1. spot_price_history - Historical spot prices for lag/rolling features
2. family_hour_baselines - Pre-computed family-time patterns
3. pool_risk_scores - Historical interruption rates per pool
4. node_templates - User-defined filtering requirements
5. termination_events - System B interruption detection log
6. rebalancing_actions - System B auto-rebalancing actions
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB


# revision identifiers, used by Alembic.
revision = '20260216_atharvaai'
down_revision = None  # Update this to point to the latest migration
branch_labels = None
depends_on = None


def upgrade():
    """Create AtharvaAi tables."""

    # 1. spot_price_history - For lag/rolling features (144-point buffer)
    op.create_table(
        'spot_price_history',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('instance_type', sa.String(50), nullable=False),
        sa.Column('az', sa.String(20), nullable=False),
        sa.Column('region', sa.String(20), nullable=False),
        sa.Column('timestamp', sa.DateTime(), nullable=False),
        sa.Column('spot_price', sa.Numeric(10, 6), nullable=False),
        sa.Column('ondemand_price', sa.Numeric(10, 6), nullable=False),
        sa.Column('savings', sa.Numeric(5, 4), nullable=True),  # (ondemand - spot) / ondemand
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now()),
        sa.UniqueConstraint('instance_type', 'az', 'timestamp', name='uq_spot_price_history')
    )

    # Indexes for fast lookups
    op.create_index(
        'idx_spot_price_history_lookup',
        'spot_price_history',
        ['instance_type', 'az', 'timestamp'],
        postgresql_ops={'timestamp': 'DESC'}
    )

    # 2. family_hour_baselines - Pre-computed family-time patterns
    op.create_table(
        'family_hour_baselines',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('instance_family', sa.String(20), nullable=False),
        sa.Column('hour', sa.Integer(), nullable=False),  # 0-23
        sa.Column('dow', sa.Integer(), nullable=True),  # 0-6 (day of week)
        sa.Column('hour_avg_savings', sa.Numeric(5, 4), nullable=True),
        sa.Column('hour_std_savings', sa.Numeric(5, 4), nullable=True),
        sa.Column('dow_avg_savings', sa.Numeric(5, 4), nullable=True),
        sa.Column('weekend_avg_savings', sa.Numeric(5, 4), nullable=True),
        sa.Column('sample_count', sa.Integer(), nullable=True),
        sa.Column('last_computed', sa.DateTime(), server_default=sa.func.now()),
        sa.UniqueConstraint('instance_family', 'hour', 'dow', name='uq_family_hour_baseline')
    )

    op.create_index(
        'idx_family_hour_baselines_lookup',
        'family_hour_baselines',
        ['instance_family', 'hour']
    )

    # 3. pool_risk_scores - Historical interruption rates
    op.create_table(
        'pool_risk_scores',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('instance_type', sa.String(50), nullable=False),
        sa.Column('az', sa.String(20), nullable=False),
        sa.Column('region', sa.String(20), nullable=False),
        sa.Column('historical_zero_rate', sa.Numeric(5, 4), nullable=False, server_default='0.05'),
        sa.Column('interruption_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('total_hours', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('last_interruption_at', sa.DateTime(), nullable=True),
        sa.Column('last_updated', sa.DateTime(), server_default=sa.func.now(), onupdate=sa.func.now()),
        sa.UniqueConstraint('instance_type', 'az', name='uq_pool_risk_score')
    )

    op.create_index(
        'idx_pool_risk_scores_lookup',
        'pool_risk_scores',
        ['instance_type', 'az']
    )

    # 4. node_templates - User-defined filtering requirements
    op.create_table(
        'node_templates',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('organization_id', sa.Integer(), nullable=True),
        sa.Column('cluster_id', sa.Integer(), nullable=True),
        sa.Column('name', sa.String(100), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('architecture', JSONB, nullable=False),  # ["amd64", "arm64"]
        sa.Column('vcpu_range', JSONB, nullable=False),  # {"min": 2, "max": 8}
        sa.Column('memory_range', JSONB, nullable=False),  # {"min": 4, "max": 32}
        sa.Column('allowed_families', JSONB, nullable=True),  # ["m5", "c5", "r5"]
        sa.Column('allowed_sizes', JSONB, nullable=True),  # ["xlarge", "2xlarge"]
        sa.Column('allowed_azs', JSONB, nullable=True),  # ["aps1-az1", "aps1-az2"]
        sa.Column('excluded_instance_types', JSONB, nullable=True),  # ["m5.metal"]
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.func.now(), onupdate=sa.func.now())
    )

    op.create_index(
        'idx_node_templates_org_cluster',
        'node_templates',
        ['organization_id', 'cluster_id']
    )

    # 5. termination_events - System B interruption detection log
    op.create_table(
        'termination_events',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('instance_type', sa.String(50), nullable=False),
        sa.Column('az', sa.String(20), nullable=False),
        sa.Column('region', sa.String(20), nullable=False),
        sa.Column('cluster_id', sa.String(100), nullable=True),
        sa.Column('instance_id', sa.String(50), nullable=True),
        sa.Column('node_name', sa.String(100), nullable=True),
        sa.Column('detected_at', sa.DateTime(), nullable=False),
        sa.Column('source', sa.String(20), nullable=False),  # 'daemonset', 'eventbridge', 'manual'
        sa.Column('action_taken', sa.String(50), nullable=True),  # 'flagged', 'rebalanced', 'none'
        sa.Column('metadata', JSONB, nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now())
    )

    op.create_index(
        'idx_termination_events_pool',
        'termination_events',
        ['instance_type', 'az', 'detected_at']
    )

    op.create_index(
        'idx_termination_events_cluster',
        'termination_events',
        ['cluster_id', 'detected_at']
    )

    # 6. rebalancing_actions - System B auto-rebalancing actions
    op.create_table(
        'rebalancing_actions',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('cluster_id', sa.String(100), nullable=False),
        sa.Column('trigger', sa.String(20), nullable=False),  # 'emergency', 'graceful'
        sa.Column('source_pool', sa.String(100), nullable=False),  # 'instance_type:az'
        sa.Column('target_pool', sa.String(100), nullable=False),  # 'instance_type:az'
        sa.Column('status', sa.String(20), nullable=False),  # 'in_progress', 'completed', 'failed'
        sa.Column('nodes_affected', sa.Integer(), nullable=True),
        sa.Column('pods_migrated', sa.Integer(), nullable=True),
        sa.Column('started_at', sa.DateTime(), nullable=False),
        sa.Column('completed_at', sa.DateTime(), nullable=True),
        sa.Column('duration_seconds', sa.Integer(), nullable=True),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('metadata', JSONB, nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now())
    )

    op.create_index(
        'idx_rebalancing_actions_cluster',
        'rebalancing_actions',
        ['cluster_id', 'started_at']
    )

    op.create_index(
        'idx_rebalancing_actions_status',
        'rebalancing_actions',
        ['status', 'started_at']
    )


def downgrade():
    """Drop AtharvaAi tables."""

    op.drop_table('rebalancing_actions')
    op.drop_table('termination_events')
    op.drop_table('node_templates')
    op.drop_table('pool_risk_scores')
    op.drop_table('family_hour_baselines')
    op.drop_table('spot_price_history')
