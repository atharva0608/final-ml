"""
Seed data migration - Default users and templates

Revision ID: 002
Revises: 001
Create Date: 2025-12-31 12:51:00

"""
from alembic import op
import sqlalchemy as sa
from datetime import datetime
import uuid

# revision identifiers, used by Alembic.
revision = '002'
down_revision = '001'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create default super admin user
    # Password: "admin123" (should be changed immediately in production)
    # Hash generated with bcrypt
    admin_id = str(uuid.uuid4())
    op.execute(f"""
        INSERT INTO users (id, email, password_hash, role, created_at, updated_at)
        VALUES (
            '{admin_id}',
            'admin@spotoptimizer.com',
            '$2b$12$LQv3c1yqBWVHxkd0LHAkCOYz6TtxMQJqhN8/LewY5PqgZ1y6zGjWG',
            'SUPER_ADMIN',
            NOW(),
            NOW()
        )
    """)

    # Create default node templates for the admin user
    templates = [
        {
            'id': str(uuid.uuid4()),
            'user_id': admin_id,
            'name': 'General Purpose - Balanced',
            'families': ['m5', 'm6i', 'm7i'],
            'architecture': 'x86_64',
            'strategy': 'BALANCED',
            'disk_type': 'GP3',
            'disk_size': 100,
            'is_default': 'Y'
        },
        {
            'id': str(uuid.uuid4()),
            'user_id': admin_id,
            'name': 'Compute Optimized - High Performance',
            'families': ['c5', 'c6i', 'c7i'],
            'architecture': 'x86_64',
            'strategy': 'PERFORMANCE',
            'disk_type': 'GP3',
            'disk_size': 100,
            'is_default': 'N'
        },
        {
            'id': str(uuid.uuid4()),
            'user_id': admin_id,
            'name': 'Memory Optimized - Large Workloads',
            'families': ['r5', 'r6i', 'r7i'],
            'architecture': 'x86_64',
            'strategy': 'BALANCED',
            'disk_type': 'GP3',
            'disk_size': 200,
            'is_default': 'N'
        },
        {
            'id': str(uuid.uuid4()),
            'user_id': admin_id,
            'name': 'ARM-Based - Cost Efficient',
            'families': ['t4g', 'm6g', 'c6g'],
            'architecture': 'arm64',
            'strategy': 'CHEAPEST',
            'disk_type': 'GP3',
            'disk_size': 100,
            'is_default': 'N'
        }
    ]

    for template in templates:
        families_str = '{' + ','.join(template['families']) + '}'
        op.execute(f"""
            INSERT INTO node_templates (
                id, user_id, name, families, architecture,
                strategy, disk_type, disk_size, is_default,
                created_at, updated_at
            )
            VALUES (
                '{template['id']}',
                '{template['user_id']}',
                '{template['name']}',
                ARRAY{families_str},
                '{template['architecture']}',
                '{template['strategy']}',
                '{template['disk_type']}',
                {template['disk_size']},
                '{template['is_default']}',
                NOW(),
                NOW()
            )
        """)


def downgrade() -> None:
    # Remove default templates
    op.execute("DELETE FROM node_templates WHERE name LIKE 'General Purpose%' OR name LIKE 'Compute Optimized%' OR name LIKE 'Memory Optimized%' OR name LIKE 'ARM-Based%'")

    # Remove default admin user
    op.execute("DELETE FROM users WHERE email = 'admin@spotoptimizer.com'")
