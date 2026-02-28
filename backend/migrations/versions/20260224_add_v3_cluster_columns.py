"""add v3 cluster columns

Revision ID: 20260224_add_v3_cluster_cols
Revises: 20260220_add_hibernation
Create Date: 2026-02-24 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '20260224_add_v3_cluster_cols'
down_revision = '20260220_add_hibernation'
branch_labels = None
depends_on = None

def upgrade():
    # Add columns with server_default for existing rows
    op.add_column('clusters', sa.Column('optimization_mode', sa.String(length=20), server_default='BALANCED', nullable=True))
    op.add_column('clusters', sa.Column('model_version', sa.String(length=10), server_default='6', nullable=True))
    op.add_column('clusters', sa.Column('workload_type', sa.String(length=10), server_default='STATELESS', nullable=True))

    # set existing nulls explicitly just to be safe
    op.execute("UPDATE clusters SET optimization_mode = 'BALANCED' WHERE optimization_mode IS NULL")
    op.execute("UPDATE clusters SET model_version = '6' WHERE model_version IS NULL")
    op.execute("UPDATE clusters SET workload_type = 'STATELESS' WHERE workload_type IS NULL")

    # alter nullable=False where appropriate
    op.alter_column('clusters', 'optimization_mode', nullable=False, server_default='BALANCED')
    op.alter_column('clusters', 'workload_type', nullable=False, server_default='STATELESS')

def downgrade():
    op.drop_column('clusters', 'workload_type')
    op.drop_column('clusters', 'model_version')
    op.drop_column('clusters', 'optimization_mode')
