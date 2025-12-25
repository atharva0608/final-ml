# Database Schema Documentation

## Overview
This document provides comprehensive documentation of all database tables, their columns, relationships, and data flow patterns in the SpotGuard system.

---

## 📊 Core Tables

### 1. `clients` - Client Organizations
```sql
CREATE TABLE clients (
    id VARCHAR(36) PRIMARY KEY,              -- UUID v4, unique client identifier
    name VARCHAR(255) NOT NULL,              -- Client organization name
    email VARCHAR(255),                      -- Contact email
    api_token VARCHAR(64) UNIQUE,            -- Bearer token for API authentication
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
);
```

**Purpose:** Stores client organizations that own instances and agents.

**Relationships:**
- One client → Many agents
- One client → Many instances
- One client → Many switches

**Indexes:**
- PRIMARY KEY (id)
- UNIQUE (api_token)

---

### 2. `agents` - Agent Processes Running on Instances
```sql
CREATE TABLE agents (
    id VARCHAR(36) PRIMARY KEY,                         -- UUID v4, unique agent identifier
    client_id VARCHAR(36) NOT NULL,                     -- Foreign key to clients table
    logical_agent_id VARCHAR(255),                      -- Persistent ID across instance switches
    instance_id VARCHAR(64),                            -- Current AWS instance ID
    instance_type VARCHAR(32),                          -- EC2 instance type (e.g., t3.medium)
    region VARCHAR(32),                                 -- AWS region (e.g., ap-south-1)
    az VARCHAR(32),                                     -- Availability zone (e.g., ap-south-1a)
    ami_id VARCHAR(64),                                 -- Current AMI ID
    current_mode VARCHAR(20),                           -- 'spot' or 'ondemand'
    current_pool_id VARCHAR(128),                       -- Current spot pool ID (if spot mode)

    -- Agent State
    status VARCHAR(20) DEFAULT 'online',                -- 'online', 'offline', 'deleted', 'switching'
    enabled BOOLEAN DEFAULT TRUE,                       -- Agent enabled/disabled by user
    agent_version VARCHAR(32),                          -- Agent software version
    hostname VARCHAR(255),                              -- Instance hostname
    private_ip VARCHAR(45),                             -- Private IP address
    public_ip VARCHAR(45),                              -- Public IP address (if exists)

    -- Replica Configuration
    auto_switch_enabled BOOLEAN DEFAULT TRUE,           -- Enable ML-driven auto-switching
    manual_replica_enabled BOOLEAN DEFAULT FALSE,       -- Enable continuous manual replicas (mutually exclusive with auto_switch)
    auto_terminate_enabled BOOLEAN DEFAULT TRUE,        -- Auto-terminate old instances after switch
    terminate_wait_seconds INT DEFAULT 1800,            -- Seconds to wait before terminating (30 minutes)

    replica_enabled BOOLEAN DEFAULT FALSE,              -- [DEPRECATED] Use manual_replica_enabled
    replica_count INT DEFAULT 0,                        -- Current number of active replicas
    current_replica_id VARCHAR(36),                     -- ID of current replica

    -- Monitoring
    last_heartbeat_at TIMESTAMP,                        -- Last agent heartbeat timestamp
    last_interruption_signal VARCHAR(50),               -- Last AWS interruption signal received
    instance_count INT DEFAULT 0,                       -- Total instances managed by this agent

    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    installed_at TIMESTAMP,                             -- When agent was first installed

    FOREIGN KEY (client_id) REFERENCES clients(id),
    INDEX idx_client_status (client_id, status),
    INDEX idx_logical_agent (logical_agent_id),
    INDEX idx_instance (instance_id),
    INDEX idx_heartbeat (last_heartbeat_at)
);
```

**Purpose:** Tracks agent processes that manage instance lifecycle and switching.

**Key Concepts:**
- **logical_agent_id**: Persistent ID that doesn't change when instance switches. Used to track the same workload across multiple instances.
- **Mutual Exclusivity**: `auto_switch_enabled` and `manual_replica_enabled` are mutually exclusive
  - When `auto_switch_enabled = TRUE`: ML model controls switching, emergency replicas only
  - When `manual_replica_enabled = TRUE`: User controls switching, continuous replicas maintained

**Flow Example - Manual Replica Enabled:**
```
User enables manual_replica_enabled toggle in UI
  ↓
Frontend sends POST /api/client/agents/<id>/config with manualReplicaEnabled: true
  ↓
Backend sets agents.manual_replica_enabled = TRUE, auto_switch_enabled = FALSE
  ↓
ReplicaCoordinator (runs every 10 seconds) detects manual_replica_enabled = TRUE
  ↓
Checks agents.replica_count = 0?
  ↓ YES
Creates replica in cheapest pool
  ↓
Updates agents.current_replica_id, agents.replica_count = 1
  ↓
Replica stays active until:
  - User switches to replica (promotes) → NEW replica created for new primary
  - User terminates replica → NEW replica created immediately
  - User disables manual_replica_enabled → All replicas terminated
```

---

### 3. `instances` - AWS EC2 Instances
```sql
CREATE TABLE instances (
    id VARCHAR(64) PRIMARY KEY,                         -- AWS instance ID (e.g., i-1234567890abcdef0)
    client_id VARCHAR(36) NOT NULL,                     -- Foreign key to clients
    agent_id VARCHAR(36),                               -- Agent managing this instance
    instance_type VARCHAR(32),                          -- EC2 instance type
    region VARCHAR(32),                                 -- AWS region
    az VARCHAR(32),                                     -- Availability zone
    ami_id VARCHAR(64),                                 -- AMI used to launch instance

    -- Mode and Pricing
    current_mode VARCHAR(20),                           -- 'spot' or 'ondemand'
    current_pool_id VARCHAR(128),                       -- Spot pool ID (if spot)
    spot_price DECIMAL(10, 4),                          -- Current spot price ($/hour)
    ondemand_price DECIMAL(10, 4),                      -- On-demand price ($/hour)
    baseline_ondemand_price DECIMAL(10, 4),             -- Reference on-demand price for savings calculation

    -- Lifecycle
    is_active BOOLEAN DEFAULT TRUE,                     -- Instance currently running
    installed_at TIMESTAMP,                             -- When agent installed
    last_switch_at TIMESTAMP,                           -- Last time instance switched modes
    terminated_at TIMESTAMP,                            -- When instance was terminated

    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,

    FOREIGN KEY (client_id) REFERENCES clients(id),
    FOREIGN KEY (agent_id) REFERENCES agents(id),
    INDEX idx_client_active (client_id, is_active),
    INDEX idx_agent (agent_id),
    INDEX idx_mode (current_mode)
);
```

**Purpose:** Tracks all EC2 instances (primary and old instances).

**Flow Example - Auto-Terminate Disabled:**
```
Agent switches from instance A to instance B
  ↓
Agent sends switch report with old_instance.id = A, new_instance.id = B
  ↓
Backend checks agents.auto_terminate_enabled for this agent
  ↓
auto_terminate_enabled = FALSE?
  ↓ YES
Backend keeps instances[A].is_active = TRUE (does NOT terminate)
  ↓
Backend inserts instances[B].is_active = TRUE
  ↓
Result: Both A and B are active (user must manually terminate A)
```

**Flow Example - Auto-Terminate Enabled:**
```
Agent switches from instance A to instance B
  ↓
Agent waits terminate_wait_seconds (e.g., 1800 = 30 minutes)
  ↓
Agent terminates instance A in AWS
  ↓
Agent sends switch report with timing.old_terminated_at = <timestamp>
  ↓
Backend checks agents.auto_terminate_enabled AND timing.old_terminated_at exists
  ↓ BOTH TRUE
Backend sets instances[A].is_active = FALSE, terminated_at = <timestamp>
  ↓
Result: Only B is active, A is marked terminated
```

---

### 4. `replica_instances` - Standby Replicas
```sql
CREATE TABLE replica_instances (
    id VARCHAR(36) PRIMARY KEY,                         -- UUID v4, unique replica identifier
    agent_id VARCHAR(36) NOT NULL,                      -- Agent this replica belongs to
    instance_id VARCHAR(64),                            -- Replica instance ID (or generated ID if not launched yet)
    replica_type VARCHAR(50),                           -- 'manual', 'automatic-rebalance', 'automatic-termination'

    -- Pool and Location
    pool_id VARCHAR(128),                               -- Spot pool where replica is running
    instance_type VARCHAR(32),                          -- EC2 instance type
    region VARCHAR(32),                                 -- AWS region
    az VARCHAR(32),                                     -- Availability zone

    -- Lifecycle Timestamps
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,     -- When replica record was created
    launched_at TIMESTAMP NULL,                         -- When instance was actually launched in AWS
    ready_at TIMESTAMP NULL,                            -- When replica became ready for promotion
    promoted_at TIMESTAMP NULL,                         -- When replica was promoted to primary
    terminated_at TIMESTAMP NULL,                       -- When replica was terminated

    -- Status
    status VARCHAR(50) DEFAULT 'launching',             -- 'launching', 'syncing', 'ready', 'promoted', 'terminated', 'failed'
    sync_status VARCHAR(50),                            -- 'initializing', 'syncing', 'synced', 'out-of-sync'
    state_transfer_progress DECIMAL(5, 2) DEFAULT 0.00, -- Percentage of state synced (0.00 to 100.00)
    sync_latency_ms INT,                                -- Sync latency in milliseconds

    -- Lifecycle
    is_active BOOLEAN DEFAULT TRUE,                     -- Replica currently active
    created_by VARCHAR(50),                             -- 'user', 'coordinator', 'system'
    parent_instance_id VARCHAR(64),                     -- Primary instance this replica was created from
    hourly_cost DECIMAL(10, 4),                         -- Replica hourly cost

    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    ready_at TIMESTAMP,                                 -- When replica became ready for promotion
    promoted_at TIMESTAMP,                              -- When replica was promoted to primary
    terminated_at TIMESTAMP,                            -- When replica was terminated

    FOREIGN KEY (agent_id) REFERENCES agents(id),
    INDEX idx_agent_active (agent_id, is_active),
    INDEX idx_status (status),
    INDEX idx_type (replica_type)
);
```

**Purpose:** Stores standby replicas that can be promoted to primary.

**Replica Types:**
- **`manual`**: Created by ReplicaCoordinator when manual_replica_enabled = TRUE. Stays active until disabled or promoted.
- **`automatic-rebalance`**: Created when AWS sends rebalance recommendation. Emergency replica.
- **`automatic-termination`**: Created on AWS termination notice (2-minute warning). Emergency failover.

**Flow Example - Manual Replica Lifecycle:**
```
1. Creation:
   User enables manual_replica_enabled
     ↓
   ReplicaCoordinator creates replica
     ↓
   INSERT INTO replica_instances (
       id = <uuid>,
       agent_id = <agent_id>,
       replica_type = 'manual',
       status = 'launching',
       is_active = TRUE
   )

2. Syncing:
   Replica agent starts syncing state from primary
     ↓
   Replica sends POST /api/agents/<id>/replicas/<replica_id>/sync-status
     ↓
   UPDATE replica_instances SET
       status = 'syncing',
       sync_status = 'syncing',
       state_transfer_progress = 65.0,
       sync_latency_ms = 12

3. Ready:
   State transfer completes
     ↓
   UPDATE replica_instances SET
       status = 'ready',
       sync_status = 'synced',
       state_transfer_progress = 100.0,
       ready_at = NOW()

4. Promotion:
   User clicks "Switch to Replica" button
     ↓
   Frontend sends POST /api/agents/<id>/replicas/<replica_id>/promote
     ↓
   UPDATE replica_instances SET
       status = 'promoted',
       promoted_at = NOW(),
       is_active = FALSE
     ↓
   Replica becomes new primary instance
     ↓ (within 10 seconds)
   ReplicaCoordinator detects promotion (promoted_at within last 5 minutes)
     ↓
   Creates NEW replica for new primary
     ↓
   INSERT INTO replica_instances (new replica for new primary)
```

---

### 5. `spot_pools` - Available Spot Capacity Pools
```sql
CREATE TABLE spot_pools (
    id VARCHAR(128) PRIMARY KEY,                        -- Pool identifier (e.g., "t3.medium.ap-south-1a")
    pool_name VARCHAR(255),                             -- Human-readable name
    instance_type VARCHAR(32),                          -- EC2 instance type
    region VARCHAR(32),                                 -- AWS region
    az VARCHAR(32),                                     -- Availability zone

    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,

    UNIQUE KEY unique_pool (instance_type, region, az),
    INDEX idx_type_region (instance_type, region)
);
```

**Purpose:** Defines available spot capacity pools (combinations of instance type, region, AZ).

**Example Pools:**
```
t3.medium.ap-south-1a
t3.medium.ap-south-1b
t3.medium.ap-south-1c
```

---

### 6. `spot_price_snapshots` - Real-Time Spot Pricing
```sql
CREATE TABLE spot_price_snapshots (
    id INT AUTO_INCREMENT PRIMARY KEY,
    pool_id VARCHAR(128) NOT NULL,                      -- Foreign key to spot_pools
    price DECIMAL(10, 4) NOT NULL,                      -- Spot price at capture time ($/hour)
    captured_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,    -- When price was captured

    FOREIGN KEY (pool_id) REFERENCES spot_pools(id),
    INDEX idx_pool_time (pool_id, captured_at),
    INDEX idx_captured (captured_at)
);
```

**Purpose:** Stores real-time spot prices reported by agents during heartbeats.

**Data Source:** Agents send pricing reports every heartbeat (typically every 60 seconds).

**Flow Example - Agent Heartbeat with Pricing:**
```
Agent running on instance in pool "t3.medium.ap-south-1a"
  ↓
Agent queries AWS Spot Price API
  ↓
Gets current prices:
  - ap-south-1a: $0.0312/hr
  - ap-south-1b: $0.0298/hr
  - ap-south-1c: $0.0324/hr
  ↓
Agent sends POST /api/agents/<id>/pricing-report
  ↓
Backend inserts into spot_price_snapshots:
  INSERT INTO spot_price_snapshots (pool_id, price, captured_at) VALUES
    ('t3.medium.ap-south-1a', 0.0312, NOW()),
    ('t3.medium.ap-south-1b', 0.0298, NOW()),
    ('t3.medium.ap-south-1c', 0.0324, NOW())
  ↓
These prices are used for:
  - Manual switching panel (shows current prices)
  - Price history charts (7-day graphs)
  - Replica creation (finds cheapest pool)
  - ML model decision making
```

**Why This Table is Critical:**
- ✅ Provides REAL-TIME pricing for manual switching
- ✅ Powers 7-day price history charts
- ✅ Used by ReplicaCoordinator to find cheapest pools
- ✅ Essential for cost optimization decisions

**Without This Data:**
- ❌ Manual switching panel shows no prices
- ❌ Price history charts are empty
- ❌ Replica creation can't find cheapest pools
- ❌ ML model has no pricing data

---

### 7. `switches` - Instance Switch History
```sql
CREATE TABLE switches (
    id VARCHAR(36) PRIMARY KEY,
    client_id VARCHAR(36) NOT NULL,
    agent_id VARCHAR(36) NOT NULL,
    command_id VARCHAR(36),                             -- Command that triggered this switch

    -- Old Instance
    old_instance_id VARCHAR(64),
    old_instance_type VARCHAR(32),
    old_region VARCHAR(32),
    old_az VARCHAR(32),
    old_mode VARCHAR(20),                               -- 'spot' or 'ondemand'
    old_pool_id VARCHAR(128),
    old_ami_id VARCHAR(64),

    -- New Instance
    new_instance_id VARCHAR(64),
    new_instance_type VARCHAR(32),
    new_region VARCHAR(32),
    new_az VARCHAR(32),
    new_mode VARCHAR(20),
    new_pool_id VARCHAR(128),
    new_ami_id VARCHAR(64),

    -- Pricing
    on_demand_price DECIMAL(10, 4),                     -- On-demand price for reference
    old_spot_price DECIMAL(10, 4),                      -- Old instance spot price
    new_spot_price DECIMAL(10, 4),                      -- New instance spot price
    savings_impact DECIMAL(10, 4),                      -- Price difference ($/hour)

    -- Trigger
    event_trigger VARCHAR(50),                          -- 'auto_switch', 'manual', 'emergency', 'rebalance'
    trigger_type VARCHAR(50),                           -- Same as event_trigger (deprecated duplicate)

    -- Timing
    timing_data JSON,                                   -- Full timing details
    initiated_at TIMESTAMP,                             -- When switch was initiated
    ami_created_at TIMESTAMP,                           -- When AMI was created from old instance
    instance_launched_at TIMESTAMP,                     -- When new instance was launched
    instance_ready_at TIMESTAMP,                        -- When new instance became ready
    old_terminated_at TIMESTAMP,                        -- When old instance was terminated (NULL if auto_terminate disabled)

    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (client_id) REFERENCES clients(id),
    FOREIGN KEY (agent_id) REFERENCES agents(id),
    INDEX idx_client_time (client_id, initiated_at),
    INDEX idx_agent (agent_id),
    INDEX idx_old_instance (old_instance_id),
    INDEX idx_new_instance (new_instance_id)
);
```

**Purpose:** Records every instance switch for history, analytics, and savings calculation.

**Flow Example - Complete Switch with Auto-Terminate ON:**
```
1. ML Model decides to switch to cheaper pool
     ↓
2. Backend creates command:
   INSERT INTO commands (agent_id, target_mode='spot', target_pool_id='t3.medium.ap-south-1b', terminate_wait_seconds=1800)
     ↓
3. Agent polls and receives command
     ↓
4. Agent creates AMI from current instance (t3.medium.ap-south-1a)
   AMI: ami-abc123, created at 10:00:00
     ↓
5. Agent launches new instance in target pool (t3.medium.ap-south-1b)
   New instance: i-newinstance, launched at 10:05:00
     ↓
6. Agent waits for new instance to be ready
   Ready at 10:07:30
     ↓
7. Agent waits terminate_wait_seconds (1800s = 30 minutes)
     ↓
8. Agent terminates old instance
   Terminated at 10:37:30
     ↓
9. Agent sends switch report:
   POST /api/agents/<id>/switch-report with:
   {
     old_instance: { instance_id: 'i-oldinstance', mode: 'spot', pool_id: 't3.medium.ap-south-1a' },
     new_instance: { instance_id: 'i-newinstance', mode: 'spot', pool_id: 't3.medium.ap-south-1b' },
     timing: {
       initiated_at: '2025-11-23T10:00:00Z',
       ami_created_at: '2025-11-23T10:00:00Z',
       instance_launched_at: '2025-11-23T10:05:00Z',
       instance_ready_at: '2025-11-23T10:07:30Z',
       old_terminated_at: '2025-11-23T10:37:30Z'  // ← Only included if actually terminated
     },
     pricing: {
       on_demand: 0.0416,
       old_spot: 0.0312,
       new_spot: 0.0298
     }
   }
     ↓
10. Backend inserts switch record:
    INSERT INTO switches (
      client_id, agent_id,
      old_instance_id='i-oldinstance', old_mode='spot', old_pool_id='t3.medium.ap-south-1a',
      new_instance_id='i-newinstance', new_mode='spot', new_pool_id='t3.medium.ap-south-1b',
      on_demand_price=0.0416, old_spot_price=0.0312, new_spot_price=0.0298,
      savings_impact=0.0014,  // (0.0312 - 0.0298)
      initiated_at='2025-11-23T10:00:00Z',
      ami_created_at='2025-11-23T10:00:00Z',
      instance_launched_at='2025-11-23T10:05:00Z',
      instance_ready_at='2025-11-23T10:07:30Z',
      old_terminated_at='2025-11-23T10:37:30Z'
    )
     ↓
11. Backend marks old instance as terminated:
    UPDATE instances SET is_active=FALSE, terminated_at='2025-11-23T10:37:30Z'
    WHERE id='i-oldinstance'
     ↓
12. Backend registers new instance:
    INSERT INTO instances (id='i-newinstance', is_active=TRUE, ...)
```

**Important Fields:**
- **old_terminated_at**: Only populated if auto_terminate_enabled = TRUE AND agent actually terminated the instance
  - If auto_terminate_enabled = FALSE: This field is NULL
  - Backend checks this field before marking old instance as terminated

---

### 8. `spot_interruption_events` - AWS Interruption Signals
```sql
CREATE TABLE spot_interruption_events (
    id VARCHAR(36) PRIMARY KEY,
    agent_id VARCHAR(36) NOT NULL,
    instance_id VARCHAR(64),

    signal_type VARCHAR(50),                            -- 'rebalance-recommendation' or 'instance-termination'
    signal_time TIMESTAMP,                              -- When AWS sent the signal
    detected_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,    -- When agent detected it

    replica_id VARCHAR(36),                             -- Replica created in response
    failover_completed BOOLEAN DEFAULT FALSE,           -- Whether failover completed
    failover_completed_at TIMESTAMP,

    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (agent_id) REFERENCES agents(id),
    INDEX idx_agent_time (agent_id, detected_at),
    INDEX idx_signal_type (signal_type)
);
```

**Purpose:** Tracks AWS spot interruption signals for emergency replica orchestration.

**Signal Types:**
- **`rebalance-recommendation`**: AWS warns instance MAY be interrupted (rebalanced). Not guaranteed termination. Gives ~15 minutes to 2 hours warning.
- **`instance-termination`**: AWS confirms instance WILL be terminated in 2 minutes. Guaranteed termination.

**Flow Example - Emergency Replica on Rebalance:**
```
1. AWS sends rebalance recommendation signal
     ↓
2. Agent detects signal via EC2 metadata endpoint
     ↓
3. Agent sends POST /api/agents/<id>/interruption-signal
   {
     signal_type: 'rebalance-recommendation',
     signal_time: '2025-11-23T10:00:00Z'
   }
     ↓
4. Backend inserts event:
   INSERT INTO spot_interruption_events (
     agent_id, instance_id, signal_type='rebalance-recommendation',
     signal_time='2025-11-23T10:00:00Z', detected_at=NOW()
   )
     ↓
5. ReplicaCoordinator detects event (within 10 seconds)
     ↓
6. Checks: Does agent have auto_switch_enabled = TRUE?
     ↓ YES
7. Creates emergency replica:
   INSERT INTO replica_instances (
     agent_id, replica_type='automatic-rebalance', status='launching'
   )
     ↓
8. Updates event with replica_id
     ↓
9. Monitors replica until ready
     ↓
[Two possible outcomes:]

Outcome A: Rebalance clears (no termination)
  ↓
  Wait 2 hours, no termination signal
  ↓
  Terminate emergency replica (no longer needed)
  ↓
  UPDATE replica_instances SET is_active=FALSE, status='terminated'

Outcome B: Termination notice received
  ↓
  Agent sends termination signal
  ↓
  INSERT spot_interruption_events (signal_type='instance-termination')
  ↓
  ReplicaCoordinator promotes replica immediately
  ↓
  UPDATE spot_interruption_events SET failover_completed=TRUE
  ↓
  Agent connects to replica
  ↓
  ML model resumes control
```

---

## 📈 Data Flow Patterns

### Pattern 1: Agent Heartbeat
```
Agent (every 60 seconds):
  ↓
  POST /api/agents/<id>/heartbeat
  {
    status: 'online',
    instance_id: 'i-123',
    mode: 'spot',
    pool_id: 't3.medium.ap-south-1a'
  }
  ↓
Backend:
  UPDATE agents SET
    status='online',
    last_heartbeat_at=NOW(),
    instance_id='i-123',
    current_mode='spot',
    current_pool_id='t3.medium.ap-south-1a'
```

### Pattern 2: Pricing Report
```
Agent (every 60 seconds):
  ↓
  POST /api/agents/<id>/pricing-report
  {
    pools: [
      { id: 't3.medium.ap-south-1a', price: 0.0312 },
      { id: 't3.medium.ap-south-1b', price: 0.0298 },
      { id: 't3.medium.ap-south-1c', price: 0.0324 }
    ],
    on_demand_price: 0.0416
  }
  ↓
Backend:
  For each pool:
    INSERT INTO spot_price_snapshots (pool_id, price, captured_at)
    VALUES (pool.id, pool.price, NOW())
```

### Pattern 3: Manual Switching
```
User clicks "Switch to Pool X":
  ↓
  Frontend: POST /api/client/instances/<id>/force-switch
  { target: 'pool', pool_id: 't3.medium.ap-south-1b' }
  ↓
Backend:
  INSERT INTO commands (
    agent_id, target_mode='spot',
    target_pool_id='t3.medium.ap-south-1b',
    terminate_wait_seconds=<from agent config>
  )
  ↓
Agent polls GET /api/agents/<id>/pending-commands
  ↓
Agent executes switch (see switches table flow)
```

---

## 🔍 Key Queries

### Get Agent with All Configuration
```sql
SELECT
    a.id, a.logical_agent_id, a.instance_id,
    a.auto_switch_enabled, a.manual_replica_enabled,
    a.auto_terminate_enabled, a.terminate_wait_seconds,
    a.replica_count, a.current_replica_id,
    a.status, a.last_heartbeat_at
FROM agents a
WHERE a.client_id = ? AND a.id = ?;
```

### Get Current Spot Prices for Pools
```sql
SELECT sp.id, sp.pool_name, sp.az, sps.price
FROM spot_pools sp
LEFT JOIN (
    SELECT pool_id, price,
           ROW_NUMBER() OVER (PARTITION BY pool_id ORDER BY captured_at DESC) as rn
    FROM spot_price_snapshots
    WHERE captured_at >= DATE_SUB(NOW(), INTERVAL 1 HOUR)
) sps ON sps.pool_id = sp.id AND sps.rn = 1
WHERE sp.instance_type = ? AND sp.region = ?
ORDER BY sps.price ASC;
```

### Get Active Replicas for Agent
```sql
SELECT id, instance_id, replica_type, status, sync_status, state_transfer_progress
FROM replica_instances
WHERE agent_id = ?
  AND is_active = TRUE
  AND status NOT IN ('terminated', 'promoted')
ORDER BY created_at DESC;
```

---

**Last Updated:** 2025-11-23
**Schema Version:** 2.0
**All Tables Documented:** ✅
