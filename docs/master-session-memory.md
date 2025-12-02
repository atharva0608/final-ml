# Master Session Memory - CAST-AI Mini (Agentless Spot Optimizer)

**Version**: 3.0.0
**Last Updated**: 2025-12-02
**Status**: Living Document - Update with all design changes

---

## Executive Summary

This document is the **single source of truth** for the current system design. All changes to architecture, decision logic, or configuration must be reflected here.

### What We're Building

> A **single-instance, agentless spot optimizer** that uses AWS APIs and a **1-hour price prediction model** to intelligently decide when to stay on the current spot pool, when to switch to another spot pool, and when to fall back to on-demand.

### Key Principles

1. **Agentless**: No custom agent process runs on instances. All operations use AWS SDK from backend.
2. **Single Instance Focus**: This phase manages one EC2 instance at a time (PoC/test case).
3. **Future-Proof**: Design allows later extension to multi-instance, Kubernetes, or agent-based approaches.
4. **Production Ready**: Despite being "mini", this is usable in production for critical single instances.

---

## 1. Current Scope: Agentless CAST-AI Mini

### What This Is

A backend service that:
- Monitors a single EC2 spot instance
- Collects usage metrics via CloudWatch
- Fetches current and historical spot prices
- Uses ML model to predict prices 1 hour ahead
- Decides whether to stay, switch, or fall back to on-demand
- Executes decisions via AWS SDK (launch new instance, terminate old)

### What This Is NOT (Yet)

- ❌ Multi-instance cluster management
- ❌ Kubernetes integration
- ❌ Custom agent running on instances
- ❌ Replica management or manual failover modes
- ❌ Multi-region support

These features are **intentionally out of scope** for this phase but the architecture supports them in the future.

---

## 2. Architecture Overview

```
┌─────────────────────────────────────────────────────────┐
│                     Backend Service                      │
│                                                          │
│  ┌────────────────┐      ┌─────────────────────────┐   │
│  │   Decision     │      │      Executor           │   │
│  │    Engine      │◄────►│   (AWS SDK Layer)       │   │
│  │                │      │                         │   │
│  │ • Pool Disc.   │      │ • get_instance_state()  │   │
│  │ • Price Filter │      │ • get_usage_metrics()   │   │
│  │ • 1h Forecast  │      │ • get_pricing_snapshot()│   │
│  │ • Usage Class. │      │ • launch_instance()     │   │
│  │ • Action Select│      │ • terminate_instance()  │   │
│  └────────────────┘      └─────────────────────────┘   │
│           │                        │                    │
│           │                        │                    │
│           ▼                        ▼                    │
│  ┌────────────────────────────────────────────────┐    │
│  │  PricePredictionIndependentCrossAZ (ML Model)  │    │
│  │  • Predicts price 1h ahead                     │    │
│  │  • Per pool, per AZ                            │    │
│  └────────────────────────────────────────────────┘    │
│                                                          │
└─────────────────────────────────────────────────────────┘
                         │
                         │ AWS SDK Calls
                         ▼
            ┌────────────────────────────┐
            │      AWS Services          │
            │                            │
            │  • EC2 API                 │
            │  • CloudWatch              │
            │  • Spot Price History      │
            │  • Instance Metadata       │
            └────────────────────────────┘
```

---

## 3. Executor: Backend as the "Agent"

The **Executor** is a clean abstraction layer that hides AWS calls behind a simple interface.

### Purpose

- Allows decision logic to be cloud-agnostic
- Makes it easy to swap AWS SDK for Kubernetes or agent-based implementations later
- Centralizes all infrastructure interactions

### Executor Interface

#### 3.1 `get_instance_state(instance_id) → InstanceState`

**AWS Calls**: `DescribeInstances`, `DescribeInstanceStatus`

**Returns**:
```python
{
    "state": "running | stopped | terminated",
    "az": "us-east-1a",
    "instance_type": "m5.large",
    "lifecycle": "spot | on-demand",
    "instance_id": "i-123456",
    "subnet_id": "subnet-abc",
    "vpc_id": "vpc-xyz",
    "tags": {...}
}
```

#### 3.2 `get_usage_metrics(instance_id, window_minutes) → UsageMetrics`

**AWS Calls**: CloudWatch `GetMetricStatistics` or `GetMetricData`

**Metrics Collected**:
- `CPUUtilization` (required)
- `NetworkIn` / `NetworkOut` (optional)
- `Memory` (optional, requires CloudWatch Agent)

**Returns**:
```python
{
    "cpu_p95": 45.2,      # 95th percentile
    "cpu_avg": 32.1,      # average
    "network_in_p95": 1024000,
    "network_out_p95": 512000,
    "memory_p95": 62.5,   # if available
    "memory_avg": 55.0
}
```

#### 3.3 `get_pricing_snapshot(instance_type, region, pools[]) → PricingSnapshot`

**AWS Calls**: `DescribeSpotPriceHistory` + internal price cache

**Returns**:
```python
{
    "on_demand_price": 0.096,
    "pools": [
        {
            "pool_id": "us-east-1a-standard",
            "az": "us-east-1a",
            "current_spot_price": 0.035,
            "discount_percent": 63.5
        },
        ...
    ]
}
```

#### 3.4 `launch_instance(target_spec) → instance_id`

**AWS Calls**: `RunInstances`

**Input**:
```python
{
    "instance_type": "m5.large",
    "az": "us-east-1a",
    "subnet_id": "subnet-abc",
    "pool_id": "us-east-1a-standard",
    "ami_id": "ami-xyz" or "launch_template_id": "lt-123",
    "tags": {...},
    "lifecycle": "spot | on-demand"
}
```

**Returns**: `"i-789012"`

#### 3.5 `terminate_instance(instance_id) → bool`

**AWS Calls**: `TerminateInstances`

**Returns**: `true` on success

#### 3.6 `wait_for_instance_state(instance_id, target_state, timeout_seconds) → bool`

Polls `DescribeInstances` until state matches or timeout.

**Returns**: `true` if reached target state, `false` if timeout

---

## 4. Decision Engine: The Brain

The Decision Engine is **one unified component** with multiple internal logical sub-components.

### 4.1 Input Structure

```python
{
    # Current instance
    "instance_id": "i-123456",
    "instance_type": "m5.large",
    "az": "us-east-1a",
    "lifecycle": "spot",
    "current_pool_id": "us-east-1a-standard",

    # Usage metrics
    "cpu_p95": 45.0,
    "cpu_avg": 32.0,
    "memory_p95": 55.0,
    "network_p95": 1024000,

    # Current pricing
    "current_spot_price": 0.035,
    "current_discount": 63.5,
    "on_demand_price": 0.096,

    # Predicted pricing (1h ahead)
    "predicted_price_1h": 0.042,
    "predicted_discount_1h": 56.3,
    "predicted_volatility": 0.15,

    # Config
    "config": {
        "baseline_discount": 60.0,
        "baseline_volatility": 0.10,
        "discount_margin": 5.0,
        "volatility_factor_max": 1.5,
        "min_future_discount_gain": 3.0,
        "min_future_risk_improvement": 0.05,
        "cooldown_minutes": 10,
        "fallback_to_ondemand_enabled": true
    }
}
```

### 4.2 Internal Components

#### 4.2.1 PoolDiscoveryAndDedup

**Purpose**: Find all available spot pools for this instance type in the region.

**Logic**:
- Query AWS for all AZs supporting this instance type
- Query spot price history for all pools
- Deduplicate by `(AZ, pool_id)` to avoid treating same pool twice
- Output: `List[Pool]`

#### 4.2.2 CurrentPriceFilter

**Purpose**: Filter pools by current price and basic sanity checks.

**Logic**:
- Keep only pools where:
  - `current_price <= current_pool_price * 1.1` (not more than 10% more expensive)
  - `current_discount >= baseline_discount - (discount_margin * 2)` (not too far below baseline)
  - No immediate instability flags (if available)
- Output: `candidate_pools_current`

#### 4.2.3 OneHourPriceForecast

**Purpose**: Call ML model to predict 1-hour ahead prices.

**Logic**:
- For current pool + each candidate pool:
  - Call `PricePredictionIndependentCrossAZ.predict(pool, timestamp)`
  - Compute:
    - `predicted_price_1h`
    - `predicted_discount = (1 - predicted_price_1h / on_demand_price) * 100`
    - `predicted_volatility` (optional: std dev of recent predictions)

**Output**: Each pool now has predicted metrics

#### 4.2.4 UsageClassification

**Purpose**: Classify instance as over/right/under-provisioned.

**Thresholds**:
- **OVER_PROVISIONED**: `cpu_p95 < 30%` AND `memory_p95 < 40%`
- **UNDER_PROVISIONED**: `cpu_p95 > 80%` OR `memory_p95 > 80%`
- **RIGHT_SIZED**: Everything in between

**Output**: Usage classification enum

#### 4.2.5 FutureBaselineCheck

**Purpose**: Check if current pool will be acceptable in 1 hour.

**Logic**:
```python
is_discount_ok = (predicted_discount_current >= baseline_discount - discount_margin)
is_volatility_ok = (predicted_vol_current <= baseline_volatility * volatility_factor_max)
current_pool_future_ok = is_discount_ok AND is_volatility_ok
```

**Output**: `bool` - is current pool predicted to be OK?

#### 4.2.6 CandidateFilterWithUsageRules

**Purpose**: Apply right-sizing rules based on usage classification.

**Logic**:

**If RIGHT_SIZED**:
- Only allow same instance type or similar shape
- No upsizing or downsizing

**If OVER_PROVISIONED**:
- Only allow **smaller** instance types
- Must be **cheaper AND more stable** than current
- Ignore bigger instances even if cheaper (per user rule)

**If UNDER_PROVISIONED**:
- Only allow **bigger** instance types
- Must be **same price or cheaper AND stable**
- If no safe/cheap spot exists, consider fallback to on-demand

**Output**: `allowed_candidates[]`

#### 4.2.7 FutureImprovementFilter

**Purpose**: Ensure candidates are meaningfully better than current pool's predicted future.

**Logic**:
```python
for candidate in allowed_candidates:
    discount_improvement = candidate.predicted_discount - current.predicted_discount
    risk_improvement = current.predicted_risk - candidate.predicted_risk

    if (discount_improvement >= min_future_discount_gain AND
        risk_improvement >= min_future_risk_improvement):
        keep_candidate()
    else:
        discard_candidate()
```

**Output**: `qualified_candidates[]`

#### 4.2.8 ActionSelector

**Purpose**: Make final decision.

**Logic**:
```python
if current_pool_future_ok AND usage != UNDER_PROVISIONED:
    return Action(type=STAY)

elif len(qualified_candidates) > 0:
    best = pick_safest_candidate(qualified_candidates)
    return Action(
        type=SWITCH_TO_SPOT,
        target_pool_id=best.pool_id,
        target_instance_type=best.instance_type
    )

elif usage == UNDER_PROVISIONED AND fallback_to_ondemand_enabled:
    return Action(
        type=FALLBACK_ONDEMAND,
        target_instance_type=choose_ondemand_size()
    )

else:
    return Action(type=STAY)
```

### 4.3 Output Structure

```python
{
    "action_type": "STAY | SWITCH_TO_SPOT | FALLBACK_ONDEMAND",
    "target_instance_type": "m5.large or null",
    "target_pool_id": "us-east-1b-standard or null",
    "reason": "Current pool predicted stable at 62% discount for next hour",
    "cooldown_until": "2025-12-02T10:30:00Z",
    "decision_metadata": {
        "current_pool_future_discount": 62.0,
        "current_pool_future_volatility": 0.08,
        "best_candidate_discount": 65.0,
        "usage_classification": "RIGHT_SIZED",
        "pools_evaluated": 12,
        "candidates_after_filters": 2
    }
}
```

---

## 5. Agentless Control Flow - End-to-End

### 5.1 Trigger

**Options**:
- Scheduled (cron, every 5-10 minutes)
- Manual button in UI ("run decision now")
- Event-driven (price alert, usage spike)

### 5.2 Decision Cycle

```python
# 1. Collect State
instance_state = executor.get_instance_state(instance_id)
usage_metrics = executor.get_usage_metrics(instance_id, window_minutes=30)
pricing_snapshot = executor.get_pricing_snapshot(
    instance_state.instance_type,
    region,
    all_pools
)

# 2. Check Cooldown
if db.is_in_cooldown(instance_id):
    log("Instance in cooldown, skipping decision")
    return

# 3. Run ML Prediction
predictions = ml_model.predict_1h_ahead(pricing_snapshot.pools)

# 4. Run Decision Engine
decision = decision_engine.decide(
    instance_state=instance_state,
    usage_metrics=usage_metrics,
    pricing_snapshot=pricing_snapshot,
    predictions=predictions,
    config=config
)

# 5. Execute Action
if decision.action_type == "STAY":
    log_decision(decision)

elif decision.action_type == "SWITCH_TO_SPOT":
    execute_switch(decision)

elif decision.action_type == "FALLBACK_ONDEMAND":
    execute_fallback(decision)

# 6. Set Cooldown
db.set_cooldown(instance_id, decision.cooldown_until)
```

### 5.3 Execute Switch

```python
def execute_switch(decision):
    # 1. Build target spec
    target_spec = {
        "instance_type": decision.target_instance_type,
        "pool_id": decision.target_pool_id,
        "az": extract_az_from_pool(decision.target_pool_id),
        "ami_id": instance_state.ami_id,
        "tags": instance_state.tags
    }

    # 2. Launch new instance
    new_instance_id = executor.launch_instance(target_spec)
    log_event("LAUNCH", new_instance_id, decision.reason)

    # 3. Wait for running state
    success = executor.wait_for_instance_state(
        new_instance_id,
        "running",
        timeout_seconds=300
    )

    if not success:
        log_error("New instance failed to start")
        executor.terminate_instance(new_instance_id)
        return

    # 4. Terminate old instance
    executor.terminate_instance(instance_state.instance_id)
    log_event("TERMINATE", instance_state.instance_id)

    # 5. Wait for termination
    executor.wait_for_instance_state(
        instance_state.instance_id,
        "terminated",
        timeout_seconds=120
    )

    # 6. Update database
    db.mark_instance_terminated(instance_state.instance_id)
    db.mark_instance_primary(new_instance_id)
    db.record_switch_event(
        old_id=instance_state.instance_id,
        new_id=new_instance_id,
        reason=decision.reason,
        cost_savings=calculate_savings(decision)
    )

    # 7. Notify frontend via WebSocket
    websocket.broadcast({
        "type": "SWITCH_COMPLETED",
        "old_instance": instance_state.instance_id,
        "new_instance": new_instance_id,
        "reason": decision.reason
    })
```

### 5.4 Execute Fallback

Same as switch, but:
- `lifecycle = "on-demand"` in target_spec
- Log reason as "fallback to on-demand for stability"
- Update cost tracking to reflect on-demand pricing

---

## 6. Configuration Parameters

### 6.1 Core Thresholds

| Parameter | Default | Description |
|-----------|---------|-------------|
| `baseline_discount` | 60.0 | Typical desired discount (%) |
| `baseline_volatility` | 0.10 | Typical volatility threshold |
| `discount_margin` | 5.0 | Acceptable drop below baseline (%) |
| `volatility_factor_max` | 1.5 | Max volatility multiple vs baseline |
| `min_future_discount_gain` | 3.0 | Min improvement to justify switch (%) |
| `min_future_risk_improvement` | 0.05 | Min risk improvement to justify switch |
| `cooldown_minutes` | 10 | Min time between decisions |

### 6.2 Usage Classification Thresholds

| Threshold | Value | Description |
|-----------|-------|-------------|
| `over_provisioned_cpu_max` | 30.0 | CPU p95 below this = over-provisioned |
| `over_provisioned_mem_max` | 40.0 | Memory p95 below this = over-provisioned |
| `under_provisioned_cpu_min` | 80.0 | CPU p95 above this = under-provisioned |
| `under_provisioned_mem_min` | 80.0 | Memory p95 above this = under-provisioned |

### 6.3 Feature Flags

| Flag | Default | Description |
|------|---------|-------------|
| `fallback_to_ondemand_enabled` | true | Allow fallback to on-demand |
| `allow_rightsize_down` | true | Allow downsizing when over-provisioned |
| `allow_rightsize_up` | true | Allow upsizing when under-provisioned |
| `dry_run_mode` | false | Log decisions but don't execute |

---

## 7. ML Model Integration

### 7.1 Model: PricePredictionIndependentCrossAZ

**Purpose**: Predict spot price 1 hour ahead for a given pool.

**Input**:
```python
{
    "pool_id": "us-east-1a-standard",
    "instance_type": "m5.large",
    "timestamp": "2025-12-02T10:00:00Z",
    "recent_prices": [0.035, 0.036, 0.034, ...]  # last 24h
}
```

**Output**:
```python
{
    "predicted_price_1h": 0.042,
    "confidence": 0.87,
    "prediction_timestamp": "2025-12-02T11:00:00Z"
}
```

### 7.2 Model Training

- Trained on historical spot price data
- Features: time of day, day of week, recent price trends, volatility
- Model type: XGBoost / LightGBM / LSTM (TBD based on performance)
- Retrained weekly or on-demand

### 7.3 Model Fallback

If ML model fails or is unavailable:
- Use recent average price as prediction
- Apply conservative thresholds (higher discount_margin)
- Log warning and alert operator

---

## 8. Database Schema (Key Tables)

### 8.1 instances

```sql
CREATE TABLE instances (
    instance_id VARCHAR(20) PRIMARY KEY,
    instance_type VARCHAR(50),
    az VARCHAR(20),
    lifecycle ENUM('spot', 'on-demand'),
    status ENUM('running', 'stopped', 'terminated'),
    is_primary BOOLEAN DEFAULT false,
    created_at TIMESTAMP,
    terminated_at TIMESTAMP NULL
);
```

### 8.2 decision_history

```sql
CREATE TABLE decision_history (
    id INT PRIMARY KEY AUTO_INCREMENT,
    instance_id VARCHAR(20),
    timestamp TIMESTAMP,
    action_type ENUM('STAY', 'SWITCH_TO_SPOT', 'FALLBACK_ONDEMAND'),
    reason TEXT,
    target_instance_type VARCHAR(50) NULL,
    target_pool_id VARCHAR(100) NULL,
    executed BOOLEAN DEFAULT false,
    decision_metadata JSON
);
```

### 8.3 switch_events

```sql
CREATE TABLE switch_events (
    id INT PRIMARY KEY AUTO_INCREMENT,
    old_instance_id VARCHAR(20),
    new_instance_id VARCHAR(20),
    timestamp TIMESTAMP,
    reason TEXT,
    old_price DECIMAL(10,4),
    new_price DECIMAL(10,4),
    cost_savings DECIMAL(10,2),
    downtime_seconds INT,
    success BOOLEAN
);
```

---

## 9. Safety Mechanisms

### 9.1 Cooldown

- Prevents rapid repeated decisions
- Default: 10 minutes between decisions for same instance
- Can be overridden manually via UI

### 9.2 Circuit Breaker

If 3+ switches fail in a row:
- Auto-disable auto-switching for this instance
- Send alert to operator
- Require manual intervention to re-enable

### 9.3 Dry Run Mode

- Log all decisions without executing
- Useful for testing new thresholds/models
- Enable via config flag

### 9.4 Manual Override

- UI button to disable auto-decisions
- Instance enters "manual mode" until re-enabled
- All decisions logged but not executed

---

## 10. Future Extensibility

### 10.1 Multi-Instance Support

**Current**: One instance at a time
**Future**: Loop over all managed instances

**Changes Needed**:
- Extend decision cycle to iterate over `instances[]`
- Add per-instance cooldown tracking
- Parallelize decision execution

### 10.2 Kubernetes Integration

**Current**: Direct EC2 instances
**Future**: Kubernetes node pools

**Changes Needed**:
- Create `KubernetesExecutor` implementing same interface
- Replace EC2 calls with kubectl/K8s API
- Extend decision logic for pod scheduling

### 10.3 Agent-Based Approach

**Current**: Agentless via AWS SDK
**Future**: Optional agent for faster metrics

**Changes Needed**:
- Create `AgentBasedExecutor`
- Agent reports metrics via API
- Backend issues commands via agent API
- Decision logic unchanged

### 10.4 Advanced ML Models

**Current**: 1-hour prediction
**Future**: Multi-horizon, risk modeling

**Changes Needed**:
- Extend ML model to predict 1h, 6h, 24h
- Add risk scoring (interruption probability)
- Enhance decision logic with risk-adjusted thresholds

---

## 11. Change Log

### v3.0.0 (2025-12-02)

**Major Changes**:
- Complete pivot to agentless architecture
- Single-instance focus (removed multi-agent, replica modes)
- Unified Decision Engine with clear sub-components
- Executor abstraction for future extensibility
- 1-hour price prediction as primary decision input

**Removed**:
- Custom agent process
- Replica management (manual/automatic modes)
- Multi-instance cluster logic
- Emergency fallback system (replaced with fallback-to-ondemand)

**Archived**:
- All old agent-related docs → `old-version/docs/`
- Old agent code → `old-version/agent/`

### v2.0.0 (2025-11-21)

- Agent-based architecture with replicas
- Smart Emergency Fallback system
- Manual and automatic replica modes

### v1.0.0 (Initial)

- Basic spot optimizer with agent

---

## 12. Maintenance

### Updating This Document

**When to Update**:
- Adding/changing any config parameter
- Modifying decision logic or thresholds
- Adding new Executor methods
- Changing database schema
- Adjusting ML model inputs/outputs

**How to Update**:
1. Edit this file directly
2. Update version number and change log
3. Commit with message: `docs: update master session memory - [brief change]`
4. **DO NOT** create new session memory docs

### Document Owner

This is the **living design doc**. All session memory, design decisions, and architecture changes go here.

---

## Appendix A: Glossary

| Term | Definition |
|------|------------|
| **Pool** | A specific spot capacity pool (AZ + instance family combination) |
| **Lifecycle** | Whether instance is spot or on-demand |
| **Discount** | Percentage savings vs on-demand price |
| **Volatility** | Measure of price stability (std dev of recent prices) |
| **Right-sizing** | Adjusting instance size to match actual usage |
| **Cooldown** | Minimum time between decisions to prevent thrashing |
| **Fallback** | Switching to on-demand when no safe spot option exists |

---

## Appendix B: Quick Reference - Decision Flow

```
START
  │
  ├─ Collect: instance state, usage, prices
  ├─ Predict: 1h ahead prices for all pools
  ├─ Classify: usage (over/right/under-provisioned)
  │
  ├─ Is current pool predicted OK?
  │  ├─ YES → STAY
  │  └─ NO  → Find candidates
  │           │
  │           ├─ Filter by current price
  │           ├─ Filter by usage rules (right-sizing)
  │           ├─ Filter by future improvement
  │           │
  │           ├─ Any qualified candidates?
  │           │  ├─ YES → SWITCH to best
  │           │  └─ NO  → Under-provisioned?
  │           │           ├─ YES → FALLBACK to on-demand
  │           │           └─ NO  → STAY
  │
END
```

---

**End of Master Session Memory**
