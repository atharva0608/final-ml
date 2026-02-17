"""Add pod_metrics table for DaemonSet metrics collection

Revision ID: 20260216_pod_metrics
Revises:
Create Date: 2026-02-16

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '20260216_pod_metrics'
down_revision = None  # Set this to the latest migration ID in your project
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create pod_metrics table"""
    op.create_table(
        'pod_metrics',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('cluster_id', sa.String(length=36), nullable=False),
        sa.Column('namespace', sa.String(length=253), nullable=False),
        sa.Column('pod_name', sa.String(length=253), nullable=False),
        sa.Column('node_name', sa.String(length=253), nullable=False),
        sa.Column('controller_kind', sa.String(length=50), nullable=True),
        sa.Column('controller_name', sa.String(length=253), nullable=True),
        sa.Column('cpu_usage_millicores', sa.Integer(), nullable=False),
        sa.Column('cpu_request_millicores', sa.Integer(), nullable=True),
        sa.Column('cpu_limit_millicores', sa.Integer(), nullable=True),
        sa.Column('memory_usage_bytes', sa.BigInteger(), nullable=False),
        sa.Column('memory_request_bytes', sa.BigInteger(), nullable=True),
        sa.Column('memory_limit_bytes', sa.BigInteger(), nullable=True),
        sa.Column('cpu_utilization_pct', sa.Float(), nullable=True),
        sa.Column('memory_utilization_pct', sa.Float(), nullable=True),
        sa.Column('container_count', sa.Integer(), nullable=False, server_default='1'),
        sa.Column('timestamp', sa.DateTime(), nullable=False),
        sa.Column('metadata', postgresql.JSONB(astext_type=sa.Text()), nullable=True, server_default='{}'),
        sa.ForeignKeyConstraint(['cluster_id'], ['clusters.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )

    # Create indexes for efficient querying
    op.create_index('idx_pod_metric_cluster_time', 'pod_metrics', ['cluster_id', 'timestamp'])
    op.create_index('idx_pod_metric_controller', 'pod_metrics', ['cluster_id', 'namespace', 'controller_kind', 'controller_name', 'timestamp'])
    op.create_index('idx_pod_metric_node_time', 'pod_metrics', ['cluster_id', 'node_name', 'timestamp'])
    op.create_index('idx_pod_metric_pod_time', 'pod_metrics', ['cluster_id', 'namespace', 'pod_name', 'timestamp'])
    op.create_index(op.f('ix_pod_metrics_cluster_id'), 'pod_metrics', ['cluster_id'])
    op.create_index(op.f('ix_pod_metrics_controller_kind'), 'pod_metrics', ['controller_kind'])
    op.create_index(op.f('ix_pod_metrics_controller_name'), 'pod_metrics', ['controller_name'])
    op.create_index(op.f('ix_pod_metrics_id'), 'pod_metrics', ['id'])
    op.create_index(op.f('ix_pod_metrics_namespace'), 'pod_metrics', ['namespace'])
    op.create_index(op.f('ix_pod_metrics_node_name'), 'pod_metrics', ['node_name'])
    op.create_index(op.f('ix_pod_metrics_pod_name'), 'pod_metrics', ['pod_name'])
    op.create_index(op.f('ix_pod_metrics_timestamp'), 'pod_metrics', ['timestamp'])


def downgrade() -> None:
    """Drop pod_metrics table"""
    op.drop_index(op.f('ix_pod_metrics_timestamp'), table_name='pod_metrics')
    op.drop_index(op.f('ix_pod_metrics_pod_name'), table_name='pod_metrics')
    op.drop_index(op.f('ix_pod_metrics_node_name'), table_name='pod_metrics')
    op.drop_index(op.f('ix_pod_metrics_namespace'), table_name='pod_metrics')
    op.drop_index(op.f('ix_pod_metrics_id'), table_name='pod_metrics')
    op.drop_index(op.f('ix_pod_metrics_controller_name'), table_name='pod_metrics')
    op.drop_index(op.f('ix_pod_metrics_controller_kind'), table_name='pod_metrics')
    op.drop_index(op.f('ix_pod_metrics_cluster_id'), table_name='pod_metrics')
    op.drop_index('idx_pod_metric_pod_time', table_name='pod_metrics')
    op.drop_index('idx_pod_metric_node_time', table_name='pod_metrics')
    op.drop_index('idx_pod_metric_controller', table_name='pod_metrics')
    op.drop_index('idx_pod_metric_cluster_time', table_name='pod_metrics')
    op.drop_table('pod_metrics')
