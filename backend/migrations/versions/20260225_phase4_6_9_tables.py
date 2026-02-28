"""add phase 4, 6, 9 remediation tables

Revision ID: 20260225_phase4_6_9
Revises: 20260225_phase5_timescaledb_hypertable
Create Date: 2026-02-25 14:30:00.000000

Adds tables for:
- Phase 4: alert_config, alert_history (Security & Alerting)
- Phase 6: credential_cache (JIT Security)
- Phase 9: chaos_experiment (Chaos Testing)
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from datetime import datetime

# revision identifiers, used by Alembic.
revision = '20260225_phase4_6_9'
down_revision = '20260225_phase5_timescaledb_hypertable'
branch_labels = None
depends_on = None


def upgrade():
    """Create Phase 4, 6, and 9 tables."""

    # ========================================
    # PHASE 4: Security & Alerting
    # ========================================

    # Create ENUM types for alert_config
    alert_channel_enum = postgresql.ENUM(
        'EMAIL', 'SLACK', 'PAGERDUTY', 'WEBHOOK',
        name='alert_channel_enum'
    )
    alert_channel_enum.create(op.get_bind())

    alert_severity_enum = postgresql.ENUM(
        'INFO', 'WARNING', 'ERROR', 'CRITICAL',
        name='alert_severity_enum'
    )
    alert_severity_enum.create(op.get_bind())

    alert_type_enum = postgresql.ENUM(
        'SPOT_INTERRUPTION', 'CIRCUIT_BREAKER_OPEN', 'CIRCUIT_BREAKER_CLOSED',
        'PRICING_STALE', 'VOLATILITY_HIGH', 'JIT_LIMIT_EXCEEDED', 'PDB_BLOCKED',
        'EXECUTION_FAILED', 'KARPENTER_FAILURE', 'AGENT_DISCONNECTED',
        name='alert_type_enum'
    )
    alert_type_enum.create(op.get_bind())

    # Table: alert_config
    op.create_table(
        'alert_config',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('organization_id', sa.String(36), nullable=False, index=True),
        sa.Column('name', sa.String(255), nullable=False),
        sa.Column('description', sa.Text, nullable=True),

        # Alert configuration
        sa.Column('alert_type', alert_type_enum, nullable=False, index=True),
        sa.Column('severity', alert_severity_enum, nullable=False, default='INFO'),
        sa.Column('channel', alert_channel_enum, nullable=False, index=True),
        sa.Column('enabled', sa.Boolean, nullable=False, default=True, index=True),

        # Channel configuration
        sa.Column('channel_config', sa.JSON, nullable=False, default=dict),

        # Thresholds
        sa.Column('threshold_value', sa.Float, nullable=True),
        sa.Column('threshold_duration_seconds', sa.Integer, nullable=True),

        # Region filtering
        sa.Column('target_regions', postgresql.ARRAY(sa.String), nullable=True),
        sa.Column('target_clusters', postgresql.ARRAY(sa.String), nullable=True),

        # Rate limiting
        sa.Column('cooldown_seconds', sa.Integer, nullable=False, default=300),
        sa.Column('max_alerts_per_hour', sa.Integer, nullable=False, default=10),

        # HMAC signing (for webhooks)
        sa.Column('webhook_secret', sa.String(64), nullable=True),

        sa.Column('created_at', sa.DateTime, nullable=False, default=datetime.utcnow),
        sa.Column('updated_at', sa.DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow),
    )

    # Indexes for alert_config
    op.create_index('idx_alert_config_org_enabled', 'alert_config', ['organization_id', 'enabled'])
    op.create_index('idx_alert_config_type_severity', 'alert_config', ['alert_type', 'severity'])

    # Create ENUM for alert_history status
    alert_status_enum = postgresql.ENUM(
        'PENDING', 'SENT', 'FAILED', 'RATE_LIMITED', 'DEDUPLICATED',
        name='alert_status_enum'
    )
    alert_status_enum.create(op.get_bind())

    # Table: alert_history
    op.create_table(
        'alert_history',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('alert_config_id', sa.String(36), nullable=False, index=True),
        sa.Column('organization_id', sa.String(36), nullable=False, index=True),

        # Alert details
        sa.Column('alert_type', alert_type_enum, nullable=False, index=True),
        sa.Column('severity', alert_severity_enum, nullable=False),
        sa.Column('channel', alert_channel_enum, nullable=False),
        sa.Column('status', alert_status_enum, nullable=False, default='PENDING', index=True),

        # Message
        sa.Column('title', sa.String(500), nullable=False),
        sa.Column('message', sa.Text, nullable=False),
        sa.Column('metadata', sa.JSON, nullable=False, default=dict),

        # Retry tracking
        sa.Column('retry_count', sa.Integer, nullable=False, default=0),
        sa.Column('last_retry_at', sa.DateTime, nullable=True),
        sa.Column('error_message', sa.Text, nullable=True),

        # Deduplication
        sa.Column('deduplication_key', sa.String(64), nullable=False, index=True),

        # HMAC signature (for webhooks)
        sa.Column('hmac_signature', sa.String(128), nullable=True),

        sa.Column('sent_at', sa.DateTime, nullable=True),
        sa.Column('created_at', sa.DateTime, nullable=False, default=datetime.utcnow, index=True),
    )

    # Indexes for alert_history
    op.create_index('idx_alert_history_status_created', 'alert_history', ['status', 'created_at'])
    op.create_index('idx_alert_history_dedup', 'alert_history', ['deduplication_key', 'created_at'])

    # ========================================
    # PHASE 6: JIT Security (STS Credentials)
    # ========================================

    # Table: credential_cache
    op.create_table(
        'credential_cache',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('account_id', sa.String(36), nullable=False, index=True),
        sa.Column('user_id', sa.String(36), nullable=False, index=True),
        sa.Column('approval_id', sa.String(36), nullable=True, index=True),

        # Encrypted credential fields (AES-256-GCM)
        sa.Column('encrypted_access_key', sa.Text, nullable=False),
        sa.Column('encrypted_secret_key', sa.Text, nullable=False),
        sa.Column('encrypted_session_token', sa.Text, nullable=False),

        # Credential metadata
        sa.Column('role_arn', sa.String(255), nullable=False),
        sa.Column('session_name', sa.String(128), nullable=False),
        sa.Column('region', sa.String(20), nullable=False, default='us-east-1'),

        # Expiration tracking
        sa.Column('issued_at', sa.DateTime, nullable=False, default=datetime.utcnow),
        sa.Column('expires_at', sa.DateTime, nullable=False, index=True),
        sa.Column('rotation_threshold_at', sa.DateTime, nullable=False),
        sa.Column('last_used_at', sa.DateTime, nullable=True),

        # Audit
        sa.Column('request_ip', sa.String(45), nullable=True),
        sa.Column('request_user_agent', sa.String(500), nullable=True),

        sa.Column('created_at', sa.DateTime, nullable=False, default=datetime.utcnow),
    )

    # Indexes for credential_cache
    op.create_index('idx_credential_cache_expires', 'credential_cache', ['expires_at'])
    op.create_index('idx_credential_cache_user_account', 'credential_cache', ['user_id', 'account_id'])

    # ========================================
    # PHASE 9: Chaos Testing
    # ========================================

    # Create ENUM types for chaos_experiment
    chaos_experiment_type_enum = postgresql.ENUM(
        'REDIS_FLUSH', 'DB_CONNECTION_LOSS', 'API_LATENCY', 'SPOT_INTERRUPTION',
        'PRICING_OUTAGE', 'POOL_BLACKLIST', 'KARPENTER_SLOW', 'PDB_DEADLOCK',
        'CELERY_CRASH', 'NETWORK_PARTITION',
        name='chaos_experiment_type_enum'
    )
    chaos_experiment_type_enum.create(op.get_bind())

    chaos_experiment_status_enum = postgresql.ENUM(
        'PENDING', 'RUNNING', 'COMPLETED', 'FAILED', 'ROLLED_BACK', 'CANCELLED',
        name='chaos_experiment_status_enum'
    )
    chaos_experiment_status_enum.create(op.get_bind())

    # Table: chaos_experiment
    op.create_table(
        'chaos_experiment',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('cluster_id', sa.String(36), nullable=False, index=True),
        sa.Column('organization_id', sa.String(36), nullable=False, index=True),

        # Experiment configuration
        sa.Column('experiment_type', chaos_experiment_type_enum, nullable=False, index=True),
        sa.Column('name', sa.String(255), nullable=False),
        sa.Column('description', sa.Text, nullable=True),
        sa.Column('config', sa.JSON, nullable=False, default=dict),

        # Safety guardrails
        sa.Column('requires_approval', sa.Boolean, nullable=False, default=True),
        sa.Column('approved_by', sa.String(36), nullable=True),
        sa.Column('approved_at', sa.DateTime, nullable=True),
        sa.Column('production_enabled', sa.Boolean, nullable=False, default=False),

        # Status
        sa.Column('status', chaos_experiment_status_enum, nullable=False, default='PENDING', index=True),
        sa.Column('started_at', sa.DateTime, nullable=True),
        sa.Column('completed_at', sa.DateTime, nullable=True),

        # Results
        sa.Column('error_rate_before', sa.Float, nullable=True),
        sa.Column('error_rate_during', sa.Float, nullable=True),
        sa.Column('error_rate_after', sa.Float, nullable=True),
        sa.Column('latency_p50_before', sa.Float, nullable=True),
        sa.Column('latency_p50_during', sa.Float, nullable=True),
        sa.Column('latency_p50_after', sa.Float, nullable=True),
        sa.Column('latency_p99_before', sa.Float, nullable=True),
        sa.Column('latency_p99_during', sa.Float, nullable=True),
        sa.Column('latency_p99_after', sa.Float, nullable=True),

        # Rollback tracking
        sa.Column('auto_rolled_back', sa.Boolean, nullable=False, default=False),
        sa.Column('rollback_reason', sa.Text, nullable=True),
        sa.Column('rollback_at', sa.DateTime, nullable=True),

        # Observability
        sa.Column('metrics_snapshot', sa.JSON, nullable=True),
        sa.Column('logs_url', sa.String(500), nullable=True),

        sa.Column('created_at', sa.DateTime, nullable=False, default=datetime.utcnow, index=True),
        sa.Column('updated_at', sa.DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow),
    )

    # Indexes for chaos_experiment
    op.create_index('idx_chaos_experiment_cluster_status', 'chaos_experiment', ['cluster_id', 'status'])
    op.create_index('idx_chaos_experiment_type_created', 'chaos_experiment', ['experiment_type', 'created_at'])


def downgrade():
    """Drop Phase 4, 6, and 9 tables."""

    # Phase 9
    op.drop_index('idx_chaos_experiment_type_created', table_name='chaos_experiment')
    op.drop_index('idx_chaos_experiment_cluster_status', table_name='chaos_experiment')
    op.drop_table('chaos_experiment')
    op.execute('DROP TYPE chaos_experiment_status_enum')
    op.execute('DROP TYPE chaos_experiment_type_enum')

    # Phase 6
    op.drop_index('idx_credential_cache_user_account', table_name='credential_cache')
    op.drop_index('idx_credential_cache_expires', table_name='credential_cache')
    op.drop_table('credential_cache')

    # Phase 4
    op.drop_index('idx_alert_history_dedup', table_name='alert_history')
    op.drop_index('idx_alert_history_status_created', table_name='alert_history')
    op.drop_table('alert_history')
    op.execute('DROP TYPE alert_status_enum')

    op.drop_index('idx_alert_config_type_severity', table_name='alert_config')
    op.drop_index('idx_alert_config_org_enabled', table_name='alert_config')
    op.drop_table('alert_config')
    op.execute('DROP TYPE alert_type_enum')
    op.execute('DROP TYPE alert_severity_enum')
    op.execute('DROP TYPE alert_channel_enum')
