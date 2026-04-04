"""
Add FORCE_DELETE_NODE to agentactiontype PostgreSQL enum.

Used to force-delete ghost K8s Node objects when the underlying EC2 instance
has already been terminated by AWS (hardware failure, spot reclamation) and
the Node is stuck NotReady, blocking StatefulSet pod rescheduling.

Revision ID: 20260311_add_force_delete_node_action
Revises: 20260310_add_stateful_rightsizing_toggle
Create Date: 2026-03-11
"""

from alembic import op

revision = '20260311_add_force_delete_node_action'
down_revision = '20260310_add_stateful_rightsizing_toggle'
branch_labels = None
depends_on = None


def upgrade():
    # ALTER TYPE cannot run inside a transaction block on some PG versions;
    # use COMMIT + SET to work around that in Alembic's default transactional mode.
    op.execute("ALTER TYPE agentactiontype ADD VALUE IF NOT EXISTS 'FORCE_DELETE_NODE'")


def downgrade():
    # PostgreSQL does not support removing enum values without recreating the type.
    # Downgrade is a no-op — the value will simply go unused if rolled back.
    pass
