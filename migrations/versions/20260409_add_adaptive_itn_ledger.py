"""add adaptive_itn_ledger table

Revision ID: 20260409_adaptive_itn
Revises: 20260409_action_step
Create Date: 2026-04-09
"""

from alembic import op
import sqlalchemy as sa

revision = "20260409_adaptive_itn"
down_revision = "20260409_action_step"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "adaptive_itn_ledger",
        sa.Column("pool_key", sa.String(200), primary_key=True, nullable=False),
        sa.Column("node_hours_observed", sa.Float(), nullable=False, server_default="0"),
        sa.Column("interruption_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("raw_itn_score", sa.Float(), nullable=False, server_default="0"),
        sa.Column("confidence", sa.Float(), nullable=False, server_default="0"),
        sa.Column("last_interruption_ts", sa.DateTime(), nullable=True),
        sa.Column(
            "last_updated",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
    )
    op.create_index(
        "ix_adaptive_itn_ledger_pool_key",
        "adaptive_itn_ledger",
        ["pool_key"],
    )
    op.create_index(
        "ix_adaptive_itn_ledger_last_updated",
        "adaptive_itn_ledger",
        ["last_updated"],
    )


def downgrade():
    op.drop_index("ix_adaptive_itn_ledger_last_updated", table_name="adaptive_itn_ledger")
    op.drop_index("ix_adaptive_itn_ledger_pool_key", table_name="adaptive_itn_ledger")
    op.drop_table("adaptive_itn_ledger")
