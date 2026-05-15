"""Add phase and start_time to pod_metrics — T-12.

Revision ID: 20260427_pod_metrics_phase_starttime
Revises: 20260427_karpenter_node_claims
Create Date: 2026-04-27

Adds:
  - pod_metrics.phase        VARCHAR(20) DEFAULT NULL
  - pod_metrics.start_time   TIMESTAMP   DEFAULT NULL
  Both are online-DDL-safe (ADD COLUMN with DEFAULT NULL).
"""

from alembic import op
import sqlalchemy as sa

revision = '20260427_pod_metrics_phase_starttime'
down_revision = '20260427_karpenter_node_claims'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        'pod_metrics',
        sa.Column('phase', sa.String(20), nullable=True),
    )
    op.add_column(
        'pod_metrics',
        sa.Column('start_time', sa.DateTime(), nullable=True),
    )
    op.create_index('idx_pod_metric_phase', 'pod_metrics', ['cluster_id', 'phase'])


def downgrade():
    op.drop_index('idx_pod_metric_phase', 'pod_metrics')
    op.drop_column('pod_metrics', 'start_time')
    op.drop_column('pod_metrics', 'phase')
