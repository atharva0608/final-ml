"""Add instance_type_diversification_pct to cluster_optimization_settings

Revision ID: 20260327_add_inst_type_div_pct
Revises: 20260327_global_pool_ema
Create Date: 2026-03-27

Sub-setting for Diversify Spot Pools:
  100% = every node must get a unique instance type (strictest)
  50%  = up to round(N * 0.5) nodes may share the same type
  0%   = no restriction on type repetition
"""
from alembic import op
import sqlalchemy as sa


revision = '20260327_add_inst_type_div_pct'
down_revision = '20260327_cluster_dismissed'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        'cluster_optimization_settings',
        sa.Column('instance_type_diversification_pct', sa.Integer(), nullable=True, server_default='100')
    )
    # Backfill existing rows to 100 (fully diversified — matches previous strict behavior)
    op.execute(
        "UPDATE cluster_optimization_settings SET instance_type_diversification_pct = 100 "
        "WHERE instance_type_diversification_pct IS NULL"
    )


def downgrade():
    op.drop_column('cluster_optimization_settings', 'instance_type_diversification_pct')
