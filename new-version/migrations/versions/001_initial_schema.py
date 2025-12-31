"""
Initial schema migration

Creates all tables for Spot Optimizer platform

Revision ID: 001
Revises:
Create Date: 2025-12-31 12:50:00

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '001'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create users table
    op.create_table(
        'users',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('email', sa.String(255), nullable=False, unique=True, index=True),
        sa.Column('password_hash', sa.String(255), nullable=False),
        sa.Column('role', sa.Enum('CLIENT', 'SUPER_ADMIN', name='userrole'), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.func.now(), onupdate=sa.func.now()),
    )
    op.create_index('idx_users_email', 'users', ['email'])

    # Create accounts table
    op.create_table(
        'accounts',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('user_id', sa.String(36), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False, index=True),
        sa.Column('aws_account_id', sa.String(12), nullable=False),
        sa.Column('role_arn', sa.String(255), nullable=False),
        sa.Column('external_id', sa.String(64), nullable=True),
        sa.Column('status', sa.Enum('PENDING', 'SCANNING', 'ACTIVE', 'ERROR', name='accountstatus'), nullable=False, index=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )

    # Create clusters table
    op.create_table(
        'clusters',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('account_id', sa.String(36), sa.ForeignKey('accounts.id', ondelete='CASCADE'), nullable=False, index=True),
        sa.Column('name', sa.String(255), nullable=False, index=True),
        sa.Column('region', sa.String(50), nullable=False, index=True),
        sa.Column('vpc_id', sa.String(50), nullable=True),
        sa.Column('api_endpoint', sa.String(255), nullable=True),
        sa.Column('k8s_version', sa.String(20), nullable=True),
        sa.Column('status', sa.Enum('PENDING', 'ACTIVE', 'INACTIVE', 'ERROR', name='clusterstatus'), nullable=False, index=True),
        sa.Column('agent_installed', sa.String(1), nullable=False, server_default='N'),
        sa.Column('last_heartbeat', sa.DateTime(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )

    # Create instances table
    op.create_table(
        'instances',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('cluster_id', sa.String(36), sa.ForeignKey('clusters.id', ondelete='CASCADE'), nullable=False, index=True),
        sa.Column('instance_id', sa.String(20), nullable=False, unique=True, index=True),
        sa.Column('instance_type', sa.String(50), nullable=False, index=True),
        sa.Column('lifecycle', sa.Enum('SPOT', 'ON_DEMAND', name='instancelifecycle'), nullable=False, index=True),
        sa.Column('az', sa.String(50), nullable=False, index=True),
        sa.Column('price', sa.Float(), nullable=True),
        sa.Column('cpu_util', sa.Float(), nullable=True),
        sa.Column('memory_util', sa.Float(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    op.create_index('idx_cluster_lifecycle', 'instances', ['cluster_id', 'lifecycle'])
    op.create_index('idx_cluster_instance_type', 'instances', ['cluster_id', 'instance_type'])

    # Create node_templates table
    op.create_table(
        'node_templates',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('user_id', sa.String(36), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False, index=True),
        sa.Column('name', sa.String(255), nullable=False),
        sa.Column('families', postgresql.ARRAY(sa.String()), nullable=False),
        sa.Column('architecture', sa.String(20), nullable=False, server_default='x86_64'),
        sa.Column('strategy', sa.Enum('CHEAPEST', 'BALANCED', 'PERFORMANCE', name='templatestrategy'), nullable=False),
        sa.Column('disk_type', sa.Enum('GP3', 'GP2', 'IO1', 'IO2', name='disktype'), nullable=False),
        sa.Column('disk_size', sa.Integer(), nullable=False, server_default='100'),
        sa.Column('is_default', sa.String(1), nullable=False, server_default='N'),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint('user_id', 'name', name='uq_user_template_name'),
    )

    # Create cluster_policies table
    op.create_table(
        'cluster_policies',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('cluster_id', sa.String(36), sa.ForeignKey('clusters.id', ondelete='CASCADE'), nullable=False, unique=True, index=True),
        sa.Column('config', postgresql.JSONB(), nullable=False, server_default='{}'),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )

    # Create hibernation_schedules table
    op.create_table(
        'hibernation_schedules',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('cluster_id', sa.String(36), sa.ForeignKey('clusters.id', ondelete='CASCADE'), nullable=False, unique=True, index=True),
        sa.Column('schedule_matrix', postgresql.JSONB(), nullable=False),
        sa.Column('timezone', sa.String(50), nullable=False, server_default='UTC'),
        sa.Column('prewarm_enabled', sa.String(1), nullable=False, server_default='N'),
        sa.Column('prewarm_minutes', sa.Integer(), nullable=False, server_default='30'),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )

    # Create audit_logs table (immutable)
    op.create_table(
        'audit_logs',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('timestamp', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now(), index=True),
        sa.Column('actor_id', sa.String(36), nullable=False, index=True),
        sa.Column('actor_name', sa.String(255), nullable=False),
        sa.Column('event', sa.String(255), nullable=False, index=True),
        sa.Column('resource', sa.String(255), nullable=False),
        sa.Column('resource_type', sa.Enum('CLUSTER', 'INSTANCE', 'TEMPLATE', 'POLICY', 'HIBERNATION', 'USER', 'ACCOUNT', name='resourcetype'), nullable=False, index=True),
        sa.Column('outcome', sa.Enum('SUCCESS', 'FAILURE', name='auditoutcome'), nullable=False),
        sa.Column('ip_address', sa.String(45), nullable=True),
        sa.Column('user_agent', sa.String(512), nullable=True),
        sa.Column('diff_before', postgresql.JSONB(), nullable=True),
        sa.Column('diff_after', postgresql.JSONB(), nullable=True),
    )
    op.create_index('idx_audit_timestamp_desc', 'audit_logs', [sa.text('timestamp DESC')])
    op.create_index('idx_audit_actor_timestamp', 'audit_logs', ['actor_id', sa.text('timestamp DESC')])
    op.create_index('idx_audit_resource_type_timestamp', 'audit_logs', ['resource_type', sa.text('timestamp DESC')])

    # Create ml_models table
    op.create_table(
        'ml_models',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('version', sa.String(50), nullable=False, unique=True, index=True),
        sa.Column('file_path', sa.String(512), nullable=False),
        sa.Column('status', sa.Enum('TESTING', 'PRODUCTION', 'DEPRECATED', name='mlmodelstatus'), nullable=False, index=True),
        sa.Column('performance_metrics', postgresql.JSONB(), nullable=True),
        sa.Column('uploaded_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column('validated_at', sa.DateTime(), nullable=True),
        sa.Column('promoted_at', sa.DateTime(), nullable=True),
    )

    # Create optimization_jobs table
    op.create_table(
        'optimization_jobs',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('cluster_id', sa.String(36), sa.ForeignKey('clusters.id', ondelete='CASCADE'), nullable=False, index=True),
        sa.Column('status', sa.Enum('QUEUED', 'RUNNING', 'COMPLETED', 'FAILED', name='optimizationjobstatus'), nullable=False, index=True),
        sa.Column('results', postgresql.JSONB(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now(), index=True),
        sa.Column('started_at', sa.DateTime(), nullable=True),
        sa.Column('completed_at', sa.DateTime(), nullable=True),
    )
    op.create_index('idx_optimization_cluster_status', 'optimization_jobs', ['cluster_id', 'status'])
    op.create_index('idx_optimization_created_desc', 'optimization_jobs', [sa.text('created_at DESC')])

    # Create lab_experiments table
    op.create_table(
        'lab_experiments',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('model_id', sa.String(36), sa.ForeignKey('ml_models.id', ondelete='CASCADE'), nullable=False, index=True),
        sa.Column('instance_id', sa.String(20), nullable=False),
        sa.Column('test_type', sa.String(50), nullable=False),
        sa.Column('telemetry', postgresql.JSONB(), nullable=False, server_default='{}'),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now(), index=True),
    )

    # Create agent_actions table (Kubernetes action queue)
    op.create_table(
        'agent_actions',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('cluster_id', sa.String(36), sa.ForeignKey('clusters.id', ondelete='CASCADE'), nullable=False, index=True),
        sa.Column('action_type', sa.Enum('EVICT_POD', 'CORDON_NODE', 'DRAIN_NODE', 'LABEL_NODE', 'UPDATE_DEPLOYMENT', name='agentactiontype'), nullable=False, index=True),
        sa.Column('payload', postgresql.JSONB(), nullable=False, server_default='{}'),
        sa.Column('status', sa.Enum('PENDING', 'PICKED_UP', 'COMPLETED', 'FAILED', 'EXPIRED', name='agentactionstatus'), nullable=False, index=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now(), index=True),
        sa.Column('expires_at', sa.DateTime(), nullable=False, index=True),
        sa.Column('picked_up_at', sa.DateTime(), nullable=True),
        sa.Column('completed_at', sa.DateTime(), nullable=True),
        sa.Column('result', postgresql.JSONB(), nullable=True),
        sa.Column('error_message', sa.String(1024), nullable=True),
        sa.CheckConstraint('expires_at > created_at', name='check_expires_after_created'),
    )
    op.create_index('idx_agent_action_cluster_status', 'agent_actions', ['cluster_id', 'status'])
    op.create_index('idx_agent_action_expires', 'agent_actions', ['expires_at'])

    # Create api_keys table (Agent authentication)
    op.create_table(
        'api_keys',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('cluster_id', sa.String(36), sa.ForeignKey('clusters.id', ondelete='CASCADE'), nullable=False, index=True),
        sa.Column('key_hash', sa.String(64), nullable=False, unique=True, index=True),
        sa.Column('key_prefix', sa.String(8), nullable=False, index=True),
        sa.Column('description', sa.String(255), nullable=True),
        sa.Column('last_used_at', sa.DateTime(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column('expires_at', sa.DateTime(), nullable=True),
    )


def downgrade() -> None:
    # Drop tables in reverse order (respecting foreign key dependencies)
    op.drop_table('api_keys')
    op.drop_table('agent_actions')
    op.drop_table('lab_experiments')
    op.drop_table('optimization_jobs')
    op.drop_table('ml_models')
    op.drop_table('audit_logs')
    op.drop_table('hibernation_schedules')
    op.drop_table('cluster_policies')
    op.drop_table('node_templates')
    op.drop_table('instances')
    op.drop_table('clusters')
    op.drop_table('accounts')
    op.drop_table('users')

    # Drop enums
    op.execute('DROP TYPE IF EXISTS userrole')
    op.execute('DROP TYPE IF EXISTS accountstatus')
    op.execute('DROP TYPE IF EXISTS clusterstatus')
    op.execute('DROP TYPE IF EXISTS instancelifecycle')
    op.execute('DROP TYPE IF EXISTS templatestrategy')
    op.execute('DROP TYPE IF EXISTS disktype')
    op.execute('DROP TYPE IF EXISTS resourcetype')
    op.execute('DROP TYPE IF EXISTS auditoutcome')
    op.execute('DROP TYPE IF EXISTS mlmodelstatus')
    op.execute('DROP TYPE IF EXISTS optimizationjobstatus')
    op.execute('DROP TYPE IF EXISTS agentactiontype')
    op.execute('DROP TYPE IF EXISTS agentactionstatus')
