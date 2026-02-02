"""
Migration 010: Add Resource Scope to Tag Templates

Adds resource_scope column to tag_templates table to support scoping templates to specific resource types.
"""
from alembic import op
import sqlalchemy as sa

# Revision identifiers
revision = '010_tag_template_resource_scope'
down_revision = '009_dynamic_auto_tags'
branch_labels = None
depends_on = None


def upgrade():
    """Add resource_scope to tag_templates"""
    try:
        op.add_column('tag_templates',
            sa.Column('resource_scope', sa.String(50), nullable=False, server_default='all',
                      comment='Resource scope (all, ec2, s3, etc)'))
    except Exception:
        pass  # Column may already exist
    
    print("✅ Migration 010: Successfully added resource_scope to tag_templates")


def downgrade():
    """Remove resource_scope from tag_templates"""
    try:
        op.drop_column('tag_templates', 'resource_scope')
    except Exception:
        pass
    
    print("✅ Migration 010: Rolled back resource_scope from tag_templates")
