-- CAST-AI Mini - Simplified Database Schema
-- Version: 3.0.0 (Agentless)
-- No agents, no replicas, no complex state management

DROP DATABASE IF EXISTS spot_optimizer;
CREATE DATABASE spot_optimizer CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
USE spot_optimizer;

-- ============================================================================
-- Core Tables
-- ============================================================================

-- Managed instances
CREATE TABLE instances (
    instance_id VARCHAR(20) PRIMARY KEY,
    instance_type VARCHAR(50) NOT NULL,
    az VARCHAR(20) NOT NULL,
    region VARCHAR(20) NOT NULL DEFAULT 'us-east-1',
    lifecycle ENUM('spot', 'on-demand') NOT NULL DEFAULT 'spot',
    state ENUM('running', 'stopping', 'stopped', 'terminated') NOT NULL DEFAULT 'running',

    -- Pricing
    current_spot_price DECIMAL(10, 6),
    on_demand_price DECIMAL(10, 6),
    current_discount_percent DECIMAL(5, 2),

    -- Auto controls
    auto_switch_enabled BOOLEAN NOT NULL DEFAULT true,
    auto_terminate_enabled BOOLEAN NOT NULL DEFAULT true,

    -- Cooldown
    last_decision_at TIMESTAMP NULL,
    cooldown_until TIMESTAMP NULL,

    -- Metadata
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    terminated_at TIMESTAMP NULL,

    INDEX idx_state (state),
    INDEX idx_auto_controls (auto_switch_enabled, auto_terminate_enabled),
    INDEX idx_cooldown (cooldown_until)
) ENGINE=InnoDB;

-- Decision history
CREATE TABLE decisions (
    id INT AUTO_INCREMENT PRIMARY KEY,
    decision_id VARCHAR(50) UNIQUE NOT NULL,
    instance_id VARCHAR(20) NOT NULL,

    -- Decision
    action ENUM('STAY', 'MIGRATE', 'DEFER') NOT NULL,
    recommended_instance_type VARCHAR(50),
    recommended_pool_id VARCHAR(100),
    recommended_az VARCHAR(20),

    -- Scores
    confidence DECIMAL(5, 4),
    expected_cost_savings_percent DECIMAL(5, 2),
    expected_stability_improvement_percent DECIMAL(5, 2),

    -- Reasoning
    reason TEXT,
    primary_factors JSON,

    -- Execution
    executed BOOLEAN DEFAULT false,
    execution_status ENUM('pending', 'in_progress', 'completed', 'failed') DEFAULT 'pending',
    execution_error TEXT,

    -- Metadata
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    executed_at TIMESTAMP NULL,

    INDEX idx_instance (instance_id),
    INDEX idx_action (action),
    INDEX idx_executed (executed),
    INDEX idx_created (created_at),
    FOREIGN KEY (instance_id) REFERENCES instances(instance_id) ON DELETE CASCADE
) ENGINE=InnoDB;

-- Switch events (migrations)
CREATE TABLE switches (
    id INT AUTO_INCREMENT PRIMARY KEY,
    decision_id VARCHAR(50),

    -- Old instance
    old_instance_id VARCHAR(20) NOT NULL,
    old_instance_type VARCHAR(50) NOT NULL,
    old_az VARCHAR(20) NOT NULL,
    old_spot_price DECIMAL(10, 6),

    -- New instance
    new_instance_id VARCHAR(20) NOT NULL,
    new_instance_type VARCHAR(50) NOT NULL,
    new_az VARCHAR(20) NOT NULL,
    new_spot_price DECIMAL(10, 6),

    -- Metrics
    cost_savings_percent DECIMAL(5, 2),
    stability_improvement_percent DECIMAL(5, 2),
    downtime_seconds INT DEFAULT 0,
    migration_cost_dollars DECIMAL(10, 4),

    -- Status
    status ENUM('initiated', 'launching', 'migrated', 'failed') DEFAULT 'initiated',
    error_message TEXT,

    -- Metadata
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    completed_at TIMESTAMP NULL,

    INDEX idx_old_instance (old_instance_id),
    INDEX idx_new_instance (new_instance_id),
    INDEX idx_status (status),
    INDEX idx_created (created_at),
    FOREIGN KEY (decision_id) REFERENCES decisions(decision_id) ON DELETE SET NULL
) ENGINE=InnoDB;

-- Spot pool pricing (current and historical)
CREATE TABLE pool_pricing (
    id INT AUTO_INCREMENT PRIMARY KEY,
    pool_id VARCHAR(100) NOT NULL,
    instance_type VARCHAR(50) NOT NULL,
    az VARCHAR(20) NOT NULL,
    region VARCHAR(20) NOT NULL DEFAULT 'us-east-1',

    -- Pricing
    spot_price DECIMAL(10, 6) NOT NULL,
    on_demand_price DECIMAL(10, 6) NOT NULL,
    discount_percent DECIMAL(5, 2),

    -- Stability metrics
    interruption_count_24h INT DEFAULT 0,
    price_volatility_24h DECIMAL(10, 6),

    -- Timestamp
    timestamp TIMESTAMP NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    UNIQUE KEY unique_pool_timestamp (pool_id, timestamp),
    INDEX idx_instance_type (instance_type),
    INDEX idx_az (az),
    INDEX idx_timestamp (timestamp)
) ENGINE=InnoDB;

-- System configuration
CREATE TABLE system_config (
    config_key VARCHAR(100) PRIMARY KEY,
    config_value TEXT NOT NULL,
    description TEXT,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
) ENGINE=InnoDB;

-- Insert default configuration
INSERT INTO system_config (config_key, config_value, description) VALUES
('decision_interval_minutes', '5', 'How often to run decision engine (minutes)'),
('cooldown_minutes', '10', 'Minimum time between decisions per instance'),
('min_confidence_threshold', '0.8', 'Minimum confidence to execute migration'),
('min_savings_threshold', '5.0', 'Minimum cost savings % to justify migration'),
('stability_weight', '0.70', 'Weight for stability in ranking (0-1)'),
('cost_weight', '0.30', 'Weight for cost in ranking (0-1)'),
('use_dynamic_baseline', 'true', 'Calculate baseline from current pool averages'),
('ml_models_enabled', 'true', 'Use ML models for predictions'),
('migration_cost_hours', '0.5', 'Equivalent cost of migration downtime (hours)');

-- ============================================================================
-- Views for easy access
-- ============================================================================

-- Active instances
CREATE VIEW v_active_instances AS
SELECT
    i.*,
    CASE
        WHEN i.cooldown_until IS NOT NULL AND i.cooldown_until > NOW()
        THEN 'in_cooldown'
        ELSE 'ready'
    END as cooldown_status,
    TIMESTAMPDIFF(MINUTE, i.last_decision_at, NOW()) as minutes_since_last_decision
FROM instances i
WHERE i.state IN ('running', 'stopping');

-- Recent decisions
CREATE VIEW v_recent_decisions AS
SELECT
    d.*,
    i.instance_type as current_instance_type,
    i.az as current_az,
    i.auto_switch_enabled,
    i.auto_terminate_enabled
FROM decisions d
JOIN instances i ON d.instance_id = i.instance_id
WHERE d.created_at >= DATE_SUB(NOW(), INTERVAL 7 DAY)
ORDER BY d.created_at DESC;

-- Switch summary
CREATE VIEW v_switch_summary AS
SELECT
    DATE(created_at) as switch_date,
    COUNT(*) as total_switches,
    SUM(CASE WHEN status = 'migrated' THEN 1 ELSE 0 END) as successful_switches,
    SUM(CASE WHEN status = 'failed' THEN 1 ELSE 0 END) as failed_switches,
    AVG(cost_savings_percent) as avg_savings_percent,
    AVG(downtime_seconds) as avg_downtime_seconds,
    SUM(migration_cost_dollars) as total_migration_cost
FROM switches
WHERE created_at >= DATE_SUB(NOW(), INTERVAL 30 DAY)
GROUP BY DATE(created_at)
ORDER BY switch_date DESC;

-- ============================================================================
-- Stored Procedures
-- ============================================================================

DELIMITER //

-- Get instance with cooldown check
CREATE PROCEDURE sp_get_instance_for_decision(IN p_instance_id VARCHAR(20))
BEGIN
    SELECT
        i.*,
        CASE
            WHEN i.cooldown_until IS NULL OR i.cooldown_until <= NOW()
            THEN true
            ELSE false
        END as can_decide,
        CASE
            WHEN i.cooldown_until IS NOT NULL AND i.cooldown_until > NOW()
            THEN TIMESTAMPDIFF(MINUTE, NOW(), i.cooldown_until)
            ELSE 0
        END as cooldown_minutes_remaining
    FROM instances i
    WHERE i.instance_id = p_instance_id
      AND i.state = 'running';
END //

-- Record decision
CREATE PROCEDURE sp_record_decision(
    IN p_decision_id VARCHAR(50),
    IN p_instance_id VARCHAR(20),
    IN p_action VARCHAR(20),
    IN p_recommended_instance_type VARCHAR(50),
    IN p_recommended_pool_id VARCHAR(100),
    IN p_recommended_az VARCHAR(20),
    IN p_confidence DECIMAL(5,4),
    IN p_expected_savings DECIMAL(5,2),
    IN p_expected_stability DECIMAL(5,2),
    IN p_reason TEXT,
    IN p_primary_factors JSON
)
BEGIN
    INSERT INTO decisions (
        decision_id, instance_id, action,
        recommended_instance_type, recommended_pool_id, recommended_az,
        confidence, expected_cost_savings_percent, expected_stability_improvement_percent,
        reason, primary_factors
    ) VALUES (
        p_decision_id, p_instance_id, p_action,
        p_recommended_instance_type, p_recommended_pool_id, p_recommended_az,
        p_confidence, p_expected_savings, p_expected_stability,
        p_reason, p_primary_factors
    );

    -- Update instance last decision time
    UPDATE instances
    SET last_decision_at = NOW()
    WHERE instance_id = p_instance_id;
END //

-- Record switch event
CREATE PROCEDURE sp_record_switch(
    IN p_decision_id VARCHAR(50),
    IN p_old_instance_id VARCHAR(20),
    IN p_new_instance_id VARCHAR(20),
    IN p_new_instance_type VARCHAR(50),
    IN p_new_az VARCHAR(20),
    IN p_new_spot_price DECIMAL(10,6)
)
BEGIN
    DECLARE v_old_instance_type VARCHAR(50);
    DECLARE v_old_az VARCHAR(20);
    DECLARE v_old_spot_price DECIMAL(10,6);

    -- Get old instance details
    SELECT instance_type, az, current_spot_price
    INTO v_old_instance_type, v_old_az, v_old_spot_price
    FROM instances
    WHERE instance_id = p_old_instance_id;

    -- Insert switch record
    INSERT INTO switches (
        decision_id,
        old_instance_id, old_instance_type, old_az, old_spot_price,
        new_instance_id, new_instance_type, new_az, new_spot_price,
        status
    ) VALUES (
        p_decision_id,
        p_old_instance_id, v_old_instance_type, v_old_az, v_old_spot_price,
        p_new_instance_id, p_new_instance_type, p_new_az, p_new_spot_price,
        'initiated'
    );

    -- Mark old instance as terminated
    UPDATE instances
    SET state = 'terminated', terminated_at = NOW()
    WHERE instance_id = p_old_instance_id;

    -- Insert new instance
    INSERT INTO instances (
        instance_id, instance_type, az, lifecycle,
        current_spot_price, state
    ) VALUES (
        p_new_instance_id, p_new_instance_type, p_new_az, 'spot',
        p_new_spot_price, 'running'
    );
END //

-- Update switch status
CREATE PROCEDURE sp_update_switch_status(
    IN p_new_instance_id VARCHAR(20),
    IN p_status VARCHAR(20),
    IN p_downtime_seconds INT,
    IN p_error_message TEXT
)
BEGIN
    UPDATE switches
    SET status = p_status,
        downtime_seconds = p_downtime_seconds,
        error_message = p_error_message,
        completed_at = NOW()
    WHERE new_instance_id = p_new_instance_id
      AND status = 'initiated';
END //

DELIMITER ;

-- ============================================================================
-- Sample Data for Testing
-- ============================================================================

-- Insert a test instance
INSERT INTO instances (
    instance_id, instance_type, az, lifecycle, state,
    current_spot_price, on_demand_price, current_discount_percent,
    auto_switch_enabled, auto_terminate_enabled
) VALUES (
    'i-test123456789',
    'm5.large',
    'us-east-1a',
    'spot',
    'running',
    0.045,
    0.096,
    53.13,
    true,
    true
);

-- ============================================================================
-- Cleanup and Maintenance
-- ============================================================================

-- Event to clean old pricing data (keep 90 days)
CREATE EVENT IF NOT EXISTS cleanup_old_pricing
ON SCHEDULE EVERY 1 DAY
DO
DELETE FROM pool_pricing
WHERE timestamp < DATE_SUB(NOW(), INTERVAL 90 DAY);

-- Event to clean old decision history (keep 180 days)
CREATE EVENT IF NOT EXISTS cleanup_old_decisions
ON SCHEDULE EVERY 1 DAY
DO
DELETE FROM decisions
WHERE created_at < DATE_SUB(NOW(), INTERVAL 180 DAY);

-- ============================================================================
-- Grants
-- ============================================================================

GRANT ALL PRIVILEGES ON spot_optimizer.* TO 'spotuser'@'%';
FLUSH PRIVILEGES;

-- ============================================================================
-- Schema complete
-- ============================================================================
