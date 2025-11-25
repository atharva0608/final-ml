-- ============================================================================
-- AWS Spot Optimizer - Complete Unified MySQL Schema v5.1
-- ============================================================================
--
-- MySQL 8.0+ Compatible Schema
-- Combines features from v3.0 and v4.0 schemas
--
-- Features:
-- - Client and agent management with logical identity preservation
-- - Priority-based command queue system
-- - Comprehensive pricing data collection and history
-- - Detailed switch tracking with timing metrics
-- - ML model registry and decision engine integration
-- - Spot pool management
-- - Agent configurations with risk thresholds
-- - Cost tracking and savings calculation
-- - Replica management
-- - Audit logging and notifications
-- - Stored procedures for common operations
-- - Automated cleanup events
-- ============================================================================

-- Ensure database is created with correct collation
-- CREATE DATABASE IF NOT EXISTS spot_optimizer
--   CHARACTER SET utf8mb4
--   COLLATE utf8mb4_unicode_ci;
-- USE spot_optimizer;

-- Set character set and disable foreign key checks for initial setup
SET NAMES utf8mb4;
SET CHARACTER SET utf8mb4;
SET collation_connection = utf8mb4_unicode_ci;
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
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='Client accounts that group agents and track overall savings';

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
    config_version INT DEFAULT 0 COMMENT 'Configuration version counter for forcing agent config refresh',
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
    manual_replica_enabled BOOLEAN DEFAULT FALSE,
    current_replica_id VARCHAR(255) DEFAULT NULL,
    
    -- Timestamps
    installed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    last_switch_at TIMESTAMP NULL,
    last_interruption_signal TIMESTAMP NULL,
    interruption_handled_count INT DEFAULT 0,
    last_failover_at TIMESTAMP NULL,
    terminated_at TIMESTAMP NULL,

    -- Agent v4.0.0 Enhanced Tracking
    last_termination_notice_at TIMESTAMP NULL COMMENT 'Last termination notice (2-min warning)',
    last_rebalance_recommendation_at TIMESTAMP NULL COMMENT 'Last rebalance recommendation received',
    emergency_replica_count INT DEFAULT 0 COMMENT 'Count of emergency replicas created',
    cleanup_enabled BOOLEAN DEFAULT TRUE COMMENT 'Enable automatic cleanup of AMIs/snapshots',
    last_cleanup_at TIMESTAMP NULL COMMENT 'Last successful cleanup operation',

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
    INDEX idx_agents_replica (manual_replica_enabled, replica_count),
    
    CONSTRAINT fk_agents_client FOREIGN KEY (client_id) 
        REFERENCES clients(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='Individual agent instances with persistent logical identity';

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
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='Per-agent configuration for risk thresholds and switch limits';

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
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='Priority-based command queue for coordinating agent actions';

-- ============================================================================
-- SPOT POOLS
-- ============================================================================

CREATE TABLE IF NOT EXISTS spot_pools (
    id VARCHAR(128) PRIMARY KEY,
    pool_name VARCHAR(255),
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
    INDEX idx_spot_pools_active (is_active),
    INDEX idx_spot_pools_name (pool_name)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='Available spot instance pools with unique instance_type + region + AZ';

-- Trigger to auto-generate pool_name if not provided
DELIMITER //
CREATE TRIGGER before_spot_pools_insert
BEFORE INSERT ON spot_pools
FOR EACH ROW
BEGIN
    IF NEW.pool_name IS NULL THEN
        SET NEW.pool_name = CONCAT(NEW.instance_type, ' (', NEW.az, ')');
    END IF;
END//

CREATE TRIGGER before_spot_pools_update
BEFORE UPDATE ON spot_pools
FOR EACH ROW
BEGIN
    IF NEW.pool_name IS NULL THEN
        SET NEW.pool_name = CONCAT(NEW.instance_type, ' (', NEW.az, ')');
    END IF;
END//
DELIMITER ;

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
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='Historical spot price data for ML models and trend analysis';

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
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='Historical on-demand price data for cost calculations';

-- Current On-Demand Prices (Materialized for quick access)
CREATE TABLE IF NOT EXISTS ondemand_prices (
    id CHAR(36) PRIMARY KEY DEFAULT (UUID()),
    instance_type VARCHAR(50) NOT NULL,
    region VARCHAR(50) NOT NULL,
    price DECIMAL(10, 6) NOT NULL,
    recorded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    UNIQUE KEY uk_type_region (instance_type, region),
    INDEX idx_ondemand_prices_type (instance_type, region)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Current Spot Prices (from agents)
CREATE TABLE IF NOT EXISTS spot_prices (
    id CHAR(36) PRIMARY KEY DEFAULT (UUID()),
    pool_id VARCHAR(100) NOT NULL,
    instance_type VARCHAR(50) NOT NULL,
    region VARCHAR(50) NOT NULL,
    az VARCHAR(50) NOT NULL,
    price DECIMAL(10, 6) NOT NULL,
    recorded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    INDEX idx_spot_prices_pool (pool_id),
    INDEX idx_spot_prices_type (instance_type),
    INDEX idx_spot_prices_time (recorded_at DESC),
    INDEX idx_spot_prices_timeseries (pool_id, recorded_at DESC),
    INDEX idx_spot_prices_analysis (instance_type, region, recorded_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

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
    
    CONSTRAINT fk_pricing_reports_agent FOREIGN KEY (agent_id) 
        REFERENCES agents(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='Pricing reports submitted by agents with current market data';

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
    instance_status VARCHAR(20) DEFAULT 'running_primary' COMMENT 'running_primary, running_replica, zombie, terminated',
    is_primary BOOLEAN DEFAULT TRUE COMMENT 'TRUE if primary instance, FALSE if replica',
    installed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_switch_at TIMESTAMP NULL,
    last_interruption_signal TIMESTAMP NULL,
    interruption_handled_count INT DEFAULT 0,
    last_failover_at TIMESTAMP NULL,
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
    INDEX idx_instances_status (instance_status),
    
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
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='Detailed switch history with timing metrics and cost impact';

-- Simple instance switch log for quick recording
CREATE TABLE IF NOT EXISTS instance_switches (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    agent_id VARCHAR(255) NOT NULL,
    old_instance_id VARCHAR(255),
    new_instance_id VARCHAR(255),
    switch_reason VARCHAR(100),
    switched_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    success BOOLEAN DEFAULT TRUE,
    error_message TEXT,
    metadata JSON,

    INDEX idx_instance_switches_agent (agent_id, switched_at DESC),
    INDEX idx_instance_switches_time (switched_at DESC),
    INDEX idx_instance_switches_old (old_instance_id),
    INDEX idx_instance_switches_new (new_instance_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='Simple switch log for internal tracking and quick queries';

-- ============================================================================
-- REPLICAS
-- ============================================================================

CREATE TABLE IF NOT EXISTS replica_instances (
    id VARCHAR(255) PRIMARY KEY,
    agent_id VARCHAR(255) NOT NULL,
    instance_id VARCHAR(255) NOT NULL,
    replica_type ENUM('manual', 'automatic-rebalance', 'automatic-termination') NOT NULL,
    pool_id VARCHAR(128),
    instance_type VARCHAR(50),
    region VARCHAR(50),
    az VARCHAR(50),

    -- Lifecycle tracking
    status ENUM('launching', 'syncing', 'ready', 'promoted', 'terminated', 'failed') NOT NULL DEFAULT 'launching',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    launched_at TIMESTAMP NULL,
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
    sync_started_at TIMESTAMP NULL COMMENT 'Timestamp when state synchronization started',
    sync_completed_at TIMESTAMP NULL COMMENT 'Timestamp when state synchronization completed successfully',
    state_transfer_progress DECIMAL(5,2) DEFAULT 0.00,
    error_message TEXT NULL COMMENT 'Error message details for failed replica status',

    -- Cost tracking
    hourly_cost DECIMAL(10,6),
    total_cost DECIMAL(10,4) DEFAULT 0.0000,
    total_runtime_hours DECIMAL(10, 2) DEFAULT 0 COMMENT 'Total hours replica has been running',
    accumulated_cost DECIMAL(15, 4) DEFAULT 0 COMMENT 'Accumulated cost for this replica',

    -- Interruption handling
    interruption_signal_type ENUM('rebalance-recommendation', 'termination-notice') DEFAULT NULL,
    interruption_detected_at TIMESTAMP NULL,
    termination_time TIMESTAMP NULL,
    failover_completed_at TIMESTAMP NULL,

    -- Tags and metadata
    tags JSON,

    INDEX idx_replica_agent_status (agent_id, status),
    INDEX idx_replica_parent (parent_instance_id),
    INDEX idx_replica_created (created_at),
    INDEX idx_replica_active (agent_id, is_active),
    INDEX idx_replica_sync_completed (sync_completed_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ===========================================================================
-- PRICING SNAPSHOTS CLEAN (Time-bucketed for charts)
-- ===========================================================================

CREATE TABLE IF NOT EXISTS pricing_snapshots_clean (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    pool_id VARCHAR(128) NOT NULL,
    instance_type VARCHAR(50) NOT NULL,
    region VARCHAR(50) NOT NULL,
    az VARCHAR(50) NOT NULL,
    spot_price DECIMAL(10,6) NOT NULL,
    ondemand_price DECIMAL(10,6),
    savings_percent DECIMAL(5,2),
    time_bucket TIMESTAMP NOT NULL,
    bucket_start TIMESTAMP NOT NULL,
    bucket_end TIMESTAMP NOT NULL,
    source_instance_id VARCHAR(255),
    source_agent_id VARCHAR(255),
    source_type ENUM('primary', 'replica-manual', 'replica-automatic', 'interpolated') NOT NULL,
    confidence_score DECIMAL(3,2) NOT NULL DEFAULT 1.00,
    data_source ENUM('measured', 'interpolated') NOT NULL DEFAULT 'measured',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY unique_pool_bucket (pool_id, time_bucket),
    INDEX idx_pool_time (pool_id, time_bucket),
    INDEX idx_time_bucket (time_bucket),
    INDEX idx_instance_type_time (instance_type, region, time_bucket)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='Clean time-bucketed pricing data for multi-pool charts';

-- ===========================================================================
-- RAW PRICING SUBMISSIONS (Before Deduplication)
-- ===========================================================================

CREATE TABLE IF NOT EXISTS pricing_submissions_raw (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    submission_id CHAR(36) NOT NULL UNIQUE,
    source_instance_id VARCHAR(255) NOT NULL,
    source_agent_id VARCHAR(255) NOT NULL,
    source_type ENUM('primary', 'replica-manual', 'replica-automatic') NOT NULL,
    pool_id VARCHAR(128) NOT NULL,
    instance_type VARCHAR(50) NOT NULL,
    region VARCHAR(50) NOT NULL,
    az VARCHAR(50) NOT NULL,
    spot_price DECIMAL(10,6) NOT NULL,
    ondemand_price DECIMAL(10,6),
    observed_at TIMESTAMP NOT NULL,
    submitted_at TIMESTAMP NOT NULL,
    received_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    client_id CHAR(36),
    batch_id VARCHAR(100),
    is_duplicate BOOLEAN DEFAULT FALSE,
    duplicate_of CHAR(36),
    processed BOOLEAN DEFAULT FALSE,
    processed_at TIMESTAMP NULL,

    INDEX idx_submission_id (submission_id),
    INDEX idx_pool_observed (pool_id, observed_at),
    INDEX idx_received (received_at),
    INDEX idx_duplicate (is_duplicate, processed),
    INDEX idx_agent_submitted (source_agent_id, submitted_at),
    FOREIGN KEY (pool_id) REFERENCES spot_pools(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='Raw pricing submissions before deduplication and quality checks';

-- ===========================================================================
-- DATA PROCESSING JOBS
-- ===========================================================================

CREATE TABLE IF NOT EXISTS data_processing_jobs (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    job_type ENUM('deduplication', 'interpolation', 'gap-filling', 'cleanup') NOT NULL,
    status ENUM('pending', 'running', 'completed', 'failed') NOT NULL DEFAULT 'pending',
    start_time TIMESTAMP NOT NULL,
    end_time TIMESTAMP NULL,
    records_processed INT DEFAULT 0,
    records_inserted INT DEFAULT 0,
    records_updated INT DEFAULT 0,
    records_deleted INT DEFAULT 0,
    error_message TEXT,
    metadata JSON,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    completed_at TIMESTAMP NULL,

    INDEX idx_job_type_status (job_type, status),
    INDEX idx_created (created_at),
    INDEX idx_status (status)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='Track batch data processing jobs for monitoring and debugging';

-- ===========================================================================
-- PRICING SNAPSHOTS (ML and Interpolated)
-- ===========================================================================

CREATE TABLE IF NOT EXISTS pricing_snapshots_interpolated (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    pool_id VARCHAR(128) NOT NULL,
    instance_type VARCHAR(50) NOT NULL,
    region VARCHAR(50) NOT NULL,
    az VARCHAR(50) NOT NULL,
    spot_price DECIMAL(10,6) NOT NULL,
    time_bucket TIMESTAMP NOT NULL,
    interpolated_from_before BIGINT,
    interpolated_from_after BIGINT,
    confidence_score DECIMAL(3,2) NOT NULL DEFAULT 0.80,
    gap_duration_minutes INT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    UNIQUE KEY unique_pool_bucket (pool_id, time_bucket),
    INDEX idx_pool_time (pool_id, time_bucket),
    INDEX idx_confidence (confidence_score),
    FOREIGN KEY (pool_id) REFERENCES spot_pools(id) ON DELETE CASCADE,
    FOREIGN KEY (interpolated_from_before) REFERENCES pricing_snapshots_clean(id) ON DELETE SET NULL,
    FOREIGN KEY (interpolated_from_after) REFERENCES pricing_snapshots_clean(id) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='Interpolated pricing data for filling gaps in time series';

CREATE TABLE IF NOT EXISTS pricing_snapshots_ml (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    pool_id VARCHAR(128) NOT NULL,
    instance_type VARCHAR(50) NOT NULL,
    region VARCHAR(50) NOT NULL,
    az VARCHAR(50) NOT NULL,
    predicted_price DECIMAL(10,6) NOT NULL,
    time_bucket TIMESTAMP NOT NULL,
    model_id VARCHAR(100),
    model_version VARCHAR(50),
    prediction_confidence DECIMAL(3,2),
    based_on_measurements INT,
    features_used JSON,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    UNIQUE KEY unique_pool_bucket (pool_id, time_bucket),
    INDEX idx_pool_time (pool_id, time_bucket),
    INDEX idx_model (model_id, model_version),
    INDEX idx_confidence (prediction_confidence),
    FOREIGN KEY (pool_id) REFERENCES spot_pools(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='ML-predicted pricing data for forecasting and optimization';


-- ===========================================================================
-- SPOT INTERRUPTION EVENTS
-- ===========================================================================

CREATE TABLE IF NOT EXISTS spot_interruption_events (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    instance_id VARCHAR(255) NOT NULL,
    agent_id VARCHAR(255) NOT NULL,
    pool_id VARCHAR(128),
    signal_type ENUM('rebalance-recommendation', 'termination-notice') NOT NULL,
    detected_at TIMESTAMP NOT NULL,
    termination_time TIMESTAMP,
    response_action ENUM('created-replica', 'promoted-existing-replica', 'emergency-snapshot', 'no-action') NOT NULL,
    response_time_ms INT,
    replica_id VARCHAR(255),
    replica_ready BOOLEAN DEFAULT FALSE,
    replica_ready_time_ms INT,
    failover_completed BOOLEAN DEFAULT FALSE,
    failover_time_ms INT,
    data_loss_seconds INT DEFAULT 0,
    success BOOLEAN DEFAULT TRUE,
    error_message TEXT,
    instance_age_hours DECIMAL(10,2),
    pool_interruption_probability DECIMAL(5,4),
    metadata JSON,

    -- ML Training Features
    spot_price_at_interruption DECIMAL(10,6) COMMENT 'Spot price when interrupted',
    price_trend_before VARCHAR(20) COMMENT 'rising/falling/stable in last hour',
    price_change_percent DECIMAL(5,2) COMMENT 'Price change % in last hour',
    time_since_price_change_minutes INT COMMENT 'Minutes since last price change',
    day_of_week TINYINT COMMENT '0=Sunday, 6=Saturday',
    hour_of_day TINYINT COMMENT '0-23 UTC',
    pool_historical_interruption_rate DECIMAL(5,4) COMMENT 'Historical interruption rate for pool',
    region_interruption_rate DECIMAL(5,4) COMMENT 'Historical rate for region',
    competing_instances_count INT COMMENT 'Other instances in same pool',
    previous_interruptions_count INT DEFAULT 0 COMMENT 'Times this agent was interrupted before',
    time_since_last_interruption_hours DECIMAL(10,2) COMMENT 'Hours since last interruption',

    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_interruption_agent (agent_id, detected_at),
    INDEX idx_interruption_signal (signal_type),
    INDEX idx_interruption_success (success),
    INDEX idx_interruption_pool (pool_id, detected_at),
    INDEX idx_interruption_ml_features (pool_id, day_of_week, hour_of_day, spot_price_at_interruption),
    INDEX idx_interruption_time_patterns (day_of_week, hour_of_day, signal_type),
    INDEX idx_interruption_price_trend (price_trend_before, price_change_percent)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='Track all spot interruption events and responses for ML training';

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
    upload_session_id CHAR(36),

    -- Status
    is_active BOOLEAN DEFAULT FALSE,
    is_fallback BOOLEAN DEFAULT FALSE,

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
    INDEX idx_model_registry_active (is_active),
    INDEX idx_model_registry_session (upload_session_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='ML model versions and metadata for decision engines';

CREATE TABLE IF NOT EXISTS model_upload_sessions (
    id CHAR(36) PRIMARY KEY DEFAULT (UUID()),
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
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='Tracks model upload sessions for versioning (keeps last 2 sessions)';

-- ============================================================================
-- ML MODEL PREDICTIONS & RISK SCORES
-- ============================================================================

CREATE TABLE IF NOT EXISTS model_predictions (
    id CHAR(36) PRIMARY KEY DEFAULT (UUID()),
    client_id CHAR(36) NOT NULL,
    agent_id CHAR(36) NOT NULL,
    instance_id VARCHAR(50),
    
    -- Model info
    model_name VARCHAR(100),
    model_version VARCHAR(64),
    
    -- Risk Assessment
    risk_score DECIMAL(5, 4),
    interruption_risk DECIMAL(5, 4),
    price_volatility_risk DECIMAL(5, 4),
    
    -- Recommendation
    recommended_action VARCHAR(50),
    recommended_mode VARCHAR(20),
    recommended_pool_id VARCHAR(100),
    confidence DECIMAL(5, 4),
    
    -- Pricing context
    current_price DECIMAL(10, 6),
    predicted_price DECIMAL(10, 6),
    expected_savings_per_hour DECIMAL(10, 6),
    potential_savings DECIMAL(10, 6),
    
    -- Decision Status
    allowed BOOLEAN DEFAULT TRUE,
    reason TEXT,
    
    -- Features & Metadata
    features JSON,
    decision_metadata JSON,
    
    -- Action tracking
    action_taken BOOLEAN DEFAULT FALSE,
    command_id CHAR(36),
    
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    INDEX idx_predictions_client (client_id),
    INDEX idx_predictions_agent (agent_id),
    INDEX idx_predictions_instance (instance_id),
    INDEX idx_predictions_client_time (client_id, created_at DESC),
    INDEX idx_predictions_time (created_at DESC),
    INDEX idx_predictions_action (recommended_action),
    INDEX idx_predictions_confidence (confidence DESC),
    
    CONSTRAINT fk_predictions_client FOREIGN KEY (client_id) 
        REFERENCES clients(id) ON DELETE CASCADE,
    CONSTRAINT fk_predictions_agent FOREIGN KEY (agent_id) 
        REFERENCES agents(id) ON DELETE CASCADE,
    CONSTRAINT fk_predictions_command FOREIGN KEY (command_id) 
        REFERENCES commands(id) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='ML model predictions and risk assessments for agent decisions';

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
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='Audit log of decision engine executions with input/output data';

-- ============================================================================
-- COST TRACKING
-- ============================================================================

CREATE TABLE IF NOT EXISTS cost_records (
    id CHAR(36) PRIMARY KEY DEFAULT (UUID()),
    client_id CHAR(36) NOT NULL,
    agent_id CHAR(36) NOT NULL,
    
    -- Period
    period_start TIMESTAMP NOT NULL,
    period_end TIMESTAMP NOT NULL,
    
    -- Instance info
    instance_id VARCHAR(50),
    instance_type VARCHAR(50),
    mode VARCHAR(20),
    region VARCHAR(50),
    
    -- Hours
    hours_running DECIMAL(10, 4),
    
    -- Costs
    actual_cost DECIMAL(12, 6),
    ondemand_cost DECIMAL(12, 6),
    baseline_cost DECIMAL(15, 4),
    savings DECIMAL(12, 6),
    savings_percentage DECIMAL(5, 2),
    
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    INDEX idx_cost_client (client_id),
    INDEX idx_cost_agent (agent_id),
    INDEX idx_cost_period (period_start, period_end),
    INDEX idx_cost_mode (mode),
    
    CONSTRAINT fk_cost_client FOREIGN KEY (client_id)
        REFERENCES clients(id) ON DELETE CASCADE,
    CONSTRAINT fk_cost_agent FOREIGN KEY (agent_id)
        REFERENCES agents(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='Cost tracking records for savings calculations and reporting';

-- Monthly Savings Summary
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
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ===========================================================================
-- CLIENT SAVINGS DAILY
-- ===========================================================================

CREATE TABLE IF NOT EXISTS client_savings_daily (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    client_id CHAR(36) NOT NULL,
    date DATE NOT NULL,
    baseline_cost DECIMAL(15, 4) DEFAULT 0.0000,
    actual_cost DECIMAL(15, 4) DEFAULT 0.0000,
    savings DECIMAL(15, 4) DEFAULT 0.0000,
    savings_percentage DECIMAL(5, 2),
    switch_count INT DEFAULT 0,
    instance_count INT DEFAULT 0,
    online_agent_count INT DEFAULT 0,
    computed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uk_client_date (client_id, date),
    INDEX idx_savings_daily_client (client_id),
    INDEX idx_savings_daily_date (date),
    FOREIGN KEY (client_id) REFERENCES clients(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='Daily savings summary for charts';

-- ============================================================================
-- ANALYTICS & TRACKING
-- ============================================================================

CREATE TABLE IF NOT EXISTS clients_daily_snapshot (
    snapshot_date DATE PRIMARY KEY,
    total_clients INT NOT NULL DEFAULT 0,
    new_clients_today INT NOT NULL DEFAULT 0,
    active_clients INT NOT NULL DEFAULT 0,

    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    INDEX idx_snapshot_date (snapshot_date DESC)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='Daily snapshots of client counts for growth analytics';

CREATE TABLE IF NOT EXISTS agent_decision_history (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    agent_id CHAR(36) NOT NULL,
    client_id CHAR(36) NOT NULL,

    -- Decision details
    decision_type VARCHAR(64) NOT NULL,
    recommended_action VARCHAR(64),
    recommended_pool_id VARCHAR(128),
    risk_score DECIMAL(5, 4),
    expected_savings DECIMAL(15, 4),

    -- Current state at decision time
    current_mode VARCHAR(20),
    current_pool_id VARCHAR(128),
    current_price DECIMAL(10, 6),

    decision_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    INDEX idx_decision_agent (agent_id, decision_time DESC),
    INDEX idx_decision_client (client_id, decision_time DESC),
    INDEX idx_decision_time (decision_time DESC),
    INDEX idx_decision_type (decision_type),

    CONSTRAINT fk_decision_agent FOREIGN KEY (agent_id)
        REFERENCES agents(id) ON DELETE CASCADE,
    CONSTRAINT fk_decision_client FOREIGN KEY (client_id)
        REFERENCES clients(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='History of all agent decision engine recommendations';

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
-- AUDIT LOG
-- ============================================================================

CREATE TABLE IF NOT EXISTS audit_logs (
    id CHAR(36) PRIMARY KEY DEFAULT (UUID()),
    
    -- Entity
    entity_type VARCHAR(50),
    entity_id CHAR(36),
    
    -- Action
    action VARCHAR(100),
    
    -- Actor
    actor_type VARCHAR(50),
    actor_id VARCHAR(100),
    
    -- Details
    details JSON,
    changes JSON,
    
    -- Request info
    ip_address VARCHAR(45),
    user_agent TEXT,
    
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    INDEX idx_audit_entity (entity_type, entity_id),
    INDEX idx_audit_action (action),
    INDEX idx_audit_actor (actor_type, actor_id),
    INDEX idx_audit_time (created_at DESC)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='Comprehensive audit trail of all system actions';

-- ============================================================================
-- NOTIFICATIONS
-- ============================================================================


-- ===========================================================================
-- POOL RELIABILITY METRICS
-- ===========================================================================

CREATE TABLE IF NOT EXISTS pool_reliability_metrics (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    pool_id VARCHAR(128) NOT NULL,
    period_start TIMESTAMP NOT NULL,
    period_end TIMESTAMP NOT NULL,
    interruption_count INT DEFAULT 0,
    rebalance_count INT DEFAULT 0,
    termination_count INT DEFAULT 0,
    total_instance_hours DECIMAL(10, 2) DEFAULT 0,
    interrupted_instance_hours DECIMAL(10, 2) DEFAULT 0,
    uptime_percentage DECIMAL(5, 2),
    reliability_score DECIMAL(5, 2) DEFAULT 100.00,
    price_volatility DECIMAL(10, 6),
    avg_price DECIMAL(10, 6),
    min_price DECIMAL(10, 6),
    max_price DECIMAL(10, 6),
    computed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uk_pool_period (pool_id, period_start),
    INDEX idx_reliability_pool (pool_id),
    INDEX idx_reliability_period (period_start, period_end),
    INDEX idx_reliability_score (reliability_score DESC)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='Pool reliability and interruption tracking';

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
-- VIEWS
-- ============================================================================

-- Agent overview with current pricing
CREATE OR REPLACE VIEW agent_overview AS
SELECT 
    a.id,
    a.client_id,
    c.name AS client_name,
    a.logical_agent_id,
    a.instance_id,
    a.instance_type,
    a.region,
    a.az,
    a.current_mode,
    a.current_pool_id,
    a.status,
    a.enabled,
    a.auto_switch_enabled,
    a.last_heartbeat_at,
    a.agent_version,
    a.instance_count,
    
    -- Latest pricing (using subquery for MySQL compatibility)
    (SELECT pr.on_demand_price FROM pricing_reports pr 
     WHERE pr.agent_id = a.id ORDER BY pr.received_at DESC LIMIT 1) AS on_demand_price,
    (SELECT pr.current_spot_price FROM pricing_reports pr 
     WHERE pr.agent_id = a.id ORDER BY pr.received_at DESC LIMIT 1) AS current_spot_price,
    (SELECT pr.cheapest_pool_id FROM pricing_reports pr 
     WHERE pr.agent_id = a.id ORDER BY pr.received_at DESC LIMIT 1) AS cheapest_pool_id,
    (SELECT pr.cheapest_pool_price FROM pricing_reports pr 
     WHERE pr.agent_id = a.id ORDER BY pr.received_at DESC LIMIT 1) AS cheapest_pool_price,
    
    -- Pending commands
    (SELECT COUNT(*) FROM commands cmd 
     WHERE cmd.agent_id = a.id AND cmd.status = 'pending') AS pending_commands,
    
    -- Calculate potential savings
    CASE 
        WHEN a.current_mode = 'spot' AND 
             (SELECT pr.on_demand_price FROM pricing_reports pr 
              WHERE pr.agent_id = a.id ORDER BY pr.received_at DESC LIMIT 1) > 0 AND
             (SELECT pr.current_spot_price FROM pricing_reports pr 
              WHERE pr.agent_id = a.id ORDER BY pr.received_at DESC LIMIT 1) > 0
        THEN ROUND((((SELECT pr.on_demand_price FROM pricing_reports pr 
                      WHERE pr.agent_id = a.id ORDER BY pr.received_at DESC LIMIT 1) - 
                     (SELECT pr.current_spot_price FROM pricing_reports pr 
                      WHERE pr.agent_id = a.id ORDER BY pr.received_at DESC LIMIT 1)) / 
                    (SELECT pr.on_demand_price FROM pricing_reports pr 
                     WHERE pr.agent_id = a.id ORDER BY pr.received_at DESC LIMIT 1) * 100), 1)
        ELSE 0
    END AS current_savings_pct,
    
    -- Last switch
    a.last_switch_at,
    
    -- Agent config
    ac.min_savings_percent,
    ac.risk_threshold,
    ac.max_switches_per_week
    
FROM agents a
JOIN clients c ON c.id = a.client_id
LEFT JOIN agent_configs ac ON ac.agent_id = a.id;

-- Client savings summary
CREATE OR REPLACE VIEW client_savings_summary AS
SELECT 
    c.id AS client_id,
    c.name AS client_name,
    c.status,
    c.plan,
    COUNT(DISTINCT a.id) AS total_agents,
    COUNT(DISTINCT CASE WHEN a.status = 'online' THEN a.id END) AS online_agents,
    COUNT(DISTINCT CASE WHEN a.enabled = TRUE THEN a.id END) AS enabled_agents,
    
    -- Total savings (last 30 days)
    COALESCE(SUM(cr.savings), 0) AS total_savings_30d,
    COALESCE(SUM(cr.actual_cost), 0) AS total_cost_30d,
    COALESCE(SUM(cr.ondemand_cost), 0) AS total_ondemand_cost_30d,
    
    CASE 
        WHEN SUM(cr.ondemand_cost) > 0 
        THEN ROUND((SUM(cr.savings) / SUM(cr.ondemand_cost) * 100), 1)
        ELSE 0
    END AS savings_pct_30d,
    
    -- Switch counts
    (SELECT COUNT(*) FROM switches s 
     JOIN agents a2 ON a2.id = s.agent_id 
     WHERE a2.client_id = c.id 
     AND s.initiated_at > DATE_SUB(NOW(), INTERVAL 30 DAY)) AS switches_30d,
     
    -- All-time savings
    c.total_savings AS total_savings_all_time

FROM clients c
LEFT JOIN agents a ON a.client_id = c.id
LEFT JOIN cost_records cr ON cr.agent_id = a.id 
    AND cr.period_start > DATE_SUB(NOW(), INTERVAL 30 DAY)
GROUP BY c.id, c.name, c.status, c.plan, c.total_savings;

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

-- Active spot pools with latest prices
CREATE OR REPLACE VIEW active_spot_pools AS
SELECT 
    sp.id AS pool_id,
    sp.instance_type,
    sp.region,
    sp.az,
    sp.is_active,
    (SELECT sps.price FROM spot_price_snapshots sps 
     WHERE sps.pool_id = sp.id 
     ORDER BY sps.captured_at DESC LIMIT 1) AS latest_price,
    (SELECT sps.captured_at FROM spot_price_snapshots sps 
     WHERE sps.pool_id = sp.id 
     ORDER BY sps.captured_at DESC LIMIT 1) AS price_updated_at,
    
    -- Instance count using this pool
    (SELECT COUNT(*) FROM agents a 
     WHERE a.current_pool_id = sp.id 
     AND a.current_mode = 'spot'
     AND a.status = 'online') AS active_instances
     
FROM spot_pools sp
WHERE sp.is_active = TRUE;

-- ============================================================================
-- STORED PROCEDURES
-- ============================================================================

DELIMITER //

-- Register or update agent
CREATE PROCEDURE IF NOT EXISTS register_agent(
    IN p_client_token VARCHAR(255),
    IN p_logical_agent_id VARCHAR(255),
    IN p_hostname VARCHAR(255),
    IN p_instance_id VARCHAR(50),
    IN p_instance_type VARCHAR(50),
    IN p_region VARCHAR(50),
    IN p_az VARCHAR(50),
    IN p_ami_id VARCHAR(50),
    IN p_current_mode VARCHAR(20),
    IN p_agent_version VARCHAR(32),
    IN p_private_ip VARCHAR(45),
    IN p_public_ip VARCHAR(45)
)
BEGIN
    DECLARE v_client_id CHAR(36);
    DECLARE v_agent_id CHAR(36);
    DECLARE v_agent_exists INT DEFAULT 0;
    
    -- Get client ID from token
    SELECT id INTO v_client_id 
    FROM clients 
    WHERE client_token = p_client_token AND is_active = TRUE
    LIMIT 1;
    
    IF v_client_id IS NULL THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Invalid client token';
    END IF;
    
    -- Check if agent exists
    SELECT id, 1 INTO v_agent_id, v_agent_exists
    FROM agents 
    WHERE client_id = v_client_id AND logical_agent_id = p_logical_agent_id
    LIMIT 1;
    
    IF v_agent_exists = 1 THEN
        -- Update existing agent
        UPDATE agents SET
            hostname = p_hostname,
            instance_id = p_instance_id,
            instance_type = p_instance_type,
            region = p_region,
            az = p_az,
            ami_id = p_ami_id,
            current_mode = p_current_mode,
            current_pool_id = IF(p_current_mode = 'spot', CONCAT(p_instance_type, '.', p_az), NULL),
            agent_version = p_agent_version,
            private_ip = p_private_ip,
            public_ip = p_public_ip,
            status = 'online',
            last_heartbeat_at = NOW()
        WHERE id = v_agent_id;
    ELSE
        -- Create new agent
        SET v_agent_id = UUID();
        INSERT INTO agents (
            id, client_id, logical_agent_id, hostname, instance_id, instance_type,
            region, az, ami_id, current_mode, current_pool_id, agent_version,
            private_ip, public_ip, status, last_heartbeat_at
        ) VALUES (
            v_agent_id, v_client_id, p_logical_agent_id, p_hostname, p_instance_id, p_instance_type,
            p_region, p_az, p_ami_id, p_current_mode, 
            IF(p_current_mode = 'spot', CONCAT(p_instance_type, '.', p_az), NULL),
            p_agent_version, p_private_ip, p_public_ip, 'online', NOW()
        );
        
        -- Create default agent config
        INSERT INTO agent_configs (agent_id) VALUES (v_agent_id);
    END IF;
    
    -- Return agent info
    SELECT 
        a.id AS agent_id,
        a.enabled,
        a.auto_switch_enabled,
        a.auto_terminate_enabled,
        a.terminate_wait_seconds,
        a.replica_enabled,
        a.replica_count,
        ac.min_savings_percent,
        ac.risk_threshold,
        ac.max_switches_per_week,
        ac.min_pool_duration_hours
    FROM agents a
    LEFT JOIN agent_configs ac ON ac.agent_id = a.id
    WHERE a.id = v_agent_id;
END //

-- Get pending commands for agent (sorted by priority)
CREATE PROCEDURE IF NOT EXISTS get_pending_commands(IN p_agent_id CHAR(36))
BEGIN
    SELECT 
        id,
        command_type,
        target_mode,
        target_pool_id,
        instance_id,
        priority,
        terminate_wait_seconds,
        created_by,
        trigger_type,
        created_at
    FROM commands
    WHERE agent_id = p_agent_id
      AND status = 'pending'
    ORDER BY priority DESC, created_at ASC;
END //

-- Mark command as executed
CREATE PROCEDURE IF NOT EXISTS mark_command_executed(
    IN p_command_id CHAR(36),
    IN p_success BOOLEAN,
    IN p_message TEXT
)
BEGIN
    UPDATE commands
    SET status = IF(p_success, 'completed', 'failed'),
        success = p_success,
        message = p_message,
        executed_at = NOW(),
        completed_at = NOW()
    WHERE id = p_command_id;
END //

-- Get cheapest pool for instance type
CREATE PROCEDURE IF NOT EXISTS get_cheapest_pool(
    IN p_instance_type VARCHAR(50),
    IN p_region VARCHAR(50)
)
BEGIN
    SELECT 
        sp.pool_id,
        sp.az,
        sp.price
    FROM spot_prices sp
    INNER JOIN (
        SELECT pool_id, MAX(recorded_at) AS max_time
        FROM spot_prices
        WHERE instance_type = p_instance_type
          AND region = p_region
        GROUP BY pool_id
    ) latest ON sp.pool_id = latest.pool_id AND sp.recorded_at = latest.max_time
    ORDER BY sp.price ASC;
END //

-- Calculate agent savings for period
CREATE PROCEDURE IF NOT EXISTS calculate_agent_savings(
    IN p_agent_id CHAR(36),
    IN p_start_date TIMESTAMP,
    IN p_end_date TIMESTAMP
)
BEGIN
    SELECT 
        SUM(CASE WHEN mode = 'spot' THEN hours_running ELSE 0 END) AS hours_on_spot,
        SUM(CASE WHEN mode = 'ondemand' THEN hours_running ELSE 0 END) AS hours_on_demand,
        SUM(actual_cost) AS spot_cost,
        SUM(ondemand_cost) AS demand_cost,
        SUM(savings) AS total_savings,
        CASE 
            WHEN SUM(ondemand_cost) > 0 
            THEN ROUND((SUM(savings) / SUM(ondemand_cost) * 100), 2)
            ELSE 0 
        END AS savings_pct
    FROM cost_records
    WHERE agent_id = p_agent_id
      AND period_start >= p_start_date
      AND period_end <= p_end_date;
END //

-- Calculate client savings for period
CREATE PROCEDURE IF NOT EXISTS calculate_client_savings(
    IN p_client_id CHAR(36),
    IN p_start_date TIMESTAMP,
    IN p_end_date TIMESTAMP
)
BEGIN
    SELECT 
        SUM(cr.hours_running) AS total_hours,
        SUM(cr.actual_cost) AS actual_cost,
        SUM(cr.ondemand_cost) AS baseline_cost,
        SUM(cr.savings) AS total_savings,
        CASE 
            WHEN SUM(cr.ondemand_cost) > 0 
            THEN ROUND((SUM(cr.savings) / SUM(cr.ondemand_cost) * 100), 2)
            ELSE 0 
        END AS savings_pct,
        (SELECT COUNT(*) FROM switches s 
         WHERE s.client_id = p_client_id 
         AND s.initiated_at >= p_start_date 
         AND s.initiated_at <= p_end_date) AS switch_count
    FROM cost_records cr
    WHERE cr.client_id = p_client_id
      AND cr.period_start >= p_start_date
      AND cr.period_end <= p_end_date;
END //

-- Check agent switch limits
CREATE PROCEDURE IF NOT EXISTS check_switch_limits(IN p_agent_id CHAR(36))
BEGIN
    DECLARE v_switches_today INT DEFAULT 0;
    DECLARE v_switches_week INT DEFAULT 0;
    DECLARE v_max_per_day INT DEFAULT 3;
    DECLARE v_max_per_week INT DEFAULT 10;
    DECLARE v_can_switch BOOLEAN DEFAULT TRUE;
    DECLARE v_reason TEXT DEFAULT 'OK';
    
    -- Get config
    SELECT 
        COALESCE(max_switches_per_day, 3),
        COALESCE(max_switches_per_week, 10)
    INTO v_max_per_day, v_max_per_week
    FROM agent_configs
    WHERE agent_id = p_agent_id;
    
    -- Count recent switches
    SELECT COUNT(*) INTO v_switches_today
    FROM switches
    WHERE agent_id = p_agent_id
      AND initiated_at > DATE_SUB(NOW(), INTERVAL 1 DAY);
    
    SELECT COUNT(*) INTO v_switches_week
    FROM switches
    WHERE agent_id = p_agent_id
      AND initiated_at > DATE_SUB(NOW(), INTERVAL 7 DAY);
    
    -- Determine if switch is allowed
    IF v_switches_today >= v_max_per_day THEN
        SET v_can_switch = FALSE;
        SET v_reason = 'Daily switch limit reached';
    ELSEIF v_switches_week >= v_max_per_week THEN
        SET v_can_switch = FALSE;
        SET v_reason = 'Weekly switch limit reached';
    END IF;
    
    -- Return result
    SELECT 
        v_can_switch AS can_switch,
        v_reason AS reason,
        v_switches_today AS switches_today,
        v_switches_week AS switches_week;
END //

-- Update spot pool prices (bulk insert)
CREATE PROCEDURE IF NOT EXISTS update_spot_pool_prices(IN p_pools JSON)
BEGIN
    DECLARE i INT DEFAULT 0;
    DECLARE pool_count INT;
    DECLARE v_pool_id VARCHAR(128);
    DECLARE v_price DECIMAL(10, 6);
    
    SET pool_count = JSON_LENGTH(p_pools);
    
    WHILE i < pool_count DO
        SET v_pool_id = JSON_UNQUOTE(JSON_EXTRACT(p_pools, CONCAT('$[', i, '].pool_id')));
        SET v_price = JSON_EXTRACT(p_pools, CONCAT('$[', i, '].price'));
        
        INSERT INTO spot_price_snapshots (pool_id, price)
        VALUES (v_pool_id, v_price);
        
        SET i = i + 1;
    END WHILE;
    
    SELECT pool_count AS inserted_count;
END //

-- Cleanup old data (retention policy)
CREATE PROCEDURE IF NOT EXISTS cleanup_old_data()
BEGIN
    DECLARE rows_deleted INT DEFAULT 0;
    
    -- Old spot prices (keep 90 days)
    DELETE FROM spot_price_snapshots WHERE captured_at < DATE_SUB(NOW(), INTERVAL 90 DAY);
    SET rows_deleted = rows_deleted + ROW_COUNT();
    
    -- Old on-demand snapshots (keep 90 days)
    DELETE FROM ondemand_price_snapshots WHERE captured_at < DATE_SUB(NOW(), INTERVAL 90 DAY);
    SET rows_deleted = rows_deleted + ROW_COUNT();
    
    -- Old pricing reports (keep 30 days)
    DELETE FROM pricing_reports WHERE received_at < DATE_SUB(NOW(), INTERVAL 30 DAY);
    SET rows_deleted = rows_deleted + ROW_COUNT();
    
    -- Old predictions (keep 30 days)
    DELETE FROM model_predictions WHERE created_at < DATE_SUB(NOW(), INTERVAL 30 DAY);
    SET rows_deleted = rows_deleted + ROW_COUNT();
    
    -- Old risk scores (keep 90 days)
    DELETE FROM risk_scores WHERE created_at < DATE_SUB(NOW(), INTERVAL 90 DAY);
    SET rows_deleted = rows_deleted + ROW_COUNT();
    
    -- Old decision engine logs (keep 30 days)
    DELETE FROM decision_engine_log WHERE created_at < DATE_SUB(NOW(), INTERVAL 30 DAY);
    SET rows_deleted = rows_deleted + ROW_COUNT();
    
    -- Old system events (keep 90 days)
    DELETE FROM system_events WHERE created_at < DATE_SUB(NOW(), INTERVAL 90 DAY);
    SET rows_deleted = rows_deleted + ROW_COUNT();
    
    -- Old audit logs (keep 180 days for compliance)
    DELETE FROM audit_logs WHERE created_at < DATE_SUB(NOW(), INTERVAL 180 DAY);
    SET rows_deleted = rows_deleted + ROW_COUNT();
    
    -- Read notifications (keep 30 days)
    DELETE FROM notifications WHERE is_read = TRUE AND created_at < DATE_SUB(NOW(), INTERVAL 30 DAY);
    SET rows_deleted = rows_deleted + ROW_COUNT();
    
    -- Completed commands (keep 7 days)
    DELETE FROM commands WHERE status IN ('completed', 'failed', 'cancelled') AND completed_at < DATE_SUB(NOW(), INTERVAL 7 DAY);
    SET rows_deleted = rows_deleted + ROW_COUNT();
    
    -- Executed pending commands (keep 7 days)
    DELETE FROM pending_switch_commands WHERE executed_at IS NOT NULL AND executed_at < DATE_SUB(NOW(), INTERVAL 7 DAY);
    SET rows_deleted = rows_deleted + ROW_COUNT();
    
    SELECT rows_deleted AS total_rows_deleted;
END //

-- Update client total savings
CREATE PROCEDURE IF NOT EXISTS update_client_total_savings()
BEGIN
    UPDATE clients c
    SET total_savings = (
        SELECT COALESCE(SUM(cr.savings), 0)
        FROM cost_records cr
        JOIN agents a ON a.id = cr.agent_id
        WHERE a.client_id = c.id
    );
    
    SELECT ROW_COUNT() AS clients_updated;
END //

-- Compute monthly savings for all clients
CREATE PROCEDURE IF NOT EXISTS compute_monthly_savings()
BEGIN
    DECLARE done INT DEFAULT FALSE;
    DECLARE v_client_id CHAR(36);
    DECLARE v_year INT DEFAULT YEAR(NOW());
    DECLARE v_month INT DEFAULT MONTH(NOW());
    DECLARE v_baseline_cost DECIMAL(15, 4);
    DECLARE v_actual_cost DECIMAL(15, 4);
    DECLARE v_savings DECIMAL(15, 4);
    DECLARE v_switch_count INT;
    
    DECLARE client_cursor CURSOR FOR 
        SELECT id FROM clients WHERE is_active = TRUE;
    DECLARE CONTINUE HANDLER FOR NOT FOUND SET done = TRUE;
    
    OPEN client_cursor;
    
    read_loop: LOOP
        FETCH client_cursor INTO v_client_id;
        IF done THEN
            LEAVE read_loop;
        END IF;
        
        -- Calculate baseline (on-demand) cost
        SELECT COALESCE(SUM(baseline_ondemand_price * 24 * 30), 0) INTO v_baseline_cost
        FROM instances
        WHERE client_id = v_client_id AND is_active = TRUE;
        
        -- Calculate actual cost from switches
        SELECT COALESCE(SUM(
            CASE 
                WHEN new_mode = 'spot' THEN new_spot_price * 24 * 30
                ELSE on_demand_price * 24 * 30
            END
        ), v_baseline_cost) INTO v_actual_cost
        FROM switches
        WHERE client_id = v_client_id 
        AND YEAR(timestamp) = v_year 
        AND MONTH(timestamp) = v_month;
        
        SET v_savings = GREATEST(0, v_baseline_cost - v_actual_cost);
        
        -- Count switches
        SELECT COUNT(*) INTO v_switch_count
        FROM switches
        WHERE client_id = v_client_id 
        AND YEAR(timestamp) = v_year 
        AND MONTH(timestamp) = v_month;
        
        -- Store monthly savings
        INSERT INTO client_savings_monthly 
        (client_id, year, month, baseline_cost, actual_cost, savings, switch_count)
        VALUES (v_client_id, v_year, v_month, v_baseline_cost, v_actual_cost, v_savings, v_switch_count)
        ON DUPLICATE KEY UPDATE
            baseline_cost = v_baseline_cost,
            actual_cost = v_actual_cost,
            savings = v_savings,
            switch_count = v_switch_count,
            computed_at = NOW();
    END LOOP;
    
    CLOSE client_cursor;
    
    SELECT 'Monthly savings computed successfully' AS result;
END //

DELIMITER ;

-- ============================================================================
-- EVENTS (Scheduled Tasks)
-- ============================================================================

-- Enable event scheduler
SET GLOBAL event_scheduler = ON;

-- Daily cleanup event (runs at 2 AM)
DROP EVENT IF EXISTS evt_daily_cleanup;
CREATE EVENT evt_daily_cleanup
ON SCHEDULE EVERY 1 DAY
STARTS (TIMESTAMP(CURRENT_DATE) + INTERVAL 1 DAY + INTERVAL 2 HOUR)
DO
    CALL cleanup_old_data();

-- Mark stale agents as offline (runs every minute)
DROP EVENT IF EXISTS evt_mark_stale_agents;
CREATE EVENT evt_mark_stale_agents
ON SCHEDULE EVERY 1 MINUTE
DO
    UPDATE agents 
    SET status = 'offline' 
    WHERE status = 'online' 
      AND last_heartbeat_at < DATE_SUB(NOW(), INTERVAL 5 MINUTE);

-- Compute monthly savings (runs daily at 1 AM)
DROP EVENT IF EXISTS evt_compute_monthly_savings;
CREATE EVENT evt_compute_monthly_savings
ON SCHEDULE EVERY 1 DAY
STARTS (TIMESTAMP(CURRENT_DATE) + INTERVAL 1 DAY + INTERVAL 1 HOUR)
DO
    CALL compute_monthly_savings();

-- Update client total savings (runs daily at 3 AM)
DROP EVENT IF EXISTS evt_update_total_savings;
CREATE EVENT evt_update_total_savings
ON SCHEDULE EVERY 1 DAY
STARTS (TIMESTAMP(CURRENT_DATE) + INTERVAL 1 DAY + INTERVAL 3 HOUR)
DO
    CALL update_client_total_savings();

-- ============================================================================
-- INITIAL DATA
-- ============================================================================

-- Create a demo client for testing
INSERT INTO clients (id, name, email, client_token, plan, max_agents, max_instances, is_active)
VALUES (UUID(), 'Demo Client', 'demo@example.com', 'demo-token-12345', 'pro', 10, 50, TRUE)
ON DUPLICATE KEY UPDATE name = name;

-- ============================================================================
-- RE-ENABLE FOREIGN KEY CHECKS
-- ============================================================================

SET FOREIGN_KEY_CHECKS = 1;

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

-- Show all views
SELECT TABLE_NAME AS view_name
FROM information_schema.VIEWS
WHERE TABLE_SCHEMA = DATABASE();

-- Show all stored procedures
SELECT ROUTINE_NAME AS procedure_name
FROM information_schema.ROUTINES
WHERE ROUTINE_SCHEMA = DATABASE()
AND ROUTINE_TYPE = 'PROCEDURE';

-- Show all events
SELECT EVENT_NAME, STATUS, EVENT_DEFINITION
FROM information_schema.EVENTS
WHERE EVENT_SCHEMA = DATABASE();

-- ============================================================================
-- SAMPLE QUERIES FOR COMMON OPERATIONS
-- ============================================================================

/*
-- Get agent status with latest pricing
SELECT * FROM agent_overview WHERE client_id = '<client_uuid>';

-- Get client savings summary
SELECT * FROM client_savings_summary WHERE client_id = '<client_uuid>';

-- Get recent switches for an agent
SELECT * FROM recent_switches WHERE agent_id = '<agent_uuid>' LIMIT 10;

-- Get cheapest available pools for instance type
CALL get_cheapest_pool('t3.medium', 'us-east-1');

-- Calculate savings for agent over period
CALL calculate_agent_savings('<agent_uuid>', '2025-01-01 00:00:00', NOW());

-- Check if agent can perform switch
CALL check_switch_limits('<agent_uuid>');

-- Get pending commands for agent
CALL get_pending_commands('<agent_uuid>');

-- Register or update agent
CALL register_agent(
    'demo-token-12345',
    'logical-agent-001', 
    'my-server',
    'i-1234567890abcdef0',
    't3.medium',
    'us-east-1',
    'us-east-1a',
    'ami-12345678',
    'spot',
    '4.0.0',
    '10.0.1.100',
    '54.123.45.67'
);

-- Get active spot pools with current prices
SELECT * FROM active_spot_pools 
WHERE instance_type = 't3.medium' 
AND region = 'us-east-1'
ORDER BY latest_price ASC;

-- Manually trigger cleanup
CALL cleanup_old_data();

-- Manually compute monthly savings
CALL compute_monthly_savings();

-- Update all client total savings
CALL update_client_total_savings();
*/

-- ============================================================================
-- CLEANUP TRACKING (Agent v4.0.0 Enhancement)
-- ============================================================================

CREATE TABLE IF NOT EXISTS cleanup_logs (
    id INT AUTO_INCREMENT PRIMARY KEY,
    agent_id CHAR(36),
    client_id CHAR(36),
    cleanup_type ENUM('snapshots', 'amis', 'full') NOT NULL,
    deleted_snapshots_count INT DEFAULT 0,
    deleted_amis_count INT DEFAULT 0,
    failed_count INT DEFAULT 0,
    details JSON,
    cutoff_date TIMESTAMP NULL,
    executed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_agent_id (agent_id),
    INDEX idx_client_id (client_id),
    INDEX idx_executed_at (executed_at),
    FOREIGN KEY (agent_id) REFERENCES agents(id) ON DELETE CASCADE,
    FOREIGN KEY (client_id) REFERENCES clients(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='Track cleanup operations from agents';

-- ============================================================================
-- TERMINATION & REBALANCE EVENTS (Enhanced Tracking)
-- ============================================================================

CREATE TABLE IF NOT EXISTS termination_events (
    id INT AUTO_INCREMENT PRIMARY KEY,
    agent_id CHAR(36) NOT NULL,
    instance_id VARCHAR(50) NOT NULL,
    event_type ENUM('termination_notice', 'rebalance_recommendation') NOT NULL,
    action_type VARCHAR(50),
    action_taken VARCHAR(255),
    emergency_replica_id CHAR(36),
    new_instance_id VARCHAR(50),
    detected_at TIMESTAMP NOT NULL,
    resolved_at TIMESTAMP NULL,
    status ENUM('detected', 'handling', 'resolved', 'failed') DEFAULT 'detected',
    error_message TEXT,
    metadata JSON,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_agent_id (agent_id),
    INDEX idx_instance_id (instance_id),
    INDEX idx_event_type (event_type),
    INDEX idx_status (status),
    INDEX idx_detected_at (detected_at),
    FOREIGN KEY (agent_id) REFERENCES agents(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='Track termination and rebalance events with resolution workflow';

-- ============================================================================
-- SAVINGS SNAPSHOTS (Daily Aggregation)
-- ============================================================================

CREATE TABLE IF NOT EXISTS savings_snapshots (
    id INT AUTO_INCREMENT PRIMARY KEY,
    client_id CHAR(36) NOT NULL,
    snapshot_date DATE NOT NULL,
    total_savings DECIMAL(15, 4) DEFAULT 0,
    daily_savings DECIMAL(15, 4) DEFAULT 0,
    spot_hours DECIMAL(10, 2) DEFAULT 0,
    ondemand_hours DECIMAL(10, 2) DEFAULT 0,
    total_cost DECIMAL(15, 4) DEFAULT 0,
    would_be_cost DECIMAL(15, 4) DEFAULT 0,
    average_savings_percent DECIMAL(5, 2) DEFAULT 0,
    switch_count INT DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY uk_client_date (client_id, snapshot_date),
    INDEX idx_snapshot_date (snapshot_date),
    FOREIGN KEY (client_id) REFERENCES clients(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='Daily aggregated savings for historical tracking';

-- ============================================================================
-- AGENT HEALTH METRICS
-- ============================================================================

CREATE TABLE IF NOT EXISTS agent_health_metrics (
    id INT AUTO_INCREMENT PRIMARY KEY,
    agent_id CHAR(36) NOT NULL,
    metric_time TIMESTAMP NOT NULL,
    heartbeat_latency_ms INT,
    command_execution_time_ms INT,
    pricing_fetch_success BOOLEAN,
    termination_check_success BOOLEAN,
    rebalance_check_success BOOLEAN,
    error_count INT DEFAULT 0,
    warning_count INT DEFAULT 0,
    metadata JSON,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_agent_id (agent_id),
    INDEX idx_metric_time (metric_time),
    FOREIGN KEY (agent_id) REFERENCES agents(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='Track agent health and performance metrics';

-- ============================================================================
-- REPLICA COST TRACKING
-- ============================================================================

CREATE TABLE IF NOT EXISTS replica_cost_log (
    id INT AUTO_INCREMENT PRIMARY KEY,
    replica_id CHAR(36) NOT NULL,
    agent_id CHAR(36) NOT NULL,
    client_id CHAR(36) NOT NULL,
    instance_id VARCHAR(50),
    pool_id VARCHAR(100),
    hourly_cost DECIMAL(10, 6),
    log_time TIMESTAMP NOT NULL,
    duration_hours DECIMAL(5, 2) DEFAULT 1,
    total_cost DECIMAL(10, 4),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_replica_id (replica_id),
    INDEX idx_agent_id (agent_id),
    INDEX idx_client_id (client_id),
    INDEX idx_log_time (log_time),
    FOREIGN KEY (agent_id) REFERENCES agents(id) ON DELETE CASCADE,
    FOREIGN KEY (client_id) REFERENCES clients(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='Track replica costs for detailed cost analysis';

-- ============================================================================
-- POOL RISK ANALYSIS
-- ============================================================================

CREATE TABLE IF NOT EXISTS pool_risk_analysis (
    id INT AUTO_INCREMENT PRIMARY KEY,
    pool_id VARCHAR(100) NOT NULL,
    instance_type VARCHAR(50) NOT NULL,
    region VARCHAR(20) NOT NULL,
    az VARCHAR(30) NOT NULL,
    analysis_time TIMESTAMP NOT NULL,
    risk_score DECIMAL(5, 4) DEFAULT 0,
    price_volatility DECIMAL(10, 6),
    avg_price_24h DECIMAL(10, 6),
    min_price_24h DECIMAL(10, 6),
    max_price_24h DECIMAL(10, 6),
    interruption_frequency INT DEFAULT 0,
    recommendation ENUM('safe', 'caution', 'avoid') DEFAULT 'safe',
    metadata JSON,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_pool_id (pool_id),
    INDEX idx_analysis_time (analysis_time),
    INDEX idx_risk_score (risk_score),
    INDEX idx_recommendation (recommendation)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='Store pool risk analysis results';

-- ============================================================================
-- ADDITIONAL VIEWS FOR ENHANCED FEATURES
-- ============================================================================

-- Client Savings Summary View
CREATE OR REPLACE VIEW v_client_savings_summary AS
SELECT
    c.id AS client_id,
    c.name AS client_name,
    COALESCE(SUM(ss.total_savings), 0) AS lifetime_savings,
    COALESCE(SUM(CASE
        WHEN ss.snapshot_date >= DATE_SUB(CURDATE(), INTERVAL 30 DAY)
        THEN ss.daily_savings ELSE 0 END), 0) AS monthly_savings,
    COALESCE(SUM(CASE
        WHEN ss.snapshot_date >= DATE_SUB(CURDATE(), INTERVAL 7 DAY)
        THEN ss.daily_savings ELSE 0 END), 0) AS weekly_savings,
    COALESCE(AVG(ss.average_savings_percent), 0) AS avg_savings_percent,
    COUNT(DISTINCT a.id) AS agent_count,
    SUM(CASE WHEN a.status = 'online' THEN 1 ELSE 0 END) AS online_agents
FROM clients c
LEFT JOIN savings_snapshots ss ON c.id = ss.client_id
LEFT JOIN agents a ON c.id = a.client_id
GROUP BY c.id, c.name;

-- Recent Termination Events View
CREATE OR REPLACE VIEW v_recent_termination_events AS
SELECT
    te.*,
    a.hostname,
    a.instance_type,
    c.name AS client_name
FROM termination_events te
JOIN agents a ON te.agent_id = a.id
JOIN clients c ON a.client_id = c.id
WHERE te.detected_at >= DATE_SUB(NOW(), INTERVAL 24 HOUR)
ORDER BY te.detected_at DESC;

-- Current Pool Risk View
CREATE OR REPLACE VIEW v_pool_risk_current AS
SELECT
    pool_id,
    instance_type,
    region,
    az,
    risk_score,
    price_volatility,
    avg_price_24h,
    recommendation,
    analysis_time
FROM pool_risk_analysis pra
WHERE analysis_time = (
    SELECT MAX(analysis_time)
    FROM pool_risk_analysis
    WHERE pool_id = pra.pool_id
);

-- ============================================================================
-- ADDITIONAL STORED PROCEDURES
-- ============================================================================

DELIMITER //

-- Calculate Daily Savings Snapshots
CREATE PROCEDURE IF NOT EXISTS sp_calculate_daily_savings(IN p_date DATE)
BEGIN
    INSERT INTO savings_snapshots (client_id, snapshot_date, daily_savings, switch_count)
    SELECT
        c.id,
        p_date,
        COALESCE(SUM(s.savings_impact * 24), 0) AS daily_savings,
        COUNT(s.id) AS switch_count
    FROM clients c
    LEFT JOIN switches s ON c.id = s.client_id
        AND DATE(s.initiated_at) = p_date
    GROUP BY c.id
    ON DUPLICATE KEY UPDATE
        daily_savings = VALUES(daily_savings),
        switch_count = VALUES(switch_count),
        updated_at = NOW();
END //

-- Cleanup Old Metrics
CREATE PROCEDURE IF NOT EXISTS sp_cleanup_old_metrics(IN days_to_keep INT)
BEGIN
    DELETE FROM agent_health_metrics
    WHERE metric_time < DATE_SUB(NOW(), INTERVAL days_to_keep DAY);

    DELETE FROM pool_risk_analysis
    WHERE analysis_time < DATE_SUB(NOW(), INTERVAL days_to_keep DAY);

    DELETE FROM replica_cost_log
    WHERE log_time < DATE_SUB(NOW(), INTERVAL days_to_keep DAY);

    DELETE FROM cleanup_logs
    WHERE executed_at < DATE_SUB(NOW(), INTERVAL days_to_keep DAY);
END //

DELIMITER ;

-- ============================================================================
-- ADDITIONAL SCHEDULED EVENTS
-- ============================================================================

-- Calculate daily savings at midnight
CREATE EVENT IF NOT EXISTS evt_calculate_daily_savings
ON SCHEDULE EVERY 1 DAY
STARTS (TIMESTAMP(CURRENT_DATE) + INTERVAL 1 DAY)
DO CALL sp_calculate_daily_savings(DATE_SUB(CURRENT_DATE, INTERVAL 1 DAY));

-- Cleanup old metrics weekly
CREATE EVENT IF NOT EXISTS evt_cleanup_old_metrics
ON SCHEDULE EVERY 1 WEEK
STARTS (TIMESTAMP(CURRENT_DATE) + INTERVAL 1 WEEK)
DO CALL sp_cleanup_old_metrics(30);

-- ============================================================================
-- END OF SCHEMA
-- ============================================================================

SELECT '✓ AWS Spot Optimizer MySQL Schema v5.1 - Setup Complete!' AS status;
