"""
Fix Tag Templates: Add resource_scope

Revision ID: fix_tag_templates_01
Revisits: 10b272181247
Create Date: 2026-01-30 15:55:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSON

# revision identifiers, used by Alembic.
revision = 'fix_tag_templates_01'
down_revision = '10b272181247'
branch_labels = None
depends_on = None


def upgrade():
    # Add resource_scope to tag_templates
    try:
        op.add_column('tag_templates',
            sa.Column('resource_scope', sa.String(50), nullable=False, server_default='all',
                      comment='Resource scope (all, ec2, s3, etc)'))
    except Exception:
        pass


def downgrade():
    try:
        op.drop_column('tag_templates', 'resource_scope')
    except Exception:
        pass
