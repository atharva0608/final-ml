"""Add cluster_uid unique display ID to clusters

Revision ID: 20260403_add_cluster_uid
Revises: 20260330_add_attach_to_asg_enabled
Create Date: 2026-04-03

Adds a short 8-char hex unique ID to each cluster for human-readable
identification. Differentiates clusters with the same name and assists
with re-discovery.
"""

from alembic import op
import sqlalchemy as sa
import uuid


# revision identifiers
revision = "20260403_add_cluster_uid"
down_revision = "20260401_add_karpenter_migration_columns"
branch_labels = None
depends_on = None


def upgrade():
    # Add column (nullable first so we can backfill)
    op.add_column(
        "clusters",
        sa.Column("cluster_uid", sa.String(8), nullable=True),
    )

    # Backfill existing rows with unique 8-char hex IDs
    conn = op.get_bind()
    rows = conn.execute(sa.text("SELECT id FROM clusters WHERE cluster_uid IS NULL")).fetchall()
    for row in rows:
        uid = uuid.uuid4().hex[:8]
        conn.execute(
            sa.text("UPDATE clusters SET cluster_uid = :uid WHERE id = :id"),
            {"uid": uid, "id": row[0]},
        )

    # Now make it non-nullable and unique
    op.alter_column("clusters", "cluster_uid", nullable=False)
    op.create_unique_constraint("uq_clusters_cluster_uid", "clusters", ["cluster_uid"])
    op.create_index("ix_clusters_cluster_uid", "clusters", ["cluster_uid"])


def downgrade():
    op.drop_index("ix_clusters_cluster_uid", table_name="clusters")
    op.drop_constraint("uq_clusters_cluster_uid", "clusters", type_="unique")
    op.drop_column("clusters", "cluster_uid")
