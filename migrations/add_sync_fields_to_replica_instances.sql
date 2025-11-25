-- Migration: Add sync tracking fields to replica_instances table
-- These fields are used by agents to track synchronization progress

USE db;

-- Add sync_started_at field to track when synchronization began
ALTER TABLE replica_instances
ADD COLUMN IF NOT EXISTS sync_started_at TIMESTAMP NULL
COMMENT 'Timestamp when state synchronization started';

-- Add sync_completed_at field to track when synchronization completed
ALTER TABLE replica_instances
ADD COLUMN IF NOT EXISTS sync_completed_at TIMESTAMP NULL
COMMENT 'Timestamp when state synchronization completed successfully';

-- Add error_message field to store error details for failed replicas
ALTER TABLE replica_instances
ADD COLUMN IF NOT EXISTS error_message TEXT NULL
COMMENT 'Error message details for failed replica status';

-- Add index for sync_completed_at for performance on queries filtering by sync state
CREATE INDEX IF NOT EXISTS idx_replica_sync_completed ON replica_instances(sync_completed_at);
