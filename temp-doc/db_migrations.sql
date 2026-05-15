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

ALTER TABLE clusters
    ADD COLUMN IF NOT EXISTS onboarding_phase VARCHAR(32) NOT NULL DEFAULT 'shadow';

-- CRITICAL: Backfill existing active clusters to 'managed'.
-- Without this, ALL currently-running clusters will be gated to shadow mode
-- and stop optimizing immediately after deploy.
UPDATE clusters
SET onboarding_phase = 'managed'
WHERE status IN ('ACTIVE', 'active', 'CONNECTED', 'connected')
  AND agent_installed = 'Y'
  AND onboarding_phase = 'shadow';

-- New clusters start at 'shadow' (the column default is correct for new rows).
-- Clusters without an agent also default to shadow — correct behavior.

-- Verify the backfill:
-- SELECT onboarding_phase, count(*) FROM clusters GROUP BY onboarding_phase;
