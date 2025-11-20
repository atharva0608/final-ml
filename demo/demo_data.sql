-- Demo Data for Testing Graphs and Replica Functionality
-- This script inserts sample data for visualization and testing

-- ============================================================================
-- DEMO CLIENTS
-- ============================================================================

INSERT INTO clients (id, name, email, industry, created_at) VALUES
('demo-client-1', 'Acme Corporation', 'admin@acme.com', 'Technology', NOW() - INTERVAL 90 DAY),
('demo-client-2', 'TechStart Inc', 'info@techstart.com', 'Startup', NOW() - INTERVAL 60 DAY)
ON DUPLICATE KEY UPDATE name = VALUES(name);

-- ============================================================================
-- DEMO SPOT POOLS
-- ============================================================================

INSERT INTO spot_pools (id, pool_name, instance_type, region, az, is_available, created_at) VALUES
(1, 'us-east-1a-t3.medium', 't3.medium', 'us-east-1', 'us-east-1a', TRUE, NOW() - INTERVAL 90 DAY),
(2, 'us-east-1b-t3.medium', 't3.medium', 'us-east-1', 'us-east-1b', TRUE, NOW() - INTERVAL 90 DAY),
(3, 'us-east-1c-t3.medium', 't3.medium', 'us-east-1', 'us-east-1c', TRUE, NOW() - INTERVAL 90 DAY),
(4, 'us-west-2a-t3.large', 't3.large', 'us-west-2', 'us-west-2a', TRUE, NOW() - INTERVAL 90 DAY),
(5, 'us-west-2b-t3.large', 't3.large', 'us-west-2', 'us-west-2b', TRUE, NOW() - INTERVAL 90 DAY)
ON DUPLICATE KEY UPDATE pool_name = VALUES(pool_name);

-- ============================================================================
-- DEMO INSTANCES
-- ============================================================================

INSERT INTO instances (id, client_id, instance_type, region, az, current_pool_id, current_mode, spot_price, ondemand_price, is_active, installed_at) VALUES
('i-demo001', 'demo-client-1', 't3.medium', 'us-east-1', 'us-east-1a', 1, 'spot', 0.0416, 0.0832, TRUE, NOW() - INTERVAL 30 DAY),
('i-demo002', 'demo-client-1', 't3.medium', 'us-east-1', 'us-east-1b', 2, 'spot', 0.0420, 0.0832, TRUE, NOW() - INTERVAL 25 DAY),
('i-demo003', 'demo-client-2', 't3.large', 'us-west-2', 'us-west-2a', 4, 'spot', 0.0832, 0.1664, TRUE, NOW() - INTERVAL 20 DAY),
('i-demo004', 'demo-client-2', 't3.large', 'us-west-2', 'us-west-2b', 5, 'spot', 0.0840, 0.1664, TRUE, NOW() - INTERVAL 15 DAY)
ON DUPLICATE KEY UPDATE is_active = VALUES(is_active);

-- ============================================================================
-- DEMO AGENTS
-- ============================================================================

INSERT INTO agents (id, client_id, instance_id, logical_agent_id, hostname, status, enabled, auto_switch_enabled, agent_version, manual_replica_enabled, auto_replica_enabled, last_heartbeat_at, created_at) VALUES
('agent-demo-1', 'demo-client-1', 'i-demo001', 'agent-acme-prod-1', 'acme-prod-1.internal', 'online', TRUE, TRUE, '2.1.0', TRUE, TRUE, NOW(), NOW() - INTERVAL 30 DAY),
('agent-demo-2', 'demo-client-1', 'i-demo002', 'agent-acme-prod-2', 'acme-prod-2.internal', 'online', TRUE, TRUE, '2.1.0', TRUE, TRUE, NOW(), NOW() - INTERVAL 25 DAY),
('agent-demo-3', 'demo-client-2', 'i-demo003', 'agent-techstart-1', 'techstart-1.internal', 'online', TRUE, FALSE, '2.0.5', TRUE, FALSE, NOW(), NOW() - INTERVAL 20 DAY),
('agent-demo-4', 'demo-client-2', 'i-demo004', 'agent-techstart-2', 'techstart-2.internal', 'offline', TRUE, TRUE, '2.1.0', FALSE, TRUE, NOW() - INTERVAL 2 HOUR, NOW() - INTERVAL 15 DAY)
ON DUPLICATE KEY UPDATE status = VALUES(status);

-- ============================================================================
-- DEMO PRICING DATA (Last 7 days, 5-minute intervals)
-- ============================================================================

-- Generate pricing snapshots for the last 7 days
-- This creates realistic price fluctuations for graphing

DELIMITER //

CREATE PROCEDURE IF NOT EXISTS generate_demo_pricing_data()
BEGIN
    DECLARE bucket_time TIMESTAMP;
    DECLARE end_time TIMESTAMP;
    DECLARE pool INT;
    DECLARE base_price DECIMAL(10,6);
    DECLARE price_variation DECIMAL(10,6);

    SET end_time = NOW();
    SET bucket_time = NOW() - INTERVAL 7 DAY;

    -- Clear existing demo data
    DELETE FROM pricing_snapshots_clean WHERE time_bucket >= NOW() - INTERVAL 7 DAY;

    WHILE bucket_time <= end_time DO
        -- Pool 1: t3.medium us-east-1a
        SET base_price = 0.0416;
        SET price_variation = (RAND() - 0.5) * 0.008; -- +/- $0.004
        INSERT INTO pricing_snapshots_clean (
            pool_id, instance_type, region, az, spot_price, ondemand_price,
            savings_percent, time_bucket, bucket_start, bucket_end,
            source_instance_id, source_type, confidence_score, data_source
        ) VALUES (
            1, 't3.medium', 'us-east-1', 'us-east-1a',
            base_price + price_variation, 0.0832,
            ROUND(((0.0832 - (base_price + price_variation)) / 0.0832) * 100, 2),
            bucket_time, bucket_time, bucket_time + INTERVAL 5 MINUTE,
            'i-demo001', 'primary', 1.00, 'measured'
        );

        -- Pool 2: t3.medium us-east-1b
        SET base_price = 0.0420;
        SET price_variation = (RAND() - 0.5) * 0.008;
        INSERT INTO pricing_snapshots_clean (
            pool_id, instance_type, region, az, spot_price, ondemand_price,
            savings_percent, time_bucket, bucket_start, bucket_end,
            source_instance_id, source_type, confidence_score, data_source
        ) VALUES (
            2, 't3.medium', 'us-east-1', 'us-east-1b',
            base_price + price_variation, 0.0832,
            ROUND(((0.0832 - (base_price + price_variation)) / 0.0832) * 100, 2),
            bucket_time, bucket_time, bucket_time + INTERVAL 5 MINUTE,
            'i-demo002', 'primary', 1.00, 'measured'
        );

        -- Pool 3: t3.medium us-east-1c
        SET base_price = 0.0418;
        SET price_variation = (RAND() - 0.5) * 0.008;
        INSERT INTO pricing_snapshots_clean (
            pool_id, instance_type, region, az, spot_price, ondemand_price,
            savings_percent, time_bucket, bucket_start, bucket_end,
            source_instance_id, source_type, confidence_score, data_source
        ) VALUES (
            3, 't3.medium', 'us-east-1', 'us-east-1c',
            base_price + price_variation, 0.0832,
            ROUND(((0.0832 - (base_price + price_variation)) / 0.0832) * 100, 2),
            bucket_time, bucket_time, bucket_time + INTERVAL 5 MINUTE,
            'i-demo001', 'primary', 1.00, 'measured'
        );

        -- Pool 4: t3.large us-west-2a
        SET base_price = 0.0832;
        SET price_variation = (RAND() - 0.5) * 0.016;
        INSERT INTO pricing_snapshots_clean (
            pool_id, instance_type, region, az, spot_price, ondemand_price,
            savings_percent, time_bucket, bucket_start, bucket_end,
            source_instance_id, source_type, confidence_score, data_source
        ) VALUES (
            4, 't3.large', 'us-west-2', 'us-west-2a',
            base_price + price_variation, 0.1664,
            ROUND(((0.1664 - (base_price + price_variation)) / 0.1664) * 100, 2),
            bucket_time, bucket_time, bucket_time + INTERVAL 5 MINUTE,
            'i-demo003', 'primary', 1.00, 'measured'
        );

        -- Pool 5: t3.large us-west-2b
        SET base_price = 0.0840;
        SET price_variation = (RAND() - 0.5) * 0.016;
        INSERT INTO pricing_snapshots_clean (
            pool_id, instance_type, region, az, spot_price, ondemand_price,
            savings_percent, time_bucket, bucket_start, bucket_end,
            source_instance_id, source_type, confidence_score, data_source
        ) VALUES (
            5, 't3.large', 'us-west-2', 'us-west-2b',
            base_price + price_variation, 0.1664,
            ROUND(((0.1664 - (base_price + price_variation)) / 0.1664) * 100, 2),
            bucket_time, bucket_time, bucket_time + INTERVAL 5 MINUTE,
            'i-demo004', 'primary', 1.00, 'measured'
        );

        -- Increment time bucket by 5 minutes
        SET bucket_time = bucket_time + INTERVAL 5 MINUTE;
    END WHILE;
END //

DELIMITER ;

-- Execute the procedure to generate data
CALL generate_demo_pricing_data();

-- Drop the procedure after use
DROP PROCEDURE IF EXISTS generate_demo_pricing_data;

-- ============================================================================
-- DEMO REPLICA INSTANCES
-- ============================================================================

INSERT INTO replica_instances (
    id, agent_id, instance_id, replica_type, pool_id,
    instance_type, region, az, status, created_by,
    parent_instance_id, is_active, sync_status, sync_latency_ms,
    state_transfer_progress, hourly_cost, total_cost,
    created_at, ready_at, last_sync_at
) VALUES
-- Active manual replica for agent-demo-1
(
    'replica-demo-1', 'agent-demo-1', 'i-replica-demo-1', 'manual', 2,
    't3.medium', 'us-east-1', 'us-east-1b', 'ready', 'admin@acme.com',
    'i-demo001', TRUE, 'synced', 45, 100.0, 0.0420, 1.25,
    NOW() - INTERVAL 3 HOUR, NOW() - INTERVAL 2 HOUR 55 MINUTE, NOW()
),
-- Ready automatic replica for agent-demo-2 (rebalance)
(
    'replica-demo-2', 'agent-demo-2', 'i-replica-demo-2', 'automatic-rebalance', 3,
    't3.medium', 'us-east-1', 'us-east-1c', 'ready', 'system',
    'i-demo002', TRUE, 'synced', 38, 100.0, 0.0418, 0.85,
    NOW() - INTERVAL 2 HOUR, NOW() - INTERVAL 1 HOUR 58 MINUTE, NOW()
),
-- Syncing automatic replica for agent-demo-3 (termination notice)
(
    'replica-demo-3', 'agent-demo-3', 'i-replica-demo-3', 'automatic-termination', 5,
    't3.large', 'us-west-2', 'us-west-2b', 'syncing', 'system',
    'i-demo003', TRUE, 'syncing', 125, 75.5, 0.0840, 0.12,
    NOW() - INTERVAL 15 MINUTE, NULL, NOW()
),
-- Terminated replica (for history)
(
    'replica-demo-4', 'agent-demo-1', 'i-replica-demo-4', 'manual', 1,
    't3.medium', 'us-east-1', 'us-east-1a', 'terminated', 'admin@acme.com',
    'i-demo001', FALSE, 'synced', NULL, 100.0, 0.0416, 5.45,
    NOW() - INTERVAL 5 DAY, NOW() - INTERVAL 4 DAY 23 HOUR, NOW() - INTERVAL 4 DAY
)
ON DUPLICATE KEY UPDATE status = VALUES(status);

-- Update agent replica counts
UPDATE agents SET replica_count = 1, current_replica_id = 'replica-demo-1' WHERE id = 'agent-demo-1';
UPDATE agents SET replica_count = 1, current_replica_id = 'replica-demo-2' WHERE id = 'agent-demo-2';
UPDATE agents SET replica_count = 1, current_replica_id = 'replica-demo-3' WHERE id = 'agent-demo-3';

-- ============================================================================
-- DEMO INSTANCE SWITCHES
-- ============================================================================

INSERT INTO instance_switches (
    agent_id, old_instance_id, new_instance_id, switch_reason,
    old_instance_price, new_instance_price, ondemand_baseline,
    price_confidence_old, price_confidence_new,
    price_data_source_old, price_data_source_new,
    estimated_savings, savings_confidence,
    switched_at, success
) VALUES
-- Successful manual switch
(
    'agent-demo-1', 'i-old-demo-1', 'i-demo001', 'manual-user-initiated',
    0.0450, 0.0416, 0.0832,
    1.00, 1.00, 'measured', 'measured',
    3.40, 'high',
    NOW() - INTERVAL 30 DAY, TRUE
),
-- Automatic switch due to price spike
(
    'agent-demo-2', 'i-old-demo-2', 'i-demo002', 'automatic-price-spike',
    0.0750, 0.0420, 0.0832,
    1.00, 1.00, 'measured', 'measured',
    33.00, 'high',
    NOW() - INTERVAL 15 DAY, TRUE
),
-- Replica promotion (manual failover)
(
    'agent-demo-1', 'i-demo001', 'i-replica-demo-1', 'manual-replica-promotion',
    0.0416, 0.0420, 0.0832,
    1.00, 1.00, 'measured', 'measured',
    -0.40, 'high',
    NOW() - INTERVAL 5 DAY, TRUE
)
ON DUPLICATE KEY UPDATE success = VALUES(success);

-- ============================================================================
-- DEMO SPOT INTERRUPTION EVENTS
-- ============================================================================

INSERT INTO spot_interruption_events (
    instance_id, agent_id, pool_id, signal_type, detected_at,
    termination_time, response_action, response_time_ms,
    replica_id, replica_ready, replica_ready_time_ms,
    failover_completed, failover_time_ms, data_loss_seconds,
    success, instance_age_hours, pool_interruption_probability
) VALUES
-- Successful rebalance handling
(
    'i-demo002', 'agent-demo-2', 2, 'rebalance-recommendation', NOW() - INTERVAL 2 HOUR,
    NULL, 'created-replica', 2345, 'replica-demo-2',
    TRUE, 58000, FALSE, NULL, 0, TRUE, 48.5, 0.35
),
-- Successful termination notice handling
(
    'i-old-demo-1', 'agent-demo-1', 1, 'termination-notice', NOW() - INTERVAL 5 DAY,
    NOW() - INTERVAL 5 DAY + INTERVAL 2 MINUTE, 'promoted-existing-replica', 1234,
    'replica-demo-4', TRUE, 5000, TRUE, 8543, 2, TRUE, 120.0, 0.85
),
-- Failed handling (no replica)
(
    'i-old-demo-3', 'agent-demo-4', 4, 'termination-notice', NOW() - INTERVAL 10 DAY,
    NOW() - INTERVAL 10 DAY + INTERVAL 2 MINUTE, 'emergency-snapshot', 5678,
    NULL, FALSE, NULL, FALSE, NULL, 120, FALSE, 24.0, 0.65
)
ON DUPLICATE KEY UPDATE success = VALUES(success);

-- ============================================================================
-- DEMO ML MODEL SESSIONS
-- ============================================================================

INSERT INTO model_upload_sessions (
    id, session_type, status, is_live, is_fallback,
    file_count, file_names, total_size_bytes, created_at, activated_at
) VALUES
-- Live session
(
    'ml-session-live', 'models', 'activated', TRUE, FALSE,
    2, '["xgboost_price_model.pkl", "feature_scaler.joblib"]', 5242880,
    NOW() - INTERVAL 7 DAY, NOW() - INTERVAL 7 DAY
),
-- Fallback session
(
    'ml-session-fallback', 'models', 'activated', FALSE, TRUE,
    2, '["xgboost_price_model_v1.pkl", "feature_scaler_v1.joblib"]', 4718592,
    NOW() - INTERVAL 14 DAY, NOW() - INTERVAL 14 DAY
),
-- Pending session (uploaded but not activated)
(
    'ml-session-pending', 'models', 'uploaded', FALSE, FALSE,
    3, '["xgboost_price_model_v3.pkl", "feature_scaler_v3.joblib", "model_config.json"]', 6291456,
    NOW() - INTERVAL 1 HOUR, NULL
)
ON DUPLICATE KEY UPDATE status = VALUES(status);

-- ============================================================================
-- SUMMARY
-- ============================================================================

SELECT '✅ Demo data inserted successfully!' AS Status;

SELECT
    'Clients' AS Entity, COUNT(*) AS Count FROM clients WHERE id LIKE 'demo-%'
UNION ALL
SELECT 'Spot Pools', COUNT(*) FROM spot_pools
UNION ALL
SELECT 'Instances', COUNT(*) FROM instances WHERE id LIKE 'i-demo%'
UNION ALL
SELECT 'Agents', COUNT(*) FROM agents WHERE id LIKE 'agent-demo-%'
UNION ALL
SELECT 'Replicas', COUNT(*) FROM replica_instances WHERE id LIKE 'replica-demo-%'
UNION ALL
SELECT 'Pricing Snapshots (7 days)', COUNT(*) FROM pricing_snapshots_clean WHERE time_bucket >= NOW() - INTERVAL 7 DAY
UNION ALL
SELECT 'Instance Switches', COUNT(*) FROM instance_switches WHERE agent_id LIKE 'agent-demo-%'
UNION ALL
SELECT 'Interruption Events', COUNT(*) FROM spot_interruption_events WHERE agent_id LIKE 'agent-demo-%'
UNION ALL
SELECT 'ML Model Sessions', COUNT(*) FROM model_upload_sessions WHERE id LIKE 'ml-session-%';

SELECT 'Demo data ready for testing graphs and replica functionality!' AS Message;
