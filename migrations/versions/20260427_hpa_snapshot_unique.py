"""Add unique constraint on hpa_status_snapshots (cluster_id, workload_name, snapshot_at) — P-26.

Revision ID: 20260427_hpa_snapshot_unique
Revises: 20260427_hpa_tables
Create Date: 2026-04-27
"""

from alembic import op
import sqlalchemy as sa

revision = '20260427_hpa_snapshot_unique'
down_revision = '20260427_hpa_tables'
branch_labels = None
depends_on = None


def upgrade():
    op.create_unique_constraint(
        'uq_hpa_snapshot_cluster_workload_time',
        'hpa_status_snapshots',
        ['cluster_id', 'workload_name', 'snapshot_at'],
    )


def downgrade():
    op.drop_constraint(
        'uq_hpa_snapshot_cluster_workload_time',
        'hpa_status_snapshots',
        type_='unique',
    )
