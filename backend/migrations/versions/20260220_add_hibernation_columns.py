"""add hibernation columns to clusters

Revision ID: 20260220_add_hibernation
Revises: 20260216_schedule_type, 20260216_pod_metrics
Create Date: 2026-02-20 13:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '20260220_add_hibernation'
down_revision = ('20260216_schedule_type', '20260216_pod_metrics')
branch_labels = None
depends_on = None


def upgrade():
    # Add hibernation state tracking columns to clusters table
    op.add_column('clusters', sa.Column('is_hibernating', sa.Boolean(), nullable=True, server_default='false'))
    op.add_column('clusters', sa.Column('hibernation_state', postgresql.JSON(astext_type=sa.Text()), nullable=True))
    op.add_column('clusters', sa.Column('hibernation_lock', sa.String(length=255), nullable=True))
    op.add_column('clusters', sa.Column('hibernation_lock_acquired_at', sa.DateTime(), nullable=True))

    # Update existing rows to have is_hibernating = false
    op.execute("UPDATE clusters SET is_hibernating = false WHERE is_hibernating IS NULL")

    # Make is_hibernating non-nullable after setting defaults
    op.alter_column('clusters', 'is_hibernating', nullable=False, server_default='false')


def downgrade():
    # Remove hibernation columns
    op.drop_column('clusters', 'hibernation_lock_acquired_at')
    op.drop_column('clusters', 'hibernation_lock')
    op.drop_column('clusters', 'hibernation_state')
    op.drop_column('clusters', 'is_hibernating')
