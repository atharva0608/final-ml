"""Add account_id to instances table for standalone instance support

Revision ID: 20260212_instance_account
Revises: 20260210_hib_strategies
Create Date: 2026-02-12
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers
revision = '20260212_instance_account'
down_revision = '20260210_hib_strategies'
branch_labels = None
depends_on = None


def upgrade():
    # Add account_id column to instances table (nullable initially)
    op.add_column('instances',
        sa.Column('account_id', sa.String(36), nullable=True))

    # Backfill account_id from cluster relationship for existing instances
    op.execute("""
        UPDATE instances i
        SET account_id = c.account_id
        FROM clusters c
        WHERE i.cluster_id = c.id
        AND i.account_id IS NULL
    """)

    # Add foreign key constraint
    op.create_foreign_key(
        'instances_account_id_fkey',
        'instances', 'accounts',
        ['account_id'], ['id'],
        ondelete='CASCADE'
    )

    # Add index for performance
    op.create_index('ix_instances_account_id', 'instances', ['account_id'])

    # Add composite index for common queries
    op.create_index('idx_account_state', 'instances', ['account_id', 'state'])


def downgrade():
    # Drop indexes
    op.drop_index('idx_account_state', 'instances')
    op.drop_index('ix_instances_account_id', 'instances')

    # Drop foreign key
    op.drop_constraint('instances_account_id_fkey', 'instances', type_='foreignkey')

    # Drop column
    op.drop_column('instances', 'account_id')
