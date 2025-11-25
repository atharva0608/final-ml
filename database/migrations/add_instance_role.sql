-- ============================================================================
-- Migration: Add Instance Role/State Tracking
-- Date: 2025-11-25
-- Purpose: Track instance lifecycle - primary (active) vs zombie (switched from)
-- ============================================================================

USE spot_optimizer;

-- Add role column to instances table
ALTER TABLE instances
ADD COLUMN instance_role ENUM('primary', 'zombie', 'replica') DEFAULT 'primary'
COMMENT 'Instance role: primary (currently active), zombie (switched from), replica (backup instance)'
AFTER is_active;

-- Add index for faster queries
ALTER TABLE instances
ADD INDEX idx_instances_role (instance_role);

-- Add agent_id to instances if not exists (for better tracking)
-- This helps us identify which agent "owns" this instance
ALTER TABLE instances
MODIFY COLUMN agent_id CHAR(36) NULL
COMMENT 'Agent that currently uses this instance (NULL for zombie instances)';

-- Update existing instances
-- Mark instances that match an agent's current instance_id as 'primary'
UPDATE instances i
JOIN agents a ON i.id = a.instance_id
SET i.instance_role = 'primary', i.agent_id = a.id
WHERE i.is_active = TRUE;

-- Mark all other active instances without a matching agent as 'zombie'
UPDATE instances
SET instance_role = 'zombie'
WHERE is_active = TRUE
  AND instance_role IS NULL
  AND id NOT IN (SELECT instance_id FROM agents WHERE instance_id IS NOT NULL);

-- Mark inactive instances as zombie
UPDATE instances
SET instance_role = 'zombie'
WHERE is_active = FALSE;

-- Create trigger to automatically set zombie state when instance is replaced
DELIMITER //

DROP TRIGGER IF EXISTS before_agent_instance_update//

CREATE TRIGGER before_agent_instance_update
BEFORE UPDATE ON agents
FOR EACH ROW
BEGIN
    -- If instance_id is changing, mark old instance as zombie
    IF OLD.instance_id IS NOT NULL
       AND NEW.instance_id IS NOT NULL
       AND OLD.instance_id != NEW.instance_id THEN
        -- Mark old instance as zombie
        UPDATE instances
        SET instance_role = 'zombie',
            agent_id = NULL,
            is_active = FALSE,
            terminated_at = NOW()
        WHERE id = OLD.instance_id;
    END IF;

    -- Mark new instance as primary
    IF NEW.instance_id IS NOT NULL THEN
        UPDATE instances
        SET instance_role = 'primary',
            agent_id = NEW.id,
            is_active = TRUE
        WHERE id = NEW.instance_id;
    END IF;
END//

DELIMITER ;

-- Add helpful view for primary instances
CREATE OR REPLACE VIEW v_primary_instances AS
SELECT
    i.id AS instance_id,
    i.instance_type,
    i.region,
    i.az,
    i.current_mode,
    i.current_pool_id,
    i.spot_price,
    i.ondemand_price,
    i.instance_role,
    a.id AS agent_id,
    a.logical_agent_id,
    a.status AS agent_status,
    a.client_id,
    c.name AS client_name
FROM instances i
JOIN agents a ON i.agent_id = a.id
JOIN clients c ON a.client_id = c.id
WHERE i.instance_role = 'primary'
  AND i.is_active = TRUE;

-- Add helpful view for zombie instances
CREATE OR REPLACE VIEW v_zombie_instances AS
SELECT
    i.id AS instance_id,
    i.instance_type,
    i.region,
    i.az,
    i.current_mode,
    i.current_pool_id,
    i.instance_role,
    i.terminated_at,
    i.client_id,
    c.name AS client_name
FROM instances i
JOIN clients c ON i.client_id = c.id
WHERE i.instance_role = 'zombie';

SELECT '✓ Instance role tracking added successfully!' AS status;
SELECT
    instance_role,
    COUNT(*) AS count
FROM instances
GROUP BY instance_role
ORDER BY instance_role;
