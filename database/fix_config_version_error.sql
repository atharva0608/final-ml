-- ============================================================================
-- HOTFIX: Add missing config_version column to agents table
-- ============================================================================
-- This fixes the error:
--   "Unknown column 'config_version' in 'field list'"
--
-- The backend code expects this column to exist in the agents table
-- to track configuration version changes and force agent config refreshes.
-- ============================================================================

USE spot_optimizer;

-- Check if the column already exists (prevents duplicate errors)
SET @column_exists = (
    SELECT COUNT(*)
    FROM INFORMATION_SCHEMA.COLUMNS
    WHERE TABLE_SCHEMA = 'spot_optimizer'
      AND TABLE_NAME = 'agents'
      AND COLUMN_NAME = 'config_version'
);

-- Add the column if it doesn't exist
SET @sql = IF(
    @column_exists = 0,
    'ALTER TABLE agents ADD COLUMN config_version INT DEFAULT 0 COMMENT ''Configuration version counter for forcing agent config refresh'' AFTER agent_version',
    'SELECT ''Column config_version already exists'' AS status'
);

PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

-- Verify the column exists
SELECT
    COLUMN_NAME,
    DATA_TYPE,
    COLUMN_DEFAULT,
    IS_NULLABLE,
    COLUMN_COMMENT
FROM INFORMATION_SCHEMA.COLUMNS
WHERE TABLE_SCHEMA = 'spot_optimizer'
  AND TABLE_NAME = 'agents'
  AND COLUMN_NAME = 'config_version';

SELECT '✓ Fix applied successfully! You can now save agent configurations.' AS result;
