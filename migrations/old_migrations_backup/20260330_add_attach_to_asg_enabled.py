"""Add attach_to_asg_enabled to cluster_optimization_settings

Revision ID: 20260330_add_attach_to_asg_enabled
Revises: 20260328_drop_unused_settings_columns
Create Date: 2026-03-30

Adds a CAST-like attach-to-ASG mode flag.  When enabled the replacement Spot
instance is attached to the source ASG after joining Kubernetes and the source
OD node is terminated with ShouldDecrementDesiredCapacity=False.
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers
revision = "20260330_add_attach_to_asg_enabled"
down_revision = "drop_unused_settings_columns"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "cluster_optimization_settings",
        sa.Column(
            "attach_to_asg_enabled",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )


def downgrade():
    op.drop_column("cluster_optimization_settings", "attach_to_asg_enabled")
