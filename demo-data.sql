-- ==============================================================================
-- AWS Spot Optimizer - Comprehensive Demo Data v2.0
-- ==============================================================================
-- Compatible with schema_cleaned.sql v6.0
-- Includes all necessary data to demonstrate working system
-- ==============================================================================

USE spot_optimizer;

-- Clean existing demo data if re-running
DELETE FROM agent_decision_history WHERE client_id IN (SELECT id FROM clients WHERE email LIKE '%demo%');
DELETE FROM system_events WHERE client_id IN (SELECT id FROM clients WHERE email LIKE '%demo%');
DELETE FROM notifications WHERE client_id IN (SELECT id FROM clients WHERE email LIKE '%demo%');
DELETE FROM pricing_reports WHERE agent_id IN (SELECT id FROM agents WHERE client_id IN (SELECT id FROM clients WHERE email LIKE '%demo%'));
DELETE FROM switches WHERE agent_id IN (SELECT id FROM agents WHERE client_id IN (SELECT id FROM clients WHERE email LIKE '%demo%'));
DELETE FROM instances WHERE client_id IN (SELECT id FROM clients WHERE email LIKE '%demo%');
DELETE FROM agent_configs WHERE agent_id IN (SELECT id FROM agents WHERE client_id IN (SELECT id FROM clients WHERE email LIKE '%demo%'));
DELETE FROM agents WHERE client_id IN (SELECT id FROM clients WHERE email LIKE '%demo%');
DELETE FROM client_savings_monthly WHERE client_id IN (SELECT id FROM clients WHERE email LIKE '%demo%');
DELETE FROM clients_daily_snapshot;
DELETE FROM clients WHERE email LIKE '%demo%';

-- ==============================================================================
-- 1. DEMO CLIENTS
-- ==============================================================================

INSERT INTO clients (id, name, email, client_token, plan, max_agents, max_instances, status, total_savings, created_at)
VALUES
    ('demo-client-001', 'Acme Corporation', 'demo@acme.com', 'demo_token_acme_12345', 'enterprise', 50, 100, 'active', 15847.8923, DATE_SUB(NOW(), INTERVAL 90 DAY)),
    ('demo-client-002', 'StartupXYZ Inc', 'demo@startupxyz.com', 'demo_token_startup_67890', 'professional', 10, 20, 'active', 3421.5612, DATE_SUB(NOW(), INTERVAL 30 DAY)),
    ('demo-client-003', 'Beta Tester Ltd', 'demo@betatester.com', 'demo_token_beta_11111', 'free', 5, 10, 'active', 892.3401, DATE_SUB(NOW(), INTERVAL 7 DAY));

-- ==============================================================================
-- 2. SPOT POOLS (Various Instance Types and AZs)
-- ==============================================================================

INSERT INTO spot_pools (id, instance_type, region, az, is_active, created_at)
VALUES
    -- ap-south-1 region
    ('t3.medium.ap-south-1a', 't3.medium', 'ap-south-1', 'ap-south-1a', TRUE, NOW()),
    ('t3.medium.ap-south-1b', 't3.medium', 'ap-south-1', 'ap-south-1b', TRUE, NOW()),
    ('t3.large.ap-south-1a', 't3.large', 'ap-south-1', 'ap-south-1a', TRUE, NOW()),
    ('t3.large.ap-south-1b', 't3.large', 'ap-south-1', 'ap-south-1b', TRUE, NOW()),
    ('m5.large.ap-south-1a', 'm5.large', 'ap-south-1', 'ap-south-1a', TRUE, NOW()),
    ('m5.large.ap-south-1b', 'm5.large', 'ap-south-1', 'ap-south-1b', TRUE, NOW()),
    ('m5.xlarge.ap-south-1a', 'm5.xlarge', 'ap-south-1', 'ap-south-1a', TRUE, NOW()),
    ('c5.large.ap-south-1a', 'c5.large', 'ap-south-1', 'ap-south-1a', TRUE, NOW()),
    ('c5.xlarge.ap-south-1a', 'c5.xlarge', 'ap-south-1', 'ap-south-1a', TRUE, NOW()),
    ('r5.large.ap-south-1a', 'r5.large', 'ap-south-1', 'ap-south-1a', TRUE, NOW()),

    -- us-east-1 region
    ('t3.medium.us-east-1a', 't3.medium', 'us-east-1', 'us-east-1a', TRUE, NOW()),
    ('m5.large.us-east-1a', 'm5.large', 'us-east-1', 'us-east-1a', TRUE, NOW());

-- ==============================================================================
-- 3. ON-DEMAND PRICE SNAPSHOTS (Historical pricing for comparison)
-- ==============================================================================

INSERT INTO ondemand_price_snapshots (region, instance_type, price, captured_at, recorded_at)
VALUES
    -- ap-south-1 prices
    ('ap-south-1', 't3.medium', 0.0456, NOW(), NOW()),
    ('ap-south-1', 't3.large', 0.0912, NOW(), NOW()),
    ('ap-south-1', 'm5.large', 0.1104, NOW(), NOW()),
    ('ap-south-1', 'm5.xlarge', 0.2208, NOW(), NOW()),
    ('ap-south-1', 'c5.large', 0.0936, NOW(), NOW()),
    ('ap-south-1', 'c5.xlarge', 0.1872, NOW(), NOW()),
    ('ap-south-1', 'r5.large', 0.1376, NOW(), NOW()),

    -- us-east-1 prices
    ('us-east-1', 't3.medium', 0.0416, NOW(), NOW()),
    ('us-east-1', 'm5.large', 0.096, NOW(), NOW());

-- ==============================================================================
-- 4. SPOT PRICE SNAPSHOTS (Historical spot prices for ML models)
-- ==============================================================================

-- Generate 48 hours of spot price history with realistic variations
INSERT INTO spot_price_snapshots (pool_id, price, captured_at, recorded_at)
SELECT
    pool_id,
    base_price + (RAND() * 0.008 - 0.004) AS price,  -- Add ±0.004 variance
    DATE_SUB(NOW(), INTERVAL seq HOUR) AS captured_at,
    DATE_SUB(NOW(), INTERVAL seq HOUR) AS recorded_at
FROM (
    SELECT 't3.medium.ap-south-1a' AS pool_id, 0.0137 AS base_price
    UNION ALL SELECT 't3.medium.ap-south-1b', 0.0142
    UNION ALL SELECT 't3.large.ap-south-1a', 0.0274
    UNION ALL SELECT 't3.large.ap-south-1b', 0.0281
    UNION ALL SELECT 'm5.large.ap-south-1a', 0.0331
    UNION ALL SELECT 'm5.large.ap-south-1b', 0.0348
    UNION ALL SELECT 'm5.xlarge.ap-south-1a', 0.0662
    UNION ALL SELECT 'c5.large.ap-south-1a', 0.0281
    UNION ALL SELECT 'c5.xlarge.ap-south-1a', 0.0562
    UNION ALL SELECT 'r5.large.ap-south-1a', 0.0413
    UNION ALL SELECT 't3.medium.us-east-1a', 0.0125
    UNION ALL SELECT 'm5.large.us-east-1a', 0.0288
) pools
CROSS JOIN (
    SELECT @row := @row + 1 AS seq FROM
        (SELECT 0 UNION SELECT 1 UNION SELECT 2 UNION SELECT 3 UNION SELECT 4) t1,
        (SELECT 0 UNION SELECT 1 UNION SELECT 2 UNION SELECT 3 UNION SELECT 4) t2,
        (SELECT 0 UNION SELECT 1 UNION SELECT 2 UNION SELECT 3 UNION SELECT 4) t3,
        (SELECT @row := 0) r
    LIMIT 48
) sequences;

-- ==============================================================================
-- 5. DEMO AGENTS (Various statuses and configurations)
-- ==============================================================================

INSERT INTO agents (
    id, client_id, logical_agent_id, hostname, instance_id, instance_type,
    region, az, ami_id, private_ip, public_ip, current_mode, current_pool_id,
    spot_price, ondemand_price, baseline_ondemand_price, agent_version,
    status, enabled, last_heartbeat_at, auto_switch_enabled, auto_terminate_enabled,
    installed_at, created_at, last_switch_at
)
VALUES
    -- Acme Corporation agents (enterprise plan - 5 agents)
    (
        'agent-001', 'demo-client-001', 'web-server-prod-01', 'ip-10-0-1-101',
        'i-0abc123def456', 't3.medium', 'ap-south-1', 'ap-south-1a', 'ami-0abcd1234',
        '10.0.1.101', '13.232.45.67', 'spot', 't3.medium.ap-south-1a',
        0.0137, 0.0456, 0.0456, '4.2.0',
        'online', TRUE, NOW(), TRUE, TRUE,
        DATE_SUB(NOW(), INTERVAL 45 DAY), DATE_SUB(NOW(), INTERVAL 45 DAY), DATE_SUB(NOW(), INTERVAL 3 HOUR)
    ),
    (
        'agent-002', 'demo-client-001', 'api-server-prod-01', 'ip-10-0-1-102',
        'i-0def789ghi012', 'm5.large', 'ap-south-1', 'ap-south-1b', 'ami-0abcd1234',
        '10.0.1.102', '13.232.45.68', 'spot', 'm5.large.ap-south-1b',
        0.0348, 0.1104, 0.1104, '4.2.0',
        'online', TRUE, NOW(), TRUE, TRUE,
        DATE_SUB(NOW(), INTERVAL 30 DAY), DATE_SUB(NOW(), INTERVAL 30 DAY), DATE_SUB(NOW(), INTERVAL 1 HOUR)
    ),
    (
        'agent-003', 'demo-client-001', 'worker-01', 'ip-10-0-2-101',
        'i-0xyz789abc456', 'c5.large', 'ap-south-1', 'ap-south-1a', 'ami-0abcd1234',
        '10.0.2.101', '13.232.45.69', 'spot', 'c5.large.ap-south-1a',
        0.0281, 0.0936, 0.0936, '4.2.0',
        'online', TRUE, DATE_SUB(NOW(), INTERVAL 30 SECOND), TRUE, TRUE,
        DATE_SUB(NOW(), INTERVAL 20 DAY), DATE_SUB(NOW(), INTERVAL 20 DAY), DATE_SUB(NOW(), INTERVAL 6 HOUR)
    ),
    (
        'agent-004', 'demo-client-001', 'db-primary', 'ip-10-0-3-101',
        'i-0aaa111bbb222', 'm5.xlarge', 'ap-south-1', 'ap-south-1a', 'ami-0abcd1234',
        '10.0.3.101', '13.232.45.70', 'on-demand', NULL,
        NULL, 0.2208, 0.2208, '4.2.0',
        'online', TRUE, NOW(), TRUE, FALSE,
        DATE_SUB(NOW(), INTERVAL 60 DAY), DATE_SUB(NOW(), INTERVAL 60 DAY), DATE_SUB(NOW(), INTERVAL 2 HOUR)
    ),
    (
        'agent-005', 'demo-client-001', 'worker-02', 'ip-10-0-2-102',
        'i-0zzz888yyy777', 'c5.xlarge', 'ap-south-1', 'ap-south-1a', 'ami-0abcd1234',
        '10.0.2.102', NULL, 'unknown', NULL,
        NULL, 0.1872, 0.1872, '4.1.0',
        'offline', TRUE, DATE_SUB(NOW(), INTERVAL 2 HOUR), TRUE, TRUE,
        DATE_SUB(NOW(), INTERVAL 10 DAY), DATE_SUB(NOW(), INTERVAL 10 DAY), NULL
    ),

    -- StartupXYZ agents (professional plan - 2 agents)
    (
        'agent-006', 'demo-client-002', 'app-server-01', 'ip-172-31-1-10',
        'i-0startup001', 't3.large', 'ap-south-1', 'ap-south-1a', 'ami-0startup1',
        '172.31.1.10', '65.1.123.45', 'spot', 't3.large.ap-south-1a',
        0.0274, 0.0912, 0.0912, '4.2.0',
        'online', TRUE, NOW(), TRUE, TRUE,
        DATE_SUB(NOW(), INTERVAL 15 DAY), DATE_SUB(NOW(), INTERVAL 15 DAY), DATE_SUB(NOW(), INTERVAL 4 HOUR)
    ),
    (
        'agent-007', 'demo-client-002', 'cache-server-01', 'ip-172-31-1-11',
        'i-0startup002', 'r5.large', 'ap-south-1', 'ap-south-1a', 'ami-0startup1',
        '172.31.1.11', '65.1.123.46', 'spot', 'r5.large.ap-south-1a',
        0.0413, 0.1376, 0.1376, '4.2.0',
        'online', TRUE, DATE_SUB(NOW(), INTERVAL 45 SECOND), TRUE, TRUE,
        DATE_SUB(NOW(), INTERVAL 20 DAY), DATE_SUB(NOW(), INTERVAL 20 DAY), DATE_SUB(NOW(), INTERVAL 5 HOUR)
    ),

    -- Beta tester agent (free plan - 1 agent)
    (
        'agent-008', 'demo-client-003', 'test-instance-01', 'ip-10-20-30-40',
        'i-0beta001', 't3.medium', 'us-east-1', 'us-east-1a', 'ami-0beta001',
        '10.20.30.40', '54.234.56.78', 'spot', 't3.medium.us-east-1a',
        0.0125, 0.0416, 0.0416, '4.2.0',
        'online', TRUE, NOW(), TRUE, TRUE,
        DATE_SUB(NOW(), INTERVAL 5 DAY), DATE_SUB(NOW(), INTERVAL 5 DAY), DATE_SUB(NOW(), INTERVAL 2 HOUR)
    );

-- ==============================================================================
-- 6. AGENT CONFIGS
-- ==============================================================================

INSERT INTO agent_configs (agent_id, min_savings_percent, risk_threshold,
                          max_switches_per_week, max_switches_per_day, min_pool_duration_hours)
VALUES
    ('agent-001', 30.00, 0.30, 10, 3, 2),
    ('agent-002', 30.00, 0.30, 10, 3, 2),
    ('agent-003', 30.00, 0.30, 10, 3, 2),
    ('agent-004', 30.00, 0.30, 10, 3, 2),
    ('agent-005', 30.00, 0.30, 10, 3, 2),
    ('agent-006', 25.00, 0.35, 12, 4, 2),
    ('agent-007', 25.00, 0.35, 12, 4, 2),
    ('agent-008', 20.00, 0.40, 15, 5, 1);

-- ==============================================================================
-- 7. INSTANCES (Current running instances)
-- ==============================================================================

INSERT INTO instances (id, client_id, agent_id, instance_type, region, az, ami_id,
                      current_mode, current_pool_id, spot_price, ondemand_price,
                      baseline_ondemand_price, is_active, installed_at, last_switch_at)
VALUES
    ('i-0abc123def456', 'demo-client-001', 'agent-001', 't3.medium', 'ap-south-1', 'ap-south-1a', 'ami-0abcd1234',
     'spot', 't3.medium.ap-south-1a', 0.0137, 0.0456, 0.0456, TRUE,
     DATE_SUB(NOW(), INTERVAL 3 HOUR), DATE_SUB(NOW(), INTERVAL 3 HOUR)),

    ('i-0def789ghi012', 'demo-client-001', 'agent-002', 'm5.large', 'ap-south-1', 'ap-south-1b', 'ami-0abcd1234',
     'spot', 'm5.large.ap-south-1b', 0.0348, 0.1104, 0.1104, TRUE,
     DATE_SUB(NOW(), INTERVAL 1 HOUR), DATE_SUB(NOW(), INTERVAL 1 HOUR)),

    ('i-0xyz789abc456', 'demo-client-001', 'agent-003', 'c5.large', 'ap-south-1', 'ap-south-1a', 'ami-0abcd1234',
     'spot', 'c5.large.ap-south-1a', 0.0281, 0.0936, 0.0936, TRUE,
     DATE_SUB(NOW(), INTERVAL 6 HOUR), DATE_SUB(NOW(), INTERVAL 6 HOUR)),

    ('i-0aaa111bbb222', 'demo-client-001', 'agent-004', 'm5.xlarge', 'ap-south-1', 'ap-south-1a', 'ami-0abcd1234',
     'on-demand', NULL, NULL, 0.2208, 0.2208, TRUE,
     DATE_SUB(NOW(), INTERVAL 2 HOUR), DATE_SUB(NOW(), INTERVAL 2 HOUR)),

    ('i-0startup001', 'demo-client-002', 'agent-006', 't3.large', 'ap-south-1', 'ap-south-1a', 'ami-0startup1',
     'spot', 't3.large.ap-south-1a', 0.0274, 0.0912, 0.0912, TRUE,
     DATE_SUB(NOW(), INTERVAL 4 HOUR), DATE_SUB(NOW(), INTERVAL 4 HOUR)),

    ('i-0startup002', 'demo-client-002', 'agent-007', 'r5.large', 'ap-south-1', 'ap-south-1a', 'ami-0startup1',
     'spot', 'r5.large.ap-south-1a', 0.0413, 0.1376, 0.1376, TRUE,
     DATE_SUB(NOW(), INTERVAL 5 HOUR), DATE_SUB(NOW(), INTERVAL 5 HOUR)),

    ('i-0beta001', 'demo-client-003', 'agent-008', 't3.medium', 'us-east-1', 'us-east-1a', 'ami-0beta001',
     'spot', 't3.medium.us-east-1a', 0.0125, 0.0416, 0.0416, TRUE,
     DATE_SUB(NOW(), INTERVAL 2 HOUR), DATE_SUB(NOW(), INTERVAL 2 HOUR));

-- ==============================================================================
-- 8. PRICING REPORTS (CRITICAL - Last 10 minutes of data for each agent)
-- ==============================================================================
-- This is what the Models view uses to show "pricing health"

-- Generate 5 recent reports for each online agent (within last 10 minutes)
INSERT INTO pricing_reports (
    id, agent_id, instance_id, instance_type, region, az, current_mode, current_pool_id,
    on_demand_price, current_spot_price, cheapest_pool_id, cheapest_pool_price,
    spot_pools, collected_at, received_at
)
SELECT
    UUID() as id,
    agent_id,
    instance_id,
    instance_type,
    region,
    az,
    current_mode,
    current_pool_id,
    ondemand_price as on_demand_price,
    spot_price + (RAND() * 0.002 - 0.001) as current_spot_price,
    current_pool_id as cheapest_pool_id,
    spot_price + (RAND() * 0.002 - 0.001) as cheapest_pool_price,
    JSON_OBJECT(
        'pools', JSON_ARRAY(
            JSON_OBJECT('pool_id', current_pool_id, 'price', spot_price, 'az', az)
        )
    ) as spot_pools,
    DATE_SUB(NOW(), INTERVAL seq * 2 MINUTE) as collected_at,
    DATE_SUB(NOW(), INTERVAL seq * 2 MINUTE) as received_at
FROM agents
CROSS JOIN (
    SELECT 0 AS seq UNION SELECT 1 UNION SELECT 2 UNION SELECT 3 UNION SELECT 4
) sequences
WHERE status = 'online'
AND id IN ('agent-001', 'agent-002', 'agent-003', 'agent-004', 'agent-006', 'agent-007', 'agent-008');

-- ==============================================================================
-- 9. SWITCHES (Historical switch events)
-- ==============================================================================

INSERT INTO switches (
    id, client_id, agent_id, command_id,
    old_instance_id, old_instance_type, old_region, old_az, old_mode, old_pool_id,
    new_instance_id, new_instance_type, new_region, new_az, new_mode, new_pool_id,
    on_demand_price, old_spot_price, new_spot_price, savings_impact,
    event_trigger, trigger_type, snapshot_used, snapshot_id, ami_id,
    initiated_at, instance_ready_at, old_terminated_at, timestamp,
    total_duration_seconds, downtime_seconds, success
)
VALUES
    (UUID(), 'demo-client-001', 'agent-001', NULL,
     'i-0old001', 't3.medium', 'ap-south-1', 'ap-south-1b', 'spot', 't3.medium.ap-south-1b',
     'i-0abc123def456', 't3.medium', 'ap-south-1', 'ap-south-1a', 'spot', 't3.medium.ap-south-1a',
     0.0456, 0.0152, 0.0137, 0.0015,
     'interruption', 'ml', TRUE, 'snap-0abc123', 'ami-0abcd1234',
     DATE_SUB(NOW(), INTERVAL 3 HOUR), DATE_SUB(NOW(), INTERVAL 3 HOUR), DATE_SUB(NOW(), INTERVAL 3 HOUR),
     DATE_SUB(NOW(), INTERVAL 3 HOUR), 183, 45, TRUE),

    (UUID(), 'demo-client-001', 'agent-002', NULL,
     'i-0old002', 'm5.large', 'ap-south-1', 'ap-south-1a', 'spot', 'm5.large.ap-south-1a',
     'i-0def789ghi012', 'm5.large', 'ap-south-1', 'ap-south-1b', 'spot', 'm5.large.ap-south-1b',
     0.1104, 0.0365, 0.0348, 0.0017,
     'price', 'ml', TRUE, 'snap-0def789', 'ami-0abcd1234',
     DATE_SUB(NOW(), INTERVAL 1 HOUR), DATE_SUB(NOW(), INTERVAL 1 HOUR), DATE_SUB(NOW(), INTERVAL 1 HOUR),
     DATE_SUB(NOW(), INTERVAL 1 HOUR), 201, 52, TRUE),

    (UUID(), 'demo-client-001', 'agent-003', NULL,
     'i-0old003', 'c5.large', 'ap-south-1', 'ap-south-1b', 'spot', 'c5.large.ap-south-1b',
     'i-0xyz789abc456', 'c5.large', 'ap-south-1', 'ap-south-1a', 'spot', 'c5.large.ap-south-1a',
     0.0936, 0.0295, 0.0281, 0.0014,
     'price', 'ml', TRUE, 'snap-0xyz789', 'ami-0abcd1234',
     DATE_SUB(NOW(), INTERVAL 6 HOUR), DATE_SUB(NOW(), INTERVAL 6 HOUR), DATE_SUB(NOW(), INTERVAL 6 HOUR),
     DATE_SUB(NOW(), INTERVAL 6 HOUR), 167, 38, TRUE),

    (UUID(), 'demo-client-001', 'agent-004', NULL,
     'i-0old004', 'm5.xlarge', 'ap-south-1', 'ap-south-1a', 'spot', 'm5.xlarge.ap-south-1a',
     'i-0aaa111bbb222', 'm5.xlarge', 'ap-south-1', 'ap-south-1a', 'on-demand', NULL,
     0.2208, 0.0680, 0.2208, -0.1528,
     'risk', 'ml', TRUE, 'snap-0aaa111', 'ami-0abcd1234',
     DATE_SUB(NOW(), INTERVAL 2 HOUR), DATE_SUB(NOW(), INTERVAL 2 HOUR), DATE_SUB(NOW(), INTERVAL 2 HOUR),
     DATE_SUB(NOW(), INTERVAL 2 HOUR), 245, 60, TRUE),

    (UUID(), 'demo-client-002', 'agent-006', NULL,
     'i-0old006', 't3.large', 'ap-south-1', 'ap-south-1b', 'spot', 't3.large.ap-south-1b',
     'i-0startup001', 't3.large', 'ap-south-1', 'ap-south-1a', 'spot', 't3.large.ap-south-1a',
     0.0912, 0.0288, 0.0274, 0.0014,
     'manual', 'manual', TRUE, 'snap-0startup', 'ami-0startup1',
     DATE_SUB(NOW(), INTERVAL 4 HOUR), DATE_SUB(NOW(), INTERVAL 4 HOUR), DATE_SUB(NOW(), INTERVAL 4 HOUR),
     DATE_SUB(NOW(), INTERVAL 4 HOUR), 195, 48, TRUE);

-- ==============================================================================
-- 10. SYSTEM EVENTS (Activity log)
-- ==============================================================================

INSERT INTO system_events (client_id, agent_id, event_type, severity, message, created_at)
VALUES
    ('demo-client-001', 'agent-001', 'switch', 'info', 'Spot instance switched successfully from ap-south-1b to ap-south-1a', DATE_SUB(NOW(), INTERVAL 3 HOUR)),
    ('demo-client-001', 'agent-001', 'interruption', 'warning', 'Spot interruption notice received - switching to new pool', DATE_SUB(NOW(), INTERVAL 3 HOUR)),
    ('demo-client-001', 'agent-002', 'switch', 'info', 'Switched to better spot pool with 4.65% lower price', DATE_SUB(NOW(), INTERVAL 1 HOUR)),
    ('demo-client-001', 'agent-003', 'price_alert', 'warning', 'Spot price increased to $0.0295/hr (21.3% above baseline)', DATE_SUB(NOW(), INTERVAL 6 HOUR)),
    ('demo-client-001', 'agent-003', 'switch', 'info', 'Successfully switched to pool with better pricing', DATE_SUB(NOW(), INTERVAL 6 HOUR)),
    ('demo-client-001', 'agent-004', 'risk_alert', 'high', 'ML model detected 78% interruption risk - switching to on-demand', DATE_SUB(NOW(), INTERVAL 2 HOUR)),
    ('demo-client-001', 'agent-004', 'switch', 'info', 'Switched to on-demand mode for stability', DATE_SUB(NOW(), INTERVAL 2 HOUR)),
    ('demo-client-001', 'agent-005', 'heartbeat_miss', 'error', 'Agent missed 4 consecutive heartbeats - marked offline', DATE_SUB(NOW(), INTERVAL 2 HOUR)),
    ('demo-client-001', NULL, 'savings_milestone', 'info', 'Total savings reached $15,000 milestone! 🎉', DATE_SUB(NOW(), INTERVAL 1 DAY)),
    ('demo-client-002', 'agent-006', 'switch', 'info', 'Manual switch completed successfully', DATE_SUB(NOW(), INTERVAL 4 HOUR)),
    ('demo-client-002', 'agent-007', 'agent_online', 'info', 'Agent came online and registered successfully', DATE_SUB(NOW(), INTERVAL 5 HOUR)),
    ('demo-client-002', NULL, 'client_created', 'info', 'New client account created', DATE_SUB(NOW(), INTERVAL 30 DAY)),
    ('demo-client-003', 'agent-008', 'agent_online', 'info', 'Agent installed and registered', DATE_SUB(NOW(), INTERVAL 5 DAY)),
    ('demo-client-003', NULL, 'client_created', 'info', 'New client account created', DATE_SUB(NOW(), INTERVAL 7 DAY));

-- ==============================================================================
-- 11. NOTIFICATIONS (User notifications)
-- ==============================================================================

INSERT INTO notifications (id, client_id, agent_id, notification_type, title, message, severity, is_read, created_at)
VALUES
    (UUID(), 'demo-client-001', 'agent-001', 'interruption', 'Spot Interruption Handled',
     'Your spot instance was interrupted but automatically switched to a new pool. No downtime occurred.',
     'info', TRUE, DATE_SUB(NOW(), INTERVAL 3 HOUR)),

    (UUID(), 'demo-client-001', 'agent-004', 'switch', 'Switched to On-Demand',
     'Agent switched to on-demand mode due to high interruption risk (78%). Will switch back when conditions improve.',
     'warning', FALSE, DATE_SUB(NOW(), INTERVAL 2 HOUR)),

    (UUID(), 'demo-client-001', 'agent-005', 'offline', 'Agent Offline',
     'Agent "worker-02" has not responded to heartbeats for 2 hours. Please check the instance status.',
     'error', FALSE, DATE_SUB(NOW(), INTERVAL 2 HOUR)),

    (UUID(), 'demo-client-001', NULL, 'savings', 'Savings Milestone!',
     'Congratulations! You have saved $15,847.89 since you started using Spot Optimizer. Keep it up! 🎉',
     'info', FALSE, DATE_SUB(NOW(), INTERVAL 1 DAY)),

    (UUID(), 'demo-client-002', 'agent-006', 'switch', 'Cost Optimization',
     'Agent switched to a better spot pool, reducing hourly cost by 4.86%. Monthly savings: ~$29.50',
     'info', TRUE, DATE_SUB(NOW(), INTERVAL 4 HOUR)),

    (UUID(), 'demo-client-003', 'agent-008', 'welcome', 'Welcome to Spot Optimizer!',
     'Your first agent is now online and optimizing costs. Check out the dashboard to see real-time savings.',
     'info', TRUE, DATE_SUB(NOW(), INTERVAL 5 DAY));

-- ==============================================================================
-- 12. CLIENT MONTHLY SAVINGS SUMMARY
-- ==============================================================================

INSERT INTO client_savings_monthly (client_id, year, month, baseline_cost, actual_cost, savings, savings_percentage, switch_count, instance_count)
VALUES
    ('demo-client-001', YEAR(DATE_SUB(NOW(), INTERVAL 1 MONTH)), MONTH(DATE_SUB(NOW(), INTERVAL 1 MONTH)),
     7234.56, 1842.34, 5392.22, 74.53, 18, 5),

    ('demo-client-001', YEAR(NOW()), MONTH(NOW()),
     4178.34, 1523.12, 2655.22, 63.54, 12, 5),

    ('demo-client-002', YEAR(NOW()), MONTH(NOW()),
     1123.89, 287.45, 836.44, 74.42, 8, 2),

    ('demo-client-003', YEAR(NOW()), MONTH(NOW()),
     78.43, 18.92, 59.51, 75.88, 3, 1);

-- ==============================================================================
-- 13. CLIENT DAILY SNAPSHOTS (For growth analytics)
-- ==============================================================================

INSERT INTO clients_daily_snapshot (snapshot_date, total_clients, new_clients_today, active_clients)
SELECT
    DATE_SUB(CURDATE(), INTERVAL seq DAY) as snapshot_date,
    CASE
        WHEN seq >= 90 THEN 1
        WHEN seq >= 30 THEN 2
        WHEN seq >= 7 THEN 3
        ELSE 3
    END as total_clients,
    CASE
        WHEN seq = 90 THEN 1
        WHEN seq = 30 THEN 1
        WHEN seq = 7 THEN 1
        ELSE 0
    END as new_clients_today,
    CASE
        WHEN seq >= 90 THEN 1
        WHEN seq >= 30 THEN 2
        WHEN seq >= 7 THEN 3
        ELSE 3
    END as active_clients
FROM (
    SELECT @row := @row + 1 AS seq FROM
        (SELECT 0 UNION SELECT 1 UNION SELECT 2 UNION SELECT 3 UNION SELECT 4 UNION
         SELECT 5 UNION SELECT 6 UNION SELECT 7 UNION SELECT 8 UNION SELECT 9) t1,
        (SELECT 0 UNION SELECT 1 UNION SELECT 2 UNION SELECT 3 UNION SELECT 4 UNION
         SELECT 5 UNION SELECT 6 UNION SELECT 7 UNION SELECT 8 UNION SELECT 9) t2,
        (SELECT @row := -1) r
) sequences
WHERE seq < 90
ORDER BY seq DESC;

-- ==============================================================================
-- 14. AGENT DECISION HISTORY (For Models view - last 5 decisions per agent)
-- ==============================================================================

INSERT INTO agent_decision_history (
    agent_id, client_id, decision_type, recommended_action,
    recommended_pool_id, risk_score, expected_savings,
    current_mode, current_pool_id, current_price, decision_time, executed, execution_time
)
VALUES
    -- agent-001 recent decisions
    ('agent-001', 'demo-client-001', 'stay', 'stay', NULL, 0.15, 0.0319,
     'spot', 't3.medium.ap-south-1a', 0.0137, DATE_SUB(NOW(), INTERVAL 5 MINUTE), FALSE, NULL),
    ('agent-001', 'demo-client-001', 'stay', 'stay', NULL, 0.18, 0.0319,
     'spot', 't3.medium.ap-south-1a', 0.0137, DATE_SUB(NOW(), INTERVAL 35 MINUTE), FALSE, NULL),
    ('agent-001', 'demo-client-001', 'stay', 'stay', NULL, 0.16, 0.0319,
     'spot', 't3.medium.ap-south-1a', 0.0138, DATE_SUB(NOW(), INTERVAL 1 HOUR), FALSE, NULL),
    ('agent-001', 'demo-client-001', 'stay', 'stay', NULL, 0.20, 0.0319,
     'spot', 't3.medium.ap-south-1a', 0.0136, DATE_SUB(NOW(), INTERVAL 2 HOUR), FALSE, NULL),
    ('agent-001', 'demo-client-001', 'switch_spot', 'switch', 't3.medium.ap-south-1a', 0.75, 0.0015,
     'spot', 't3.medium.ap-south-1b', 0.0152, DATE_SUB(NOW(), INTERVAL 3 HOUR), TRUE, DATE_SUB(NOW(), INTERVAL 3 HOUR)),

    -- agent-002 recent decisions
    ('agent-002', 'demo-client-001', 'stay', 'stay', NULL, 0.12, 0.0756,
     'spot', 'm5.large.ap-south-1b', 0.0348, DATE_SUB(NOW(), INTERVAL 10 MINUTE), FALSE, NULL),
    ('agent-002', 'demo-client-001', 'stay', 'stay', NULL, 0.14, 0.0756,
     'spot', 'm5.large.ap-south-1b', 0.0349, DATE_SUB(NOW(), INTERVAL 30 MINUTE), FALSE, NULL),
    ('agent-002', 'demo-client-001', 'stay', 'stay', NULL, 0.11, 0.0756,
     'spot', 'm5.large.ap-south-1b', 0.0347, DATE_SUB(NOW(), INTERVAL 50 MINUTE), FALSE, NULL),
    ('agent-002', 'demo-client-001', 'switch_spot', 'switch', 'm5.large.ap-south-1b', 0.22, 0.0017,
     'spot', 'm5.large.ap-south-1a', 0.0365, DATE_SUB(NOW(), INTERVAL 1 HOUR), TRUE, DATE_SUB(NOW(), INTERVAL 1 HOUR)),
    ('agent-002', 'demo-client-001', 'stay', 'stay', NULL, 0.25, 0.0739,
     'spot', 'm5.large.ap-south-1a', 0.0365, DATE_SUB(NOW(), INTERVAL 2 HOUR), FALSE, NULL),

    -- agent-003 recent decisions
    ('agent-003', 'demo-client-001', 'stay', 'stay', NULL, 0.25, 0.0655,
     'spot', 'c5.large.ap-south-1a', 0.0281, DATE_SUB(NOW(), INTERVAL 15 MINUTE), FALSE, NULL),
    ('agent-003', 'demo-client-001', 'stay', 'stay', NULL, 0.23, 0.0655,
     'spot', 'c5.large.ap-south-1a', 0.0280, DATE_SUB(NOW(), INTERVAL 45 MINUTE), FALSE, NULL),
    ('agent-003', 'demo-client-001', 'stay', 'stay', NULL, 0.28, 0.0655,
     'spot', 'c5.large.ap-south-1a', 0.0282, DATE_SUB(NOW(), INTERVAL 2 HOUR), FALSE, NULL),
    ('agent-003', 'demo-client-001', 'stay', 'stay', NULL, 0.30, 0.0641,
     'spot', 'c5.large.ap-south-1a', 0.0283, DATE_SUB(NOW(), INTERVAL 4 HOUR), FALSE, NULL),
    ('agent-003', 'demo-client-001', 'switch_spot', 'switch', 'c5.large.ap-south-1a', 0.40, 0.0014,
     'spot', 'c5.large.ap-south-1b', 0.0295, DATE_SUB(NOW(), INTERVAL 6 HOUR), TRUE, DATE_SUB(NOW(), INTERVAL 6 HOUR)),

    -- agent-004 recent decisions (on-demand mode)
    ('agent-004', 'demo-client-001', 'stay', 'stay', NULL, 0.82, -0.1528,
     'on-demand', NULL, 0.2208, DATE_SUB(NOW(), INTERVAL 20 MINUTE), FALSE, NULL),
    ('agent-004', 'demo-client-001', 'stay', 'stay', NULL, 0.80, -0.1528,
     'on-demand', NULL, 0.2208, DATE_SUB(NOW(), INTERVAL 50 MINUTE), FALSE, NULL),
    ('agent-004', 'demo-client-001', 'stay', 'stay', NULL, 0.85, -0.1528,
     'on-demand', NULL, 0.2208, DATE_SUB(NOW(), INTERVAL 1 HOUR), FALSE, NULL),
    ('agent-004', 'demo-client-001', 'switch_ondemand', 'switch', NULL, 0.78, -0.1528,
     'spot', 'm5.xlarge.ap-south-1a', 0.0680, DATE_SUB(NOW(), INTERVAL 2 HOUR), TRUE, DATE_SUB(NOW(), INTERVAL 2 HOUR)),
    ('agent-004', 'demo-client-001', 'stay', 'stay', NULL, 0.72, -0.1518,
     'spot', 'm5.xlarge.ap-south-1a', 0.0670, DATE_SUB(NOW(), INTERVAL 3 HOUR), FALSE, NULL),

    -- agent-006 recent decisions
    ('agent-006', 'demo-client-002', 'stay', 'stay', NULL, 0.20, 0.0638,
     'spot', 't3.large.ap-south-1a', 0.0274, DATE_SUB(NOW(), INTERVAL 25 MINUTE), FALSE, NULL),
    ('agent-006', 'demo-client-002', 'stay', 'stay', NULL, 0.18, 0.0638,
     'spot', 't3.large.ap-south-1a', 0.0273, DATE_SUB(NOW(), INTERVAL 55 MINUTE), FALSE, NULL),
    ('agent-006', 'demo-client-002', 'stay', 'stay', NULL, 0.22, 0.0638,
     'spot', 't3.large.ap-south-1a', 0.0275, DATE_SUB(NOW(), INTERVAL 2 HOUR), FALSE, NULL),
    ('agent-006', 'demo-client-002', 'switch_spot', 'switch', 't3.large.ap-south-1a', 0.35, 0.0014,
     'spot', 't3.large.ap-south-1b', 0.0288, DATE_SUB(NOW(), INTERVAL 4 HOUR), TRUE, DATE_SUB(NOW(), INTERVAL 4 HOUR)),
    ('agent-006', 'demo-client-002', 'stay', 'stay', NULL, 0.30, 0.0624,
     'spot', 't3.large.ap-south-1b', 0.0288, DATE_SUB(NOW(), INTERVAL 5 HOUR), FALSE, NULL),

    -- agent-007 recent decisions
    ('agent-007', 'demo-client-002', 'stay', 'stay', NULL, 0.28, 0.0963,
     'spot', 'r5.large.ap-south-1a', 0.0413, DATE_SUB(NOW(), INTERVAL 18 MINUTE), FALSE, NULL),
    ('agent-007', 'demo-client-002', 'stay', 'stay', NULL, 0.26, 0.0963,
     'spot', 'r5.large.ap-south-1a', 0.0412, DATE_SUB(NOW(), INTERVAL 48 MINUTE), FALSE, NULL),
    ('agent-007', 'demo-client-002', 'stay', 'stay', NULL, 0.30, 0.0963,
     'spot', 'r5.large.ap-south-1a', 0.0414, DATE_SUB(NOW(), INTERVAL 1 HOUR), FALSE, NULL),
    ('agent-007', 'demo-client-002', 'stay', 'stay', NULL, 0.25, 0.0963,
     'spot', 'r5.large.ap-south-1a', 0.0411, DATE_SUB(NOW(), INTERVAL 2 HOUR), FALSE, NULL),
    ('agent-007', 'demo-client-002', 'stay', 'stay', NULL, 0.32, 0.0963,
     'spot', 'r5.large.ap-south-1a', 0.0415, DATE_SUB(NOW(), INTERVAL 3 HOUR), FALSE, NULL),

    -- agent-008 recent decisions
    ('agent-008', 'demo-client-003', 'stay', 'stay', NULL, 0.15, 0.0291,
     'spot', 't3.medium.us-east-1a', 0.0125, DATE_SUB(NOW(), INTERVAL 12 MINUTE), FALSE, NULL),
    ('agent-008', 'demo-client-003', 'stay', 'stay', NULL, 0.17, 0.0291,
     'spot', 't3.medium.us-east-1a', 0.0126, DATE_SUB(NOW(), INTERVAL 42 MINUTE), FALSE, NULL),
    ('agent-008', 'demo-client-003', 'stay', 'stay', NULL, 0.14, 0.0291,
     'spot', 't3.medium.us-east-1a', 0.0124, DATE_SUB(NOW(), INTERVAL 1 HOUR), FALSE, NULL),
    ('agent-008', 'demo-client-003', 'stay', 'stay', NULL, 0.19, 0.0291,
     'spot', 't3.medium.us-east-1a', 0.0127, DATE_SUB(NOW(), INTERVAL 90 MINUTE), FALSE, NULL),
    ('agent-008', 'demo-client-003', 'stay', 'stay', NULL, 0.16, 0.0291,
     'spot', 't3.medium.us-east-1a', 0.0125, DATE_SUB(NOW(), INTERVAL 2 HOUR), FALSE, NULL);

-- ==============================================================================
-- 15. MODEL REGISTRY (Sample ML models)
-- ==============================================================================

INSERT INTO model_registry (id, model_name, model_type, version, file_path, is_active, description, loaded_at)
VALUES
    (UUID(), 'capacity_predictor', 'classification', 'v1.2.0', '/models/capacity_predictor_v1.2.0.pkl', TRUE,
     'Predicts spot capacity interruption risk based on historical patterns', NOW()),

    (UUID(), 'price_predictor', 'regression', 'v1.1.0', '/models/price_predictor_v1.1.0.pkl', TRUE,
     'Predicts future spot prices for cost optimization', NOW());

-- ==============================================================================
-- 16. RISK SCORES (Sample ML predictions)
-- ==============================================================================

INSERT INTO risk_scores (client_id, agent_id, instance_id, risk_score, recommended_action,
                        recommended_mode, recommended_pool_id, expected_savings_per_hour,
                        allowed, reason, model_version)
SELECT
    a.client_id,
    a.id,
    a.instance_id,
    CASE
        WHEN a.current_mode = 'on-demand' THEN 0.80 + (RAND() * 0.10)
        ELSE 0.15 + (RAND() * 0.15)
    END as risk_score,
    CASE
        WHEN a.current_mode = 'on-demand' THEN 'stay'
        ELSE 'stay'
    END as recommended_action,
    a.current_mode,
    a.current_pool_id,
    CASE
        WHEN a.current_mode = 'spot' THEN (a.ondemand_price - a.spot_price)
        ELSE 0
    END as expected_savings_per_hour,
    TRUE as allowed,
    'Current conditions are optimal' as reason,
    'v1.2.0' as model_version
FROM agents a
WHERE a.status = 'online'
AND a.id IN ('agent-001', 'agent-002', 'agent-003', 'agent-004', 'agent-006', 'agent-007', 'agent-008');

-- ==============================================================================
-- SUMMARY AND VERIFICATION
-- ==============================================================================

SELECT '✅ Comprehensive demo data v2.0 inserted successfully!' AS Status;
SELECT '' AS '';
SELECT '📊 Data Summary:' AS Info;
SELECT
    'Clients' AS Entity,
    COUNT(*) AS Count,
    'Demo accounts with realistic usage patterns' AS Description
FROM clients WHERE email LIKE '%demo%'
UNION ALL
SELECT
    'Agents',
    COUNT(*),
    CONCAT(
        SUM(CASE WHEN status = 'online' THEN 1 ELSE 0 END),
        ' online, ',
        SUM(CASE WHEN status = 'offline' THEN 1 ELSE 0 END),
        ' offline'
    )
FROM agents WHERE client_id IN (SELECT id FROM clients WHERE email LIKE '%demo%')
UNION ALL
SELECT
    'Spot Pools',
    COUNT(*),
    'Various instance types across regions'
FROM spot_pools
UNION ALL
SELECT
    'Pricing Reports',
    COUNT(*),
    'Last 10 minutes - shows agents are active'
FROM pricing_reports
UNION ALL
SELECT
    'Switches',
    COUNT(*),
    'Historical switch events with timing data'
FROM switches WHERE agent_id IN (SELECT id FROM agents WHERE client_id IN (SELECT id FROM clients WHERE email LIKE '%demo%'))
UNION ALL
SELECT
    'Agent Decisions',
    COUNT(*),
    'Last 5 decisions per agent for Models view'
FROM agent_decision_history
UNION ALL
SELECT
    'System Events',
    COUNT(*),
    'Activity logs and alerts'
FROM system_events WHERE client_id IN (SELECT id FROM clients WHERE email LIKE '%demo%')
UNION ALL
SELECT
    'Notifications',
    COUNT(*),
    'User notifications (some unread)'
FROM notifications WHERE client_id IN (SELECT id FROM clients WHERE email LIKE '%demo%')
UNION ALL
SELECT
    'Spot Price History',
    COUNT(*),
    'Last 48 hours for ML models'
FROM spot_price_snapshots
UNION ALL
SELECT
    'Client Snapshots',
    COUNT(*),
    'Last 90 days for growth charts'
FROM clients_daily_snapshot;

SELECT '' AS '';
SELECT '🎯 Demo Accounts (ready to test):' AS Info;
SELECT
    name AS 'Client Name',
    email AS 'Email',
    client_token AS 'API Token',
    plan AS 'Plan',
    CONCAT('$', FORMAT(total_savings, 2)) AS 'Total Savings',
    (SELECT COUNT(*) FROM agents WHERE client_id = clients.id AND status = 'online') AS 'Online Agents'
FROM clients
WHERE email LIKE '%demo%'
ORDER BY created_at;

SELECT '' AS '';
SELECT '✨ Features you can now test:' AS Features;
SELECT '1' AS No, '✓ Dashboard - Global stats and metrics' AS Feature
UNION ALL SELECT '2', '✓ Client Management - View all demo clients'
UNION ALL SELECT '3', '✓ Agent Monitoring - See online/offline agents'
UNION ALL SELECT '4', '✓ Models View - Agent decisions with pricing health (5+ reports in 10min)'
UNION ALL SELECT '5', '✓ Switch History - Detailed switch events with timing'
UNION ALL SELECT '6', '✓ Pricing Trends - Historical data for charts'
UNION ALL SELECT '7', '✓ Notifications - Unread alerts for demo accounts'
UNION ALL SELECT '8', '✓ System Health - Decision engine and model status'
UNION ALL SELECT '9', '✓ Growth Analytics - 90 days of client growth data'
UNION ALL SELECT '10', '✓ Cost Savings - Monthly aggregated savings';

SELECT '' AS '';
SELECT '🔍 Quick Verification:' AS Verification;
SELECT
    'agent-001' AS Agent,
    (SELECT COUNT(*) FROM pricing_reports WHERE agent_id = 'agent-001' AND received_at > DATE_SUB(NOW(), INTERVAL 10 MINUTE)) AS 'Reports (Last 10min)',
    CASE
        WHEN (SELECT COUNT(*) FROM pricing_reports WHERE agent_id = 'agent-001' AND received_at > DATE_SUB(NOW(), INTERVAL 10 MINUTE)) >= 5
        THEN '✓ HEALTHY'
        ELSE '✗ NEEDS MORE DATA'
    END AS 'Pricing Health Status'
FROM dual
UNION ALL
SELECT
    'agent-002',
    (SELECT COUNT(*) FROM pricing_reports WHERE agent_id = 'agent-002' AND received_at > DATE_SUB(NOW(), INTERVAL 10 MINUTE)),
    CASE
        WHEN (SELECT COUNT(*) FROM pricing_reports WHERE agent_id = 'agent-002' AND received_at > DATE_SUB(NOW(), INTERVAL 10 MINUTE)) >= 5
        THEN '✓ HEALTHY'
        ELSE '✗ NEEDS MORE DATA'
    END
FROM dual
UNION ALL
SELECT
    'agent-003',
    (SELECT COUNT(*) FROM pricing_reports WHERE agent_id = 'agent-003' AND received_at > DATE_SUB(NOW(), INTERVAL 10 MINUTE)),
    CASE
        WHEN (SELECT COUNT(*) FROM pricing_reports WHERE agent_id = 'agent-003' AND received_at > DATE_SUB(NOW(), INTERVAL 10 MINUTE)) >= 5
        THEN '✓ HEALTHY'
        ELSE '✗ NEEDS MORE DATA'
    END
FROM dual;

