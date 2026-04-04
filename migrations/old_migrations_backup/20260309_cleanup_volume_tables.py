"""
Cleanup volume tables (volume_metrics, volume_recommendations)

Revision ID: 20260309_cleanup_volume_tables
Revises: 20260309_substitute_nodes
Create Date: 2026-03-09
"""
from alembic import op

revision = '20260309_cleanup_volume_tables'
down_revision = '20260309_substitute_nodes'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("DROP TABLE IF EXISTS volume_metrics CASCADE")
    op.execute("DROP TABLE IF EXISTS volume_recommendations CASCADE")


def downgrade() -> None:
    # Tables not restored in downgrade — they were legacy tables
    pass
