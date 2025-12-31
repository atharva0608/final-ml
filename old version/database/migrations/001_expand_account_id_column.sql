-- Migration: Expand account_id column to support temporary onboarding IDs
-- Date: 2025-12-22
-- Description: Increases VARCHAR(12) to VARCHAR(64) to accommodate "pending-xxx" temporary IDs
--
-- AWS Account IDs are exactly 12 digits, but during onboarding we generate temporary
-- placeholders like "pending-efd57fb0da9a" which are ~20 characters long.
-- After verification, these are replaced with the real 12-digit AWS Account ID.

-- PostgreSQL
ALTER TABLE accounts
ALTER COLUMN account_id TYPE VARCHAR(64);

-- MySQL/MariaDB (if needed)
-- ALTER TABLE accounts MODIFY COLUMN account_id VARCHAR(64) NOT NULL;

-- Verify the change
-- SELECT
--     column_name,
--     data_type,
--     character_maximum_length
-- FROM information_schema.columns
-- WHERE table_name = 'accounts'
--   AND column_name = 'account_id';
