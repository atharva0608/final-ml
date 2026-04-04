"""
Add optimizer_proposals table

Revision ID: 20260309_optimizer_proposals
Revises: 20260309_spot_advisor_rates
Create Date: 2026-03-09
"""
from alembic import op
import sqlalchemy as sa

revision = '20260309_optimizer_proposals'
down_revision = '20260309_spot_advisor_rates'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create enum type only if it doesn't already exist
    op.execute("DO $$ BEGIN CREATE TYPE proposalstatus AS ENUM ('PENDING', 'APPROVED', 'REJECTED', 'EXECUTED'); EXCEPTION WHEN duplicate_object THEN NULL; END $$;")

    # Create table only if it doesn't already exist
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if 'optimizer_proposals' not in inspector.get_table_names():
        op.create_table(
            'optimizer_proposals',
            sa.Column('id', sa.String(36), primary_key=True),
            sa.Column('cluster_id', sa.String(36), nullable=False, index=True),
            sa.Column('node_name', sa.String(255), nullable=True),
            sa.Column('current_instance_type', sa.String(50), nullable=True),
            sa.Column('proposed_instance_type', sa.String(50), nullable=True),
            sa.Column('proposed_az', sa.String(50), nullable=True),
            sa.Column('estimated_savings', sa.Float, nullable=True),
            sa.Column('risk_delta', sa.Float, nullable=True),
            sa.Column('status', sa.Enum('PENDING', 'APPROVED', 'REJECTED', 'EXECUTED',
                                        name='proposalstatus', create_type=False), nullable=True),
            sa.Column('created_at', sa.DateTime, nullable=True),
            sa.Column('executed_at', sa.DateTime, nullable=True),
        )


def downgrade() -> None:
    op.drop_table('optimizer_proposals')
    op.execute("DROP TYPE IF EXISTS proposalstatus")
