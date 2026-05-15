"""C2: add severity breakdown columns to adaptive_itn_ledger

Revision ID: 20260410_adaptive_itn_severity
Revises: 20260409_adaptive_itn
Create Date: 2026-04-10
"""

from alembic import op
import sqlalchemy as sa

revision = "20260410_adaptive_itn_severity"
down_revision = "20260409_adaptive_itn"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "adaptive_itn_ledger",
        sa.Column("itn_warning_count", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "adaptive_itn_ledger",
        sa.Column("actual_termination_count", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "adaptive_itn_ledger",
        sa.Column("rebalance_notice_count", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "adaptive_itn_ledger",
        sa.Column("peak_simultaneous_itn", sa.Integer(), nullable=False, server_default="0"),
    )


def downgrade():
    op.drop_column("adaptive_itn_ledger", "peak_simultaneous_itn")
    op.drop_column("adaptive_itn_ledger", "rebalance_notice_count")
    op.drop_column("adaptive_itn_ledger", "actual_termination_count")
    op.drop_column("adaptive_itn_ledger", "itn_warning_count")
