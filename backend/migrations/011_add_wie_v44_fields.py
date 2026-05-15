"""add WIE v4.4 placement intent fields

Revision ID: 011_add_wie_v44_fields
Revises: 010_add_placement_policies
Create Date: 2026-04-22 16:14:00.000000

Adds two Boolean columns to workload_classifications:
  - az_spread_required: True when workload must be spread across >= 2 AZs
  - disruption_safe:    True when it is safe to remove one pod right now

Both default to false for existing rows (safe, conservative default).
"""
from alembic import op
import sqlalchemy as sa

revision = '011_add_wie_v44_fields'
down_revision = '010_add_placement_policies'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "workload_classifications",
        sa.Column("az_spread_required", sa.Boolean(), nullable=False, server_default="false"),
    )
    op.add_column(
        "workload_classifications",
        sa.Column("disruption_safe", sa.Boolean(), nullable=False, server_default="false"),
    )


def downgrade():
    op.drop_column("workload_classifications", "az_spread_required")
    op.drop_column("workload_classifications", "disruption_safe")
