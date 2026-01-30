"""create_core_modules_tables

Revision ID: 008_core_modules
Revises: 007_cleanup_policies
Create Date: 2026-01-20 17:40:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '008_core_modules'
down_revision = '007_cleanup_policies'
branch_labels = None
depends_on = None

def upgrade():
    # --- 1. CLUSTERS ---
    op.create_table('clusters',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('name', sa.String(), nullable=True),
        sa.Column('account_id', sa.String(), nullable=False),
        sa.Column('arn', sa.String(), nullable=True),
        sa.Column('region', sa.String(), nullable=True),
        # Using string for Enums to avoid Postgres/Alembic type creation conflicts usually safer in manual migrations
        sa.Column('cluster_type', sa.Enum('EKS', 'ECS', 'GKE', 'AKS', name='clustertype'), nullable=True),
        sa.Column('version', sa.String(), nullable=True),
        sa.Column('endpoint', sa.String(), nullable=True),
        sa.Column('status', sa.Enum('DISCOVERED', 'ACTIVE', 'INACTIVE', 'ERROR', 'TERMINATED', name='clusterstatus'), nullable=True),
        sa.Column('agent_installed', sa.String(), nullable=True),
        sa.Column('is_agentless', sa.String(), nullable=True),
        sa.Column('aws_role_arn', sa.String(), nullable=True),
        sa.Column('aws_external_id', sa.String(), nullable=True),
        sa.Column('last_heartbeat', sa.DateTime(), nullable=True),
        sa.Column('tags', sa.JSON(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['account_id'], ['accounts.id'], )
    )
    op.create_index(op.f('ix_clusters_arn'), 'clusters', ['arn'], unique=True)
    op.create_index(op.f('ix_clusters_name'), 'clusters', ['name'], unique=False)

    # --- 2. TICKETS ---
    op.create_table('tickets',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('user_id', sa.String(), nullable=False),
        sa.Column('organization_id', sa.String(), nullable=False),
        sa.Column('approver_id', sa.String(), nullable=True),
        sa.Column('parent_id', sa.String(), nullable=True),
        sa.Column('type', sa.Enum('ACCESS_WINDOW', 'ACTION', name='tickettype'), nullable=True),
        sa.Column('resource_id', sa.String(), nullable=True),
        sa.Column('action_type', sa.String(), nullable=True),
        sa.Column('reason_category', sa.String(), nullable=True),
        sa.Column('reason_text', sa.Text(), nullable=True),
        sa.Column('duration_hours', sa.Integer(), nullable=True),
        sa.Column('status', sa.Enum('PENDING', 'PENDING_CONSENT', 'APPROVED_ACTIVE', 'REJECTED', 'REVOKED', 'EXPIRED', name='ticketstatus'), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('approved_at', sa.DateTime(), nullable=True),
        sa.Column('activated_at', sa.DateTime(), nullable=True),
        sa.Column('expires_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
        sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], ),
        sa.ForeignKeyConstraint(['approver_id'], ['users.id'], ),
        sa.ForeignKeyConstraint(['parent_id'], ['tickets.id'], )
    )

    # --- 3. HIBERNATION SCHEDULES ---
    op.create_table('hibernation_schedules',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('cluster_id', sa.String(), nullable=False),
        sa.Column('schedule_matrix', sa.String(length=168), nullable=False),
        sa.Column('timezone', sa.String(), nullable=True),
        sa.Column('pre_warm_minutes', sa.Integer(), nullable=True),
        sa.Column('is_active', sa.String(length=1), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['cluster_id'], ['clusters.id'], ),
        sa.UniqueConstraint('cluster_id')
    )

def downgrade():
    op.drop_table('hibernation_schedules')
    op.drop_table('tickets')
    op.drop_index(op.f('ix_clusters_name'), table_name='clusters')
    op.drop_index(op.f('ix_clusters_arn'), table_name='clusters')
    op.drop_table('clusters')
    # Note: Enums are not automatically dropped in downgrade usually on Postgres unless specific op used.
