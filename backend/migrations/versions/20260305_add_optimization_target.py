"""Add optimization_target to cluster_optimization_settings

Revision ID: 20260305_opt_target
"""
from alembic import op
import sqlalchemy as sa


def upgrade():
    op.add_column(
        'cluster_optimization_settings',
        sa.Column('optimization_target', sa.String(20), server_default='spot', nullable=False)
    )


def downgrade():
    op.drop_column('cluster_optimization_settings', 'optimization_target')
