"""add PATCH_CONTAINER_RESOURCES to agentactiontype enum

Revision ID: 20260304_patch_container
Revises: (run after latest head — merge if needed)
Create Date: 2026-03-04

Why: Right-sizing now generates PATCH_CONTAINER_RESOURCES AgentActions to
update Deployment/StatefulSet container CPU/memory requests+limits directly,
complementing the existing PATCH_KARPENTER_NODEPOOL for node-level changes.
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers
revision = '20260304_patch_container'
down_revision = None   # Set to previous revision ID after merge if needed
branch_labels = None
depends_on = None


def upgrade():
    # PostgreSQL requires a transaction-safe ALTER TYPE ... ADD VALUE
    # Using execute() with COMMIT not needed in Alembic — it handles DDL transactions.
    op.execute(
        "ALTER TYPE agentactiontype ADD VALUE IF NOT EXISTS 'PATCH_CONTAINER_RESOURCES'"
    )


def downgrade():
    # PostgreSQL does not support removing enum values natively (would require
    # recreating the type).  Mark as no-op and document manual steps if needed.
    # To remove: CREATE TYPE agentactiontype_new AS ENUM (...all values except PATCH_CONTAINER_RESOURCES...);
    #            ALTER TABLE agent_actions ALTER COLUMN action_type TYPE agentactiontype_new USING action_type::text::agentactiontype_new;
    #            DROP TYPE agentactiontype;
    #            ALTER TYPE agentactiontype_new RENAME TO agentactiontype;
    pass
