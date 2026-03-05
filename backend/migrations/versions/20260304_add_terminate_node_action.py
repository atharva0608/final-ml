"""add TERMINATE_NODE to agentactiontype enum

Revision ID: 20260304_terminate_node
Revises: (run after latest head — merge if needed)
Create Date: 2026-03-04

Why: auto_rebalancer now queues a TERMINATE_NODE action between DRAIN_NODE and
PATCH_KARPENTER_NODEPOOL. Without this step, drained pods reschedule onto other
on-demand nodes rather than going Pending, so Karpenter never provisions spot
replacements. Terminating the EC2 instance causes Kubernetes to remove the node
object, pods go Pending, and Karpenter provisions a new spot node.
"""

from alembic import op


# revision identifiers
revision = '20260304_terminate_node'
down_revision = '20260304_patch_container'  # chain after the previous migration
branch_labels = None
depends_on = None


def upgrade():
    op.execute(
        "ALTER TYPE agentactiontype ADD VALUE IF NOT EXISTS 'TERMINATE_NODE'"
    )


def downgrade():
    # PostgreSQL does not support removing enum values natively.
    # To remove manually:
    #   CREATE TYPE agentactiontype_new AS ENUM (...all values except TERMINATE_NODE...);
    #   ALTER TABLE agent_actions ALTER COLUMN action_type TYPE agentactiontype_new
    #       USING action_type::text::agentactiontype_new;
    #   DROP TYPE agentactiontype;
    #   ALTER TYPE agentactiontype_new RENAME TO agentactiontype;
    pass
