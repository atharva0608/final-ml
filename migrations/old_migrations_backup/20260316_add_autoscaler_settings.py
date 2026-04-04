"""Add min_node_count, scale_down_threshold_pct, scale_down_stabilization_minutes
   to cluster_optimization_settings

Revision ID: 20260316_autoscaler_settings
Revises: 20260316_spot_join_timeout
Create Date: 2026-03-16
"""
from alembic import op

revision = '20260316_autoscaler_settings'
down_revision = '20260316_spot_join_timeout'
branch_labels = None
depends_on = None


def upgrade():
    # Use IF NOT EXISTS — columns may have been applied directly before migration ran
    op.execute("ALTER TABLE cluster_optimization_settings ADD COLUMN IF NOT EXISTS min_node_count INTEGER NOT NULL DEFAULT 1")
    op.execute("ALTER TABLE cluster_optimization_settings ADD COLUMN IF NOT EXISTS scale_down_threshold_pct INTEGER NOT NULL DEFAULT 20")
    op.execute("ALTER TABLE cluster_optimization_settings ADD COLUMN IF NOT EXISTS scale_down_stabilization_minutes INTEGER NOT NULL DEFAULT 15")


def downgrade():
    op.drop_column('cluster_optimization_settings', 'scale_down_stabilization_minutes')
    op.drop_column('cluster_optimization_settings', 'scale_down_threshold_pct')
    op.drop_column('cluster_optimization_settings', 'min_node_count')
