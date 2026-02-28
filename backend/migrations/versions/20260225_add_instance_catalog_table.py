"""add instance_catalog table (Phase 1 Remediation)

Revision ID: 20260225_instance_catalog
Revises: 20260216_pod_metrics
Create Date: 2026-02-25 07:10:00.000000

"""
from alembic import op
import sqlalchemy as sa
from datetime import datetime

# revision identifiers, used by Alembic.
revision = '20260225_instance_catalog'
down_revision = '20260216_pod_metrics'
branch_labels = None
depends_on = None


def upgrade():
    """
    Create instance_catalog table for AWS EC2 instance type specifications.

    This table stores live instance specifications fetched from AWS EC2 API,
    replacing hardcoded instance data.
    """
    op.create_table(
        'instance_catalog',
        # Primary key
        sa.Column('id', sa.String(36), primary_key=True),

        # Instance identification
        sa.Column('instance_type', sa.String(50), nullable=False, index=True),
        sa.Column('region', sa.String(50), nullable=False, index=True),
        sa.Column('current_generation', sa.Boolean, nullable=False, default=True, index=True),

        # Architecture
        sa.Column('architecture', sa.String(20), nullable=False, default='x86_64', index=True),
        sa.Column('supported_architectures', sa.String(100), nullable=True),

        # vCPU
        sa.Column('vcpus', sa.Integer, nullable=False, default=0, index=True),
        sa.Column('cores', sa.Integer, nullable=False, default=0),
        sa.Column('threads_per_core', sa.Integer, nullable=False, default=1),

        # Memory
        sa.Column('memory_mib', sa.Integer, nullable=False, default=0),
        sa.Column('memory_gb', sa.Float, nullable=False, default=0.0, index=True),

        # Network
        sa.Column('network_performance', sa.String(100), nullable=True),
        sa.Column('max_network_interfaces', sa.Integer, nullable=False, default=0),
        sa.Column('ipv4_addresses_per_interface', sa.Integer, nullable=False, default=0),
        sa.Column('ipv6_supported', sa.Boolean, nullable=False, default=False),
        sa.Column('ena_support', sa.String(20), nullable=True),

        # Storage
        sa.Column('ebs_optimized', sa.String(20), nullable=True),
        sa.Column('ebs_encryption_support', sa.String(20), nullable=True),
        sa.Column('instance_storage_supported', sa.Boolean, nullable=False, default=False),
        sa.Column('instance_storage_type', sa.String(20), nullable=True),
        sa.Column('instance_storage_total_gb', sa.Integer, nullable=False, default=0),

        # Processor
        sa.Column('hypervisor', sa.String(20), nullable=True),
        sa.Column('processor_manufacturer', sa.String(50), nullable=True),
        sa.Column('sustained_clock_speed_ghz', sa.Float, nullable=True),

        # GPU
        sa.Column('gpu_count', sa.Integer, nullable=False, default=0),
        sa.Column('gpu_manufacturer', sa.String(50), nullable=True),
        sa.Column('gpu_memory_mib', sa.Integer, nullable=False, default=0),

        # Performance
        sa.Column('burstable_performance_supported', sa.Boolean, nullable=False, default=False),

        # Features
        sa.Column('auto_recovery_supported', sa.Boolean, nullable=False, default=False),
        sa.Column('hibernation_supported', sa.Boolean, nullable=False, default=False),

        # Timestamps
        sa.Column('created_at', sa.DateTime, nullable=False, default=datetime.utcnow),
        sa.Column('last_updated_at', sa.DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow),
    )

    # Create composite indexes
    op.create_index(
        'idx_instance_type_region',
        'instance_catalog',
        ['instance_type', 'region'],
        unique=True
    )

    op.create_index(
        'idx_region_current_gen',
        'instance_catalog',
        ['region', 'current_generation']
    )

    op.create_index(
        'idx_region_arch',
        'instance_catalog',
        ['region', 'architecture']
    )

    op.create_index(
        'idx_vcpus_memory',
        'instance_catalog',
        ['vcpus', 'memory_gb']
    )


def downgrade():
    """Drop instance_catalog table."""
    op.drop_index('idx_vcpus_memory', table_name='instance_catalog')
    op.drop_index('idx_region_arch', table_name='instance_catalog')
    op.drop_index('idx_region_current_gen', table_name='instance_catalog')
    op.drop_index('idx_instance_type_region', table_name='instance_catalog')
    op.drop_table('instance_catalog')
