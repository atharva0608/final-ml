"""Normalize agent_actions.action_type to UPPERCASE

Revision ID: 20260305_normalize_action_type
Revises: 20260304_terminate_node
Create Date: 2026-03-05

Why: FIX-ENUM-01 — AgentActionType enum values are UPPERCASE. The actuator
dispatch now normalizes to .upper() at the boundary. This migration ensures any
existing DB rows with lowercase action_type values are uppercased so queries
and joins work correctly regardless of when rows were written.

Also adds a check constraint to prevent mixed-case inserts going forward.
"""

from alembic import op
import sqlalchemy as sa


revision = '20260305_normalize_action_type'
down_revision = '20260304_terminate_node'
branch_labels = None
depends_on = None


def upgrade():
    # Step 1: Upper-case any existing lowercase values in agent_actions
    # (safe for both PostgreSQL and SQLite test environments)
    op.execute(
        "UPDATE agent_actions "
        "SET action_type = UPPER(action_type::text)::agentactiontype "
        "WHERE action_type::text != UPPER(action_type::text)"
    )

    # Step 2: Add check constraint to prevent future mixed-case inserts.
    # PostgreSQL enum values are already case-sensitive, so this is belt-and-suspenders.
    op.execute(
        "ALTER TABLE agent_actions "
        "ADD CONSTRAINT IF NOT EXISTS chk_action_type_uppercase "
        "CHECK (action_type::text = UPPER(action_type::text))"
    )


def downgrade():
    op.execute(
        "ALTER TABLE agent_actions "
        "DROP CONSTRAINT IF EXISTS chk_action_type_uppercase"
    )
