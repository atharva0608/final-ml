"""Create node_metadata table — T-09.

Revision ID: 20260427_node_metadata_table
Revises: 20260427_workload_cv_fields
Create Date: 2026-04-27

Creates:
  - node_metadata table with UPSERT-friendly unique constraint on (cluster_id, node_name)
"""

from alembic import op
import sqlalchemy as sa

revision = '20260427_node_metadata_table'
down_revision = '20260427_workload_cv_fields'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'node_metadata',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('cluster_id', sa.String(36), sa.ForeignKey('clusters.id', ondelete='CASCADE'), nullable=False),
        sa.Column('node_name', sa.String(253), nullable=False),
        sa.Column('az', sa.String(64), nullable=True),
        sa.Column('capacity_type', sa.String(20), nullable=True),
        sa.Column('nodepool_name', sa.String(128), nullable=True),
        sa.Column('instance_type', sa.String(64), nullable=True),
        sa.Column('do_not_disrupt', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('is_ready', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('allocatable_cpu_millicores', sa.Float(), nullable=True),
        sa.Column('allocatable_memory_bytes', sa.Float(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint('cluster_id', 'node_name', name='uq_node_metadata_cluster_node'),
    )
    op.create_index('ix_node_metadata_cluster_id', 'node_metadata', ['cluster_id'])
    op.create_index('ix_node_metadata_capacity_type', 'node_metadata', ['cluster_id', 'capacity_type'])


def downgrade():
    op.drop_index('ix_node_metadata_capacity_type', 'node_metadata')
    op.drop_index('ix_node_metadata_cluster_id', 'node_metadata')
    op.drop_table('node_metadata')
