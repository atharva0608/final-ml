"""Add composite index (cluster_id, state) on instances table — Issue #23

Revision ID: 20260320_add_instance_cluster_state_index
Revises: 20260316_add_check_interval
Create Date: 2026-03-20
"""
from alembic import op
import sqlalchemy as sa

revision = '20260320_add_instance_cluster_state_index'
down_revision = '20260316_add_check_interval'
branch_labels = None
depends_on = None


def upgrade():
    # Composite index for the most frequent scan pattern in auto_rebalancer:
    # Instance.cluster_id == X AND Instance.state == 'running'
    op.execute(sa.text(
        "CREATE INDEX IF NOT EXISTS idx_instance_cluster_state "
        "ON instances (cluster_id, state)"
    ))
    # Extended index including instance_type for S2S / diversify queries
    op.execute(sa.text(
        "CREATE INDEX IF NOT EXISTS idx_instance_cluster_state_type "
        "ON instances (cluster_id, state, instance_type)"
    ))
    # Index to accelerate terminated-instance cleanup queries
    op.execute(sa.text(
        "CREATE INDEX IF NOT EXISTS idx_instance_state_updated "
        "ON instances (state, updated_at) WHERE state = 'terminated'"
    ))


def downgrade():
    op.execute(sa.text("DROP INDEX IF EXISTS idx_instance_cluster_state"))
    op.execute(sa.text("DROP INDEX IF EXISTS idx_instance_cluster_state_type"))
    op.execute(sa.text("DROP INDEX IF EXISTS idx_instance_state_updated"))
