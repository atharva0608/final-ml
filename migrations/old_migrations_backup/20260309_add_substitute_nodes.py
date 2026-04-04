"""
Add substitute_nodes table

Revision ID: 20260309_substitute_nodes
Revises: 20260309_optimizer_proposals
Create Date: 2026-03-09
"""
from alembic import op
import sqlalchemy as sa

revision = '20260309_substitute_nodes'
down_revision = '20260309_optimizer_proposals'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'substitute_nodes',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('cluster_id', sa.String(36), nullable=False, index=True),
        sa.Column('instance_id', sa.String(50), nullable=True),
        sa.Column('instance_type', sa.String(50), nullable=True),
        sa.Column('az', sa.String(50), nullable=True),
        sa.Column('state', sa.Enum('LAUNCHING', 'READY', 'PROMOTING', 'TERMINATED',
                                   name='substitutenodestate'), nullable=True),
        sa.Column('node_name', sa.String(255), nullable=True),
        sa.Column('created_at', sa.DateTime, nullable=True),
        sa.Column('promoted_at', sa.DateTime, nullable=True),
    )


def downgrade() -> None:
    op.drop_table('substitute_nodes')
    op.execute("DROP TYPE IF EXISTS substitutenodestate")
