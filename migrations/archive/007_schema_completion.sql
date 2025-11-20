-- ============================================================================
-- Migration 007: Schema Completion & Optimization
-- Adds missing columns and tables to support all UI features
-- ============================================================================

-- ===========================================================================
-- PART 1: Update agents table with manual_replica_enabled
-- ===========================================================================

ALTER TABLE agents
    ADD COLUMN IF NOT EXISTS manual_replica_enabled BOOLEAN DEFAULT FALSE
        COMMENT 'Manual replica mode - user-controlled standby replica',
    ADD COLUMN IF NOT EXISTS current_replica_id VARCHAR(255) DEFAULT NULL
        COMMENT 'Currently active replica instance',
    ADD COLUMN IF NOT EXISTS last_interruption_signal TIMESTAMP NULL
        COMMENT 'Last time interruption signal was received',
    ADD COLUMN IF NOT EXISTS interruption_handled_count INT DEFAULT 0
        COMMENT 'Number of interruptions successfully handled',
    ADD COLUMN IF NOT EXISTS last_failover_at TIMESTAMP NULL
        COMMENT 'Last time failover to replica occurred';

-- Add index for replica queries
CREATE INDEX IF NOT EXISTS idx_agents_replica ON agents(manual_replica_enabled, replica_count);

-- ===========================================================================
-- PART 2: Add replica_instances table to main schema
-- ===========================================================================

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
    created_by VARCHAR(255),
    parent_instance_id VARCHAR(255),
    is_active BOOLEAN DEFAULT TRUE,

    -- State sync tracking
    sync_status ENUM('initializing', 'syncing', 'synced', 'out-of-sync') DEFAULT 'initializing',
    sync_latency_ms INT,
    last_sync_at TIMESTAMP NULL,
    state_transfer_progress DECIMAL(5,2) DEFAULT 0.00,

    -- Cost tracking
    hourly_cost DECIMAL(10,6),
    total_cost DECIMAL(10,4) DEFAULT 0.0000,

    -- Interruption handling
    interruption_signal_type ENUM('rebalance-recommendation', 'termination-notice', NULL) DEFAULT NULL,
    interruption_detected_at TIMESTAMP NULL,
    termination_time TIMESTAMP NULL,
    failover_completed_at TIMESTAMP NULL,

    -- Tags and metadata
    tags JSON,

    INDEX idx_replica_agent_status (agent_id, status),
    INDEX idx_replica_parent (parent_instance_id),
    INDEX idx_replica_created (created_at),
    INDEX idx_replica_active (agent_id, is_active)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
COMMENT='Replica instances for failover and manual standby';

-- ===========================================================================
-- PART 3: Add pricing_snapshots_clean for multi-pool charts
-- ===========================================================================

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
    time_bucket TIMESTAMP NOT NULL,
    bucket_start TIMESTAMP NOT NULL,
    bucket_end TIMESTAMP NOT NULL,

    -- Source attribution
    source_instance_id VARCHAR(255),
    source_agent_id VARCHAR(255),
    source_type ENUM('primary', 'replica-manual', 'replica-automatic', 'interpolated') NOT NULL,

    -- Data quality
    confidence_score DECIMAL(3,2) NOT NULL DEFAULT 1.00,
    data_source ENUM('measured', 'interpolated') NOT NULL DEFAULT 'measured',

    -- Auditing
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    UNIQUE KEY unique_pool_bucket (pool_id, time_bucket),
    INDEX idx_pool_time (pool_id, time_bucket),
    INDEX idx_time_bucket (time_bucket),
    INDEX idx_instance_type_time (instance_type, region, time_bucket)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
COMMENT='Clean time-bucketed pricing data for multi-pool charts';

-- ===========================================================================
-- PART 4: Add spot_interruption_events for tracking
-- ===========================================================================

CREATE TABLE IF NOT EXISTS spot_interruption_events (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,

    -- Instance identification
    instance_id VARCHAR(255) NOT NULL,
    agent_id VARCHAR(255) NOT NULL,
    pool_id INT,

    -- Interruption details
    signal_type ENUM('rebalance-recommendation', 'termination-notice') NOT NULL,
    detected_at TIMESTAMP NOT NULL,
    termination_time TIMESTAMP,

    -- Response
    response_action ENUM('created-replica', 'promoted-existing-replica', 'emergency-snapshot', 'no-action') NOT NULL,
    response_time_ms INT,

    -- Replica handling
    replica_id VARCHAR(255),
    replica_ready BOOLEAN DEFAULT FALSE,
    replica_ready_time_ms INT,
    failover_completed BOOLEAN DEFAULT FALSE,
    failover_time_ms INT,

    -- Outcome
    data_loss_seconds INT DEFAULT 0,
    success BOOLEAN DEFAULT TRUE,
    error_message TEXT,

    -- Metadata
    instance_age_hours DECIMAL(10,2),
    pool_interruption_probability DECIMAL(5,4),
    metadata JSON,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    INDEX idx_interruption_agent (agent_id, detected_at),
    INDEX idx_interruption_signal (signal_type),
    INDEX idx_interruption_success (success),
    INDEX idx_interruption_pool (pool_id, detected_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
COMMENT='Track all spot interruption events and responses';

-- ===========================================================================
-- PART 5: Add daily/weekly savings aggregation
-- ===========================================================================

CREATE TABLE IF NOT EXISTS client_savings_daily (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    client_id CHAR(36) NOT NULL,
    date DATE NOT NULL,

    -- Costs
    baseline_cost DECIMAL(15, 4) DEFAULT 0.0000,
    actual_cost DECIMAL(15, 4) DEFAULT 0.0000,
    savings DECIMAL(15, 4) DEFAULT 0.0000,
    savings_percentage DECIMAL(5, 2),

    -- Activity
    switch_count INT DEFAULT 0,
    instance_count INT DEFAULT 0,
    online_agent_count INT DEFAULT 0,

    computed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    UNIQUE KEY uk_client_date (client_id, date),
    INDEX idx_savings_daily_client (client_id),
    INDEX idx_savings_daily_date (date),

    FOREIGN KEY (client_id) REFERENCES clients(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
COMMENT='Daily savings summary for charts';

-- ===========================================================================
-- PART 6: Add pool reliability tracking
-- ===========================================================================

CREATE TABLE IF NOT EXISTS pool_reliability_metrics (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    pool_id INT NOT NULL,

    -- Time period
    period_start TIMESTAMP NOT NULL,
    period_end TIMESTAMP NOT NULL,

    -- Interruption stats
    interruption_count INT DEFAULT 0,
    rebalance_count INT DEFAULT 0,
    termination_count INT DEFAULT 0,

    -- Uptime
    total_instance_hours DECIMAL(10, 2) DEFAULT 0,
    interrupted_instance_hours DECIMAL(10, 2) DEFAULT 0,
    uptime_percentage DECIMAL(5, 2),

    -- Reliability score (0-100)
    reliability_score DECIMAL(5, 2) DEFAULT 100.00,

    -- Price stability
    price_volatility DECIMAL(10, 6),
    avg_price DECIMAL(10, 6),
    min_price DECIMAL(10, 6),
    max_price DECIMAL(10, 6),

    computed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    UNIQUE KEY uk_pool_period (pool_id, period_start),
    INDEX idx_reliability_pool (pool_id),
    INDEX idx_reliability_period (period_start, period_end),
    INDEX idx_reliability_score (reliability_score DESC)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
COMMENT='Pool reliability and interruption tracking for safest pool selection';

-- ===========================================================================
-- PART 7: Add instance real-time metrics (optional)
-- ===========================================================================

CREATE TABLE IF NOT EXISTS instance_metrics (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    instance_id VARCHAR(255) NOT NULL,
    agent_id VARCHAR(255) NOT NULL,

    -- System metrics
    cpu_utilization DECIMAL(5, 2),
    memory_utilization DECIMAL(5, 2),
    disk_utilization DECIMAL(5, 2),
    network_in_mbps DECIMAL(10, 2),
    network_out_mbps DECIMAL(10, 2),

    -- Application metrics (optional)
    request_rate DECIMAL(10, 2),
    error_rate DECIMAL(5, 2),
    response_time_ms DECIMAL(10, 2),

    recorded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    INDEX idx_metrics_instance_time (instance_id, recorded_at DESC),
    INDEX idx_metrics_agent (agent_id),
    INDEX idx_metrics_recent (recorded_at DESC)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
COMMENT='Real-time instance performance metrics';

-- ===========================================================================
-- PART 8: Create views for common queries
-- ===========================================================================

-- View for replicas with agent info
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

-- View for pool reliability rankings
CREATE OR REPLACE VIEW v_pool_reliability_ranking AS
SELECT
    sp.id AS pool_id,
    sp.pool_name,
    sp.instance_type,
    sp.region,
    sp.az,
    COALESCE(AVG(prm.reliability_score), 100) AS avg_reliability_score,
    COALESCE(SUM(prm.interruption_count), 0) AS total_interruptions,
    COALESCE(AVG(prm.uptime_percentage), 100) AS avg_uptime_percentage,
    COALESCE(AVG(prm.avg_price), 0) AS avg_price,
    COUNT(DISTINCT prm.id) AS data_points
FROM spot_pools sp
LEFT JOIN pool_reliability_metrics prm ON sp.id = prm.pool_id
    AND prm.period_start >= DATE_SUB(NOW(), INTERVAL 30 DAY)
GROUP BY sp.id, sp.pool_name, sp.instance_type, sp.region, sp.az
ORDER BY avg_reliability_score DESC, avg_price ASC;

-- ===========================================================================
-- PART 10: Add stored procedures for maintenance
-- ===========================================================================

DELIMITER //

-- Procedure to compute daily savings
CREATE PROCEDURE IF NOT EXISTS compute_daily_savings(IN p_date DATE)
BEGIN
    INSERT INTO client_savings_daily
    (client_id, date, baseline_cost, actual_cost, savings, switch_count, instance_count, online_agent_count)
    SELECT
        c.id,
        p_date,
        COALESCE(SUM(cr.baseline_cost), 0),
        COALESCE(SUM(cr.actual_cost), 0),
        COALESCE(SUM(cr.savings), 0),
        (SELECT COUNT(*) FROM switches s
         JOIN agents a2 ON s.agent_id = a2.id
         WHERE a2.client_id = c.id
         AND DATE(s.initiated_at) = p_date),
        (SELECT COUNT(DISTINCT i.id) FROM instances i
         WHERE i.client_id = c.id AND i.is_active = TRUE),
        (SELECT COUNT(DISTINCT a3.id) FROM agents a3
         WHERE a3.client_id = c.id AND a3.status = 'online')
    FROM clients c
    LEFT JOIN agents a ON a.client_id = c.id
    LEFT JOIN cost_records cr ON cr.agent_id = a.id
        AND DATE(cr.period_start) = p_date
    WHERE c.is_active = TRUE
    GROUP BY c.id
    ON DUPLICATE KEY UPDATE
        baseline_cost = VALUES(baseline_cost),
        actual_cost = VALUES(actual_cost),
        savings = VALUES(savings),
        switch_count = VALUES(switch_count),
        instance_count = VALUES(instance_count),
        online_agent_count = VALUES(online_agent_count),
        computed_at = NOW();
END //

-- Procedure to compute pool reliability
CREATE PROCEDURE IF NOT EXISTS compute_pool_reliability(IN p_hours INT)
BEGIN
    DECLARE period_start TIMESTAMP;
    DECLARE period_end TIMESTAMP;

    SET period_end = NOW();
    SET period_start = DATE_SUB(period_end, INTERVAL p_hours HOUR);

    INSERT INTO pool_reliability_metrics
    (pool_id, period_start, period_end, interruption_count, rebalance_count,
     termination_count, uptime_percentage, reliability_score, price_volatility,
     avg_price, min_price, max_price)
    SELECT
        sp.id,
        period_start,
        period_end,
        COALESCE(interruption_stats.interruption_count, 0),
        COALESCE(interruption_stats.rebalance_count, 0),
        COALESCE(interruption_stats.termination_count, 0),
        CASE
            WHEN COALESCE(interruption_stats.interruption_count, 0) = 0 THEN 100.00
            ELSE GREATEST(0, 100.00 - (interruption_stats.interruption_count * 5))
        END,
        CASE
            WHEN COALESCE(interruption_stats.interruption_count, 0) = 0 THEN 100.00
            ELSE GREATEST(0, 100.00 - (interruption_stats.interruption_count * 5))
        END,
        COALESCE(STDDEV(psc.spot_price), 0),
        COALESCE(AVG(psc.spot_price), 0),
        COALESCE(MIN(psc.spot_price), 0),
        COALESCE(MAX(psc.spot_price), 0)
    FROM spot_pools sp
    LEFT JOIN (
        SELECT
            pool_id,
            COUNT(*) AS interruption_count,
            SUM(CASE WHEN signal_type = 'rebalance-recommendation' THEN 1 ELSE 0 END) AS rebalance_count,
            SUM(CASE WHEN signal_type = 'termination-notice' THEN 1 ELSE 0 END) AS termination_count
        FROM spot_interruption_events
        WHERE detected_at >= period_start
        GROUP BY pool_id
    ) interruption_stats ON sp.id = interruption_stats.pool_id
    LEFT JOIN pricing_snapshots_clean psc ON sp.id = psc.pool_id
        AND psc.time_bucket >= period_start
    GROUP BY sp.id
    ON DUPLICATE KEY UPDATE
        interruption_count = VALUES(interruption_count),
        rebalance_count = VALUES(rebalance_count),
        termination_count = VALUES(termination_count),
        uptime_percentage = VALUES(uptime_percentage),
        reliability_score = VALUES(reliability_score),
        price_volatility = VALUES(price_volatility),
        avg_price = VALUES(avg_price),
        min_price = VALUES(min_price),
        max_price = VALUES(max_price),
        computed_at = NOW();
END //

DELIMITER ;

-- ===========================================================================
-- PART 11: Create indexes for performance
-- ===========================================================================

-- Additional indexes for common queries
CREATE INDEX IF NOT EXISTS idx_switches_client_date ON switches(client_id, DATE(initiated_at));
CREATE INDEX IF NOT EXISTS idx_cost_records_date ON cost_records(DATE(period_start), client_id);
CREATE INDEX IF NOT EXISTS idx_pricing_clean_recent ON pricing_snapshots_clean(pool_id, time_bucket DESC);

-- ===========================================================================
-- PART 12: Add migration tracking
-- ===========================================================================

CREATE TABLE IF NOT EXISTS schema_migrations (
    version INT PRIMARY KEY,
    description VARCHAR(255) NOT NULL,
    applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

INSERT INTO schema_migrations (version, description, applied_at)
VALUES (7, 'Schema Completion & Optimization', NOW())
ON DUPLICATE KEY UPDATE applied_at = NOW();

-- ===========================================================================
-- DONE
-- ===========================================================================

SELECT '✓ Migration 007 completed successfully!' AS status;
SELECT 'Added: manual_replica_enabled, replica_instances, pricing_snapshots_clean, spot_interruption_events' AS critical_features;
SELECT 'Added: daily_savings, pool_reliability_metrics, instance_metrics' AS optimization_features;
SELECT 'Added: v_active_replicas, v_pool_reliability_ranking views' AS helper_views;
SELECT 'Added: compute_daily_savings, compute_pool_reliability stored procedures' AS automation;
