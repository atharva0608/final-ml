"""Add Cost Explorer tables for AWS billing data

Revision ID: 20260210_cost_explorer
Revises:
Create Date: 2026-02-10

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '20260210_cost_explorer'
down_revision = '20260212_instance_account'
branch_labels = None
depends_on = None


def upgrade():
    """
    Create tables for AWS Cost Explorer data caching.

    - daily_costs: Stores daily cost data grouped by service
    - cost_explorer_sync_status: Tracks sync health and last fetch timestamps
    """

    # Create daily_costs table
    op.create_table(
        'daily_costs',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('account_id', sa.String(), nullable=False),
        sa.Column('date', sa.Date(), nullable=False),
        sa.Column('service_name', sa.String(), nullable=False),
        sa.Column('cost_amount', sa.Float(), nullable=False, server_default='0.0'),
        sa.Column('currency', sa.String(), nullable=False, server_default='USD'),
        sa.Column('cost_type', sa.String(), nullable=False, server_default='Usage'),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('now()')),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['account_id'], ['accounts.id'], ondelete='CASCADE'),
    )

    # Create indexes for common queries
    op.create_index('ix_daily_costs_account_id', 'daily_costs', ['account_id'])
    op.create_index('ix_daily_costs_date', 'daily_costs', ['date'])
    op.create_index('ix_daily_costs_service_name', 'daily_costs', ['service_name'])
    op.create_index('idx_account_date', 'daily_costs', ['account_id', 'date'])
    op.create_index('idx_date_service', 'daily_costs', ['date', 'service_name'])
    op.create_index('idx_account_date_service', 'daily_costs', ['account_id', 'date', 'service_name'])

    # Create cost_explorer_sync_status table
    op.create_table(
        'cost_explorer_sync_status',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('account_id', sa.String(), nullable=False),
        sa.Column('last_sync_at', sa.DateTime(), nullable=False),
        sa.Column('last_synced_date', sa.Date(), nullable=False),
        sa.Column('status', sa.String(), nullable=False, server_default='SUCCESS'),
        sa.Column('error_message', sa.String(), nullable=True),
        sa.Column('records_synced', sa.Float(), nullable=False, server_default='0'),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('now()')),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['account_id'], ['accounts.id'], ondelete='CASCADE'),
        sa.UniqueConstraint('account_id'),
    )


def downgrade():
    """
    Drop Cost Explorer tables.
    """
    op.drop_table('cost_explorer_sync_status')
    op.drop_index('idx_account_date_service', 'daily_costs')
    op.drop_index('idx_date_service', 'daily_costs')
    op.drop_index('idx_account_date', 'daily_costs')
    op.drop_index('ix_daily_costs_service_name', 'daily_costs')
    op.drop_index('ix_daily_costs_date', 'daily_costs')
    op.drop_index('ix_daily_costs_account_id', 'daily_costs')
    op.drop_table('daily_costs')
