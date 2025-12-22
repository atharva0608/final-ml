-- Phase 2 Migration: Global Risk Intelligence & Replica System
-- Run this migration to add the new tables and columns for Phase 2 features

-- ============================================================================
-- 1. Add replica fields to instances table
-- ============================================================================

-- Add replica system fields to instances table
ALTER TABLE instances 
ADD COLUMN IF NOT EXISTS is_replica BOOLEAN NOT NULL DEFAULT false,
ADD COLUMN IF NOT EXISTS replica_of_id VARCHAR(64),
ADD COLUMN IF NOT EXISTS replica_expiry TIMESTAMP;

-- Add comments for documentation
COMMENT ON COLUMN instances.is_replica IS 'Distinguishes safety net from production instances';
COMMENT ON COLUMN instances.replica_of_id IS 'Links replica to primary instance_id';
COMMENT ON COLUMN instances.replica_expiry IS '6hr timer for false alarm cleanup';

-- ============================================================================
-- 2. Create global_risk_events table
-- ============================================================================

CREATE TABLE IF NOT EXISTS global_risk_events (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    
    -- Spot pool identification
    pool_id VARCHAR(128) NOT NULL,
    region VARCHAR(20) NOT NULL,
    availability_zone VARCHAR(20) NOT NULL,
    instance_type VARCHAR(20) NOT NULL,
    
    -- Event classification
    event_type VARCHAR(30) NOT NULL,
    
    -- Timing (15-day poisoning window)
    reported_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    expires_at TIMESTAMP NOT NULL,
    
    -- Attribution and metadata
    source_client_id UUID REFERENCES users(id),
    event_metadata JSONB,
    
    -- Indexes for performance
    CONSTRAINT global_risk_events_pkey PRIMARY KEY (id)
);

-- Create indexes for fast queries
CREATE INDEX IF NOT EXISTS idx_global_risk_pool_id ON global_risk_events(pool_id);
CREATE INDEX IF NOT EXISTS idx_global_risk_expires ON global_risk_events(expires_at);
CREATE INDEX IF NOT EXISTS idx_global_risk_region ON global_risk_events(region);
CREATE INDEX IF NOT EXISTS idx_global_risk_az ON global_risk_events(availability_zone);
CREATE INDEX IF NOT EXISTS idx_global_risk_type ON global_risk_events(instance_type);
CREATE INDEX IF NOT EXISTS idx_global_risk_event_type ON global_risk_events(event_type);
CREATE INDEX IF NOT EXISTS idx_global_risk_reported ON global_risk_events(reported_at);

-- Add comments
COMMENT ON TABLE global_risk_events IS 'Append-only log of spot disruptions across ALL clients';
COMMENT ON COLUMN global_risk_events.pool_id IS 'Format: us-east-1a:c5.large';
COMMENT ON COLUMN global_risk_events.event_type IS 'rebalance_notice or termination_notice';
COMMENT ON COLUMN global_risk_events.expires_at IS 'reported_at + 15 days (AWS pool recovery time)';

-- ============================================================================
-- 3. Create downtime_logs table
-- ============================================================================

CREATE TABLE IF NOT EXISTS downtime_logs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    
    -- Attribution
    client_id UUID NOT NULL REFERENCES users(id),
    instance_id VARCHAR(64) NOT NULL,
    
    -- Downtime window
    start_time TIMESTAMP NOT NULL,
    end_time TIMESTAMP NOT NULL,
    duration_seconds INTEGER NOT NULL,
    
    -- Root cause analysis
    cause VARCHAR(64) NOT NULL,
    cause_details TEXT,
    
    -- Context
    downtime_metadata JSONB,
    
    -- Audit
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    
    CONSTRAINT downtime_logs_pkey PRIMARY KEY (id)
);

-- Create indexes for performance
CREATE INDEX IF NOT EXISTS idx_downtime_client ON downtime_logs(client_id);
CREATE INDEX IF NOT EXISTS idx_downtime_instance ON downtime_logs(instance_id);
CREATE INDEX IF NOT EXISTS idx_downtime_start ON downtime_logs(start_time);
CREATE INDEX IF NOT EXISTS idx_downtime_cause ON downtime_logs(cause);

-- Add comments
COMMENT ON TABLE downtime_logs IS 'SLA accountability - tracks every second WE caused downtime (not AWS)';
COMMENT ON COLUMN downtime_logs.cause IS 'emergency_switch, no_replica, optimizer_failure, worker_crash';
COMMENT ON COLUMN downtime_logs.duration_seconds IS 'end_time - start_time in seconds';

-- ============================================================================
-- Migration complete
-- ============================================================================

-- Verify tables exist
SELECT 
    'global_risk_events' as table_name,
    COUNT(*) as row_count
FROM global_risk_events
UNION ALL
SELECT 
    'downtime_logs' as table_name,
    COUNT(*) as row_count
FROM downtime_logs;

-- Verify columns added
SELECT 
    column_name, 
    data_type, 
    is_nullable
FROM information_schema.columns
WHERE table_name = 'instances' 
  AND column_name IN ('is_replica', 'replica_of_id', 'replica_expiry')
ORDER BY column_name;
