"""add pod-level visibility columns to rebalancing_actions

Revision ID: 012_rebalancing_actions_pod_level
Revises: 011_add_wie_v44_fields
Create Date: 2026-04-23 13:00:00.000000

Adds three columns to rebalancing_actions:
  - migration_type: 'node_level' (default, existing rows) or 'pod_level' / 'stateful_pod' (PlacementController)
  - source: 'auto_rebalancer' (default) or 'placement_controller'
  - agent_action_id: nullable FK to agent_actions.id — links a pod-level eviction record back to the
    AgentAction that executes it. NULL for node-level migrations (no AgentAction involved).

Existing rows keep defaults (node_level / auto_rebalancer) — no backfill needed.
"""
from alembic import op
import sqlalchemy as sa


revision = '012_rebalancing_actions_pod_level'
down_revision = '011_add_wie_v44_fields'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "rebalancing_actions",
        sa.Column("migration_type", sa.String(20), nullable=False, server_default="node_level"),
    )
    op.add_column(
        "rebalancing_actions",
        sa.Column("source", sa.String(30), nullable=False, server_default="auto_rebalancer"),
    )
    op.add_column(
        "rebalancing_actions",
        sa.Column(
            "agent_action_id",
            sa.String(36),
            sa.ForeignKey("agent_actions.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.create_index(
        "idx_rebalancing_actions_source",
        "rebalancing_actions",
        ["source"],
    )
    op.create_index(
        "idx_rebalancing_actions_migration_type",
        "rebalancing_actions",
        ["migration_type"],
    )
    op.create_index(
        "idx_rebalancing_actions_agent_action_id",
        "rebalancing_actions",
        ["agent_action_id"],
    )


def downgrade():
    op.drop_index("idx_rebalancing_actions_agent_action_id", "rebalancing_actions")
    op.drop_index("idx_rebalancing_actions_migration_type", "rebalancing_actions")
    op.drop_index("idx_rebalancing_actions_source", "rebalancing_actions")
    op.drop_column("rebalancing_actions", "agent_action_id")
    op.drop_column("rebalancing_actions", "source")
    op.drop_column("rebalancing_actions", "migration_type")
