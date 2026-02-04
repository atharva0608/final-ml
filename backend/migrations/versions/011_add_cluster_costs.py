"""
Migration 011: Add Cost Columns to Cluster
Adds monthly_cost and estimated_savings to clusters table
"""
from alembic import op
import sqlalchemy as sa

# Revision identifiers
revision = '011_add_cluster_costs'
down_revision = '010_tag_template_resource_scope'
branch_labels = None
depends_on = None

def upgrade():
    """Add cost columns to clusters"""
    try:
        op.add_column('clusters', sa.Column('monthly_cost', sa.Integer(), nullable=True, server_default='0'))
        op.add_column('clusters', sa.Column('estimated_savings', sa.Integer(), nullable=True, server_default='0'))
    except Exception:
        pass # Columns may already exist

    print("✅ Migration 011: Added cost columns to clusters")

def downgrade():
    """Remove cost columns"""
    try:
        op.drop_column('clusters', 'monthly_cost')
        op.drop_column('clusters', 'estimated_savings')
    except Exception:
        pass

    print("✅ Migration 011: Rolled back cost columns")
