"""add retry_count to agent_actions

Revision ID: 013_agent_actions_retry_fields
Revises: 012_rebalancing_actions_pod_level
Create Date: 2026-04-23 13:01:00.000000

Adds:
  - retry_count (SMALLINT DEFAULT 0 NOT NULL) — incremented each time a post-eviction
    validation finds the pod on the wrong capacity type or Pending.
    Hard-stops at MAX_RETRY_COUNT=3 (placement_controller_service.py).

Existing rows get default value 0 — no backfill needed.
"""
from alembic import op
import sqlalchemy as sa


revision = '013_agent_actions_retry_fields'
down_revision = '012_rebalancing_actions_pod_level'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "agent_actions",
        sa.Column("retry_count", sa.SmallInteger(), nullable=False, server_default="0"),
    )


def downgrade():
    op.drop_column("agent_actions", "retry_count")
