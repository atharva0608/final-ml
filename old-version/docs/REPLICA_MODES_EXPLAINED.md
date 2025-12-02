# Replica Modes Explained: Auto-Switch vs Manual Replica

## Overview
There are TWO completely different replica modes in the system. Understanding the difference is critical.

---

## 🔵 Mode 1: Auto-Switch Mode (Emergency Replicas Only)

### When Active
- Toggle: **Auto-Switch = ON**
- Toggle: **Manual Replica = OFF** (mutually exclusive)

### Replica Creation Trigger
**ONLY creates replicas when AWS sends interruption notices:**

1. **Rebalance Recommendation Notice**
   - AWS signals: "Your spot instance MAY be interrupted soon"
   - System response: Create emergency replica immediately
   - Replica purpose: Standby for potential termination
   - Replica lifespan: Until termination notice OR rebalance clears

2. **Spot Termination Notice (2-minute warning)**
   - AWS signals: "Your spot instance WILL terminate in 2 minutes"
   - System response: Promote existing replica (if ready from rebalance), otherwise emergency launch
   - Override: Hand control to emergency system (bypass ML model)
   - Failover: Switch to replica immediately

### Flow Example

```
Normal Operation:
  ↓
  ML Model has full control
  ↓
  Agent monitors interruption signals
  ↓
[Rebalance Notice Detected]
  ↓
  Create Emergency Replica in cheapest pool
  ↓
  Replica syncs state from primary
  ↓
  Wait and monitor...
  ↓
[Two Outcomes:]

Outcome A: Rebalance Clears (no termination)
  ↓
  Terminate replica (no longer needed)
  ↓
  Return control to ML Model
  ↓
  Continue normal operation

Outcome B: Termination Notice Received
  ↓
  Promote replica to primary (if ready)
  ↓
  OR emergency launch new instance (if replica not ready)
  ↓
  Wait for ML model to hand back control
  ↓
  ML Model resumes decision-making
```

### Key Characteristics
- ✅ **Proactive**: Creates replica on rebalance (before termination)
- ✅ **Cost-efficient**: Only creates replicas during actual AWS emergencies
- ✅ **ML-driven**: ML model controls all switches except during emergency
- ❌ **Not always ready**: If termination happens without rebalance, no replica exists

---

## 🟢 Mode 2: Manual Replica Mode (Continuous Standby)

### When Active
- Toggle: **Manual Replica = ON**
- Toggle: **Auto-Switch = OFF** (mutually exclusive)

### Replica Creation Trigger
**ALWAYS maintains a standby replica:**

1. **When Manual Replica is enabled**
   - System response: Create replica immediately
   - Replica purpose: Continuous hot standby for instant failover
   - No AWS interruption needed

2. **After ANY switch/promotion**
   - User switches to replica (manual or otherwise)
   - System response: Create NEW replica for the new primary
   - Continues indefinitely

3. **If replica terminates/fails**
   - System response: Recreate replica automatically
   - Maintains 1 replica at all times

### Flow Example

```
User Enables Manual Replica:
  ↓
  System sets manual_replica_enabled = TRUE
  ↓
  ReplicaCoordinator detects (within 10 seconds)
  ↓
  Create replica in cheapest available pool
  ↓
  Replica stays active continuously
  ↓
  [User decides to switch to replica]
  ↓
  Promote replica to primary
  ↓
  Replica becomes new primary instance
  ↓
  IMMEDIATELY create NEW replica for new primary
  ↓
  Always maintain 1 active replica
  ↓
  [Loop continues until user disables manual replica]
```

### Key Characteristics
- ✅ **Always ready**: Replica always exists and synced
- ✅ **User-controlled**: You decide when to switch, not the ML model
- ✅ **Zero-downtime failover**: Instant promotion, no AWS launch delay
- ❌ **Higher cost**: Runs extra instance 24/7 until disabled
- ❌ **Manual decisions**: No automatic switching, you control everything

---

## 📊 Side-by-Side Comparison

| Feature | Auto-Switch Mode | Manual Replica Mode |
|---------|-----------------|---------------------|
| **Replica Creation** | Only on AWS interruption | Continuous (always) |
| **When Replica Exists** | Rebalance → Termination period | 24/7 while enabled |
| **Who Controls Switching** | ML Model (except emergency) | User |
| **Auto-Switch After Switch** | Yes, ML resumes | No, user switches |
| **Replica After Switch** | Terminated (emergency over) | NEW replica created |
| **Cost** | Lower (replica only during emergency) | Higher (continuous replica) |
| **Failover Speed** | Fast if rebalance detected, slow if not | Instant (always ready) |
| **Use Case** | Cost optimization, trust ML | User-controlled, zero-downtime |

---

## 🔧 Technical Implementation

### Background Job: ReplicaCoordinator

The `ReplicaCoordinator` runs every 10 seconds and handles both modes:

```python
def _monitor_loop(self):
    while self.running:
        agents = get_all_active_agents()

        for agent in agents:
            if agent['auto_switch_enabled']:
                # Auto-Switch Mode
                self._handle_auto_switch_mode(agent)

            elif agent['manual_replica_enabled']:
                # Manual Replica Mode
                self._handle_manual_replica_mode(agent)

        time.sleep(10)
```

### Auto-Switch Handler

```python
def _handle_auto_switch_mode(agent):
    # Check for interruption events
    interruption = get_latest_interruption(agent_id)

    if interruption and interruption.signal == 'rebalance':
        # Create emergency replica
        if not replica_exists(agent_id):
            create_emergency_replica(agent)

    elif interruption and interruption.signal == 'termination':
        # Promote replica immediately
        promote_replica(agent)
        hand_back_to_ml_model(agent)
```

### Manual Replica Handler

```python
def _handle_manual_replica_mode(agent):
    # Always ensure exactly 1 replica exists
    active_replicas = get_active_replicas(agent_id)

    if len(active_replicas) == 0:
        # No replica - create one
        create_manual_replica(agent)

    elif len(active_replicas) > 1:
        # Too many - keep newest, terminate others
        cleanup_extra_replicas(agent)

    # Check if user promoted a replica recently
    if replica_was_promoted_recently(agent_id):
        # Create NEW replica for new primary
        time.sleep(2)  # Let promotion complete
        create_manual_replica(agent)
```

---

## 🎯 When to Use Each Mode

### Use Auto-Switch Mode When:
- ✅ You want to minimize costs
- ✅ You trust ML model decisions
- ✅ You can tolerate brief downtime during undetected terminations
- ✅ Cost optimization is priority over uptime
- ✅ You run non-critical workloads

### Use Manual Replica Mode When:
- ✅ You need guaranteed zero-downtime failover
- ✅ You want full manual control over switching
- ✅ You run mission-critical workloads
- ✅ Cost of downtime > cost of extra instance
- ✅ You don't trust automatic ML decisions
- ✅ You need instant failover capability at all times

---

## 📝 Configuration Examples

### Example 1: Cost-Optimized ML Training

```yaml
Agent Configuration:
  auto_switch_enabled: TRUE
  manual_replica_enabled: FALSE
  auto_terminate_enabled: TRUE
  terminate_wait_minutes: 30

Behavior:
  - ML model switches instances for cost savings
  - Emergency replica only on AWS interruption
  - Old instances terminated after 30 minutes
  - Minimal replica costs
```

### Example 2: Production Database with Zero Downtime

```yaml
Agent Configuration:
  auto_switch_enabled: FALSE
  manual_replica_enabled: TRUE
  auto_terminate_enabled: FALSE
  terminate_wait_minutes: N/A

Behavior:
  - Continuous hot standby replica
  - User controls all switches manually
  - Old instances kept running (manual cleanup)
  - Maximum availability, higher cost
```

### Example 3: Hybrid Approach (NOT SUPPORTED)

```yaml
# ❌ INVALID - These are mutually exclusive!
Agent Configuration:
  auto_switch_enabled: TRUE  # ❌
  manual_replica_enabled: TRUE  # ❌ Can't have both

System Response:
  - Enabling one automatically disables the other
  - Frontend shows warning message
```

---

## 🐛 Troubleshooting

### Manual Replica Not Creating

**Check 1: Is ReplicaCoordinator running?**
```bash
grep "ReplicaCoordinator started" /var/log/flask/backend.log
```

**Check 2: Is manual_replica_enabled set correctly?**
```sql
SELECT id, logical_agent_id, manual_replica_enabled, replica_count
FROM agents
WHERE id = '<agent_id>';
```

**Check 3: Does agent have an active instance?**
```sql
SELECT id, agent_id, is_active
FROM instances
WHERE agent_id = '<agent_id>';
```

**Check 4: Are there available pools?**
```sql
SELECT sp.id, sp.az, sps.price
FROM spot_pools sp
LEFT JOIN (
    SELECT pool_id, price,
           ROW_NUMBER() OVER (PARTITION BY pool_id ORDER BY captured_at DESC) as rn
    FROM spot_price_snapshots
) sps ON sps.pool_id = sp.id AND sps.rn = 1
WHERE sp.instance_type = 't3.medium'
  AND sp.region = 'ap-south-1';
```

**Check 5: Check coordinator logs**
```bash
tail -f /var/log/flask/backend.log | grep -i "manual replica\|manual mode"
```

### Emergency Replica Not Creating

**Check 1: Is auto_switch_enabled set?**
```sql
SELECT id, logical_agent_id, auto_switch_enabled, replica_count
FROM agents
WHERE id = '<agent_id>';
```

**Check 2: Are interruption events being detected?**
```sql
SELECT signal_type, detected_at, replica_id
FROM spot_interruption_events
WHERE agent_id = '<agent_id>'
ORDER BY detected_at DESC
LIMIT 5;
```

**Check 3: Agent sending interruption signals?**
- Agent must send POST `/api/agents/<id>/interruption-signal` when AWS sends notice
- Check agent logs for interruption detection

---

## 💡 Best Practices

### For Manual Replica Mode:
1. **Monitor costs**: You're paying for replica 24/7
2. **Regular testing**: Test failover monthly to ensure replica is working
3. **Sync monitoring**: Ensure replica stays in sync with primary
4. **Disable when not needed**: Turn off manual replica for dev/test environments

### For Auto-Switch Mode:
1. **Trust the ML**: Don't interfere with ML decisions
2. **Monitor interruptions**: Watch for rebalance notices
3. **Set reasonable terminate_wait**: 30-60 minutes is good
4. **Enable auto_terminate**: Keep costs down

---

## 📈 Cost Analysis

### Example: t3.medium in ap-south-1

**Spot Price:** $0.0312/hour
**On-Demand Price:** $0.0416/hour
**Hours/Month:** 730

#### Auto-Switch Mode Cost
```
Primary instance:     730 hrs × $0.0312  = $22.78
Emergency replica:    ~10 hrs × $0.0312  = $0.31 (only during AWS emergencies)
Total:                                    $23.09/month
```

#### Manual Replica Mode Cost
```
Primary instance:     730 hrs × $0.0312  = $22.78
Continuous replica:   730 hrs × $0.0312  = $22.78
Total:                                    $45.56/month
```

**Cost Difference:** $22.47/month (97% more expensive)

**Break-even:** If downtime costs > $22.47/month, manual replica is worth it

---

**Last Updated:** 2025-11-23
**Backend Version:** 2.0.0
**ReplicaCoordinator:** Active
