"""Add schedule_type and date_overrides for monthly scheduling

Revision ID: 20260216_schedule_type
Revises: previous_revision
Create Date: 2026-02-16 19:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '20260216_schedule_type'
down_revision = '20260210_cost_explorer'  # Chain from latest migration
branch_labels = None
depends_on = None


def upgrade():
    # Add schedule_type column
    op.add_column('hibernation_schedules',
        sa.Column('schedule_type', sa.String(20), server_default='WEEKLY', nullable=False)
    )

    # Change schedule_matrix from String(168) to Text to support larger matrices
    op.alter_column('hibernation_schedules', 'schedule_matrix',
        existing_type=sa.String(168),
        type_=sa.Text(),
        existing_nullable=False
    )

    # Add date_overrides column for HYBRID mode
    op.add_column('hibernation_schedules',
        sa.Column('date_overrides', postgresql.JSON(astext_type=sa.Text()), server_default='{}', nullable=True)
    )


def downgrade():
    # Remove date_overrides column
    op.drop_column('hibernation_schedules', 'date_overrides')

    # Revert schedule_matrix back to String(168)
    op.alter_column('hibernation_schedules', 'schedule_matrix',
        existing_type=sa.Text(),
        type_=sa.String(168),
        existing_nullable=False
    )

    # Remove schedule_type column
    op.drop_column('hibernation_schedules', 'schedule_type')
