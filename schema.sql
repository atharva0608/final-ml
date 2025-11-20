-- ============================================================================
-- AWS Spot Optimizer - Cleaned MySQL Schema v6.0
-- ============================================================================
-- 
-- MySQL 8.0+ Compatible Schema
-- Cleaned version with only actively used tables, views, and procedures
-- 
-- REMOVED from v5.1:
--   - 6 unused tables (audit_logs, cost_records, model_predictions, ondemand_prices, replicas, spot_prices)
--   - 3 unused views (active_spot_pools, agent_overview, client_savings_summary)
--   - 11 unused stored procedures (all of them)
--   - 4 unused events (evt_daily_cleanup, evt_mark_stale_agents, evt_compute_monthly_savings, evt_update_total_savings)
-- ============================================================================

-- Set character set and disable foreign key checks for initial setup
SET NAMES utf8mb4;
SET CHARACTER SET utf8mb4;
SET FOREIGN_KEY_CHECKS = 0;

-- ============================================================================
-- CLIENTS
-- ============================================================================

CREATE TABLE IF NOT EXISTS clients (
    id CHAR(36) PRIMARY KEY DEFAULT (UUID()),
    name VARCHAR(255) NOT NULL,
    email VARCHAR(255) UNIQUE NOT NULL,
    client_token VARCHAR(255) UNIQUE NOT NULL,
    
    -- Subscription & Limits
    plan VARCHAR(50) DEFAULT 'free',
    max_agents INT DEFAULT 5,
    max_instances INT DEFAULT 10,
    
    -- Status & Metrics
    status VARCHAR(20) DEFAULT 'active',
    is_active BOOLEAN DEFAULT TRUE,
    total_savings DECIMAL(15, 4) DEFAULT 0.0000,
    
    -- Settings
    default_auto_terminate BOOLEAN DEFAULT TRUE,
    default_terminate_wait_seconds INT DEFAULT 300,
    default_auto_switch_enabled BOOLEAN DEFAULT TRUE,
    
    -- Timestamps
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    last_sync_at TIMESTAMP NULL,
    
    -- Additional metadata
    metadata JSON,
    
    INDEX idx_clients_token (client_token),
    INDEX idx_clients_status (status),
    INDEX idx_clients_active (is_active),
    INDEX idx_clients_created (created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
COMMENT='Client accounts that group agents and track overall savings';

-- ============================================================================
-- AGENTS
-- ============================================================================

CREATE TABLE IF NOT EXISTS agents (
    id CHAR(36) PRIMARY KEY DEFAULT (UUID()),
    client_id CHAR(36) NOT NULL,
    
    -- Identity (Persistent across instance switches)
    logical_agent_id VARCHAR(255) NOT NULL,
    hostname VARCHAR(255),
    
    -- Current Instance Info
    instance_id VARCHAR(50),
    instance_type VARCHAR(50),
    region VARCHAR(50),
    az VARCHAR(50),
    ami_id VARCHAR(50),
    
    -- Network
    private_ip VARCHAR(45),
    public_ip VARCHAR(45),
    
    -- Current Mode & Pool
    current_mode VARCHAR(20) DEFAULT 'unknown',
    current_pool_id VARCHAR(100),
    
    -- Pricing Context
    spot_price DECIMAL(10, 6),
    ondemand_price DECIMAL(10, 6),
    baseline_ondemand_price DECIMAL(10, 6),
    
    -- Agent Metadata
    agent_version VARCHAR(32),
    instance_count INT DEFAULT 0,
    
    -- Status
    status VARCHAR(20) DEFAULT 'offline',
    enabled BOOLEAN DEFAULT TRUE,
    last_heartbeat_at TIMESTAMP NULL,
    
    -- Configuration
    auto_switch_enabled BOOLEAN DEFAULT TRUE,
    auto_terminate_enabled BOOLEAN DEFAULT TRUE,
    terminate_wait_seconds INT DEFAULT 300,
    
    -- Replica Configuration
    replica_enabled BOOLEAN DEFAULT FALSE,
    replica_count INT DEFAULT 0,
    
    -- Timestamps
    installed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    last_switch_at TIMESTAMP NULL,
    terminated_at TIMESTAMP NULL,
    
    -- Additional metadata
    metadata JSON,
    
    -- Unique constraint: one logical agent per client
    UNIQUE KEY uk_client_logical (client_id, logical_agent_id),
    
    INDEX idx_agents_client (client_id),
    INDEX idx_agents_instance (instance_id),
    INDEX idx_agents_logical (logical_agent_id),
    INDEX idx_agents_status (status),
    INDEX idx_agents_enabled (enabled),
    INDEX idx_agents_heartbeat (last_heartbeat_at),
    INDEX idx_agents_mode (current_mode),
    INDEX idx_agents_pool (current_pool_id),
    
    CONSTRAINT fk_agents_client FOREIGN KEY (client_id) 
        REFERENCES clients(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
COMMENT='Individual agent instances with persistent logical identity';

-- ============================================================================
-- AGENT CONFIGURATIONS
-- ============================================================================

CREATE TABLE IF NOT EXISTS agent_configs (
    agent_id CHAR(36) PRIMARY KEY,
    
    -- Risk & Savings Thresholds
    min_savings_percent DECIMAL(5, 2) DEFAULT 15.00,
    risk_threshold DECIMAL(3, 2) DEFAULT 0.30,
    
    -- Switch Limits
    max_switches_per_week INT DEFAULT 10,
    max_switches_per_day INT DEFAULT 3,
    min_pool_duration_hours INT DEFAULT 2,
    
    -- Custom Configuration
    custom_config JSON,
    
    -- Timestamps
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    
    INDEX idx_agent_configs_updated (updated_at),
    
    CONSTRAINT fk_agent_configs_agent FOREIGN KEY (agent_id) 
        REFERENCES agents(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
COMMENT='Per-agent configuration for risk thresholds and switch limits';

-- ============================================================================
-- COMMANDS (Priority-based Command Queue)
-- ============================================================================

CREATE TABLE IF NOT EXISTS commands (
    id CHAR(36) PRIMARY KEY DEFAULT (UUID()),
    client_id CHAR(36) NOT NULL,
    agent_id CHAR(36) NOT NULL,
    
    -- Command Details
    command_type VARCHAR(50) NOT NULL,
    target_mode VARCHAR(20),
    target_pool_id VARCHAR(100),
    
    -- Instance Context
    instance_id VARCHAR(50),
    
    -- Priority (Higher = execute first)
    -- 100: Critical/Emergency, 75: Manual override, 50: ML urgent, 25: ML normal, 10: Scheduled
    priority INT DEFAULT 25,
    
    -- Timing
    terminate_wait_seconds INT,
    
    -- Status
    status VARCHAR(20) DEFAULT 'pending',
    
    -- Results
    success BOOLEAN,
    message TEXT,
    execution_result JSON,
    
    -- Metadata
    created_by VARCHAR(100),
    trigger_type VARCHAR(20),
    
    -- Timestamps
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    executed_at TIMESTAMP NULL,
    completed_at TIMESTAMP NULL,
    
    INDEX idx_commands_client (client_id),
    INDEX idx_commands_agent (agent_id),
    INDEX idx_commands_status (status),
    INDEX idx_commands_priority (priority DESC),
    INDEX idx_commands_pending (agent_id, status),
    INDEX idx_commands_type (command_type),
    INDEX idx_commands_created (created_at),
    
    CONSTRAINT fk_commands_client FOREIGN KEY (client_id) 
        REFERENCES clients(id) ON DELETE CASCADE,
    CONSTRAINT fk_commands_agent FOREIGN KEY (agent_id) 
        REFERENCES agents(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
COMMENT='Priority-based command queue for coordinating agent actions';

-- ============================================================================
-- SPOT POOLS
-- ============================================================================

CREATE TABLE IF NOT EXISTS spot_pools (
    id VARCHAR(128) PRIMARY KEY,
    instance_type VARCHAR(64) NOT NULL,
    region VARCHAR(32) NOT NULL,
    az VARCHAR(48) NOT NULL,
    
    -- Current Status
    is_active BOOLEAN DEFAULT TRUE,
    
    -- Timestamps
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    
    UNIQUE KEY uk_type_region_az (instance_type, region, az),
    INDEX idx_spot_pools_type_region (instance_type, region),
    INDEX idx_spot_pools_az (az),
    INDEX idx_spot_pools_active (is_active)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
COMMENT='Available spot instance pools with unique instance_type + region + AZ';

-- ============================================================================
-- PRICING DATA
-- ============================================================================

-- Spot Price History
CREATE TABLE IF NOT EXISTS spot_price_snapshots (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    pool_id VARCHAR(128) NOT NULL,
    price DECIMAL(10, 6) NOT NULL,
    captured_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    recorded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    INDEX idx_spot_snapshots_pool_time (pool_id, captured_at DESC),
    INDEX idx_spot_snapshots_captured (captured_at DESC),
    INDEX idx_spot_snapshots_pool (pool_id),
    INDEX idx_spot_snapshots_timeseries (pool_id, recorded_at DESC),
    
    CONSTRAINT fk_spot_snapshots_pool FOREIGN KEY (pool_id) 
        REFERENCES spot_pools(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
COMMENT='Historical spot price data for ML models and trend analysis';

-- On-Demand Price History
CREATE TABLE IF NOT EXISTS ondemand_price_snapshots (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    region VARCHAR(32) NOT NULL,
    instance_type VARCHAR(64) NOT NULL,
    price DECIMAL(10, 6) NOT NULL,
    captured_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    recorded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    INDEX idx_ondemand_snapshots_type_region_time (instance_type, region, captured_at DESC),
    INDEX idx_ondemand_snapshots_captured (captured_at DESC)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
COMMENT='Historical on-demand price data for cost calculations';

-- ============================================================================
-- PRICING REPORTS (from agents)
-- ============================================================================

CREATE TABLE IF NOT EXISTS pricing_reports (
    id CHAR(36) PRIMARY KEY DEFAULT (UUID()),
    agent_id CHAR(36) NOT NULL,
    
    -- Instance info at report time
    instance_id VARCHAR(50),
    instance_type VARCHAR(50),
    region VARCHAR(50),
    az VARCHAR(50),
    current_mode VARCHAR(20),
    current_pool_id VARCHAR(100),
    
    -- Pricing summary
    on_demand_price DECIMAL(10, 6),
    current_spot_price DECIMAL(10, 6),
    cheapest_pool_id VARCHAR(100),
    cheapest_pool_price DECIMAL(10, 6),
    
    -- Full data (JSON for flexibility)
    spot_pools JSON,
    
    -- Timing
    collected_at TIMESTAMP NULL,
    received_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    INDEX idx_pricing_reports_agent (agent_id),
    INDEX idx_pricing_reports_time (received_at DESC),
    INDEX idx_pricing_reports_instance_type (instance_type),
    INDEX idx_pricing_reports_collected (collected_at DESC),
    INDEX idx_pricing_reports_agent_time (agent_id, received_at DESC),
    
    CONSTRAINT fk_pricing_reports_agent FOREIGN KEY (agent_id) 
        REFERENCES agents(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
COMMENT='Pricing reports submitted by agents with current market data';

-- ============================================================================
-- INSTANCES
-- ============================================================================

CREATE TABLE IF NOT EXISTS instances (
    id VARCHAR(64) PRIMARY KEY,
    client_id CHAR(36) NOT NULL,
    agent_id CHAR(36),
    instance_type VARCHAR(64) NOT NULL,
    region VARCHAR(32) NOT NULL,
    az VARCHAR(48) NOT NULL,
    ami_id VARCHAR(64),
    current_mode VARCHAR(20) DEFAULT 'unknown',
    current_pool_id VARCHAR(128),
    spot_price DECIMAL(10, 6),
    ondemand_price DECIMAL(10, 6),
    baseline_ondemand_price DECIMAL(10, 6),
    is_active BOOLEAN DEFAULT TRUE,
    installed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_switch_at TIMESTAMP NULL,
    terminated_at TIMESTAMP NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    metadata JSON,
    
    INDEX idx_instances_client (client_id),
    INDEX idx_instances_agent (agent_id),
    INDEX idx_instances_type_region (instance_type, region),
    INDEX idx_instances_mode (current_mode),
    INDEX idx_instances_active (is_active),
    INDEX idx_instances_pool (current_pool_id),
    
    CONSTRAINT fk_instances_client FOREIGN KEY (client_id) 
        REFERENCES clients(id) ON DELETE CASCADE,
    CONSTRAINT fk_instances_agent FOREIGN KEY (agent_id) 
        REFERENCES agents(id) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ============================================================================
-- SWITCH HISTORY
-- ============================================================================

CREATE TABLE IF NOT EXISTS switches (
    id CHAR(36) PRIMARY KEY DEFAULT (UUID()),
    client_id CHAR(36) NOT NULL,
    agent_id CHAR(36) NOT NULL,
    command_id CHAR(36),
    
    -- Old Instance
    old_instance_id VARCHAR(50),
    old_instance_type VARCHAR(50),
    old_region VARCHAR(50),
    old_az VARCHAR(50),
    old_mode VARCHAR(20),
    old_pool_id VARCHAR(100),
    old_ami_id VARCHAR(50),
    
    -- New Instance
    new_instance_id VARCHAR(50),
    new_instance_type VARCHAR(50),
    new_region VARCHAR(50),
    new_az VARCHAR(50),
    new_mode VARCHAR(20),
    new_pool_id VARCHAR(100),
    new_ami_id VARCHAR(50),
    
    -- Pricing at switch time
    on_demand_price DECIMAL(10, 6),
    old_spot_price DECIMAL(10, 6),
    new_spot_price DECIMAL(10, 6),
    savings_impact DECIMAL(10, 6),
    
    -- Trigger & Context
    event_trigger VARCHAR(20),
    trigger_type VARCHAR(20),
    
    -- Snapshot Info
    snapshot_used BOOLEAN DEFAULT FALSE,
    snapshot_id VARCHAR(128),
    ami_id VARCHAR(64),
    
    -- Timing (Detailed metrics)
    initiated_at TIMESTAMP NULL,
    ami_created_at TIMESTAMP NULL,
    instance_launched_at TIMESTAMP NULL,
    instance_ready_at TIMESTAMP NULL,
    old_terminated_at TIMESTAMP NULL,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    -- Duration calculations (in seconds)
    total_duration_seconds INT,
    downtime_seconds INT,
    
    -- Additional timing data
    timing_data JSON,
    
    -- Status
    success BOOLEAN DEFAULT TRUE,
    error_message TEXT,
    
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    INDEX idx_switches_client (client_id),
    INDEX idx_switches_agent (agent_id),
    INDEX idx_switches_client_time (client_id, timestamp DESC),
    INDEX idx_switches_time (initiated_at DESC),
    INDEX idx_switches_trigger (event_trigger),
    INDEX idx_switches_instance (old_instance_id),
    INDEX idx_switches_timestamp (timestamp DESC),
    INDEX idx_switches_success (success),
    
    CONSTRAINT fk_switches_client FOREIGN KEY (client_id) 
        REFERENCES clients(id) ON DELETE CASCADE,
    CONSTRAINT fk_switches_agent FOREIGN KEY (agent_id) 
        REFERENCES agents(id) ON DELETE CASCADE,
    CONSTRAINT fk_switches_command FOREIGN KEY (command_id) 
        REFERENCES commands(id) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
COMMENT='Detailed switch history with timing metrics and cost impact';

-- ============================================================================
-- ML MODEL REGISTRY
-- ============================================================================

CREATE TABLE IF NOT EXISTS model_registry (
    id CHAR(36) PRIMARY KEY DEFAULT (UUID()),
    model_name VARCHAR(128) NOT NULL,
    model_type VARCHAR(50) NOT NULL,
    version VARCHAR(32) NOT NULL,
    
    -- Storage
    file_path VARCHAR(512) NOT NULL,
    
    -- Status
    is_active BOOLEAN DEFAULT FALSE,
    
    -- Metadata
    performance_metrics JSON,
    config JSON,
    description TEXT,
    
    -- Timestamps
    loaded_at TIMESTAMP NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    
    UNIQUE KEY uk_model_version (model_name, version),
    INDEX idx_model_registry_type_active (model_type, is_active),
    INDEX idx_model_registry_name (model_name),
    INDEX idx_model_registry_active (is_active)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
COMMENT='ML model versions and metadata for decision engines';

-- ============================================================================
-- RISK SCORES (Compatibility with v3.0)
-- ============================================================================

CREATE TABLE IF NOT EXISTS risk_scores (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    client_id CHAR(36) NOT NULL,
    agent_id CHAR(36),
    instance_id VARCHAR(64),
    risk_score DECIMAL(5, 4),
    recommended_action VARCHAR(50) NOT NULL,
    recommended_mode VARCHAR(20),
    recommended_pool_id VARCHAR(128),
    expected_savings_per_hour DECIMAL(10, 6),
    allowed BOOLEAN DEFAULT TRUE,
    reason TEXT,
    model_version VARCHAR(64),
    decision_metadata JSON,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    INDEX idx_risk_scores_client_time (client_id, created_at DESC),
    INDEX idx_risk_scores_instance (instance_id),
    INDEX idx_risk_scores_action (recommended_action),
    
    CONSTRAINT fk_risk_scores_client FOREIGN KEY (client_id) 
        REFERENCES clients(id) ON DELETE CASCADE,
    CONSTRAINT fk_risk_scores_agent FOREIGN KEY (agent_id) 
        REFERENCES agents(id) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ============================================================================
-- PENDING COMMANDS (v3.0 compatibility)
-- ============================================================================

CREATE TABLE IF NOT EXISTS pending_switch_commands (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    client_id CHAR(36) NOT NULL,
    agent_id CHAR(36) NOT NULL,
    instance_id VARCHAR(64) NOT NULL,
    target_mode VARCHAR(20) NOT NULL,
    target_pool_id VARCHAR(128),
    priority INT DEFAULT 50,
    terminate_wait_seconds INT DEFAULT 300,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    executed_at TIMESTAMP NULL,
    execution_result JSON,
    
    INDEX idx_pending_agent (agent_id, executed_at),
    INDEX idx_pending_priority (priority DESC),
    INDEX idx_pending_created (created_at),
    
    CONSTRAINT fk_pending_client FOREIGN KEY (client_id) 
        REFERENCES clients(id) ON DELETE CASCADE,
    CONSTRAINT fk_pending_agent FOREIGN KEY (agent_id) 
        REFERENCES agents(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ============================================================================
-- DECISION ENGINE LOG
-- ============================================================================

CREATE TABLE IF NOT EXISTS decision_engine_log (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    engine_type VARCHAR(64) NOT NULL,
    engine_version VARCHAR(32),
    instance_id VARCHAR(64),
    
    -- Input/Output
    input_data JSON NOT NULL,
    output_decision JSON NOT NULL,
    
    -- Performance
    execution_time_ms INT,
    
    -- Models used
    models_used JSON,
    
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    INDEX idx_decision_log_instance_time (instance_id, created_at DESC),
    INDEX idx_decision_log_created (created_at DESC),
    INDEX idx_decision_log_engine (engine_type)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
COMMENT='Audit log of decision engine executions with input/output data';

-- ============================================================================
-- SYSTEM EVENTS & LOGGING
-- ============================================================================

CREATE TABLE IF NOT EXISTS system_events (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    event_type VARCHAR(64) NOT NULL,
    severity VARCHAR(20) DEFAULT 'info',
    
    -- Entity references
    client_id CHAR(36),
    agent_id CHAR(36),
    instance_id VARCHAR(64),
    
    -- Event details
    message TEXT,
    metadata JSON,
    
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    INDEX idx_system_events_type_time (event_type, created_at DESC),
    INDEX idx_system_events_severity (severity),
    INDEX idx_system_events_client (client_id),
    INDEX idx_system_events_created (created_at DESC),
    
    CONSTRAINT fk_system_events_client FOREIGN KEY (client_id) 
        REFERENCES clients(id) ON DELETE CASCADE,
    CONSTRAINT fk_system_events_agent FOREIGN KEY (agent_id) 
        REFERENCES agents(id) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ============================================================================
-- NOTIFICATIONS
-- ============================================================================

CREATE TABLE IF NOT EXISTS notifications (
    id CHAR(36) PRIMARY KEY DEFAULT (UUID()),
    client_id CHAR(36) NOT NULL,
    agent_id CHAR(36),
    
    -- Notification content
    notification_type VARCHAR(50),
    title VARCHAR(255),
    message TEXT NOT NULL,
    severity VARCHAR(20) DEFAULT 'info',
    
    -- Status
    is_read BOOLEAN DEFAULT FALSE,
    sent_email BOOLEAN DEFAULT FALSE,
    sent_webhook BOOLEAN DEFAULT FALSE,
    
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    INDEX idx_notifications_client (client_id),
    INDEX idx_notifications_client_read (client_id, is_read),
    INDEX idx_notifications_unread (client_id, is_read),
    INDEX idx_notifications_created (created_at DESC),
    INDEX idx_notifications_type (notification_type),
    
    CONSTRAINT fk_notifications_client FOREIGN KEY (client_id) 
        REFERENCES clients(id) ON DELETE CASCADE,
    CONSTRAINT fk_notifications_agent FOREIGN KEY (agent_id) 
        REFERENCES agents(id) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ============================================================================
-- CLIENT GROWTH ANALYTICS
-- ============================================================================

CREATE TABLE IF NOT EXISTS clients_daily_snapshot (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    snapshot_date DATE NOT NULL UNIQUE,
    total_clients INT NOT NULL,
    new_clients_today INT DEFAULT 0,
    active_clients INT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    INDEX idx_snapshot_date (snapshot_date DESC)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
COMMENT='Daily snapshots of client counts for growth analytics';

-- ============================================================================
-- AGENT DECISION HISTORY
-- ============================================================================

CREATE TABLE IF NOT EXISTS agent_decision_history (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    agent_id CHAR(36) NOT NULL,
    client_id CHAR(36) NOT NULL,

    -- Decision details
    decision_type VARCHAR(50) NOT NULL COMMENT 'stay, switch_spot, switch_ondemand',
    recommended_action VARCHAR(50),
    recommended_pool_id VARCHAR(128),
    risk_score DECIMAL(5, 4),
    expected_savings DECIMAL(10, 6),

    -- Context at decision time
    current_mode VARCHAR(20),
    current_pool_id VARCHAR(128),
    current_price DECIMAL(10, 6),

    -- Timing
    decision_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    -- Execution tracking
    executed BOOLEAN DEFAULT FALSE,
    execution_time TIMESTAMP NULL,

    INDEX idx_agent_decision_agent_time (agent_id, decision_time DESC),
    INDEX idx_agent_decision_client (client_id),
    INDEX idx_agent_decision_type (decision_type),

    CONSTRAINT fk_agent_decision_agent FOREIGN KEY (agent_id)
        REFERENCES agents(id) ON DELETE CASCADE,
    CONSTRAINT fk_agent_decision_client FOREIGN KEY (client_id)
        REFERENCES clients(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
COMMENT='Historical log of all agent decisions made by the decision engine';

-- ============================================================================
-- CLIENT SAVINGS MONTHLY (Used for monthly calculations)
-- ============================================================================

CREATE TABLE IF NOT EXISTS client_savings_monthly (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    client_id CHAR(36) NOT NULL,
    year INT NOT NULL,
    month INT NOT NULL,
    
    -- Costs
    baseline_cost DECIMAL(15, 4) DEFAULT 0.0000,
    actual_cost DECIMAL(15, 4) DEFAULT 0.0000,
    savings DECIMAL(15, 4) DEFAULT 0.0000,
    savings_percentage DECIMAL(5, 2),
    
    -- Activity
    switch_count INT DEFAULT 0,
    instance_count INT DEFAULT 0,
    
    computed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    UNIQUE KEY uk_client_month (client_id, year, month),
    INDEX idx_savings_monthly_client (client_id),
    INDEX idx_savings_monthly_year_month (year, month),
    
    CONSTRAINT fk_savings_client FOREIGN KEY (client_id) 
        REFERENCES clients(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
COMMENT='Pre-aggregated monthly savings summary by client';

-- ============================================================================
-- VIEWS (Only used views)
-- ============================================================================

-- Recent switch activity
CREATE OR REPLACE VIEW recent_switches AS
SELECT 
    s.id,
    s.client_id,
    c.name AS client_name,
    s.agent_id,
    a.logical_agent_id,
    s.old_instance_id,
    s.new_instance_id,
    s.old_mode,
    s.new_mode,
    s.old_pool_id,
    s.new_pool_id,
    s.event_trigger,
    s.savings_impact,
    s.on_demand_price,
    s.old_spot_price,
    s.new_spot_price,
    s.total_duration_seconds,
    s.downtime_seconds,
    s.success,
    s.initiated_at,
    s.timestamp AS completed_at
FROM switches s
JOIN clients c ON c.id = s.client_id
JOIN agents a ON a.id = s.agent_id
ORDER BY s.initiated_at DESC;

-- ============================================================================
-- RE-ENABLE FOREIGN KEY CHECKS
-- ============================================================================

SET FOREIGN_KEY_CHECKS = 1;

-- ============================================================================
-- INITIAL DATA
-- ============================================================================

-- Create a demo client for testing
INSERT INTO clients (id, name, email, client_token, plan, max_agents, max_instances, is_active)
VALUES (UUID(), 'Demo Client', 'demo@example.com', 'demo-token-12345', 'pro', 10, 50, TRUE)
ON DUPLICATE KEY UPDATE name = name;

-- ============================================================================
-- VERIFICATION QUERIES
-- ============================================================================

-- Show all tables
SELECT 
    TABLE_NAME, 
    TABLE_ROWS, 
    ROUND(((DATA_LENGTH + INDEX_LENGTH) / 1024 / 1024), 2) AS 'Size (MB)'
FROM information_schema.TABLES
WHERE TABLE_SCHEMA = DATABASE()
ORDER BY TABLE_NAME;

-- ============================================================================
-- END OF SCHEMA
-- ============================================================================

SELECT '✓ AWS Spot Optimizer MySQL Schema v6.0 - Clean Installation Complete!' AS status;
