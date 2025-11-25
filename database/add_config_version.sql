-- ============================================================================
-- Migration: Add config_version column to agents table
-- ============================================================================
-- This migration adds the missing config_version column that the backend
-- expects for forcing config refreshes when agent settings are updated.
-- ============================================================================

USE spot_optimizer;

-- Add config_version column to agents table
ALTER TABLE agents
ADD COLUMN config_version INT DEFAULT 0 COMMENT 'Configuration version counter for forcing agent config refresh'
AFTER agent_version;

-- Verify the column was added
SELECT
    COLUMN_NAME,
    DATA_TYPE,
    IS_NULLABLE,
    COLUMN_DEFAULT,
    COLUMN_COMMENT
FROM INFORMATION_SCHEMA.COLUMNS
WHERE TABLE_SCHEMA = 'spot_optimizer'
  AND TABLE_NAME = 'agents'
  AND COLUMN_NAME = 'config_version';

SELECT 'Migration complete: config_version column added to agents table' AS status;
