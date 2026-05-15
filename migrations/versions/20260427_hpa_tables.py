"""Create hpa_configs and hpa_status_snapshots tables — T-13.

Revision ID: 20260427_hpa_tables
Revises: 20260427_pod_metrics_phase_starttime
Create Date: 2026-04-27
"""

from alembic import op
import sqlalchemy as sa

revision = '20260427_hpa_tables'
down_revision = '20260427_pod_metrics_phase_starttime'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'hpa_configs',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('cluster_id', sa.String(36), sa.ForeignKey('clusters.id', ondelete='CASCADE'), nullable=False),
        sa.Column('namespace', sa.String(253), nullable=False),
        sa.Column('workload_name', sa.String(253), nullable=False),
        sa.Column('hpa_name', sa.String(253), nullable=True),
        sa.Column('min_replicas', sa.Integer(), nullable=True),
        sa.Column('max_replicas', sa.Integer(), nullable=True),
        sa.Column('target_cpu_pct', sa.Integer(), nullable=True),
        sa.Column('current_replicas', sa.Integer(), nullable=True),
        sa.Column('desired_replicas', sa.Integer(), nullable=True),
        sa.Column('scale_up_stabilization_seconds', sa.Integer(), nullable=True),
        sa.Column('scale_down_stabilization_seconds', sa.Integer(), nullable=True),
        sa.Column('recommended_max_replicas', sa.Integer(), nullable=True),
        sa.Column('recommended_min_replicas', sa.Integer(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint(
            'cluster_id', 'namespace', 'workload_name',
            name='uq_hpa_configs_cluster_ns_workload',
        ),
    )
    op.create_index('ix_hpa_configs_cluster_id', 'hpa_configs', ['cluster_id'])

    op.create_table(
        'hpa_status_snapshots',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('cluster_id', sa.String(36), sa.ForeignKey('clusters.id', ondelete='CASCADE'), nullable=False),
        sa.Column('namespace', sa.String(253), nullable=False),
        sa.Column('workload_name', sa.String(253), nullable=False),
        sa.Column('desired_replicas', sa.Integer(), nullable=True),
        sa.Column('current_replicas', sa.Integer(), nullable=True),
        sa.Column('cpu_utilization_pct', sa.Integer(), nullable=True),
        sa.Column('snapshot_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    op.create_index(
        'idx_hpa_snapshot_cluster_workload_time',
        'hpa_status_snapshots',
        ['cluster_id', 'workload_name', 'snapshot_at'],
    )
    op.create_index(
        'idx_hpa_snapshot_cluster_time',
        'hpa_status_snapshots',
        ['cluster_id', 'snapshot_at'],
    )


def downgrade():
    op.drop_index('idx_hpa_snapshot_cluster_time', 'hpa_status_snapshots')
    op.drop_index('idx_hpa_snapshot_cluster_workload_time', 'hpa_status_snapshots')
    op.drop_table('hpa_status_snapshots')
    op.drop_index('ix_hpa_configs_cluster_id', 'hpa_configs')
    op.drop_table('hpa_configs')
