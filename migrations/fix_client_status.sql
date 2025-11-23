-- Fix existing clients with NULL or missing status column
-- This migration sets status='active' for all clients where status is NULL or empty

-- Check current status values (for verification)
SELECT id, name, is_active, status, client_token
FROM clients
WHERE status IS NULL OR status = '' OR status != 'active';

-- Update all clients with NULL or empty status to 'active'
UPDATE clients
SET status = 'active'
WHERE (status IS NULL OR status = '' OR status != 'active')
  AND is_active = TRUE;

-- Verify the fix
SELECT id, name, is_active, status
FROM clients;

-- If the status column doesn't exist, create it with default value
-- (Only run this if you get a "Unknown column 'status'" error)
-- ALTER TABLE clients ADD COLUMN status VARCHAR(20) DEFAULT 'active' AFTER is_active;
