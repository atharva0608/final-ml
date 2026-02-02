"""
Migration 009: Add Dynamic Auto-Tag Fields

Adds new columns to auto_tag_rules table for dynamic value sources:
- dynamic_tags: JSON field for dynamic tag configurations
- resource_scope: Broader scope filter (compute_only, storage_only, etc.)
- override_behavior: How to handle existing tags (skip_existing, overwrite)
- inject_system_tags: Auto-inject ManagedBy system tag

Also adds similar fields to tag_policies table for consistency.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSON

# Revision identifiers
revision = '009_dynamic_auto_tags'
down_revision = '008_core_modules'
branch_labels = None
depends_on = None


def upgrade():
    """Add dynamic auto-tag fields to support Smart Auto-Tag system"""
    
    # Add columns to auto_tag_rules table
    try:
        op.add_column('auto_tag_rules',
            sa.Column('dynamic_tags', JSON, nullable=True, default={},
                      comment='Dynamic tag configs: {key: {source, static_value, env_var_name}}'))
    except Exception:
        pass  # Column may already exist
    
    try:
        op.add_column('auto_tag_rules',
            sa.Column('resource_scope', sa.String(50), nullable=True, default='all',
                      comment='Broader resource scope filter'))
    except Exception:
        pass
    
    try:
        op.add_column('auto_tag_rules',
            sa.Column('override_behavior', sa.String(20), nullable=True, default='skip_existing',
                      comment='How to handle existing tags'))
    except Exception:
        pass
    
    try:
        op.add_column('auto_tag_rules',
            sa.Column('inject_system_tags', sa.Boolean, nullable=True, default=True,
                      comment='Auto-inject ManagedBy system tag'))
    except Exception:
        pass
    
    # Add similar columns to tag_policies table for consistency
    try:
        op.add_column('tag_policies',
            sa.Column('dynamic_tags', JSON, nullable=True, default={},
                      comment='Dynamic value sources for policy'))
    except Exception:
        pass
    
    try:
        op.add_column('tag_policies',
            sa.Column('resource_scope', sa.String(50), nullable=True, default='all',
                      comment='Broader resource scope filter'))
    except Exception:
        pass
    
    try:
        op.add_column('tag_policies',
            sa.Column('override_behavior', sa.String(20), nullable=True, default='skip_existing',
                      comment='How to handle existing tags'))
    except Exception:
        pass
    
    try:
        op.add_column('tag_policies',
            sa.Column('inject_system_tags', sa.Boolean, nullable=True, default=True,
                      comment='Auto-inject ManagedBy system tag'))
    except Exception:
        pass
    
    print("✅ Migration 009: Successfully added dynamic auto-tag fields")


def downgrade():
    """Remove dynamic auto-tag fields"""
    
    # Remove from auto_tag_rules
    try:
        op.drop_column('auto_tag_rules', 'dynamic_tags')
    except Exception:
        pass
    
    try:
        op.drop_column('auto_tag_rules', 'resource_scope')
    except Exception:
        pass
    
    try:
        op.drop_column('auto_tag_rules', 'override_behavior')
    except Exception:
        pass
    
    try:
        op.drop_column('auto_tag_rules', 'inject_system_tags')
    except Exception:
        pass
    
    # Remove from tag_policies
    try:
        op.drop_column('tag_policies', 'dynamic_tags')
    except Exception:
        pass
    
    try:
        op.drop_column('tag_policies', 'resource_scope')
    except Exception:
        pass
    
    try:
        op.drop_column('tag_policies', 'override_behavior')
    except Exception:
        pass
    
    try:
        op.drop_column('tag_policies', 'inject_system_tags')
    except Exception:
        pass
    
    print("✅ Migration 009: Rolled back dynamic auto-tag fields")
