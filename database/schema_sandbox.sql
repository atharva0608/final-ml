-- Sandbox Mode Database Schema
-- Ephemeral test sessions with temporary credentials

-- Table: Sandbox Sessions
CREATE TABLE IF NOT EXISTS sandbox_sessions (
    session_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    temp_username VARCHAR(50) UNIQUE NOT NULL,  -- e.g., 'sandbox_user_992'
    temp_password_hash VARCHAR(255) NOT NULL,    -- Bcrypt hash for login

    -- AWS Credentials (encrypted at rest)
    aws_access_key_encrypted TEXT NOT NULL,     -- AES-256 encrypted
    aws_secret_key_encrypted TEXT NOT NULL,     -- AES-256 encrypted
    aws_region VARCHAR(20) DEFAULT 'ap-south-1',

    -- Target Instance
    target_instance_id VARCHAR(50) NOT NULL,    -- Original instance to test
    target_instance_type VARCHAR(20),
    target_availability_zone VARCHAR(20),

    -- Session Lifecycle
    created_at TIMESTAMP DEFAULT NOW(),
    expires_at TIMESTAMP NOT NULL,              -- Auto-expire after 2 hours
    is_active BOOLEAN DEFAULT TRUE,

    -- Tracking
    created_by_user_id UUID,                    -- Admin who created session

    CONSTRAINT expires_after_creation CHECK (expires_at > created_at)
);

-- Index for cleanup job
CREATE INDEX IF NOT EXISTS idx_sandbox_sessions_expiry
ON sandbox_sessions(expires_at)
WHERE is_active = TRUE;

-- Table: Sandbox Actions (switch log)
CREATE TABLE IF NOT EXISTS sandbox_actions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id UUID REFERENCES sandbox_sessions(session_id) ON DELETE CASCADE,
    timestamp TIMESTAMP DEFAULT NOW(),
    action_type VARCHAR(50),  -- 'MONITORING', 'AMI_CREATED', 'SPOT_LAUNCHED', 'INSTANCE_STOPPED'
    details JSONB,            -- Flexible log data
    status VARCHAR(20),       -- 'SUCCESS', 'FAILED', 'IN_PROGRESS'
    error_message TEXT
);

-- Index for quick log retrieval
CREATE INDEX IF NOT EXISTS idx_sandbox_actions_session
ON sandbox_actions(session_id, timestamp DESC);

-- Table: Sandbox Savings (ephemeral analytics)
CREATE TABLE IF NOT EXISTS sandbox_savings (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id UUID REFERENCES sandbox_sessions(session_id) ON DELETE CASCADE,
    timestamp TIMESTAMP DEFAULT NOW(),
    spot_price DECIMAL(10, 6),
    on_demand_price DECIMAL(10, 6),
    projected_hourly_savings DECIMAL(10, 4),
    cumulative_savings DECIMAL(10, 4)  -- Running total for session
);

-- Index for analytics queries
CREATE INDEX IF NOT EXISTS idx_sandbox_savings_session
ON sandbox_savings(session_id, timestamp);
