"""Rename tickets table to approvals

Revision ID: 20260210_rename
Revises: 20260130_1200_fix_tag_templates
Create Date: 2026-02-10
"""
from alembic import op

# revision identifiers
revision = '20260210_rename'
down_revision = '20260130_1200_fix_tag_templates'
branch_labels = None
depends_on = None


def upgrade():
    # Rename tickets table to approvals
    op.rename_table('tickets', 'approvals')

    # Update foreign key self-reference (parent_id)
    # The FK constraint name may vary; using generic approach
    try:
        op.drop_constraint('tickets_parent_id_fkey', 'approvals', type_='foreignkey')
        op.create_foreign_key('approvals_parent_id_fkey', 'approvals', 'approvals', ['parent_id'], ['id'])
    except Exception:
        pass  # Constraint may not exist or have different name


def downgrade():
    # Rename approvals table back to tickets
    op.rename_table('approvals', 'tickets')

    try:
        op.drop_constraint('approvals_parent_id_fkey', 'tickets', type_='foreignkey')
        op.create_foreign_key('tickets_parent_id_fkey', 'tickets', 'tickets', ['parent_id'], ['id'])
    except Exception:
        pass
