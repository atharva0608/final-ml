-- Migration: Add model_upload_sessions table and update model_registry
-- Run this on the database to enable model versioning features

USE spot_optimizer;

-- Add columns to model_registry if they don't exist
ALTER TABLE model_registry
  ADD COLUMN IF NOT EXISTS upload_session_id CHAR(36) AFTER file_path,
  ADD COLUMN IF NOT EXISTS is_fallback BOOLEAN DEFAULT FALSE AFTER is_active;

-- Add indexes if they don't exist
CREATE INDEX IF NOT EXISTS idx_model_registry_session ON model_registry(upload_session_id);

-- Create model_upload_sessions table
CREATE TABLE IF NOT EXISTS model_upload_sessions (
    id CHAR(36) PRIMARY KEY,
    session_type VARCHAR(20) NOT NULL DEFAULT 'models',

    -- Status
    status VARCHAR(20) DEFAULT 'active',
    is_live BOOLEAN DEFAULT FALSE,
    is_fallback BOOLEAN DEFAULT FALSE,

    -- Files
    file_count INT DEFAULT 0,
    file_names JSON,
    total_size_bytes BIGINT DEFAULT 0,

    -- Metadata
    uploaded_by VARCHAR(128),
    notes TEXT,

    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    activated_at TIMESTAMP NULL,

    INDEX idx_upload_session_type_status (session_type, status),
    INDEX idx_upload_session_live (is_live),
    INDEX idx_upload_session_created (created_at DESC)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
COMMENT='Tracks model upload sessions for versioning (keeps last 2 sessions)';

SELECT '✅ Migration completed successfully' AS status;
