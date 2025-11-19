-- ==============================================================================
-- AWS Spot Optimizer - Demo Data for Testing
-- ==============================================================================
-- This file contains realistic demo data to test all features of the system
-- ==============================================================================

USE spot_optimizer;

-- Clean existing demo data if re-running
DELETE FROM audit_logs WHERE client_id IN (SELECT id FROM clients WHERE email LIKE '%demo%');
DELETE FROM system_events WHERE client_id IN (SELECT id FROM clients WHERE email LIKE '%demo%');
DELETE FROM notifications WHERE client_id IN (SELECT id FROM clients WHERE email LIKE '%demo%');
DELETE FROM cost_records WHERE agent_id IN (SELECT id FROM agents WHERE client_id IN (SELECT id FROM clients WHERE email LIKE '%demo%'));
DELETE FROM switches WHERE agent_id IN (SELECT id FROM agents WHERE client_id IN (SELECT id FROM clients WHERE email LIKE '%demo%'));
DELETE FROM instances WHERE agent_id IN (SELECT id FROM agents WHERE client_id IN (SELECT id FROM clients WHERE email LIKE '%demo%'));
DELETE FROM replicas WHERE agent_id IN (SELECT id FROM agents WHERE client_id IN (SELECT id FROM clients WHERE email LIKE '%demo%'));
DELETE FROM agent_configs WHERE agent_id IN (SELECT id FROM agents WHERE client_id IN (SELECT id FROM clients WHERE email LIKE '%demo%'));
DELETE FROM agents WHERE client_id IN (SELECT id FROM clients WHERE email LIKE '%demo%');
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
    -- t3 instances
    ('t3.medium-ap-south-1-ap-south-1a', 't3.medium', 'ap-south-1', 'ap-south-1a', TRUE, NOW()),
    ('t3.medium-ap-south-1-ap-south-1b', 't3.medium', 'ap-south-1', 'ap-south-1b', TRUE, NOW()),
    ('t3.large-ap-south-1-ap-south-1a', 't3.large', 'ap-south-1', 'ap-south-1a', TRUE, NOW()),
    ('t3.large-ap-south-1-ap-south-1b', 't3.large', 'ap-south-1', 'ap-south-1b', TRUE, NOW()),

    -- m5 instances
    ('m5.large-ap-south-1-ap-south-1a', 'm5.large', 'ap-south-1', 'ap-south-1a', TRUE, NOW()),
    ('m5.large-ap-south-1-ap-south-1b', 'm5.large', 'ap-south-1', 'ap-south-1b', TRUE, NOW()),
    ('m5.xlarge-ap-south-1-ap-south-1a', 'm5.xlarge', 'ap-south-1', 'ap-south-1a', TRUE, NOW()),

    -- c5 instances
    ('c5.large-ap-south-1-ap-south-1a', 'c5.large', 'ap-south-1', 'ap-south-1a', TRUE, NOW()),
    ('c5.xlarge-ap-south-1-ap-south-1a', 'c5.xlarge', 'ap-south-1', 'ap-south-1a', TRUE, NOW()),

    -- r5 instances
    ('r5.large-ap-south-1-ap-south-1a', 'r5.large', 'ap-south-1', 'ap-south-1a', TRUE, NOW()),

    -- US East region
    ('t3.medium-us-east-1-us-east-1a', 't3.medium', 'us-east-1', 'us-east-1a', TRUE, NOW()),
    ('m5.large-us-east-1-us-east-1a', 'm5.large', 'us-east-1', 'us-east-1a', TRUE, NOW());

-- ==============================================================================
-- 3. ON-DEMAND PRICES (Base prices for comparison)
-- ==============================================================================

INSERT INTO ondemand_prices (instance_type, region, price, recorded_at)
VALUES
    ('t3.medium', 'ap-south-1', 0.0456, NOW()),
    ('t3.large', 'ap-south-1', 0.0912, NOW()),
    ('m5.large', 'ap-south-1', 0.1104, NOW()),
    ('m5.xlarge', 'ap-south-1', 0.2208, NOW()),
    ('c5.large', 'ap-south-1', 0.0936, NOW()),
    ('c5.xlarge', 'ap-south-1', 0.1872, NOW()),
    ('r5.large', 'ap-south-1', 0.1376, NOW()),
    ('t3.medium', 'us-east-1', 0.0416, NOW()),
    ('m5.large', 'us-east-1', 0.096, NOW());

-- ==============================================================================
-- 4. SPOT PRICES (Current and Historical)
-- ==============================================================================

-- Current spot prices
INSERT INTO spot_prices (pool_id, price, recorded_at)
VALUES
    ('t3.medium-ap-south-1-ap-south-1a', 0.0137, NOW()),
    ('t3.medium-ap-south-1-ap-south-1b', 0.0142, NOW()),
    ('t3.large-ap-south-1-ap-south-1a', 0.0274, NOW()),
    ('t3.large-ap-south-1-ap-south-1b', 0.0281, NOW()),
    ('m5.large-ap-south-1-ap-south-1a', 0.0331, NOW()),
    ('m5.large-ap-south-1-ap-south-1b', 0.0348, NOW()),
    ('m5.xlarge-ap-south-1-ap-south-1a', 0.0662, NOW()),
    ('c5.large-ap-south-1-ap-south-1a', 0.0281, NOW()),
    ('c5.xlarge-ap-south-1-ap-south-1a', 0.0562, NOW()),
    ('r5.large-ap-south-1-ap-south-1a', 0.0413, NOW()),
    ('t3.medium-us-east-1-us-east-1a', 0.0125, NOW()),
    ('m5.large-us-east-1-us-east-1a', 0.0288, NOW());

-- Historical spot price snapshots (last 24 hours)
INSERT INTO spot_price_snapshots (pool_id, price, captured_at, recorded_at)
SELECT
    pool_id,
    price + (RAND() * 0.01 - 0.005), -- Add random variance
    DATE_SUB(NOW(), INTERVAL seq HOUR),
    DATE_SUB(NOW(), INTERVAL seq HOUR)
FROM
    (SELECT @row := @row + 1 AS seq FROM
        (SELECT 0 UNION SELECT 1 UNION SELECT 2 UNION SELECT 3 UNION SELECT 4 UNION
         SELECT 5 UNION SELECT 6 UNION SELECT 7 UNION SELECT 8 UNION SELECT 9) t1,
        (SELECT 0 UNION SELECT 1 UNION SELECT 2) t2,
        (SELECT @row := 0) r
    ) sequences
CROSS JOIN spot_prices
WHERE seq <= 24
LIMIT 300;

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
    -- Active spot agents for Acme Corp
    (
        'agent-001', 'demo-client-001', 'web-server-prod-01', 'ip-10-0-1-101',
        'i-0abc123def456', 't3.medium', 'ap-south-1', 'ap-south-1a', 'ami-0abcd1234',
        '10.0.1.101', '13.232.45.67', 'spot', 't3.medium-ap-south-1-ap-south-1a',
        0.0137, 0.0456, 0.0456, '2.1.0',
        'online', TRUE, NOW(), TRUE, TRUE,
        DATE_SUB(NOW(), INTERVAL 45 DAY), DATE_SUB(NOW(), INTERVAL 45 DAY), DATE_SUB(NOW(), INTERVAL 3 HOUR)
    ),
    (
        'agent-002', 'demo-client-001', 'api-server-prod-01', 'ip-10-0-1-102',
        'i-0def789ghi012', 'm5.large', 'ap-south-1', 'ap-south-1b', 'ami-0abcd1234',
        '10.0.1.102', '13.232.45.68', 'spot', 'm5.large-ap-south-1-ap-south-1b',
        0.0348, 0.1104, 0.1104, '2.1.0',
        'online', TRUE, NOW(), TRUE, TRUE,
        DATE_SUB(NOW(), INTERVAL 30 DAY), DATE_SUB(NOW(), INTERVAL 30 DAY), DATE_SUB(NOW(), INTERVAL 1 HOUR)
    ),
    (
        'agent-003', 'demo-client-001', 'worker-01', 'ip-10-0-2-101',
        'i-0xyz789abc456', 'c5.large', 'ap-south-1', 'ap-south-1a', 'ami-0abcd1234',
        '10.0.2.101', '13.232.45.69', 'spot', 'c5.large-ap-south-1-ap-south-1a',
        0.0281, 0.0936, 0.0936, '2.1.0',
        'online', TRUE, DATE_SUB(NOW(), INTERVAL 30 SECOND), TRUE, TRUE,
        DATE_SUB(NOW(), INTERVAL 20 DAY), DATE_SUB(NOW(), INTERVAL 20 DAY), DATE_SUB(NOW(), INTERVAL 6 HOUR)
    ),

    -- On-demand agent (switched due to interruption risk)
    (
        'agent-004', 'demo-client-001', 'db-primary', 'ip-10-0-3-101',
        'i-0aaa111bbb222', 'm5.xlarge', 'ap-south-1', 'ap-south-1a', 'ami-0abcd1234',
        '10.0.3.101', '13.232.45.70', 'on-demand', NULL,
        NULL, 0.2208, 0.2208, '2.1.0',
        'online', TRUE, NOW(), TRUE, FALSE,
        DATE_SUB(NOW(), INTERVAL 60 DAY), DATE_SUB(NOW(), INTERVAL 60 DAY), DATE_SUB(NOW(), INTERVAL 2 HOUR)
    ),

    -- Offline agent (not responding)
    (
        'agent-005', 'demo-client-001', 'worker-02', 'ip-10-0-2-102',
        'i-0zzz888yyy777', 'c5.xlarge', 'ap-south-1', 'ap-south-1a', 'ami-0abcd1234',
        '10.0.2.102', NULL, 'unknown', NULL,
        NULL, 0.1872, 0.1872, '2.0.5',
        'offline', TRUE, DATE_SUB(NOW(), INTERVAL 2 HOUR), TRUE, TRUE,
        DATE_SUB(NOW(), INTERVAL 10 DAY), DATE_SUB(NOW(), INTERVAL 10 DAY), NULL
    ),

    -- StartupXYZ agents
    (
        'agent-006', 'demo-client-002', 'app-server-01', 'ip-172-31-1-10',
        'i-0startup001', 't3.large', 'ap-south-1', 'ap-south-1a', 'ami-0startup1',
        '172.31.1.10', '65.1.123.45', 'spot', 't3.large-ap-south-1-ap-south-1a',
        0.0274, 0.0912, 0.0912, '2.1.0',
        'online', TRUE, NOW(), TRUE, TRUE,
        DATE_SUB(NOW(), INTERVAL 15 DAY), DATE_SUB(NOW(), INTERVAL 15 DAY), DATE_SUB(NOW(), INTERVAL 4 HOUR)
    ),
    (
        'agent-007', 'demo-client-002', 'cache-server-01', 'ip-172-31-1-11',
        'i-0startup002', 'r5.large', 'ap-south-1', 'ap-south-1a', 'ami-0startup1',
        '172.31.1.11', '65.1.123.46', 'spot', 'r5.large-ap-south-1-ap-south-1a',
        0.0413, 0.1376, 0.1376, '2.1.0',
        'online', TRUE, DATE_SUB(NOW(), INTERVAL 45 SECOND), TRUE, TRUE,
        DATE_SUB(NOW(), INTERVAL 20 DAY), DATE_SUB(NOW(), INTERVAL 20 DAY), DATE_SUB(NOW(), INTERVAL 5 HOUR)
    ),

    -- Beta tester agent
    (
        'agent-008', 'demo-client-003', 'test-instance-01', 'ip-10-20-30-40',
        'i-0beta001', 't3.medium', 'us-east-1', 'us-east-1a', 'ami-0beta001',
        '10.20.30.40', '54.234.56.78', 'spot', 't3.medium-us-east-1-us-east-1a',
        0.0125, 0.0416, 0.0416, '2.1.0',
        'online', TRUE, NOW(), TRUE, TRUE,
        DATE_SUB(NOW(), INTERVAL 5 DAY), DATE_SUB(NOW(), INTERVAL 5 DAY), DATE_SUB(NOW(), INTERVAL 2 HOUR)
    );

-- ==============================================================================
-- 6. AGENT CONFIGS
-- ==============================================================================

INSERT INTO agent_configs (agent_id, switch_cooldown_minutes, interrupt_check_interval_seconds,
                          min_savings_threshold_percent, max_spot_price_multiplier)
VALUES
    ('agent-001', 30, 60, 30.0, 1.5),
    ('agent-002', 30, 60, 30.0, 1.5),
    ('agent-003', 30, 60, 30.0, 1.5),
    ('agent-004', 30, 60, 30.0, 1.5),
    ('agent-005', 30, 60, 30.0, 1.5),
    ('agent-006', 45, 90, 25.0, 1.8),
    ('agent-007', 45, 90, 25.0, 1.8),
    ('agent-008', 60, 120, 20.0, 2.0);

-- ==============================================================================
-- 7. INSTANCES (Historical instance records)
-- ==============================================================================

INSERT INTO instances (agent_id, instance_id, instance_type, region, az, mode,
                      spot_price, ondemand_price, started_at, terminated_at,
                      termination_reason, runtime_hours)
VALUES
    -- Previous instances that were terminated/switched
    ('agent-001', 'i-0old001', 't3.medium', 'ap-south-1', 'ap-south-1b', 'spot',
     0.0152, 0.0456, DATE_SUB(NOW(), INTERVAL 48 HOUR), DATE_SUB(NOW(), INTERVAL 3 HOUR),
     'spot-interruption', 45.0),

    ('agent-002', 'i-0old002', 'm5.large', 'ap-south-1', 'ap-south-1a', 'spot',
     0.0365, 0.1104, DATE_SUB(NOW(), INTERVAL 72 HOUR), DATE_SUB(NOW(), INTERVAL 1 HOUR),
     'better-pool-available', 71.0),

    ('agent-003', 'i-0old003', 'c5.large', 'ap-south-1', 'ap-south-1b', 'spot',
     0.0295, 0.0936, DATE_SUB(NOW(), INTERVAL 30 HOUR), DATE_SUB(NOW(), INTERVAL 6 HOUR),
     'price-increase', 24.0),

    ('agent-004', 'i-0old004', 'm5.xlarge', 'ap-south-1', 'ap-south-1a', 'spot',
     0.0680, 0.2208, DATE_SUB(NOW(), INTERVAL 96 HOUR), DATE_SUB(NOW(), INTERVAL 2 HOUR),
     'high-risk-detected', 94.0),

    ('agent-006', 'i-0old006', 't3.large', 'ap-south-1', 'ap-south-1b', 'spot',
     0.0288, 0.0912, DATE_SUB(NOW(), INTERVAL 24 HOUR), DATE_SUB(NOW(), INTERVAL 4 HOUR),
     'manual-switch', 20.0);

-- ==============================================================================
-- 8. SWITCHES (Historical switch events)
-- ==============================================================================

INSERT INTO switches (agent_id, switch_type, from_mode, to_mode, from_instance_id,
                     to_instance_id, from_instance_type, to_instance_type, from_pool_id,
                     to_pool_id, from_price, to_price, reason, status,
                     duration_seconds, switched_at, completed_at)
VALUES
    ('agent-001', 'spot-to-spot', 'spot', 'spot', 'i-0old001', 'i-0abc123def456',
     't3.medium', 't3.medium', 't3.medium-ap-south-1-ap-south-1b', 't3.medium-ap-south-1-ap-south-1a',
     0.0152, 0.0137, 'Interruption notice received', 'completed',
     183, DATE_SUB(NOW(), INTERVAL 3 HOUR), DATE_SUB(NOW(), INTERVAL 3 HOUR)),

    ('agent-002', 'spot-to-spot', 'spot', 'spot', 'i-0old002', 'i-0def789ghi012',
     'm5.large', 'm5.large', 'm5.large-ap-south-1-ap-south-1a', 'm5.large-ap-south-1-ap-south-1b',
     0.0365, 0.0348, 'Better pool available with lower price', 'completed',
     201, DATE_SUB(NOW(), INTERVAL 1 HOUR), DATE_SUB(NOW(), INTERVAL 1 HOUR)),

    ('agent-003', 'spot-to-spot', 'spot', 'spot', 'i-0old003', 'i-0xyz789abc456',
     'c5.large', 'c5.large', 'c5.large-ap-south-1-ap-south-1b', 'c5.large-ap-south-1-ap-south-1a',
     0.0295, 0.0281, 'Price increased above threshold', 'completed',
     167, DATE_SUB(NOW(), INTERVAL 6 HOUR), DATE_SUB(NOW(), INTERVAL 6 HOUR)),

    ('agent-004', 'spot-to-ondemand', 'spot', 'on-demand', 'i-0old004', 'i-0aaa111bbb222',
     'm5.xlarge', 'm5.xlarge', 'm5.xlarge-ap-south-1-ap-south-1a', NULL,
     0.0680, 0.2208, 'High interruption risk detected by ML model', 'completed',
     245, DATE_SUB(NOW(), INTERVAL 2 HOUR), DATE_SUB(NOW(), INTERVAL 2 HOUR)),

    ('agent-006', 'spot-to-spot', 'spot', 'spot', 'i-0old006', 'i-0startup001',
     't3.large', 't3.large', 't3.large-ap-south-1-ap-south-1b', 't3.large-ap-south-1-ap-south-1a',
     0.0288, 0.0274, 'Manual switch requested by user', 'completed',
     195, DATE_SUB(NOW(), INTERVAL 4 HOUR), DATE_SUB(NOW(), INTERVAL 4 HOUR));

-- ==============================================================================
-- 9. COST RECORDS (Hourly cost tracking)
-- ==============================================================================

INSERT INTO cost_records (agent_id, client_id, instance_id, instance_type, mode,
                         spot_price, ondemand_price, actual_cost, potential_cost,
                         savings, recorded_hour)
SELECT
    a.id,
    a.client_id,
    a.instance_id,
    a.instance_type,
    a.current_mode,
    a.spot_price,
    a.ondemand_price,
    CASE WHEN a.current_mode = 'spot' THEN a.spot_price ELSE a.ondemand_price END,
    a.ondemand_price,
    CASE WHEN a.current_mode = 'spot' THEN (a.ondemand_price - a.spot_price) ELSE 0 END,
    DATE_FORMAT(DATE_SUB(NOW(), INTERVAL seq HOUR), '%Y-%m-%d %H:00:00')
FROM agents a
CROSS JOIN (
    SELECT @row := @row + 1 AS seq FROM
        (SELECT 0 UNION SELECT 1 UNION SELECT 2 UNION SELECT 3 UNION SELECT 4) t1,
        (SELECT 0 UNION SELECT 1 UNION SELECT 2 UNION SELECT 3 UNION SELECT 4) t2,
        (SELECT @row := 0) r
    LIMIT 72
) sequences
WHERE a.status = 'online' AND a.id IN ('agent-001', 'agent-002', 'agent-003', 'agent-004', 'agent-006', 'agent-007', 'agent-008');

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

INSERT INTO notifications (client_id, agent_id, type, title, message, severity, is_read, created_at)
VALUES
    ('demo-client-001', 'agent-001', 'interruption', 'Spot Interruption Handled',
     'Your spot instance was interrupted but automatically switched to a new pool. No downtime occurred.',
     'info', TRUE, DATE_SUB(NOW(), INTERVAL 3 HOUR)),

    ('demo-client-001', 'agent-004', 'switch', 'Switched to On-Demand',
     'Agent switched to on-demand mode due to high interruption risk (78%). Will switch back when conditions improve.',
     'warning', FALSE, DATE_SUB(NOW(), INTERVAL 2 HOUR)),

    ('demo-client-001', 'agent-005', 'offline', 'Agent Offline',
     'Agent "worker-02" has not responded to heartbeats for 2 hours. Please check the instance status.',
     'error', FALSE, DATE_SUB(NOW(), INTERVAL 2 HOUR)),

    ('demo-client-001', NULL, 'savings', 'Savings Milestone!',
     'Congratulations! You have saved $15,847.89 since you started using Spot Optimizer. Keep it up! 🎉',
     'info', FALSE, DATE_SUB(NOW(), INTERVAL 1 DAY)),

    ('demo-client-002', 'agent-006', 'switch', 'Cost Optimization',
     'Agent switched to a better spot pool, reducing hourly cost by 4.86%. Monthly savings: ~$29.50',
     'info', TRUE, DATE_SUB(NOW(), INTERVAL 4 HOUR)),

    ('demo-client-003', 'agent-008', 'welcome', 'Welcome to Spot Optimizer!',
     'Your first agent is now online and optimizing costs. Check out the dashboard to see real-time savings.',
     'info', TRUE, DATE_SUB(NOW(), INTERVAL 5 DAY));

-- ==============================================================================
-- 12. AUDIT LOGS (Security and compliance tracking)
-- ==============================================================================

INSERT INTO audit_logs (client_id, agent_id, user_id, action, resource_type, resource_id,
                       details, ip_address, user_agent, created_at)
VALUES
    ('demo-client-001', NULL, NULL, 'client.created', 'client', 'demo-client-001',
     '{"plan": "enterprise", "max_agents": 50}', '203.0.113.45', 'Mozilla/5.0', DATE_SUB(NOW(), INTERVAL 90 DAY)),

    ('demo-client-001', 'agent-001', NULL, 'agent.registered', 'agent', 'agent-001',
     '{"instance_type": "t3.medium", "region": "ap-south-1"}', '10.0.1.101', 'SpotOptimizer-Agent/2.1.0', DATE_SUB(NOW(), INTERVAL 45 DAY)),

    ('demo-client-001', 'agent-001', NULL, 'switch.executed', 'switch', NULL,
     '{"from": "t3.medium-ap-south-1-ap-south-1b", "to": "t3.medium-ap-south-1-ap-south-1a", "reason": "interruption"}',
     '10.0.1.101', 'SpotOptimizer-Agent/2.1.0', DATE_SUB(NOW(), INTERVAL 3 HOUR)),

    ('demo-client-001', 'agent-004', NULL, 'switch.executed', 'switch', NULL,
     '{"from_mode": "spot", "to_mode": "on-demand", "reason": "high-risk"}',
     '10.0.3.101', 'SpotOptimizer-Agent/2.1.0', DATE_SUB(NOW(), INTERVAL 2 HOUR)),

    ('demo-client-002', 'agent-006', 'user-demo-002', 'switch.manual', 'switch', NULL,
     '{"initiated_by": "user", "reason": "manual optimization"}',
     '203.0.113.100', 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)', DATE_SUB(NOW(), INTERVAL 4 HOUR));

-- ==============================================================================
-- 13. CLIENT MONTHLY SAVINGS SUMMARY
-- ==============================================================================

INSERT INTO client_savings_monthly (client_id, year, month, total_hours_spot, total_hours_ondemand,
                                   total_actual_cost, total_potential_cost, total_savings)
VALUES
    ('demo-client-001', YEAR(DATE_SUB(NOW(), INTERVAL 1 MONTH)), MONTH(DATE_SUB(NOW(), INTERVAL 1 MONTH)),
     18720, 2160, 1842.34, 7234.56, 5392.22),

    ('demo-client-001', YEAR(NOW()), MONTH(NOW()),
     14400, 720, 1523.12, 4178.34, 2655.22),

    ('demo-client-002', YEAR(NOW()), MONTH(NOW()),
     4320, 240, 287.45, 1123.89, 836.44),

    ('demo-client-003', YEAR(NOW()), MONTH(NOW()),
     504, 0, 18.92, 78.43, 59.51);

-- ==============================================================================
-- SUMMARY
-- ==============================================================================

SELECT '✅ Demo data inserted successfully!' AS Status;
SELECT 'Clients' AS Entity, COUNT(*) AS Count FROM clients WHERE email LIKE '%demo%'
UNION ALL
SELECT 'Agents', COUNT(*) FROM agents WHERE client_id IN (SELECT id FROM clients WHERE email LIKE '%demo%')
UNION ALL
SELECT 'Spot Pools', COUNT(*) FROM spot_pools
UNION ALL
SELECT 'Active Agents', COUNT(*) FROM agents WHERE status = 'online' AND client_id IN (SELECT id FROM clients WHERE email LIKE '%demo%')
UNION ALL
SELECT 'Total Switches', COUNT(*) FROM switches WHERE agent_id IN (SELECT id FROM agents WHERE client_id IN (SELECT id FROM clients WHERE email LIKE '%demo%'))
UNION ALL
SELECT 'Cost Records', COUNT(*) FROM cost_records WHERE client_id IN (SELECT id FROM clients WHERE email LIKE '%demo%')
UNION ALL
SELECT 'System Events', COUNT(*) FROM system_events WHERE client_id IN (SELECT id FROM clients WHERE email LIKE '%demo%')
UNION ALL
SELECT 'Notifications', COUNT(*) FROM notifications WHERE client_id IN (SELECT id FROM clients WHERE email LIKE '%demo%');

SELECT '🎯 You can now test all features with these demo accounts:' AS Message;
SELECT name AS 'Client', email AS 'Email', client_token AS 'Token', plan AS 'Plan', total_savings AS 'Total Savings ($)'
FROM clients WHERE email LIKE '%demo%';
