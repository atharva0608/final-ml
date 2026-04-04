"""Add max_family_diversification_cap_pct

Revision ID: 421d795851e5
Revises: 20260311_add_force_delete_node_action
Create Date: 2026-03-11 12:43:08.761560

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '421d795851e5'
down_revision = '20260311_add_force_delete_node_action'
branch_labels = None
depends_on = None

def upgrade() -> None:
    op.add_column('cluster_optimization_settings', sa.Column('max_family_diversification_cap_pct', sa.Integer(), nullable=True))

def downgrade() -> None:
    op.drop_column('cluster_optimization_settings', 'max_family_diversification_cap_pct')
