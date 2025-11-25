-- ============================================================================
-- Add termination tracking columns to instances and replica_instances tables
-- Migration: add_termination_tracking.sql
-- Date: 2025-11-25
-- ============================================================================

-- Add tracking columns to instances table
ALTER TABLE instances
    ADD COLUMN IF NOT EXISTS termination_attempted_at TIMESTAMP NULL COMMENT 'When agent last attempted to terminate this instance',
    ADD COLUMN IF NOT EXISTS termination_confirmed BOOLEAN DEFAULT FALSE COMMENT 'TRUE if AWS confirmed termination';

-- Add tracking columns to replica_instances table
ALTER TABLE replica_instances
    ADD COLUMN IF NOT EXISTS termination_attempted_at TIMESTAMP NULL COMMENT 'When agent last attempted to terminate this instance',
    ADD COLUMN IF NOT EXISTS termination_confirmed BOOLEAN DEFAULT FALSE COMMENT 'TRUE if AWS confirmed termination';

-- Add index for efficient querying of instances to terminate
CREATE INDEX IF NOT EXISTS idx_instances_zombie_termination ON instances(instance_status, termination_attempted_at, region);
CREATE INDEX IF NOT EXISTS idx_replicas_termination ON replica_instances(status, termination_attempted_at, agent_id);
