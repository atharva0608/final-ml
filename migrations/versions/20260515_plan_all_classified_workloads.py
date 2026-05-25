"""Add plan_all_classified_workloads to cluster_optimization_settings.

Revision ID: 20260515_plan_all_classified_workloads
Revises: 20260427_workload_cv_fields
Create Date: 2026-05-15

Adds:
  - cluster_optimization_settings.plan_all_classified_workloads  BOOLEAN  DEFAULT FALSE
"""

from alembic import op
import sqlalchemy as sa

revision = '20260515_plan_all_classified_workloads'
down_revision = '20260427_workload_cv_fields'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        'cluster_optimization_settings',
        sa.Column('plan_all_classified_workloads', sa.Boolean(), nullable=True, server_default='false'),
    )


def downgrade():
    op.drop_column('cluster_optimization_settings', 'plan_all_classified_workloads')
