"""add agent identity table for OIDC federation

Revision ID: 20260225_agent_identity
Revises: 20260225_add_instance_catalog_table
Create Date: 2026-02-25 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '20260225_agent_identity'
down_revision = '20260225_add_instance_catalog_table'
branch_labels = None
depends_on = None


def upgrade():
    """
    Create agent_identities table for OIDC federation and JWT token validation.

    Phase 7: Agent Security (OIDC Federation)
    - Stores agent public keys for JWT signature verification
    - Supports EKS IRSA (IAM Roles for Service Accounts)
    - Implements certificate thumbprint pinning
    - Tracks validation failures with circuit breaker pattern
    """
    op.create_table(
        'agent_identities',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('cluster_id', sa.String(), nullable=False),
        sa.Column('oidc_issuer', sa.String(), nullable=False),
        sa.Column('oidc_audience', sa.String(), nullable=False),
        sa.Column('service_account_namespace', sa.String(), nullable=False),
        sa.Column('service_account_name', sa.String(), nullable=False),
        sa.Column('public_key_pem', sa.Text(), nullable=True),
        sa.Column('public_key_algorithm', sa.String(), nullable=False),
        sa.Column('jwks_json', postgresql.JSON(astext_type=sa.Text()), nullable=True),
        sa.Column('jwks_last_updated', sa.DateTime(timezone=True), nullable=True),
        sa.Column('certificate_thumbprint', sa.String(), nullable=True),
        sa.Column('max_token_age_seconds', sa.Integer(), nullable=False),
        sa.Column('require_nbf_claim', sa.Boolean(), nullable=False),
        sa.Column('require_exp_claim', sa.Boolean(), nullable=False),
        sa.Column('is_active', sa.Boolean(), nullable=False),
        sa.Column('last_token_validated_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('validation_failure_count', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('metadata', postgresql.JSON(astext_type=sa.Text()), nullable=False),
        sa.PrimaryKeyConstraint('id')
    )

    # Indexes for performance
    op.create_index('ix_agent_identities_cluster_id', 'agent_identities', ['cluster_id'], unique=True)
    op.create_index('ix_agent_identities_certificate_thumbprint', 'agent_identities', ['certificate_thumbprint'], unique=False)

    # Foreign key to clusters table
    op.create_foreign_key(
        'fk_agent_identities_cluster_id',
        'agent_identities',
        'clusters',
        ['cluster_id'],
        ['id'],
        ondelete='CASCADE'
    )


def downgrade():
    """Drop agent_identities table"""
    op.drop_constraint('fk_agent_identities_cluster_id', 'agent_identities', type_='foreignkey')
    op.drop_index('ix_agent_identities_certificate_thumbprint', table_name='agent_identities')
    op.drop_index('ix_agent_identities_cluster_id', table_name='agent_identities')
    op.drop_table('agent_identities')
