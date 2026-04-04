"""Add node_alternative_cache and cluster_baselines tables — Per-Node Coverage System

Revision ID: 20260320_node_coverage_tables
Revises: 20260320_realized_savings
Create Date: 2026-03-20
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = '20260320_node_coverage_tables'
down_revision = '20260320_realized_savings'
branch_labels = None
depends_on = None


def upgrade():
    # node_alternative_cache: per-node ranked alternatives with coverage status
    op.create_table(
        'node_alternative_cache',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('cluster_id', sa.String(36), sa.ForeignKey('clusters.id', ondelete='CASCADE'), nullable=False),
        sa.Column('node_id', sa.String(36), nullable=True),
        sa.Column('node_name', sa.String(255), nullable=False),
        sa.Column('instance_type', sa.String(50), nullable=True),
        sa.Column('resource_profile', JSONB(), nullable=True),
        sa.Column('alternative_pools', JSONB(), nullable=True),
        sa.Column('alternative_count', sa.Integer(), nullable=True, default=0),
        sa.Column('best_pool', sa.String(150), nullable=True),
        sa.Column('best_saving_pct', sa.Float(), nullable=True),
        sa.Column('coverage_status', sa.String(20), nullable=True),
        sa.Column('computed_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('idx_nac_cluster_node', 'node_alternative_cache', ['cluster_id', 'node_name'])
    op.create_index(op.f('ix_node_alternative_cache_cluster_id'), 'node_alternative_cache', ['cluster_id'])
    op.create_index(op.f('ix_node_alternative_cache_node_id'), 'node_alternative_cache', ['node_id'])

    # cluster_baselines: cluster-level cost / composition baseline for delta calculations
    op.create_table(
        'cluster_baselines',
        sa.Column('cluster_id', sa.String(36), sa.ForeignKey('clusters.id', ondelete='CASCADE'), nullable=False),
        sa.Column('primary_node_type', sa.String(50), nullable=True),
        sa.Column('primary_az', sa.String(50), nullable=True),
        sa.Column('baseline_monthly_cost', sa.Float(), nullable=True),
        sa.Column('baseline_spot_count', sa.Integer(), nullable=True),
        sa.Column('baseline_od_count', sa.Integer(), nullable=True),
        sa.Column('computed_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('cluster_id'),
    )


def downgrade():
    op.drop_table('cluster_baselines')
    op.drop_index(op.f('ix_node_alternative_cache_node_id'), table_name='node_alternative_cache')
    op.drop_index(op.f('ix_node_alternative_cache_cluster_id'), table_name='node_alternative_cache')
    op.drop_index('idx_nac_cluster_node', table_name='node_alternative_cache')
    op.drop_table('node_alternative_cache')
