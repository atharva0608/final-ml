"""Add drain_timeout_minutes to cluster_optimization_settings

Revision ID: 20260328_add_drain_timeout_minutes
Revises: 20260327_add_inst_type_div_pct
Create Date: 2026-03-28

Configurable per-cluster drain timeout (default 15 min) for node drain
before forced termination during ASG detach operations.
"""
from alembic import op
import sqlalchemy as sa


revision = '20260328_add_drain_timeout_minutes'
down_revision = '20260327_add_inst_type_div_pct'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        'cluster_optimization_settings',
        sa.Column('drain_timeout_minutes', sa.Integer(), nullable=True, server_default='15')
    )
    op.execute(
        "UPDATE cluster_optimization_settings SET drain_timeout_minutes = 15 "
        "WHERE drain_timeout_minutes IS NULL"
    )


def downgrade():
    op.drop_column('cluster_optimization_settings', 'drain_timeout_minutes')
