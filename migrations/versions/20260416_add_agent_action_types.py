"""Add new AgentActionType enum values for KEDA install/uninstall and workload patching.

Adds: INSTALL_KEDA, UNINSTALL_KEDA, ANNOTATE_WORKLOAD, PATCH_AFFINITY

PostgreSQL ALTER TYPE … ADD VALUE is safe in PostgreSQL 9.1+ and cannot be
run inside a transaction — Alembic handles this automatically because of
execute_if() / non-transactional DDL.

Revision ID: 20260416_add_agent_action_types
Revises: 20260415_add_migration_event
Create Date: 2026-04-16
"""

from alembic import op

revision = "20260416_add_agent_action_types"
down_revision = "20260415_add_migration_event"
branch_labels = None
depends_on = None


def upgrade():
    # IF NOT EXISTS prevents errors on repeated runs / already-migrated DBs
    op.execute("ALTER TYPE agentactiontype ADD VALUE IF NOT EXISTS 'INSTALL_KEDA'")
    op.execute("ALTER TYPE agentactiontype ADD VALUE IF NOT EXISTS 'UNINSTALL_KEDA'")
    op.execute("ALTER TYPE agentactiontype ADD VALUE IF NOT EXISTS 'ANNOTATE_WORKLOAD'")
    op.execute("ALTER TYPE agentactiontype ADD VALUE IF NOT EXISTS 'PATCH_AFFINITY'")


def downgrade():
    # PostgreSQL does not support removing enum values — downgrade is intentionally a no-op.
    # To fully revert, drop the type and recreate it without these values (requires no rows
    # in agent_actions that use them).
    pass
