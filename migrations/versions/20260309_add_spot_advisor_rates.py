"""
Add spot_advisor_rates table

Revision ID: 20260309_spot_advisor_rates
Revises: 002
Create Date: 2026-03-09
"""
from alembic import op
import sqlalchemy as sa

revision = '20260309_spot_advisor_rates'
down_revision = 'eb03c09e15a1'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'spot_advisor_rates',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('region', sa.String(20), nullable=False, index=True),
        sa.Column('instance_type', sa.String(50), nullable=False, index=True),
        sa.Column('interruption_rate_category', sa.String(10), nullable=True),
        sa.Column('interruption_rate_pct', sa.Float, nullable=False),
        sa.Column('scraped_at', sa.DateTime, nullable=True),
        sa.Column('valid_from', sa.Date, nullable=False),
        sa.UniqueConstraint('region', 'instance_type', 'valid_from', name='uq_spot_advisor_rates'),
    )


def downgrade() -> None:
    op.drop_table('spot_advisor_rates')
