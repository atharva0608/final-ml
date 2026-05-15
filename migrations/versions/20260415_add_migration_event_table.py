"""Add migration_event table for §15 stateful migration status tracking.

Revision ID: 20260415_add_migration_event
Revises: 20260410_adaptive_itn_severity
Create Date: 2026-04-15
"""

from alembic import op
import sqlalchemy as sa

revision = "20260415_add_migration_event"
down_revision = "20260410_adaptive_itn_severity"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "migration_event",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("cluster_id", sa.Integer(), nullable=False),
        sa.Column("namespace", sa.String(255), nullable=False),
        sa.Column("controller_name", sa.String(255), nullable=False),
        sa.Column("controller_kind", sa.String(50), nullable=False),
        sa.Column("workload_tier", sa.SmallInteger(), nullable=True),
        sa.Column("source_node", sa.String(255), nullable=True),
        sa.Column("target_node", sa.String(255), nullable=True),
        sa.Column("state", sa.String(50), nullable=False),
        sa.Column("failure_reason", sa.Text(), nullable=True),
        sa.Column("pod_location", sa.String(50), nullable=True),
        sa.Column("freeze_restored", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "idx_migration_event_cluster",
        "migration_event",
        ["cluster_id", "created_at"],
    )
    op.create_index(
        "idx_migration_event_state",
        "migration_event",
        ["state"],
    )


def downgrade():
    op.drop_index("idx_migration_event_state", table_name="migration_event")
    op.drop_index("idx_migration_event_cluster", table_name="migration_event")
    op.drop_table("migration_event")
