"""add placement policies

Revision ID: 010_add_placement_policies
Revises: 009_add_workload_classifications
Create Date: 2026-04-21 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '010_add_placement_policies'
down_revision = '009_add_workload_classifications'
branch_labels = None
depends_on = None

def upgrade():
    # Create placement_policies table
    op.create_table(
        'placement_policies',
        
        # Identity
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('cluster_id', sa.String(36), nullable=False),
        sa.Column('workload_id', sa.String(512), nullable=False),
        sa.Column('namespace', sa.String(253), nullable=False),
        sa.Column('name', sa.String(253), nullable=False),
        sa.Column('generated_at', sa.DateTime(), nullable=False),
        
        # Phase 1 Inputs
        sa.Column('criticality_tier', sa.String(20), nullable=False),
        sa.Column('confidence_state', sa.String(20), nullable=False),
        sa.Column('spot_friendly', sa.Boolean(), nullable=False),
        
        # Distribution
        sa.Column('observed_replicas', sa.Integer(), nullable=False),
        sa.Column('ondemand_target', sa.Integer(), nullable=False),
        sa.Column('spot_target', sa.Integer(), nullable=False),
        sa.Column('spot_target_raw', sa.Integer(), nullable=False),
        
        # Traffic skew
        sa.Column('traffic_skew_detected', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('skew_signal_source', sa.String(50), nullable=True),
        sa.Column('pod_cpu_cv', sa.Float(), nullable=True),
        sa.Column('pod_request_rate_cv', sa.Float(), nullable=True),
        
        # NodePool
        sa.Column('assigned_nodepool_class', sa.String(50), nullable=False),
        sa.Column('spot_instance_families', postgresql.JSONB(), nullable=False, server_default='[]'),
        sa.Column('spot_instance_types', postgresql.JSONB(), nullable=False, server_default='[]'),
        
        # Constraints
        sa.Column('baseline_affinity', postgresql.JSONB(), nullable=False, server_default='{}'),
        sa.Column('burst_affinity', postgresql.JSONB(), nullable=False, server_default='{}'),
        sa.Column('topology_spread', postgresql.JSONB(), nullable=True),
        sa.Column('spread_relaxation_tier', sa.Integer(), nullable=False, server_default='0'),
        
        # KEDA
        sa.Column('keda_min_replicas', sa.Integer(), nullable=True),
        sa.Column('keda_max_replicas', sa.Integer(), nullable=True),
        
        # Rollout
        sa.Column('rollout_eligible', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('rollout_blocked_reason', sa.String(512), nullable=True),
        
        # Cost
        sa.Column('estimated_savings_pct', sa.Float(), nullable=False, server_default='0.0'),
        sa.Column('estimated_monthly_saving_usd', sa.Float(), nullable=False, server_default='0.0'),
        
        # Actionability
        sa.Column('actionable', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('actionable_blocked_reason', sa.String(512), nullable=True),
        
        # Audit
        sa.Column('signals_used', postgresql.JSONB(), nullable=False, server_default='[]'),
        sa.Column('schema_version', sa.String(10), nullable=False, server_default='5.10'),
        sa.Column('input_hash', sa.String(64), nullable=True),
        
        # Timestamps
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        
        # Foreign Key constraint
        sa.ForeignKeyConstraint(['cluster_id'], ['clusters.id'], ondelete='CASCADE'),
        
        # Unique constraint
        sa.UniqueConstraint('cluster_id', 'workload_id', name='uq_placement_policies_cluster_workload')
    )
    
    # Create indexes
    op.create_index('ix_placement_policies_cluster_actionable', 'placement_policies', ['cluster_id', 'actionable'])
    op.create_index('ix_placement_policies_cluster_tier', 'placement_policies', ['cluster_id', 'criticality_tier'])
    op.create_index('ix_placement_policies_cluster_rollout', 'placement_policies', ['cluster_id', 'rollout_eligible'])
    op.create_index('ix_placement_policies_workload_id', 'placement_policies', ['workload_id'])

def downgrade():
    op.drop_table('placement_policies')
