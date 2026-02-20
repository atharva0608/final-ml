"""Add AtharvaAI usage tracking to node_templates

Revision ID: 20260219_template_usage
Revises: 20260216_atharvaai_tables
Create Date: 2026-02-19 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '20260219_template_usage'
down_revision = '20260216_pod_metrics'
branch_labels = None
depends_on = None


def upgrade():
    """Add usage tracking columns to node_templates table"""
    # Add last_used_by_atharva_at column (nullable timestamp)
    op.add_column('node_templates',
        sa.Column('last_used_by_atharva_at', sa.DateTime(), nullable=True)
    )

    # Add atharva_rankings_count column (integer with default 0)
    op.add_column('node_templates',
        sa.Column('atharva_rankings_count', sa.Integer(), server_default='0', nullable=False)
    )


def downgrade():
    """Remove usage tracking columns from node_templates table"""
    op.drop_column('node_templates', 'atharva_rankings_count')
    op.drop_column('node_templates', 'last_used_by_atharva_at')
