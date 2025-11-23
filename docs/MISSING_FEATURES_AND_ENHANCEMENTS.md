# Missing Features and Planned Enhancements

## Overview

This document tracks features and API endpoints that are planned or partially implemented for full agent v4.0.0 functionality. These features were identified from the agent-v2 repository analysis.

## Current Implementation Status

### ✅ Fully Implemented

1. **Agent Registration** - `POST /api/agents/register`
2. **Heartbeat Monitoring** - `POST /api/agents/<agent_id>/heartbeat`
3. **Pricing Reports** - `POST /api/agents/<agent_id>/pricing-report`
4. **Command Queue** - `GET /api/agents/<agent_id>/pending-commands`
5. **Switch Reporting** - `POST /api/agents/<agent_id>/switch-report`
6. **Termination Handling** - `POST /api/agents/<agent_id>/termination-imminent`
7. **Emergency Replicas** - `POST /api/agents/<agent_id>/create-emergency-replica`
8. **Replica Management** - Full CRUD for replicas
9. **Client Management** - Full admin endpoints
10. **System Health** - `GET /api/admin/system-health`

### ⚠️ Partially Implemented

1. **Rebalance Recommendation Handler** - Basic implementation exists but needs enhancement
2. **Client Switches History** - GET /api/client/<client_id>/switch-history exists
3. **Client Savings Data** - GET /api/client/<client_id>/savings exists

### ❌ Not Yet Implemented

1. **Cleanup Report Handler** - `POST /api/agents/<agent_id>/cleanup-report`
2. **Client Token Validation** - `GET /api/client/validate`
3. **Agent Health Metrics Tracking** - Database table and endpoint
4. **Pool Risk Analysis** - Automated scheduled job
5. **Replica Cost Tracking** - Detailed cost logging
6. **Savings Snapshots** - Daily savings calculation

---

## Missing API Endpoints

### 1. Cleanup Report Handler

**Status:** ❌ Not Implemented

**Endpoint:** `POST /api/agents/<agent_id>/cleanup-report`

**Purpose:** Receive and log cleanup operation results from agents

**Request Body:**
```json
{
    "timestamp": "2024-01-15T12:00:00Z",
    "snapshots": {
        "type": "snapshots",
        "deleted": ["snap-123", "snap-456"],
        "failed": [],
        "cutoff_date": "2024-01-08T12:00:00Z"
    },
    "amis": {
        "type": "amis",
        "deleted_amis": ["ami-123"],
        "deleted_snapshots": ["snap-789"],
        "failed": [],
        "cutoff_date": "2023-12-16T12:00:00Z"
    }
}
```

**Response:**
```json
{
    "success": true,
    "message": "Cleanup report recorded"
}
```

**Implementation Requirements:**
- Insert into cleanup_logs table
- Track deleted/failed counts
- Store details as JSON
- Index by agent_id and executed_at

---

### 2. Client Token Validation

**Status:** ❌ Not Implemented

**Endpoint:** `GET /api/client/validate`

**Purpose:** Validate client token for frontend authentication

**Headers:**
```
Authorization: Bearer <client_token>
```

**Response:**
```json
{
    "valid": true,
    "client_id": "uuid-here",
    "name": "Client Name",
    "email": "client@example.com"
}
```

**Implementation Requirements:**
- Decode and validate token
- Check expiration
- Return client details
- Log validation attempts

---

### 3. Rebalance Recommendation Handler (Enhancement)

**Status:** ⚠️ Needs Enhancement

**Current:** Basic handling exists in `handle_termination` function
**Needed:** Separate endpoint with risk analysis

**Endpoint:** `POST /api/agents/<agent_id>/rebalance-recommendation`

**Request Body:**
```json
{
    "instance_id": "i-1234567890abcdef0",
    "detected_at": "2024-01-15T12:00:00Z"
}
```

**Response:**
```json
{
    "success": true,
    "action": "switch",
    "target_mode": "spot",
    "target_pool_id": "t3.medium.us-east-1c",
    "reason": "Current pool has elevated interruption risk",
    "risk_score": 0.45
}
```

**Enhancement Requirements:**
- Separate from termination handling
- Analyze current pool risk
- Find alternative pools with lower risk
- Can optionally create switch command automatically
- Insert into termination_events table with type 'rebalance_recommendation'

---

## Missing Database Tables

### 1. cleanup_logs Table

**Status:** ❌ Not in schema.sql

**Purpose:** Track cleanup operations from agents

**Schema:**
```sql
CREATE TABLE IF NOT EXISTS cleanup_logs (
    id INT AUTO_INCREMENT PRIMARY KEY,
    agent_id VARCHAR(36),
    client_id VARCHAR(36),
    cleanup_type ENUM('snapshots', 'amis', 'full') NOT NULL,
    deleted_snapshots_count INT DEFAULT 0,
    deleted_amis_count INT DEFAULT 0,
    failed_count INT DEFAULT 0,
    details JSON,
    cutoff_date TIMESTAMP NULL,
    executed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_agent_id (agent_id),
    INDEX idx_client_id (client_id),
    INDEX idx_executed_at (executed_at)
);
```

**Benefits:**
- Track cleanup efficiency
- Monitor failed cleanup operations
- Audit trail for resource deletion
- Client-level cleanup reporting

---

### 2. termination_events Table

**Status:** ❌ Not in schema.sql (partially tracked in spot_interruption_events)

**Purpose:** Track termination and rebalance events separately

**Schema:**
```sql
CREATE TABLE IF NOT EXISTS termination_events (
    id INT AUTO_INCREMENT PRIMARY KEY,
    agent_id VARCHAR(36) NOT NULL,
    instance_id VARCHAR(50) NOT NULL,
    event_type ENUM('termination_notice', 'rebalance_recommendation') NOT NULL,
    action_type VARCHAR(50),
    action_taken VARCHAR(255),
    emergency_replica_id VARCHAR(36),
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
    INDEX idx_detected_at (detected_at)
);
```

**Benefits:**
- Separate tracking from general interruption events
- Track resolution workflow (detected → handling → resolved)
- Record actions taken and their outcomes
- Better reporting for operational incidents

---

### 3. savings_snapshots Table

**Status:** ❌ Not in schema.sql

**Purpose:** Daily aggregated savings for historical tracking

**Schema:**
```sql
CREATE TABLE IF NOT EXISTS savings_snapshots (
    id INT AUTO_INCREMENT PRIMARY KEY,
    client_id VARCHAR(36) NOT NULL,
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
    INDEX idx_snapshot_date (snapshot_date)
);
```

**Benefits:**
- Daily aggregation reduces query load
- Historical trend analysis
- Monthly/yearly reporting
- Client savings comparison

---

### 4. agent_health_metrics Table

**Status:** ❌ Not in schema.sql

**Purpose:** Track agent health and performance metrics

**Schema:**
```sql
CREATE TABLE IF NOT EXISTS agent_health_metrics (
    id INT AUTO_INCREMENT PRIMARY KEY,
    agent_id VARCHAR(36) NOT NULL,
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
    INDEX idx_metric_time (metric_time)
);
```

**Benefits:**
- Monitor agent performance
- Detect degraded agents early
- SLA tracking
- Troubleshooting data

---

### 5. replica_cost_log Table

**Status:** ❌ Not in schema.sql

**Purpose:** Track replica costs for better cost analysis

**Schema:**
```sql
CREATE TABLE IF NOT EXISTS replica_cost_log (
    id INT AUTO_INCREMENT PRIMARY KEY,
    replica_id VARCHAR(36) NOT NULL,
    agent_id VARCHAR(36) NOT NULL,
    client_id VARCHAR(36) NOT NULL,
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
    INDEX idx_log_time (log_time)
);
```

**Benefits:**
- Accurate replica cost tracking
- ROI analysis for replica strategy
- Client billing for replica time
- Cost optimization insights

---

### 6. pool_risk_analysis Table

**Status:** ❌ Not in schema.sql

**Purpose:** Store pool risk analysis results

**Schema:**
```sql
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
);
```

**Benefits:**
- Historical risk tracking
- Trend analysis for pool safety
- ML model training data
- Automated pool recommendations

---

## Missing Database Views

### 1. v_client_savings_summary

**Purpose:** Aggregated client savings view

**Schema:**
```sql
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
```

---

### 2. v_recent_termination_events

**Purpose:** Recent termination events with context

**Schema:**
```sql
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
```

---

### 3. v_pool_risk_current

**Purpose:** Latest risk analysis for each pool

**Schema:**
```sql
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
```

---

## Missing Stored Procedures

### 1. sp_calculate_daily_savings

**Purpose:** Calculate and store daily savings snapshots

**Schema:**
```sql
DELIMITER //

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

DELIMITER ;
```

---

### 2. sp_cleanup_old_metrics

**Purpose:** Clean up old metric data

**Schema:**
```sql
DELIMITER //

CREATE PROCEDURE IF NOT EXISTS sp_cleanup_old_metrics(IN days_to_keep INT)
BEGIN
    DELETE FROM agent_health_metrics
    WHERE metric_time < DATE_SUB(NOW(), INTERVAL days_to_keep DAY);

    DELETE FROM pool_risk_analysis
    WHERE analysis_time < DATE_SUB(NOW(), INTERVAL days_to_keep DAY);

    DELETE FROM replica_cost_log
    WHERE log_time < DATE_SUB(NOW(), INTERVAL days_to_keep DAY);
END //

DELIMITER ;
```

---

## Missing Scheduled Events

### 1. evt_calculate_daily_savings

**Purpose:** Run daily savings calculation at midnight

**Schema:**
```sql
CREATE EVENT IF NOT EXISTS evt_calculate_daily_savings
ON SCHEDULE EVERY 1 DAY
STARTS (TIMESTAMP(CURRENT_DATE) + INTERVAL 1 DAY)
DO CALL sp_calculate_daily_savings(DATE_SUB(CURRENT_DATE, INTERVAL 1 DAY));
```

---

### 2. evt_cleanup_old_metrics

**Purpose:** Weekly cleanup of old metrics

**Schema:**
```sql
CREATE EVENT IF NOT EXISTS evt_cleanup_old_metrics
ON SCHEDULE EVERY 1 WEEK
STARTS (TIMESTAMP(CURRENT_DATE) + INTERVAL 1 WEEK)
DO CALL sp_cleanup_old_metrics(30);
```

---

## Missing Agent Table Columns

### Termination Tracking Columns

**Status:** ❌ Not in schema.sql

**Columns to Add:**
```sql
ALTER TABLE agents ADD COLUMN last_termination_notice_at TIMESTAMP NULL;
ALTER TABLE agents ADD COLUMN last_rebalance_recommendation_at TIMESTAMP NULL;
ALTER TABLE agents ADD COLUMN emergency_replica_count INT DEFAULT 0;
ALTER TABLE agents ADD COLUMN cleanup_enabled BOOLEAN DEFAULT true;
ALTER TABLE agents ADD COLUMN last_cleanup_at TIMESTAMP NULL;
```

---

### Replica Tracking Columns

**Status:** ❌ Not in schema.sql

**Columns to Add:**
```sql
ALTER TABLE replica_instances ADD COLUMN total_runtime_hours DECIMAL(10, 2) DEFAULT 0;
ALTER TABLE replica_instances ADD COLUMN accumulated_cost DECIMAL(15, 4) DEFAULT 0;
```

---

## Missing Background Jobs

### 1. Stale Agent Cleanup

**Purpose:** Mark agents as offline if no heartbeat received

**Frequency:** Every 6 hours

**Pseudocode:**
```python
def cleanup_stale_agents():
    HEARTBEAT_TIMEOUT = 300  # 5 minutes

    # Find stale agents
    stale_agents = execute_query("""
        UPDATE agents
        SET status = 'offline'
        WHERE last_seen < DATE_SUB(NOW(), INTERVAL %s SECOND)
          AND status != 'offline'
    """, (HEARTBEAT_TIMEOUT,))

    # Log system event for each
    for agent in stale_agents:
        log_system_event(
            event_type='agent_offline',
            severity='warning',
            message=f'Agent {agent.id} marked offline due to missing heartbeat'
        )
```

---

### 2. Pool Risk Analysis Job

**Purpose:** Analyze spot pool interruption risk

**Frequency:** Every 15 minutes

**Pseudocode:**
```python
def analyze_pool_risk():
    pools = get_active_pools()

    for pool in pools:
        # Fetch spot price history
        prices = get_price_history(pool.id, hours=24)

        # Calculate metrics
        avg_price = mean(prices)
        volatility = std_dev(prices) / avg_price

        # Count recent interruptions
        interruptions = count_interruptions(pool.id, days=30)

        # Calculate risk score
        risk_score = calculate_risk(volatility, interruptions, avg_price)

        # Determine recommendation
        if risk_score > 0.70:
            recommendation = 'avoid'
        elif risk_score > 0.40:
            recommendation = 'caution'
        else:
            recommendation = 'safe'

        # Store analysis
        insert_pool_risk_analysis(
            pool_id=pool.id,
            risk_score=risk_score,
            recommendation=recommendation,
            # ... other metrics
        )
```

---

## Required Configuration

### Environment Variables

```env
# Termination handling
TERMINATION_REPLICA_AUTO_CREATE=true
TERMINATION_NOTIFICATION_WEBHOOK=https://hooks.slack.com/...

# Cleanup settings
AUTO_CLEANUP_ENABLED=true
CLEANUP_SNAPSHOTS_DAYS=7
CLEANUP_AMIS_DAYS=30

# Savings calculation
SAVINGS_CALCULATION_HOUR=0  # Midnight

# Agent health monitoring
AGENT_HEARTBEAT_TIMEOUT=300  # 5 minutes
STALE_AGENT_CHECK_INTERVAL=21600  # 6 hours

# Pool risk analysis
POOL_RISK_ANALYSIS_INTERVAL=900  # 15 minutes
POOL_RISK_HIGH_THRESHOLD=0.70
POOL_RISK_MEDIUM_THRESHOLD=0.40
```

---

## Integration Notes

### With Agent v4.0.0

The agent now sends requests to:
- `/api/agents/{id}/termination-imminent` - Every 5 seconds when on spot ✅ Implemented
- `/api/agents/{id}/rebalance-recommendation` - Every 30 seconds when on spot ⚠️ Needs enhancement
- `/api/agents/{id}/cleanup-report` - Every hour after cleanup runs ❌ Not implemented

### With Client Dashboard

The dashboard expects:
- `/api/client/validate` - For login authentication ❌ Not implemented
- `/api/client/{id}/switches` - For switch history page ✅ Implemented
- `/api/client/{id}/savings` - For dashboard stats ✅ Implemented

---

## Implementation Priority

### High Priority (Core Functionality)

1. ✅ Termination handling
2. ✅ Replica management
3. ✅ Savings tracking (basic)
4. ⚠️ Rebalance recommendation enhancement

### Medium Priority (Operational)

5. ❌ Cleanup report handler
6. ❌ Savings snapshots with daily aggregation
7. ❌ Agent health metrics
8. ❌ Pool risk analysis

### Low Priority (Nice to Have)

9. ❌ Client token validation endpoint
10. ❌ Replica cost detailed tracking
11. ❌ Advanced views and reports

---

## Migration Path

### Phase 1: Database Schema

1. Add missing tables to schema.sql
2. Create migration script for existing installations
3. Add views and stored procedures
4. Enable scheduled events

### Phase 2: API Endpoints

1. Implement cleanup report handler
2. Enhance rebalance recommendation endpoint
3. Add client token validation
4. Update documentation

### Phase 3: Background Jobs

1. Implement stale agent cleanup
2. Implement pool risk analysis
3. Add daily savings calculation job
4. Configure environment variables

### Phase 4: Testing & Deployment

1. Test all new endpoints
2. Verify scheduled jobs work
3. Load test with multiple agents
4. Deploy to production
5. Monitor for issues

---

## References

- Agent v2 Repository: https://github.com/atharva0608/agent-v2
- Missing Features Doc: [agent-v2/missing-backend-server/MISSING_FEATURES.md]
- Required Schema: [agent-v2/missing-backend-server/REQUIRED_SCHEMA.sql]

---

**Last Updated:** 2025-11-21
**Status:** Documentation Complete, Implementation In Progress
