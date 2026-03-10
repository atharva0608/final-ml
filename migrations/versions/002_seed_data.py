"""
Seed data migration - Default admin user and node templates

Revision ID: 002
Revises: 001
Create Date: 2026-03-07

"""
from alembic import op
import uuid

# revision identifiers, used by Alembic.
revision = '002'
down_revision = '001'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create default super admin user
    # Password: "admin123" (should be changed immediately in production)
    admin_id = str(uuid.uuid4())
    op.execute(f"""
        INSERT INTO users (id, email, password_hash, role, created_at, updated_at)
        VALUES (
            '{admin_id}',
            'admin@spotoptimizer.com',
            '$2b$12$N17vanzmiH1SCRRjRQjEzeipKGRondLrG0QRiDId1wgcjL0m0KKv.',
            'SUPER_ADMIN',
            NOW(),
            NOW()
        )
        ON CONFLICT (email) DO NOTHING
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
        families_str = "ARRAY[" + ", ".join(f"'{f}'" for f in template['families']) + "]"
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
                {families_str},
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
