"""Create karpenter_node_claims table — T-11.

Revision ID: 20260427_karpenter_node_claims
Revises: 20260427_node_metadata_table
Create Date: 2026-04-27
"""

from alembic import op
import sqlalchemy as sa

revision = '20260427_karpenter_node_claims'
down_revision = '20260427_node_metadata_table'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'karpenter_node_claims',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('cluster_id', sa.String(36), sa.ForeignKey('clusters.id', ondelete='CASCADE'), nullable=False),
        sa.Column('node_name', sa.String(253), nullable=False),
        sa.Column('instance_type', sa.String(64), nullable=True),
        sa.Column('capacity_type', sa.String(20), nullable=True),
        sa.Column('az', sa.String(64), nullable=True),
        sa.Column('nodepool_name', sa.String(128), nullable=True),
        sa.Column('state', sa.String(50), nullable=True),
        sa.Column('provisioned_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint('cluster_id', 'node_name', name='uq_karpenter_node_claims_cluster_node'),
    )
    op.create_index('ix_karpenter_node_claims_cluster_id', 'karpenter_node_claims', ['cluster_id'])


def downgrade():
    op.drop_index('ix_karpenter_node_claims_cluster_id', 'karpenter_node_claims')
    op.drop_table('karpenter_node_claims')
