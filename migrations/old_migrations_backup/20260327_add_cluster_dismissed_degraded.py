"""Add is_dismissed column and DEGRADED status to clusters

Revision ID: 20260327_cluster_dismissed
Revises: 20260327_global_pool_ema
Create Date: 2026-03-27
"""
from alembic import op
import sqlalchemy as sa

revision = '20260327_cluster_dismissed'
down_revision = '20260327_global_pool_ema'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add DEGRADED to the ClusterStatus enum
    op.execute("ALTER TYPE clusterstatus ADD VALUE IF NOT EXISTS 'DEGRADED'")

    # Add is_dismissed column
    op.add_column('clusters', sa.Column(
        'is_dismissed', sa.Boolean(), nullable=False, server_default='false'
    ))

    # Index for fast filtering of dismissed clusters in discovery
    op.create_index('idx_clusters_is_dismissed', 'clusters', ['is_dismissed'])


def downgrade() -> None:
    op.drop_index('idx_clusters_is_dismissed', table_name='clusters')
    op.drop_column('clusters', 'is_dismissed')
    # Note: Postgres doesn't support removing enum values
