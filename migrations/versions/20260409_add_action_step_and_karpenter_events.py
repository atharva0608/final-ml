"""Add action_step column to rebalancing_actions and create karpenter_events table.

Revision ID: 20260409_action_step
Revises: 20260404_baseline
Create Date: 2026-04-09

Changes:
  1. rebalancing_actions.action_step VARCHAR(20) — crash-safe Karpenter phase journal.
     Values: INJECTED | WAITING_SPOT | DRAINING | TERMINATING | CLEANUP | DONE
     NULL  = non-Karpenter action or action predates this migration.

  2. karpenter_events table — stores events received from the Karpenter event-watcher
     sidecar running in the agent DaemonSet. Used to surface independent Karpenter
     provisioning/consolidation and optionally pause the ML rebalancer.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers
revision = '20260409_action_step'
down_revision = '20260404_baseline'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── 1. action_step on rebalancing_actions ────────────────────────────────
    op.add_column(
        'rebalancing_actions',
        sa.Column('action_step', sa.String(length=20), nullable=True),
    )
    op.create_index(
        'ix_rebalancing_actions_action_step',
        'rebalancing_actions',
        ['action_step'],
        unique=False,
    )

    # ── 2. karpenter_events table ─────────────────────────────────────────────
    op.create_table(
        'karpenter_events',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('cluster_id', sa.String(length=100), nullable=False),
        # K8s event reason, e.g. "NodeClaimCreated", "NodeClaimDeleted", "Consolidated"
        sa.Column('event_reason', sa.String(length=100), nullable=False),
        # K8s event source (usually "karpenter")
        sa.Column('event_source', sa.String(length=100), nullable=True),
        # Involved object kind/name, e.g. "NodeClaim/default-abc12"
        sa.Column('involved_object_kind', sa.String(length=100), nullable=True),
        sa.Column('involved_object_name', sa.String(length=255), nullable=True),
        # Human-readable message from the K8s event
        sa.Column('message', sa.Text(), nullable=True),
        # Full event payload from agent (JSON)
        sa.Column('event_payload', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        # When Karpenter generated the event (firstTimestamp / eventTime from K8s)
        sa.Column('event_time', sa.DateTime(), nullable=True),
        # When this row was written
        sa.Column('received_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        # Whether the rebalancer was paused as a result of this event
        sa.Column('triggered_pause', sa.Boolean(), server_default='false', nullable=False),
        sa.ForeignKeyConstraint(
            ['cluster_id'], ['clusters.id'], ondelete='CASCADE',
        ),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(
        'ix_karpenter_events_cluster_id',
        'karpenter_events',
        ['cluster_id'],
        unique=False,
    )
    op.create_index(
        'ix_karpenter_events_event_reason',
        'karpenter_events',
        ['event_reason'],
        unique=False,
    )
    op.create_index(
        'ix_karpenter_events_received_at',
        'karpenter_events',
        ['received_at'],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index('ix_karpenter_events_received_at', table_name='karpenter_events')
    op.drop_index('ix_karpenter_events_event_reason', table_name='karpenter_events')
    op.drop_index('ix_karpenter_events_cluster_id', table_name='karpenter_events')
    op.drop_table('karpenter_events')

    op.drop_index('ix_rebalancing_actions_action_step', table_name='rebalancing_actions')
    op.drop_column('rebalancing_actions', 'action_step')
