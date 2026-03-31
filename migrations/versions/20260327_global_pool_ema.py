"""Add global_pool_ema and global_pool_ema_history tables

Revision ID: 20260327_global_pool_ema
Revises: 20260325_max_concurrent_cooldown
Create Date: 2026-03-27

Global EMA infrastructure: cross-customer interruption rate tracking per pool.
Each pool_key = 'instance_type:az'.
EMA state dual-stored in Redis (hot cache) and Postgres (durable).
"""
from alembic import op
import sqlalchemy as sa


revision = '20260327_global_pool_ema'
down_revision = '20260325_max_concurrent_cooldown'
branch_labels = None
depends_on = None


def upgrade():
    # ── global_pool_ema ──────────────────────────────────────────────
    op.create_table(
        'global_pool_ema',
        sa.Column('pool_key', sa.String(100), primary_key=True),
        sa.Column('instance_type', sa.String(50), nullable=False),
        sa.Column('az', sa.String(50), nullable=False),
        sa.Column('region', sa.String(50), nullable=False),
        sa.Column('count', sa.Integer, nullable=False, server_default='0'),
        sa.Column('rate', sa.Numeric(5, 2), nullable=False, server_default='0.0'),
        sa.Column('peak_rate', sa.Numeric(5, 2), nullable=False, server_default='0.0'),
        sa.Column('sample_clusters', sa.Integer, nullable=False, server_default='0'),
        sa.Column('last_event', sa.DateTime, nullable=True),
        sa.Column('created_at', sa.DateTime, nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime, nullable=False, server_default=sa.func.now()),
    )
    op.create_index('idx_global_pool_ema_region', 'global_pool_ema', ['region'])
    op.create_index('idx_global_pool_ema_last_event', 'global_pool_ema', ['last_event'])

    # ── global_pool_ema_history (analytics, optional) ────────────────
    op.create_table(
        'global_pool_ema_history',
        sa.Column('id', sa.Integer, primary_key=True, autoincrement=True),
        sa.Column('pool_key', sa.String(100), nullable=False),
        sa.Column('rate', sa.Numeric(5, 2)),
        sa.Column('count', sa.Integer),
        sa.Column('recorded_at', sa.DateTime, nullable=False, server_default=sa.func.now()),
    )
    op.create_index('idx_ema_history_pool_key', 'global_pool_ema_history', ['pool_key'])


def downgrade():
    op.drop_table('global_pool_ema_history')
    op.drop_table('global_pool_ema')
