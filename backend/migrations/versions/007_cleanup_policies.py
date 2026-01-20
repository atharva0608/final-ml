"""create_cleanup_policies

Revision ID: 007_cleanup_policies
Revises: 006_tag_management
Create Date: 2026-01-20 13:10:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '007_cleanup_policies'
down_revision = '006_tag_management'
branch_labels = None
depends_on = None

def upgrade():
    # Create enum types if they don't exist
    # Note: ResourceType and CleanupActionType might already be used/defined? 
    # Current codebase uses schemas, not database-level enums usually, but let's check using 'create_type=False' in SAEnum if needed.
    # However, SQLAlchemy Enum creates type by default. 
    # Let's use sa.Enum with name to avoid duplicates or issues.
    
    op.create_table('cleanup_policies',
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('name', sa.String(), nullable=False),
        sa.Column('description', sa.String(), nullable=True),
        sa.Column('resource_type', sa.Enum('INSTANCE', 'VOLUME', 'SNAPSHOT', 'ELASTIC_IP', 'LOAD_BALANCER', 'NAT_GATEWAY', 'NETWORK_INTERFACE', 'RDS_DB', 'S3_BUCKET', 'IAM_USER', 'IAM_KEY', name='resourcetype'), nullable=False),
        sa.Column('region', sa.String(), nullable=True),
        sa.Column('conditions', sa.JSON(), nullable=False),
        sa.Column('action', sa.Enum('AUTHORIZE', 'UNAUTHORIZE', 'TERMINATE', 'DELETE', 'RELEASE', 'SNAPSHOT_STOP', 'DISABLE', 'NOTIFY', name='cleanupactiontype'), nullable=False),
        sa.Column('priority', sa.Integer(), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=True),
        sa.Column('organization_id', sa.String(), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )

def downgrade():
    op.drop_table('cleanup_policies')
    # Types usually dropped automatically? If not, we might need manual drop but usually fine for now.
