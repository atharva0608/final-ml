"""Add execution_manifests, execution_overrides, placement_policy

Revision ID: 014_execution_tables
Revises: 013_agent_actions_retry_fields
Create Date: 2026-05-04 12:00:00.000000

Creates:
  - execution_manifests  — DB-primary manifest store (Problems 2, 3, 22, 29)
  - execution_overrides  — append-only mid-run field overrides (Problems 16, 17, 26)
  - clusters.placement_policy — JSONB column for per-cluster ISS policy (Problems 10, 15)
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = '014_execution_tables'
down_revision = '013_agent_actions_retry_fields'
branch_labels = None
depends_on = None


def upgrade():
    # ── execution_manifests ──────────────────────────────────────────────────
    op.create_table(
        "execution_manifests",
        sa.Column("manifest_id",    sa.String(64),  nullable=False, primary_key=True),
        sa.Column("cluster_id",     sa.String(36),  nullable=False),
        sa.Column("status",         sa.String(20),  nullable=False, server_default="READY"),
        sa.Column("payload",        postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at",     sa.DateTime(),  nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at",     sa.DateTime(),  nullable=False, server_default=sa.func.now()),
        sa.Column("expires_at",     sa.DateTime(),  nullable=True),
        sa.Column("last_heartbeat", sa.DateTime(),  nullable=True),
        sa.Column("error_message",  sa.Text(),      nullable=True),
        sa.Column("resume_index",   sa.Integer(),   nullable=False, server_default="0"),
    )
    op.create_index("idx_em_cluster_status", "execution_manifests", ["cluster_id", "status"])
    op.create_index("idx_em_status",         "execution_manifests", ["status"])
    op.create_index("idx_em_cluster_id",     "execution_manifests", ["cluster_id"])

    # ── execution_overrides ──────────────────────────────────────────────────
    op.create_table(
        "execution_overrides",
        sa.Column("id",             sa.Integer(),   primary_key=True, autoincrement=True),
        sa.Column("manifest_id",    sa.String(64),  nullable=False),
        sa.Column("node_name",      sa.String(256), nullable=False),
        sa.Column("field",          sa.String(64),  nullable=False),
        sa.Column("original_value", sa.Text(),      nullable=True),
        sa.Column("override_value", sa.Text(),      nullable=False),
        sa.Column("reason",         sa.String(128), nullable=False),
        sa.Column("attempt_number", sa.Integer(),   nullable=False, server_default="0"),
        sa.Column("created_at",     sa.DateTime(),  nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(
            ["manifest_id"],
            ["execution_manifests.manifest_id"],
            ondelete="CASCADE",
        ),
    )
    op.create_index("idx_eo_manifest_node", "execution_overrides", ["manifest_id", "node_name"])
    op.create_index("idx_eo_manifest_id",   "execution_overrides", ["manifest_id"])

    # ── clusters.placement_policy ────────────────────────────────────────────
    # JSONB column for per-cluster InstanceSelectionService policy.
    # Schema: {"cost_strategy": "balanced", "risk_threshold": 0.30,
    #          "workload_overrides": {"stateful": {...}, "stateless": {...}}}
    op.add_column(
        "clusters",
        sa.Column(
            "placement_policy",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
            server_default=None,
        ),
    )


def downgrade():
    op.drop_column("clusters", "placement_policy")
    op.drop_index("idx_eo_manifest_id",   "execution_overrides")
    op.drop_index("idx_eo_manifest_node", "execution_overrides")
    op.drop_table("execution_overrides")
    op.drop_index("idx_em_cluster_id",    "execution_manifests")
    op.drop_index("idx_em_status",        "execution_manifests")
    op.drop_index("idx_em_cluster_status","execution_manifests")
    op.drop_table("execution_manifests")
