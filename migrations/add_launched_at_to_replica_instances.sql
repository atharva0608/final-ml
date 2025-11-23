-- ============================================================================
-- Migration: Add launched_at column to replica_instances table
-- Date: 2025-11-23
-- Description: Adds the missing launched_at TIMESTAMP column to track when
--              replica instances are launched
-- ============================================================================

-- Add the launched_at column after created_at
ALTER TABLE replica_instances
ADD COLUMN launched_at TIMESTAMP NULL
AFTER created_at;

-- Verify the column was added
SELECT 'Migration completed: launched_at column added to replica_instances table' AS status;
