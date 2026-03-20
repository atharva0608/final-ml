"""Add enable_ascp_auto_scaler to cluster_optimization_settings

Revision ID: 20260316_add_ascp_auto_scaler
Revises: 20260316_autoscaler_settings
Create Date: 2026-03-16
"""
from alembic import op

revision = '20260316_add_ascp_auto_scaler'
down_revision = '20260316_autoscaler_settings'
branch_labels = None
depends_on = None


def upgrade():
    op.execute("ALTER TABLE cluster_optimization_settings ADD COLUMN IF NOT EXISTS enable_ascp_auto_scaler BOOLEAN NOT NULL DEFAULT FALSE")


def downgrade():
    op.drop_column('cluster_optimization_settings', 'enable_ascp_auto_scaler')
