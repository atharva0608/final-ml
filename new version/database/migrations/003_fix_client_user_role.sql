-- Migration: Fix client user role from 'user' to 'client'
-- Date: 2025-12-23
-- Description: Updates the test client user to have the correct 'client' role
--              This fixes the "Access denied. Client role required" error

-- PostgreSQL

-- Update client test user role
UPDATE users
SET role = 'client'
WHERE username = 'client'
  AND role = 'user';

-- Verify the change
-- SELECT username, email, role
-- FROM users
-- WHERE username = 'client';

-- Expected result: client user should now have role = 'client'
