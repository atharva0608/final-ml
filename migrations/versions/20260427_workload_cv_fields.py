"""Add cpu_cv and traffic_skew_detected to workload_classifications.

Revision ID: 20260427_workload_cv_fields
Revises: 20260423_pod_level_cols
Create Date: 2026-04-27

Adds:
  - workload_classifications.cpu_cv          FLOAT    NULL
  - workload_classifications.traffic_skew_detected  BOOLEAN  NULL
"""

from alembic import op
import sqlalchemy as sa

revision = '20260427_workload_cv_fields'
down_revision = '20260423_pod_level_cols'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        'workload_classifications',
        sa.Column('cpu_cv', sa.Float(), nullable=True),
    )
    op.add_column(
        'workload_classifications',
        sa.Column('traffic_skew_detected', sa.Boolean(), nullable=True),
    )


def downgrade():
    op.drop_column('workload_classifications', 'traffic_skew_detected')
    op.drop_column('workload_classifications', 'cpu_cv')
