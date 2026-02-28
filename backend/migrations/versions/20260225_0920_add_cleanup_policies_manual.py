"""add cleanup_policies table manually

Revision ID: 20260225_cleanup
Revises: 8f5a2cb1dc50
Create Date: 2026-02-25 09:20:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '20260225_cleanup'
down_revision = '8f5a2cb1dc50'
branch_labels = None
depends_on = None


def upgrade():
    """Create cleanup_policies table."""

    # Check if ENUMs exist, create only if they don't
    conn = op.get_bind()

    # Check for resourcetype enum
    result = conn.execute(sa.text(
        "SELECT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'resourcetype')"
    )).scalar()

    if not result:
        resourcetype_enum = postgresql.ENUM(
            'INSTANCE', 'EKS_CLUSTER', 'ECS_CLUSTER', 'AUTO_SCALING_GROUP',
            'VOLUME', 'SNAPSHOT', 'S3_BUCKET', 'EFS_FILE_SYSTEM', 'ELASTIC_IP',
            'LOAD_BALANCER', 'NAT_GATEWAY', 'NETWORK_INTERFACE', 'VPC',
            'VPC_ENDPOINT', 'TRANSIT_GATEWAY', 'RDS_DB', 'DYNAMODB_TABLE',
            'ELASTICACHE_CLUSTER', 'SECURITY_HUB', 'KMS_KEY', 'SECRETS_MANAGER',
            'CLOUDTRAIL', 'GUARDDUTY', 'CONFIG_RECORDER', 'SSM_MANAGED_INSTANCE',
            'CLOUDWATCH_LOG_GROUP', 'CLOUDWATCH_ALARM', 'LAMBDA_FUNCTION',
            'EVENTBRIDGE_RULE', 'IAM_USER', 'IAM_KEY',
            name='resourcetype'
        )
        resourcetype_enum.create(op.get_bind())

    # Check for hygieneactiontype enum
    result = conn.execute(sa.text(
        "SELECT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'hygieneactiontype')"
    )).scalar()

    if not result:
        actiontype_enum = postgresql.ENUM(
            'AUTHORIZE', 'UNAUTHORIZE', 'TERMINATE', 'DELETE', 'RELEASE',
            'SNAPSHOT_STOP', 'DISABLE', 'NOTIFY',
            name='hygieneactiontype'
        )
        actiontype_enum.create(op.get_bind())

    # Create table only if it doesn't exist
    result = conn.execute(sa.text(
        "SELECT EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'cleanup_policies')"
    )).scalar()

    if not result:
        op.create_table('cleanup_policies',
            sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
            sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
            sa.Column('name', sa.String(), nullable=False),
            sa.Column('description', sa.String(), nullable=True),
            sa.Column('resource_type', postgresql.ENUM(name='resourcetype', create_type=False), nullable=False),
            sa.Column('region', sa.String(), nullable=True),
            sa.Column('conditions', sa.JSON(), nullable=False),
            sa.Column('action', postgresql.ENUM(name='hygieneactiontype', create_type=False), nullable=False),
            sa.Column('priority', sa.Integer(), nullable=True),
            sa.Column('is_active', sa.Boolean(), nullable=True),
            sa.Column('organization_id', sa.String(), nullable=True),
            sa.PrimaryKeyConstraint('id')
        )


def downgrade():
    """Drop cleanup_policies table."""
    op.drop_table('cleanup_policies')
