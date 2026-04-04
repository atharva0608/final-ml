"""Add karpenter migration columns

Revision ID: 20260401_add_karpenter_migration_columns
Revises: 20260330_add_attach_to_asg_enabled
Create Date: 2026-04-01

Adds managed_node_group_deleted flag to clusters table and
karpenter_only_mode flag to cluster_optimization_settings table
to support hybrid-to-Karpenter migration workflow.
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers
revision = "20260401_add_karpenter_migration_columns"
down_revision = "20260330_add_attach_to_asg_enabled"
branch_labels = None
depends_on = None


def upgrade():
    # Add rebalance_batch_percent (was missing from previous migrations)
    op.add_column(
        "cluster_optimization_settings",
        sa.Column(
            "rebalance_batch_percent",
            sa.Integer(),
            nullable=True,
        ),
    )
    op.add_column(
        "clusters",
        sa.Column(
            "managed_node_group_deleted",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )
    op.add_column(
        "cluster_optimization_settings",
        sa.Column(
            "karpenter_only_mode",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )


def downgrade():
    op.drop_column("cluster_optimization_settings", "karpenter_only_mode")
    op.drop_column("clusters", "managed_node_group_deleted")
    op.drop_column("cluster_optimization_settings", "rebalance_batch_percent")
