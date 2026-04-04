"""Add check_interval_seconds to cluster_optimization_settings

Revision ID: 20260316_add_check_interval
Revises: 20260316_add_ascp_auto_scaler
Create Date: 2026-03-16
"""
from alembic import op

revision = '20260316_add_check_interval'
down_revision = '20260316_add_ascp_auto_scaler'
branch_labels = None
depends_on = None


def upgrade():
    op.execute(
        "ALTER TABLE cluster_optimization_settings "
        "ADD COLUMN IF NOT EXISTS check_interval_seconds INTEGER NOT NULL DEFAULT 15"
    )


def downgrade():
    op.drop_column('cluster_optimization_settings', 'check_interval_seconds')
