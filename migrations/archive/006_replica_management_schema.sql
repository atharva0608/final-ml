-- Migration 006: Replica Management & Data Quality System
-- This migration adds tables for manual/automatic replica management,
-- data deduplication, gap-filling, and price interpolation.

-- ============================================================================
-- PART 1: REPLICA INSTANCES TRACKING
-- ============================================================================

-- Table to track all replica instances (manual and automatic)
CREATE TABLE IF NOT EXISTS replica_instances (
    id VARCHAR(255) PRIMARY KEY,
    agent_id VARCHAR(255) NOT NULL,
    instance_id VARCHAR(255) NOT NULL,
    replica_type ENUM('manual', 'automatic-rebalance', 'automatic-termination') NOT NULL,
    pool_id INT,
    instance_type VARCHAR(50),
    region VARCHAR(50),
    az VARCHAR(50),

    -- Lifecycle tracking
    status ENUM('launching', 'syncing', 'ready', 'promoted', 'terminated', 'failed') NOT NULL DEFAULT 'launching',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    ready_at TIMESTAMP NULL,
    promoted_at TIMESTAMP NULL,
    terminated_at TIMESTAMP NULL,

    -- Replica metadata
    created_by VARCHAR(255),  -- user email or 'system' for automatic
    parent_instance_id VARCHAR(255),  -- original instance that spawned this replica
    is_active BOOLEAN DEFAULT TRUE,

    -- State sync tracking
    sync_status ENUM('initializing', 'syncing', 'synced', 'out-of-sync') DEFAULT 'initializing',
    sync_latency_ms INT,  -- current latency between primary and replica
    last_sync_at TIMESTAMP NULL,
    state_transfer_progress DECIMAL(5,2) DEFAULT 0.00,  -- 0-100%

    -- Cost tracking
    hourly_cost DECIMAL(10,6),
    total_cost DECIMAL(10,4) DEFAULT 0.0000,

    -- Interruption handling (for automatic replicas)
    interruption_signal_type ENUM('rebalance-recommendation', 'termination-notice', NULL) DEFAULT NULL,
    interruption_detected_at TIMESTAMP NULL,
    termination_time TIMESTAMP NULL,
    failover_completed_at TIMESTAMP NULL,

    -- Tags and metadata
    tags JSON,

    FOREIGN KEY (agent_id) REFERENCES agents(id) ON DELETE CASCADE,
    FOREIGN KEY (pool_id) REFERENCES spot_pools(id) ON DELETE SET NULL,
    INDEX idx_agent_status (agent_id, status),
    INDEX idx_parent_instance (parent_instance_id),
    INDEX idx_created_at (created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- ============================================================================
-- PART 2: RAW PRICING DATA CAPTURE (AUDIT TRAIL)
-- ============================================================================

-- Raw ingestion layer - captures EVERY pricing submission with full metadata
-- This is append-only and provides complete audit trail
CREATE TABLE IF NOT EXISTS pricing_submissions_raw (
    submission_id VARCHAR(255) PRIMARY KEY,

    -- Source identification
    source_instance_id VARCHAR(255) NOT NULL,
    source_agent_id VARCHAR(255),
    source_type ENUM('primary', 'replica-manual', 'replica-automatic', 'interpolated') NOT NULL,

    -- Pricing data
    pool_id INT NOT NULL,
    instance_type VARCHAR(50),
    region VARCHAR(50),
    az VARCHAR(50),
    spot_price DECIMAL(10,6) NOT NULL,
    ondemand_price DECIMAL(10,6),

    -- Timing
    observed_at TIMESTAMP NOT NULL,  -- when agent observed the price
    submitted_at TIMESTAMP NOT NULL,  -- when agent submitted to server
    received_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,  -- when server received

    -- Deduplication tracking
    is_duplicate BOOLEAN DEFAULT FALSE,
    duplicate_of VARCHAR(255),  -- references another submission_id

    -- Validation
    is_valid BOOLEAN DEFAULT TRUE,
    validation_flags JSON,  -- any warnings or anomalies detected

    -- Metadata
    client_id VARCHAR(255),
    batch_id VARCHAR(255),  -- if submitted in batch

    FOREIGN KEY (pool_id) REFERENCES spot_pools(id) ON DELETE CASCADE,
    FOREIGN KEY (duplicate_of) REFERENCES pricing_submissions_raw(submission_id) ON DELETE SET NULL,
    INDEX idx_pool_observed (pool_id, observed_at),
    INDEX idx_source_instance (source_instance_id, observed_at),
    INDEX idx_received_at (received_at),
    INDEX idx_is_duplicate (is_duplicate)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- ============================================================================
-- PART 3: DEDUPLICATED OPERATIONAL DATA
-- ============================================================================

-- Clean operational layer - contains only unique, validated pricing data
-- This is the main table used by the application
CREATE TABLE IF NOT EXISTS pricing_snapshots_clean (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,

    -- Pool identification
    pool_id INT NOT NULL,
    instance_type VARCHAR(50) NOT NULL,
    region VARCHAR(50) NOT NULL,
    az VARCHAR(50) NOT NULL,

    -- Pricing
    spot_price DECIMAL(10,6) NOT NULL,
    ondemand_price DECIMAL(10,6),
    savings_percent DECIMAL(5,2),

    -- Time bucketing (5-minute windows)
    time_bucket TIMESTAMP NOT NULL,  -- rounded to 5-minute intervals
    bucket_start TIMESTAMP NOT NULL,
    bucket_end TIMESTAMP NOT NULL,

    -- Source attribution
    source_instance_id VARCHAR(255),
    source_agent_id VARCHAR(255),
    source_type ENUM('primary', 'replica-manual', 'replica-automatic', 'interpolated') NOT NULL,
    source_submission_id VARCHAR(255),  -- references pricing_submissions_raw

    -- Data quality
    confidence_score DECIMAL(3,2) NOT NULL DEFAULT 1.00,  -- 0.00 to 1.00
    data_source ENUM('measured', 'interpolated') NOT NULL DEFAULT 'measured',
    interpolation_method VARCHAR(50),  -- e.g., 'linear', 'weighted-average', 'cross-pool'
    interpolation_metadata JSON,

    -- Auditing
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    UNIQUE KEY unique_pool_bucket (pool_id, time_bucket),
    FOREIGN KEY (pool_id) REFERENCES spot_pools(id) ON DELETE CASCADE,
    FOREIGN KEY (source_submission_id) REFERENCES pricing_submissions_raw(submission_id) ON DELETE SET NULL,
    INDEX idx_pool_time (pool_id, time_bucket),
    INDEX idx_time_bucket (time_bucket),
    INDEX idx_confidence (confidence_score),
    INDEX idx_data_source (data_source)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- ============================================================================
-- PART 4: INTERPOLATED PRICES TRACKING
-- ============================================================================

-- Separate table for interpolated prices with full transparency
CREATE TABLE IF NOT EXISTS pricing_snapshots_interpolated (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,

    -- Pool identification
    pool_id INT NOT NULL,
    instance_type VARCHAR(50) NOT NULL,
    region VARCHAR(50) NOT NULL,
    az VARCHAR(50) NOT NULL,

    -- Gap information
    time_bucket TIMESTAMP NOT NULL,
    gap_duration_minutes INT NOT NULL,
    gap_type ENUM('short', 'medium', 'long', 'transition', 'blackout') NOT NULL,

    -- Interpolation details
    interpolation_method VARCHAR(50) NOT NULL,
    confidence_score DECIMAL(3,2) NOT NULL,

    -- Source prices used for interpolation
    price_before DECIMAL(10,6),
    price_after DECIMAL(10,6),
    timestamp_before TIMESTAMP,
    timestamp_after TIMESTAMP,

    -- Cross-pool reference (if used)
    reference_pool_ids JSON,  -- array of pool IDs used for inference

    -- Calculated price
    interpolated_price DECIMAL(10,6) NOT NULL,

    -- Quality flags
    needs_review BOOLEAN DEFAULT FALSE,
    reviewed_by VARCHAR(255),
    reviewed_at TIMESTAMP NULL,

    -- Metadata
    interpolation_metadata JSON,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (pool_id) REFERENCES spot_pools(id) ON DELETE CASCADE,
    INDEX idx_pool_time (pool_id, time_bucket),
    INDEX idx_gap_type (gap_type),
    INDEX idx_needs_review (needs_review)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- ============================================================================
-- PART 5: PRICE CORRECTIONS
-- ============================================================================

-- Track corrections to historical prices (e.g., billing discrepancies)
CREATE TABLE IF NOT EXISTS pricing_corrections (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,

    -- What's being corrected
    original_snapshot_id BIGINT,
    pool_id INT NOT NULL,
    time_bucket TIMESTAMP NOT NULL,

    -- Original vs corrected
    original_price DECIMAL(10,6) NOT NULL,
    corrected_price DECIMAL(10,6) NOT NULL,
    correction_reason VARCHAR(255) NOT NULL,

    -- Source of correction
    correction_source ENUM('aws-billing', 'manual-audit', 'system-detection') NOT NULL,
    corrected_by VARCHAR(255) NOT NULL,
    correction_notes TEXT,

    -- Timestamps
    corrected_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    applied_at TIMESTAMP NULL,

    -- Status
    status ENUM('pending', 'applied', 'rejected') DEFAULT 'pending',

    FOREIGN KEY (original_snapshot_id) REFERENCES pricing_snapshots_clean(id) ON DELETE SET NULL,
    FOREIGN KEY (pool_id) REFERENCES spot_pools(id) ON DELETE CASCADE,
    INDEX idx_pool_time (pool_id, time_bucket),
    INDEX idx_status (status)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- ============================================================================
-- PART 6: SWITCH HISTORY ENHANCEMENTS
-- ============================================================================

-- Add columns to existing instance_switches table for price tracking
ALTER TABLE instance_switches
    ADD COLUMN old_instance_price DECIMAL(10,6) DEFAULT NULL COMMENT 'Last known price of old instance',
    ADD COLUMN new_instance_price DECIMAL(10,6) DEFAULT NULL COMMENT 'First known price of new instance',
    ADD COLUMN ondemand_baseline DECIMAL(10,6) DEFAULT NULL COMMENT 'On-demand price at time of switch',
    ADD COLUMN price_confidence_old DECIMAL(3,2) DEFAULT 1.00 COMMENT 'Confidence score for old price (0.00-1.00)',
    ADD COLUMN price_confidence_new DECIMAL(3,2) DEFAULT 1.00 COMMENT 'Confidence score for new price (0.00-1.00)',
    ADD COLUMN price_data_source_old ENUM('measured', 'interpolated', 'unavailable') DEFAULT 'measured',
    ADD COLUMN price_data_source_new ENUM('measured', 'interpolated', 'unavailable') DEFAULT 'measured',
    ADD COLUMN interpolation_method_old VARCHAR(50) DEFAULT NULL,
    ADD COLUMN interpolation_method_new VARCHAR(50) DEFAULT NULL,
    ADD COLUMN estimated_savings DECIMAL(10,4) DEFAULT NULL COMMENT 'Calculated savings if price data available',
    ADD COLUMN savings_confidence ENUM('high', 'medium', 'low', 'unavailable') DEFAULT 'high';

-- ============================================================================
-- PART 7: AGENT ENHANCEMENTS FOR REPLICA SUPPORT
-- ============================================================================

-- Add replica-related columns to agents table
ALTER TABLE agents
    ADD COLUMN auto_replica_enabled BOOLEAN DEFAULT FALSE COMMENT 'Enable automatic replica creation on interruption signals',
    ADD COLUMN manual_replica_enabled BOOLEAN DEFAULT FALSE COMMENT 'Allow manual replica creation',
    ADD COLUMN current_replica_id VARCHAR(255) DEFAULT NULL COMMENT 'Currently active replica instance',
    ADD COLUMN replica_count INT DEFAULT 0 COMMENT 'Number of active replicas',
    ADD COLUMN last_interruption_signal TIMESTAMP NULL COMMENT 'Last time interruption signal was received',
    ADD COLUMN interruption_handled_count INT DEFAULT 0 COMMENT 'Number of interruptions successfully handled',
    ADD COLUMN last_failover_at TIMESTAMP NULL COMMENT 'Last time failover to replica occurred';

-- Add foreign key for current replica
ALTER TABLE agents
    ADD CONSTRAINT fk_agents_current_replica
    FOREIGN KEY (current_replica_id) REFERENCES replica_instances(id) ON DELETE SET NULL;

-- ============================================================================
-- PART 8: SPOT INTERRUPTION HISTORY
-- ============================================================================

-- Track all spot interruption signals and handling
CREATE TABLE IF NOT EXISTS spot_interruption_events (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,

    -- Instance identification
    instance_id VARCHAR(255) NOT NULL,
    agent_id VARCHAR(255) NOT NULL,
    pool_id INT,

    -- Interruption details
    signal_type ENUM('rebalance-recommendation', 'termination-notice') NOT NULL,
    detected_at TIMESTAMP NOT NULL,
    termination_time TIMESTAMP,  -- actual termination time (for termination notice)

    -- Response
    response_action ENUM('created-replica', 'promoted-existing-replica', 'emergency-snapshot', 'no-action') NOT NULL,
    response_time_ms INT COMMENT 'Time taken to respond to signal',

    -- Replica handling
    replica_id VARCHAR(255),
    replica_ready BOOLEAN DEFAULT FALSE,
    replica_ready_time_ms INT,
    failover_completed BOOLEAN DEFAULT FALSE,
    failover_time_ms INT,

    -- Outcome
    data_loss_seconds INT DEFAULT 0 COMMENT 'Seconds of data lost during transition',
    success BOOLEAN DEFAULT TRUE,
    error_message TEXT,

    -- Metadata
    instance_age_hours DECIMAL(10,2),
    pool_interruption_probability DECIMAL(5,4),
    metadata JSON,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (agent_id) REFERENCES agents(id) ON DELETE CASCADE,
    FOREIGN KEY (pool_id) REFERENCES spot_pools(id) ON DELETE SET NULL,
    FOREIGN KEY (replica_id) REFERENCES replica_instances(id) ON DELETE SET NULL,
    INDEX idx_agent_detected (agent_id, detected_at),
    INDEX idx_signal_type (signal_type),
    INDEX idx_success (success)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- ============================================================================
-- PART 9: DATA PROCESSING JOBS LOG
-- ============================================================================

-- Track deduplication and interpolation jobs
CREATE TABLE IF NOT EXISTS data_processing_jobs (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,

    job_type ENUM('deduplication', 'gap-filling', 'interpolation', 'ml-dataset-refresh') NOT NULL,
    status ENUM('running', 'completed', 'failed') NOT NULL,

    -- Time range processed
    start_time TIMESTAMP NOT NULL,
    end_time TIMESTAMP NOT NULL,

    -- Processing stats
    records_processed INT DEFAULT 0,
    duplicates_found INT DEFAULT 0,
    gaps_filled INT DEFAULT 0,
    interpolations_created INT DEFAULT 0,
    errors_encountered INT DEFAULT 0,

    -- Performance
    execution_time_ms INT,

    -- Results
    result_summary JSON,
    error_log TEXT,

    -- Timestamps
    started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    completed_at TIMESTAMP NULL,

    INDEX idx_job_type_status (job_type, status),
    INDEX idx_started_at (started_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- ============================================================================
-- PART 10: MATERIALIZED VIEW FOR ML TRAINING (Simulated with Table + Scheduled Refresh)
-- ============================================================================

-- Since MySQL doesn't have true materialized views, we create a table
-- that gets refreshed periodically (every 6 hours via scheduled job)
CREATE TABLE IF NOT EXISTS pricing_snapshots_ml (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,

    -- Pool identification
    pool_id INT NOT NULL,
    instance_type VARCHAR(50) NOT NULL,
    region VARCHAR(50) NOT NULL,
    az VARCHAR(50) NOT NULL,

    -- Pricing
    spot_price DECIMAL(10,6) NOT NULL,
    ondemand_price DECIMAL(10,6) NOT NULL,
    savings_percent DECIMAL(5,2) NOT NULL,

    -- Time
    time_bucket TIMESTAMP NOT NULL,
    hour_of_day TINYINT NOT NULL,
    day_of_week TINYINT NOT NULL,
    day_of_month TINYINT NOT NULL,
    month TINYINT NOT NULL,
    year SMALLINT NOT NULL,

    -- Data quality (only high-confidence data included)
    confidence_score DECIMAL(3,2) NOT NULL,
    data_source ENUM('measured', 'interpolated') NOT NULL,

    -- Features for ML
    price_change_1h DECIMAL(10,6),  -- price change from 1 hour ago
    price_change_24h DECIMAL(10,6),  -- price change from 24 hours ago
    price_volatility_6h DECIMAL(10,6),  -- standard deviation over 6 hours
    pool_rank_by_price TINYINT,  -- rank within region (1=cheapest)

    -- Metadata
    refreshed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (pool_id) REFERENCES spot_pools(id) ON DELETE CASCADE,
    UNIQUE KEY unique_pool_bucket (pool_id, time_bucket),
    INDEX idx_pool_time (pool_id, time_bucket),
    INDEX idx_instance_type_time (instance_type, time_bucket),
    INDEX idx_confidence (confidence_score)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- ============================================================================
-- PART 11: INDEXES FOR PERFORMANCE
-- ============================================================================

-- Additional indexes for common queries
CREATE INDEX idx_pricing_raw_cleanup ON pricing_submissions_raw(received_at, is_duplicate);
CREATE INDEX idx_pricing_clean_ml_eligible ON pricing_snapshots_clean(confidence_score, data_source, time_bucket);
CREATE INDEX idx_replica_instances_active ON replica_instances(agent_id, is_active, status);

-- ============================================================================
-- PART 12: VIEWS FOR COMMON QUERIES
-- ============================================================================

-- View for active replicas with their parent agent info
CREATE OR REPLACE VIEW v_active_replicas AS
SELECT
    ri.id,
    ri.agent_id,
    ri.instance_id,
    ri.replica_type,
    ri.status,
    ri.sync_status,
    ri.sync_latency_ms,
    ri.hourly_cost,
    ri.created_at,
    ri.ready_at,
    a.logical_agent_id,
    a.hostname AS agent_hostname,
    a.status AS agent_status,
    c.name AS client_name,
    sp.pool_name,
    sp.instance_type,
    sp.region,
    sp.az
FROM replica_instances ri
JOIN agents a ON ri.agent_id = a.id
JOIN clients c ON a.client_id = c.id
LEFT JOIN spot_pools sp ON ri.pool_id = sp.id
WHERE ri.is_active = TRUE
  AND ri.status IN ('syncing', 'ready', 'promoted');

-- View for switch history with price details
CREATE OR REPLACE VIEW v_switch_history_with_prices AS
SELECT
    isw.id,
    isw.agent_id,
    isw.old_instance_id,
    isw.new_instance_id,
    isw.switch_reason,
    isw.old_instance_price,
    isw.new_instance_price,
    isw.ondemand_baseline,
    isw.price_confidence_old,
    isw.price_confidence_new,
    isw.price_data_source_old,
    isw.price_data_source_new,
    isw.estimated_savings,
    isw.savings_confidence,
    isw.switched_at,
    a.logical_agent_id,
    c.name AS client_name,
    old_pool.pool_name AS old_pool_name,
    old_pool.instance_type AS old_instance_type,
    new_pool.pool_name AS new_pool_name,
    new_pool.instance_type AS new_instance_type
FROM instance_switches isw
JOIN agents a ON isw.agent_id = a.id
JOIN clients c ON a.client_id = c.id
LEFT JOIN instances old_inst ON isw.old_instance_id = old_inst.id
LEFT JOIN instances new_inst ON isw.new_instance_id = new_inst.id
LEFT JOIN spot_pools old_pool ON old_inst.current_pool_id = old_pool.id
LEFT JOIN spot_pools new_pool ON new_inst.current_pool_id = new_pool.id
ORDER BY isw.switched_at DESC;

-- View for data quality dashboard
CREATE OR REPLACE VIEW v_data_quality_metrics AS
SELECT
    DATE(time_bucket) AS date,
    instance_type,
    region,
    COUNT(*) AS total_snapshots,
    SUM(CASE WHEN data_source = 'measured' THEN 1 ELSE 0 END) AS measured_count,
    SUM(CASE WHEN data_source = 'interpolated' THEN 1 ELSE 0 END) AS interpolated_count,
    AVG(confidence_score) AS avg_confidence,
    MIN(confidence_score) AS min_confidence,
    SUM(CASE WHEN confidence_score >= 0.95 THEN 1 ELSE 0 END) AS high_confidence_count,
    SUM(CASE WHEN confidence_score < 0.75 THEN 1 ELSE 0 END) AS low_confidence_count
FROM pricing_snapshots_clean
GROUP BY DATE(time_bucket), instance_type, region;

-- ============================================================================
-- PART 13: INITIAL DATA MIGRATION
-- ============================================================================

-- Migrate existing pricing_snapshots data to new clean table
-- (Run this carefully in production - may take time for large datasets)
INSERT INTO pricing_snapshots_clean (
    pool_id,
    instance_type,
    region,
    az,
    spot_price,
    ondemand_price,
    savings_percent,
    time_bucket,
    bucket_start,
    bucket_end,
    source_instance_id,
    source_type,
    confidence_score,
    data_source,
    created_at
)
SELECT
    pool_id,
    instance_type,
    region,
    az,
    spot_price,
    ondemand_price,
    ROUND(((ondemand_price - spot_price) / ondemand_price * 100), 2) AS savings_percent,
    FROM_UNIXTIME(FLOOR(UNIX_TIMESTAMP(observed_at) / 300) * 300) AS time_bucket,
    FROM_UNIXTIME(FLOOR(UNIX_TIMESTAMP(observed_at) / 300) * 300) AS bucket_start,
    FROM_UNIXTIME(FLOOR(UNIX_TIMESTAMP(observed_at) / 300) * 300 + 299) AS bucket_end,
    instance_id AS source_instance_id,
    'primary' AS source_type,
    1.00 AS confidence_score,
    'measured' AS data_source,
    created_at
FROM pricing_snapshots
WHERE created_at >= DATE_SUB(NOW(), INTERVAL 30 DAY)  -- only recent data
ON DUPLICATE KEY UPDATE
    spot_price = VALUES(spot_price);  -- keep existing if duplicate

-- ============================================================================
-- DONE
-- ============================================================================

-- Add migration tracking
INSERT INTO schema_migrations (version, description, applied_at)
VALUES (6, 'Replica Management & Data Quality System', NOW())
ON DUPLICATE KEY UPDATE applied_at = NOW();
