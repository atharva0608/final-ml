"""Add DB trigger to auto-set state_entered_at on current_state change

Revision ID: 20260325_state_entered_at_trigger
Revises: 20260323_launch_outcomes
Create Date: 2026-03-25

Issue 8: state_entered_at was nullable and not consistently set when current_state
changes. The _sm_transition() function updates current_state atomically but does not
update state_entered_at. This trigger enforces auto-update at the database level.

Changes:
    - Add trigger function update_state_entered_at() that fires BEFORE UPDATE
    - Create trigger on rebalancing_actions table to auto-set state_entered_at
    - Backfill existing rows using updated_at when available, otherwise created_at
"""
from alembic import op
import sqlalchemy as sa


revision = '20260325_state_entered_at_trigger'
down_revision = '20260323_launch_outcomes'
branch_labels = None
depends_on = None


def upgrade():
    # ---------------------------------------------------------------
    # 1. Create trigger function
    # ---------------------------------------------------------------
    op.execute("""
        CREATE OR REPLACE FUNCTION update_state_entered_at()
        RETURNS TRIGGER AS $$
        BEGIN
            -- Only update timestamp when the state actually changes (not on unrelated updates)
            IF NEW.current_state IS DISTINCT FROM OLD.current_state THEN
                NEW.state_entered_at = NOW();
            END IF;
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
    """)

    # ---------------------------------------------------------------
    # 2. Create trigger on rebalancing_actions
    # ---------------------------------------------------------------
    op.execute("""
        DROP TRIGGER IF EXISTS trigger_update_state_entered ON rebalancing_actions;
    """)

    op.execute("""
        CREATE TRIGGER trigger_update_state_entered
            BEFORE UPDATE OF current_state ON rebalancing_actions
            FOR EACH ROW
            EXECUTE FUNCTION update_state_entered_at();
    """)

    # ---------------------------------------------------------------
    # 3. Backfill existing rows.
    #    Some databases have rebalancing_actions.updated_at, others only have
    #    created_at. Make the migration portable across both schemas.
    # ---------------------------------------------------------------
    op.execute("""
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1
                FROM information_schema.columns
                WHERE table_name = 'rebalancing_actions'
                  AND column_name = 'updated_at'
            ) THEN
                EXECUTE '
                    UPDATE rebalancing_actions
                    SET state_entered_at = COALESCE(updated_at, created_at)
                    WHERE state_entered_at IS NULL
                      AND COALESCE(updated_at, created_at) IS NOT NULL
                ';
            ELSE
                EXECUTE '
                    UPDATE rebalancing_actions
                    SET state_entered_at = created_at
                    WHERE state_entered_at IS NULL
                      AND created_at IS NOT NULL
                ';
            END IF;
        END
        $$;
    """)


def downgrade():
    # Remove trigger and function — leaves state_entered_at column intact
    op.execute("""
        DROP TRIGGER IF EXISTS trigger_update_state_entered ON rebalancing_actions;
    """)

    op.execute("""
        DROP FUNCTION IF EXISTS update_state_entered_at();
    """)
