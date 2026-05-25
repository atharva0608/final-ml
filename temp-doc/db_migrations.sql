-- DB Migrations for Karpenter Onboarding Plan
-- Run these in order against the production database.
-- All operations are safe to run on live clusters.

-- ============================================================
-- Migration 1: Add node_owner_type to instances table
-- (Change 3 in plan.md)
-- ============================================================

ALTER TABLE instances
    ADD COLUMN IF NOT EXISTS node_owner_type VARCHAR(32) NOT NULL DEFAULT 'unknown';

CREATE INDEX IF NOT EXISTS idx_instances_node_owner_type
    ON instances (cluster_id, node_owner_type);

-- Backfill: instances with no node_name are likely bootstrap/system
-- Real classification happens at next _sync_instance_state_from_k8s() cycle.
-- Do NOT attempt to backfill from instance metadata here — let the code do it.

-- ============================================================
-- Migration 2: Add onboarding_phase to clusters table
-- (Change 5 in plan.md)
-- ============================================================

-- NOTE: Originally used DEFAULT 'shadow' which blocked ALL new clusters from
-- executing rebalancing.  Fixed to DEFAULT 'managed' — new clusters are fully
-- managed from creation.  Shadow mode should only be set explicitly by an
-- operator, never as a default.
ALTER TABLE clusters
    ADD COLUMN IF NOT EXISTS onboarding_phase VARCHAR(32) NOT NULL DEFAULT 'managed';

-- ============================================================
-- Migration 2b: Fix column default on DBs that already ran Migration 2
-- with the old DEFAULT 'shadow'.
-- ============================================================
ALTER TABLE clusters
    ALTER COLUMN onboarding_phase SET DEFAULT 'managed';

-- Backfill ALL clusters stuck in 'shadow' to 'managed'.
-- Shadow was never intentionally set by users — it was only the (incorrect)
-- column default.  Any cluster in shadow should be graduated to managed.
UPDATE clusters
SET onboarding_phase = 'managed'
WHERE onboarding_phase = 'shadow';

-- Verify the backfill:
-- SELECT onboarding_phase, count(*) FROM clusters GROUP BY onboarding_phase;
