"""
Add auto_stateful_rightsizing_enabled to cluster_optimization_settings

Revision ID: 20260310_add_stateful_rightsizing_toggle
Revises: 20260309_cleanup_volume_tables
Create Date: 2026-03-10
"""
from alembic import op
import sqlalchemy as sa

revision = '20260310_add_stateful_rightsizing_toggle'
down_revision = '20260309_cleanup_volume_tables'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        'cluster_optimization_settings',
        sa.Column(
            'auto_stateful_rightsizing_enabled',
            sa.Boolean(),
            nullable=True,
            server_default='false',
        )
    )


def downgrade() -> None:
    op.drop_column('cluster_optimization_settings', 'auto_stateful_rightsizing_enabled')
