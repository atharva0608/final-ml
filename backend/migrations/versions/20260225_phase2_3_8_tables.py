"""add phase 2 3 8 remediation tables

Revision ID: 20260225_phase2_3_8
Revises: 20260225_instance_catalog
Create Date: 2026-02-25 07:30:00.000000

Adds tables for:
- Phase 2: family_hour_baselines, model_registry
- Phase 3: execution_state
- Phase 8: circuit_breaker_state
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from datetime import datetime

# revision identifiers, used by Alembic.
revision = '20260225_phase2_3_8'
down_revision = '20260225_instance_catalog'
branch_labels = None
depends_on = None


def upgrade():
    """Create Phase 2, 3, and 8 tables."""

    # ========================================
    # PHASE 2: ML Feature Engineering
    # ========================================

    # Table: family_hour_baselines
    op.create_table(
        'family_hour_baselines',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('instance_family', sa.String(50), nullable=False, index=True),
        sa.Column('region', sa.String(50), nullable=False, index=True),
        sa.Column('date', sa.Date, nullable=False, index=True),
        sa.Column('hour', sa.Integer, nullable=False, index=True),
        sa.Column('mean_price', sa.Float, nullable=False, default=0.0),
        sa.Column('min_price', sa.Float, nullable=False, default=0.0),
        sa.Column('max_price', sa.Float, nullable=False, default=0.0),
        sa.Column('stddev_price', sa.Float, nullable=False, default=0.0),
        sa.Column('sample_count', sa.Integer, nullable=False, default=0),
        sa.Column('created_at', sa.DateTime, nullable=False, default=datetime.utcnow),
        sa.Column('updated_at', sa.DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow),
    )

    # Composite indexes for family_hour_baselines
    op.create_index(
        'idx_family_region_date_hour',
        'family_hour_baselines',
        ['instance_family', 'region', 'date', 'hour'],
        unique=True
    )

    op.create_index(
        'idx_family_region_hour',
        'family_hour_baselines',
        ['instance_family', 'region', 'hour']
    )

    op.create_index(
        'idx_region_date',
        'family_hour_baselines',
        ['region', 'date']
    )

    # Table: model_registry
    op.create_table(
        'model_registry',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('model_version', sa.String(10), nullable=False, unique=True, index=True),
        sa.Column('model_name', sa.String(255), nullable=False),
        sa.Column('feature_schema_version', sa.String(10), nullable=False, index=True),
        sa.Column('onnx_path', sa.String(500), nullable=False),
        sa.Column('is_active', sa.Boolean, nullable=False, default=False, index=True),
        sa.Column('deployed_at', sa.DateTime, nullable=True),
        sa.Column('deprecated_at', sa.DateTime, nullable=True),
        sa.Column('created_at', sa.DateTime, nullable=False, default=datetime.utcnow),
        sa.Column('updated_at', sa.DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow),
    )

    # Indexes for model_registry
    op.create_index(
        'idx_model_version_schema',
        'model_registry',
        ['model_version', 'feature_schema_version']
    )

    op.create_index(
        'idx_active_models',
        'model_registry',
        ['is_active', 'deployed_at']
    )

    # ========================================
    # PHASE 3: Execution State Machine
    # ========================================

    # Create ENUM type for execution states
    execution_state_enum = postgresql.ENUM(
        'PENDING', 'VALIDATING', 'PREWARMING', 'DRAINING', 'PROVISIONING',
        'READY', 'COMPLETED', 'FAILED', 'ARCHIVED', 'PDB_BLOCKED',
        'CIRCUIT_OPEN', 'ROLLBACK',
        name='execution_state_enum'
    )
    execution_state_enum.create(op.get_bind())

    # Table: execution_state
    op.create_table(
        'execution_state',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('cluster_id', sa.String(36), nullable=False, index=True),
        sa.Column('state', execution_state_enum, nullable=False, default='PENDING', index=True),
        sa.Column('last_transition_at', sa.DateTime, nullable=False, default=datetime.utcnow),
        sa.Column('retry_count', sa.Integer, nullable=False, default=0),
        sa.Column('idempotency_key', sa.String(255), nullable=False, unique=True, index=True),
        sa.Column('error_message', sa.Text, nullable=True),
        sa.Column('archived_at', sa.DateTime, nullable=True, index=True),
        sa.Column('target_node_name', sa.String(255), nullable=True),
        sa.Column('substitute_instance_id', sa.String(255), nullable=True),
        sa.Column('created_at', sa.DateTime, nullable=False, default=datetime.utcnow),
        sa.Column('updated_at', sa.DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow),
    )

    # UNIQUE constraint on cluster_id (prevents split-brain)
    op.create_unique_constraint('uq_execution_state_cluster_id', 'execution_state', ['cluster_id'])

    # Indexes for execution_state
    op.create_index(
        'idx_state_archived',
        'execution_state',
        ['state', 'archived_at']
    )

    op.create_index(
        'idx_cluster_state',
        'execution_state',
        ['cluster_id', 'state']
    )

    op.create_index(
        'idx_active_executions',
        'execution_state',
        ['state', 'last_transition_at']
    )

    # ========================================
    # PHASE 8: Distributed Locks & Circuit Breaker
    # ========================================

    # Table: circuit_breaker_state
    op.create_table(
        'circuit_breaker_state',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('service_name', sa.String(255), nullable=False, unique=True, index=True),
        sa.Column('state', sa.String(20), nullable=False, default='CLOSED', index=True),
        sa.Column('failure_count', sa.Integer, nullable=False, default=0),
        sa.Column('last_failure_at', sa.DateTime, nullable=True),
        sa.Column('trip_count', sa.Integer, nullable=False, default=0),
        sa.Column('created_at', sa.DateTime, nullable=False, default=datetime.utcnow),
        sa.Column('updated_at', sa.DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow),
    )

    # Index for circuit_breaker_state
    op.create_index(
        'idx_service_state',
        'circuit_breaker_state',
        ['service_name', 'state']
    )


def downgrade():
    """Drop Phase 2, 3, and 8 tables."""

    # Phase 8
    op.drop_index('idx_service_state', table_name='circuit_breaker_state')
    op.drop_table('circuit_breaker_state')

    # Phase 3
    op.drop_index('idx_active_executions', table_name='execution_state')
    op.drop_index('idx_cluster_state', table_name='execution_state')
    op.drop_index('idx_state_archived', table_name='execution_state')
    op.drop_constraint('uq_execution_state_cluster_id', 'execution_state', type_='unique')
    op.drop_table('execution_state')

    # Drop ENUM type
    op.execute('DROP TYPE execution_state_enum')

    # Phase 2
    op.drop_index('idx_active_models', table_name='model_registry')
    op.drop_index('idx_model_version_schema', table_name='model_registry')
    op.drop_table('model_registry')

    op.drop_index('idx_region_date', table_name='family_hour_baselines')
    op.drop_index('idx_family_region_hour', table_name='family_hour_baselines')
    op.drop_index('idx_family_region_date_hour', table_name='family_hour_baselines')
    op.drop_table('family_hour_baselines')
