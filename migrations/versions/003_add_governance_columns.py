"""Add governance columns to users and organizations

Revision ID: 003
Revises: 002
Create Date: 2026-01-13

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '003'
down_revision = '002'
branch_labels = None
depends_on = None


def upgrade():
    """Add governance-related columns for RBAC and Approval features."""
    
    # Add team_id to users table
    op.add_column('users', sa.Column('team_id', sa.String(36), nullable=True))
    
    # Add governance columns to organizations table
    op.add_column('organizations', sa.Column('is_governance_enabled', sa.Boolean(), 
                  server_default='false', nullable=True))
    op.add_column('organizations', sa.Column('is_strict_approval_mode', sa.Boolean(), 
                  server_default='false', nullable=True))
    op.add_column('organizations', sa.Column('governance_config', sa.JSON(), 
                  server_default='{}', nullable=True))
    op.add_column('organizations', sa.Column('required_tags', sa.JSON(), 
                  server_default='["Owner", "Environment"]', nullable=True))
    
    # Create approval_requests table if not exists
    op.create_table(
        'approval_requests',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('requester_id', sa.String(36), sa.ForeignKey('users.id'), nullable=True),
        sa.Column('organization_id', sa.String(36), sa.ForeignKey('organizations.id'), nullable=True),
        sa.Column('resource_type', sa.String(100), nullable=True),
        sa.Column('action', sa.String(100), nullable=True),
        sa.Column('status', sa.String(50), server_default='PENDING', nullable=True),
        sa.Column('execution_payload', sa.JSON(), nullable=True),
        sa.Column('reviewer_id', sa.String(36), sa.ForeignKey('users.id'), nullable=True),
        sa.Column('reviewed_at', sa.DateTime(), nullable=True),
        sa.Column('rejection_reason', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.func.now(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        # Skip if table already exists (for backwards compatibility)
        if_not_exists=True
    )


def downgrade():
    """Remove governance columns."""
    op.drop_table('approval_requests')
    op.drop_column('organizations', 'required_tags')
    op.drop_column('users', 'team_id')
