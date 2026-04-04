# Spot Optimizer — Calculations & KPI Logic Reference

> **Purpose**: Single source of truth for every formula, score, threshold, and mathematical operation in the platform.
> All line numbers reference the current codebase state.

---

## Table of Contents

1. [ML Scoring Pipeline](#1-ml-scoring-pipeline)
2. [Expected Value (EV) Model](#2-expected-value-ev-model)
3. [Combined EV — Pool + Size Optimization](#3-combined-ev--pool--size-optimization)
4. [Decision Engine — Optimization Profiles](#4-decision-engine--optimization-profiles)
5. [Decision Engine — Candidate Scoring](#5-decision-engine--candidate-scoring)
6. [Pool Reputation System](#6-pool-reputation-system)
7. [Interruption History EMA](#7-interruption-history-ema)
8. [Circuit Breaker State Machine](#8-circuit-breaker-state-machine)
9. [Pool Rotation Thresholds](#9-pool-rotation-thresholds)
10. [Right-Sizing Bin-Pack Engine](#10-right-sizing-bin-pack-engine)
11. [Savings Calculator](#11-savings-calculator)
12. [ML Feature Engineering (45 Features)](#12-ml-feature-engineering-45-features)
13. [Cluster Metrics & Utilization KPIs](#13-cluster-metrics--utilization-kpis)
14. [Pricing & Cache Key Contracts](#14-pricing--cache-key-contracts)
15. [Capacity Failure Probability](#15-capacity-failure-probability)

---

## 1. ML Scoring Pipeline

**File**: `backend/services/pool_ranking_service.py`

### 1.1 ONNX Model Inference

Two ONNX models run on a 45-feature vector per pool:

```python
# Classifier (risk) — outputs interruption probability
risk_probability = float(classifier_session.run(None, {"input": features})[0][0][0])
risk_probability = max(0.0, min(1.0, risk_probability))          # clamp to [0,1]

# Regressor (savings) — outputs predicted % savings
predicted_savings = float(regressor_session.run(None, {"input": features})[0][0][0])
predicted_savings = max(0.0, min(1.0, predicted_savings))         # clamp to [0,1]
```

- Models: `ml_model/model/classifier_6.onnx` and `ml_model/model/regressor_6.onnx`
- Risk threshold (F1-optimized): `0.35` — pools with `risk_probability > 0.50` are hard-filtered out

### 1.2 Spot Advisor Override (Saturation Guard)

When the regressor saturates (outputs ≥ 0.99):

```python
if predicted_savings >= 0.99:
    sa_savings = sa_savings_map.get(pool.instance_type)
    if sa_savings and sa_savings > 0:
        predicted_savings = max(0.30, min(0.95, sa_savings / 100.0))
    elif pool.ondemand_price > 0:
        price_headroom = (pool.ondemand_price - pool.spot_price) / pool.ondemand_price
        predicted_savings = max(0.0, min(0.95, price_headroom))
```

Bounds: `[0.30, 0.95]` from Spot Advisor data; prevents overconfident predictions.

### 1.3 Differentiated Risk Blend (50/50)

```python
sa_risk = pool.spot_advisor_rank / 5.0   # rank 0 → 0.0 (safe), rank 4 → 0.8 (risky)
risk_probability = min(1.0, 0.5 * onnx_risk + 0.5 * sa_risk)
```

Blends two independent signals:
- **ONNX classifier**: learned from historical interruption events
- **Spot Advisor rank**: AWS published interruption frequency index (0–4)

### 1.4 Blacklist Penalty

```python
if is_flagged:
    effective_savings = max(0.0, predicted_savings - 0.20)   # -20% savings penalty
else:
    effective_savings = predicted_savings
```

### 1.5 ML Score Tiering by Instance Family

```python
if family in tier1:
    # Tier 1: Direct ONNX inference (full confidence)
    score = min(1.0, max(0.0, raw_score))

elif family in tier2:
    # Tier 2: Proxy family with penalty (partial confidence)
    penalty = tier2[family].get('penalty', 0.90)        # default 10% penalty
    score = min(1.0, max(0.0, proxy_score * penalty))

else:
    # Tier 3: Size-class average with 25% penalty (low confidence)
    score = min(1.0, max(0.0, size_class_avg * 0.75))
```

### 1.6 Composite Score (Ranking Sort Key)

```python
# Used only for pool ranking sort order (not execution decisions)
final_score = effective_savings * (1.0 - risk_probability)   # EV = savings × (1 - risk)

# Reputation multiplier applied after
rep_mult = reputation_multiplier(pool)                        # range: 0.5 – 1.2
final_score = final_score * rep_mult
final_score = max(0.1, min(10.0, final_score))               # clamped

# Multi-level sort
sort_key = (final_score, predicted_savings, -spot_price)
```

### 1.7 Spot Advisor Progressive Filtering (5-Pass Pipeline)

Before ML scoring, pools pass through progressive relaxation:

| Pass | Max Rank | Interruption Rate |
|------|----------|-------------------|
| 0    | 0        | < 5%              |
| 1    | ≤ 1      | ≤ 10%             |
| 2    | ≤ 2      | ≤ 15%             |
| 3    | ≤ 3      | ≤ 20%             |
| 4    | ≤ 4      | ≤ 25%             |

Pass 0 is tried first; if < 10 pools survive, the next pass runs.

### 1.8 Fallback Scoring (When ONNX Unavailable)

```python
headroom = (pool.ondemand_price - pool.spot_price) / pool.ondemand_price
predicted_savings = headroom
risk_probability = pool.spot_advisor_rank / 5.0 if pool.spot_advisor_rank <= 5 else 0.5
final_score = predicted_savings * (1.0 - risk_probability)
```

### 1.9 Price Fallback Estimation

```python
if spot_price <= 0.0:
    pool.spot_price = pool.ondemand_price * 0.30   # assume 70% savings
if pool.spot_price >= pool.ondemand_price:
    pool.spot_price = pool.ondemand_price * 0.70   # sanity cap
```

---

## 2. Expected Value (EV) Model

**File**: `backend/core/ev_model.py`

This is the **authoritative EV calculation** used for execution decisions (eligibility gate). The simple formula `savings × (1 - risk)` is deprecated and used only for ranking sort order.

### 2.1 Full EV Formula

```
EV = Savings
     - ExpectedInterruptionCost
     - MigrationPenalty
     - CapacityFailureRisk
     - (NormalizedVolatility × VolatilityCostMultiplier)
```

**Decision rule**: `EV > 0` AND all guardrails pass → candidate is eligible.

### 2.2 Step-by-Step Breakdown

#### Step 1: Effective Exposure Hours
```python
EffectiveExposureHours = min(RiskHorizonHours, RecoveryTimeHours)
# Default: min(2.0, 0.5) = 0.5 hours
```
Caps the cost window to actual recovery capability.

#### Step 2: Expected Interruption Cost
```python
ExpectedInterruptionCost = FinalRisk × DowntimeCostPerHour × EffectiveExposureHours
# Default: risk × 100.0 × 0.5
```

#### Step 3: Capacity Failure Risk
```python
CapacityFailureRisk = CapacityFailureProbability × RetryCost
# Default: 0.05 × 10.0 = 0.50
```
Capacity failure probability is dynamic (see §15).

#### Step 4: Migration Penalty
```python
MigrationPenalty = DrainTimeCost + WarmupCost + ControlPlaneCost
# Default: 2.0 + 1.0 + 0.5 = 3.5
```

#### Step 5: Volatility Cost
```python
VolatilityCost = NormalizedVolatility × VolatilityCostMultiplier
# Default multiplier: 5.0
```

### 2.3 Default Parameter Values

| Parameter | Default | Unit |
|-----------|---------|------|
| `risk_horizon_hours` | 2.0 | hours |
| `recovery_time_hours` | 0.5 | hours |
| `downtime_cost_per_hour` | 100.0 | USD/hr |
| `retry_cost` | 10.0 | USD |
| `capacity_failure_probability` | 0.05 | ratio |
| `drain_time_cost` | 2.0 | USD |
| `warmup_cost` | 1.0 | USD |
| `control_plane_cost` | 0.5 | USD |
| `volatility_cost_multiplier` | 5.0 | multiplier |

### 2.4 Full Pipeline (evaluate_candidate_ev)

```python
exposure_hours = min(risk_horizon_hours, recovery_time_hours)
interruption_cost = final_risk × downtime_cost_per_hour × exposure_hours
capacity_risk = capacity_failure_probability × retry_cost
migration = drain_time_cost + warmup_cost + control_plane_cost
volatility_cost = normalized_volatility × volatility_cost_multiplier

ev = savings - interruption_cost - migration - capacity_risk - volatility_cost

return {
    "ev": ev,
    "is_eligible": ev > 0,
    # ... full breakdown
}
```

---

## 3. Combined EV — Pool + Size Optimization

**File**: `backend/core/scoring.py` (`compute_combined_expected_value`)

Compares three options when both pool switching and right-sizing are possible:

| Option | Description |
|--------|-------------|
| A | Current size + switch to new pool |
| B | New size + best pool for new size |
| C | Do nothing (baseline, EV = 0) |

```python
# Option A
option_a_savings = baseline_cost - new_pool_cost
option_a_ev = (option_a_savings × (1 - new_pool_risk)) × (1 - volatility_penalty)

# Option B
migration_cost_amortized = migration_cost / 720.0   # amortized over 1 month (720 hrs)
option_b_savings = baseline_cost - new_pool_cost
option_b_ev = ((option_b_savings - migration_cost_amortized) × (1 - new_pool_risk)) × (1 - volatility_penalty)

# Best option wins
ev_delta_pct = (best_ev / baseline_cost) × 100
sufficient_improvement = ev_delta_pct >= 10.0       # 10% threshold
```

---

## 4. Decision Engine — Optimization Profiles

**File**: `backend/core/decision_engine.py` (lines 56–84)

Three optimization profiles with different risk/savings trade-offs:

| Parameter | COST_FIRST | BALANCED | NO_DOWNTIME_FIRST |
|-----------|-----------|----------|-------------------|
| `risk_ceiling` | 0.25 (25%) | 0.20 (20%) | 0.10 (10%) |
| `delta_threshold` | 0.02 (2%) | 0.03 (3%) | 0.04 (4%) |
| `max_family_ratio` | 0.40 (40%) | 0.40 (40%) | 0.30 (30%) |
| `max_az_ratio` | 0.50 (50%) | 0.50 (50%) | 0.40 (40%) |
| `capacity_freshness_min` | 80 min | 80 min | 80 min |
| `staleness_penalty` | 0.95 | 0.95 | 0.95 |
| `volatility_ceiling_adjustment` | −0.05 | −0.05 | −0.05 |

### Profile Scoring Weights

```python
_PROFILE_WEIGHTS = {
    'COST_FIRST':    {'savings': 0.60, 'risk': 0.20, 'ml': 0.20},
    'BALANCED':      {'savings': 0.40, 'risk': 0.40, 'ml': 0.20},
    'NO_DOWNTIME':   {'savings': 0.20, 'risk': 0.60, 'ml': 0.20},
}
```

### Three-Layer Risk Ceiling

```python
# Layer 1: Profile ceiling (base)
risk_ceiling = profile["risk_ceiling"]

# Layer 2: Volatility regime adjustment
if is_volatile_regime(region):
    risk_ceiling += profile["volatility_ceiling_adjustment"]   # -0.05

# Layer 3: Trust-phase override (most restrictive wins)
trust_ceiling = coordinator.get_cluster_trust_phase(cluster_id)["risk_ceiling_override"]
if trust_ceiling is not None:
    risk_ceiling = min(risk_ceiling, trust_ceiling)
```

### Capacity Staleness Penalty

```python
if capacity_age_minutes > 80:
    pool["predicted_savings"] = original_savings × 0.95   # 5% penalty for stale data
```

### Delta Threshold Gate

```python
delta = best_candidate_ev - current_pool_ev
if delta < profile["delta_threshold"]:
    return {"approved": False, "reason": "insufficient_improvement"}
```

Prevents unnecessary churn when the best candidate is only marginally better.

---

## 5. Decision Engine — Candidate Scoring

**File**: `backend/core/decision_engine.py` (lines 1318–1424)

Full weighted scoring formula used to rank candidates within a profile.

### Score Components

```python
# Savings score: normalize to 70% as "perfect" savings
savings_score = max(0.0, min((od_price - spot_price) / od_price / 0.70, 1.0))

# Safety score: normalize AWS interruption rate (25% = worst)
safety_score = max(0.0, 1.0 - (az_interruption_rate / 25.0))

# ML score: ONNX tier score (already normalized)
ml_score = min(1.0, max(0.0, ml_raw))
```

### Modifiers

```python
# Soft penalty for recent failures
soft_penalty = 0.85 if recent_failures > 0 else 1.0

# Capacity dry-run boost/block
capacity_boost = 1.05 if dry_run_passed else (0.0 if dry_run_failed else 1.0)

# Reputation multiplier (from pool history)
reputation_mult = max(0.5, min(1.2, pool_reputation_mult))   # range: 0.5–1.2

# Portfolio concentration penalty (penalizes over-concentration)
concentration = pool_node_count / total_nodes
if concentration > 0.40:   # max_single_pool_pct
    portfolio_penalty = min((concentration - 0.40) × 2.0, 0.80)
else:
    portfolio_penalty = 0.0

# Momentum bonus/penalty based on recent stability
if avg_uptime > 168:    # 7 days
    momentum_bonus = +0.05
elif avg_uptime > 72:   # 3 days
    momentum_bonus = +0.02
elif avg_uptime < 2:    # interrupted within 2 hours
    momentum_bonus = -0.10
else:
    momentum_bonus = 0.0
```

### Final Assembly

```python
W_s = weights['savings']   # profile-dependent (0.20–0.60)
W_r = weights['risk']      # profile-dependent (0.20–0.60)
W_ml = weights['ml']       # always 0.20

raw_score = (W_s × savings_score) + (W_r × safety_score) + (W_ml × ml_score)
final_score = (
    raw_score
    × soft_penalty
    × reputation_mult
    × capacity_boost
    × (1.0 - portfolio_penalty)
    + momentum_bonus
)
final_score = max(0.0, final_score)
```

### Double Gate Filter (Price + Risk)

```python
# Primary: candidate must be cheaper AND safer
candidates = [p for p in pools
              if p['spot_price'] < current_price
              and p['risk_tier'] <= current_risk_tier]

# Trade-off relaxation: allow up to N% more expensive if significantly safer
max_price = current_price × (1 + trade_off_pct / 100.0)
relaxed = [p for p in pools
           if p['spot_price'] <= max_price
           and p['risk_tier'] < current_risk_tier]
```

### AZ-Level Interruption Estimation (3-Layer)

```python
# Layer 1: Region-level base rate from Spot Advisor index
_idx_to_pct = {0: 5.0, 1: 10.0, 2: 15.0, 3: 20.0, 4: 25.0}
region_rate = _idx_to_pct.get(spot_advisor_idx, 25.0)

# Layer 2: AZ price adjustment
if price_ratio > 1.20:     az_adjustment = +1.0   # elevated demand
elif price_ratio > 1.10:   az_adjustment = +0.5

# Layer 3: Historical EMA weighting (max 50% weight)
history_weight = min(event_count / 100.0, 0.5)
aws_weight = 1.0 - history_weight
combined = (region_rate + az_adjustment) × aws_weight + own_rate × history_weight
return min(combined, 25.0)   # capped at 25%
```

---

## 6. Pool Reputation System

**File**: `backend/core/decision_engine.py` (lines 2263–2304)

Tracks historical success/failure per (instance_type, AZ) pair.

```python
successes = rep.get("successes", 0)
attempts  = rep.get("attempts", 1)
rate = successes / max(attempts, 1)

# Reputation multiplier formula
rep_mult = 0.5 + (rate × 0.7)
# rate=0.0  → mult=0.50  (terrible — penalizes by 50%)
# rate=0.43 → mult=0.80  (below average)
# rate=0.71 → mult=1.00  (neutral)
# rate=1.0  → mult=1.20  (excellent — boosts by 20%)

# Stability momentum adjustment
if avg_uptime > 168:    rep_mult = min(1.2, rep_mult + 0.05)   # 7+ days stable
elif avg_uptime < 2:    rep_mult = max(0.5, rep_mult - 0.10)   # very recent interruption
```

---

## 7. Interruption History EMA

**File**: `backend/core/decision_engine.py` (lines 2157–2164)

Each confirmed interruption event updates the AZ's historical rate using EMA:

```python
history["count"] += 1
history["rate"] = history["rate"] × 0.9 + 25.0 × 0.1
# EMA formula: pulls rate toward 25% (max tier) on each interruption
# α = 0.1 (slow decay — stable historical signal)
# After N events: rate approaches 25% asymptotically
```

TTL: 7 days (`86400 × 7` seconds).

---

## 8. Circuit Breaker State Machine

**File**: `backend/services/circuit_breaker.py`

### State Thresholds

| Constant | Value | Meaning |
|----------|-------|---------|
| `ROLLBACK_WINDOW_SECONDS` | 3600 | 1-hour rolling window for counting rollbacks |
| `NORMAL_TO_CONSERVATIVE_COUNT` | 2 | 2 rollbacks → CONSERVATIVE |
| `CONSERVATIVE_TO_HALT_COUNT` | 3 | 3 rollbacks → HALT |
| `HALT_STABLE_SECONDS` | 1800 | 30 min stable → exits HALT |
| `CONSERVATIVE_DECAY_SECONDS` | 7200 | 2 hr stable → exits CONSERVATIVE |

### State Transitions

```
NORMAL
  → CONSERVATIVE : rollback_count >= 2 in last 1 hour

CONSERVATIVE
  → HALT         : rollback_count >= 3 in last 1 hour
  → NORMAL       : minutes_in_state >= 120 AND minutes_since_failure >= 30

HALT
  → CONSERVATIVE : minutes_since_failure >= 30
```

### Risk Multiplier Formula

Applied to risk ceiling when circuit breaker is active:

```python
def risk_multiplier(state, minutes_in_conservative):
    if state == "HALT":
        return 2.0                                         # hard block
    if state == "CONSERVATIVE":
        return 1.3 × exp(-minutes_in_conservative / 120.0)
        # t=0:    1.30  (just entered conservative)
        # t=60:   0.78  (1 hour in conservative)
        # t=120:  0.47  (2 hours — ready to exit)
    return 1.0                                             # NORMAL — no penalty
```

---

## 9. Pool Rotation Thresholds

**File**: `backend/services/pool_rotation_service.py`

### Core Thresholds

| Constant | Value | Unit | Meaning |
|----------|-------|------|---------|
| `ROTATION_CHECK_INTERVAL` | 300 | seconds | Check frequency |
| `FRESH_POOL_CACHE_TTL` | 900 | seconds | Cache validity |
| `MIN_VIABLE_POOLS_DEFAULT` | 10 | count | Minimum healthy pools |
| `CASCADE_THRESHOLD_DEFAULT` | 0.70 | ratio | Cascade trigger threshold |
| `max_risk_threshold` | 0.50 | ratio | Max interruption risk |
| `max_interruption_rate` | 15 | % | Max interruption rate |
| `min_ml_score` | 0.30 | ratio | Minimum ML score to be viable |
| `blacklist_penalty_pct` | 20.0 | % | Savings penalty for flagged pools |
| `max_az_concentration` | 50 | % | Max nodes in a single AZ |
| `max_family_concentration` | 40 | % | Max nodes in a single instance family |
| `backup_az_count` | 2 | count | Number of backup AZs maintained |

### Key Formulas

**Blacklist Ratio**:
```python
blacklist_ratio = blacklisted_count / total_pools if total_pools > 0 else 0.0
```

**Cascade Risk Detection**:
```python
cascade_threshold = cascade_threshold_pct / 100.0   # e.g., 70.0 / 100.0 = 0.70
cascade_risk = blacklist_ratio > cascade_threshold
# Triggers 30-minute cascade dampener when > 70% of pools are blacklisted
```

**Primary AZ Viable Ratio**:
```python
primary_viable_ratio = viable_in_primary_az / total_in_primary_az
# Triggers rotation if ratio < 0.30 (< 30% viable in primary AZ)
```

**Pool Viability**:
```python
viable_in_az = max(0, estimated_pools_per_az - blacklisted_in_az)
# Assumed: 15 instance types per AZ
```

---

## 10. Right-Sizing Bin-Pack Engine

**File**: `backend/api/karpenter_routes.py` (lines 850–1100)

### Instance Spec Table (Sample — ap-south-1 calibrated)

```
instance_type    vCPU   Memory(GB)   OD Price ($/hr)
t3.medium         2       4.0         0.0464
m5.large          2       8.0         0.0960
m5.xlarge         4      16.0         0.1920
m5.2xlarge        8      32.0         0.3840
c5.large          2       4.0         0.0850
c5.xlarge         4       8.0         0.1700
c5.2xlarge        8      16.0         0.3400
r5.large          2      16.0         0.1260
r5.xlarge         4      32.0         0.2520
r5.2xlarge        8      64.0         0.5040
```

### Buffer-Padded Requirements

```python
buffer_pct = 30.0   # 30% overhead buffer (default)
buf = 1.0 + buffer_pct / 100.0   # = 1.3

required_vcpu = max(0.25, (current_vcpu × cpu_util_pct / 100.0) × buf)
required_mem  = max(0.50, (current_mem_gb × mem_util_pct / 100.0) × buf)
```

**Example**: m5.large (2 vCPU, 8 GB) at 50% CPU, 60% memory, 30% buffer:
- `required_vcpu = max(0.25, (2 × 0.50) × 1.3) = 1.30 vCPU`
- `required_mem  = max(0.50, (8 × 0.60) × 1.3) = 6.24 GB`
- Recommendation: t3.medium (2 vCPU, 4 GB, $0.0464/hr) ← cheapest that fits

### Delta (Monthly Savings)

```python
delta_monthly_usd = round((current_hourly - recommended_hourly) × 730, 2)
# Positive = savings (downsize), Negative = cost increase (upsize), 0 = no change
# Example: m5.large ($0.096) → t3.medium ($0.0464): delta = $36.18/month
```

### Monthly Cost Calculations

```python
monthly_od     = round(hourly_od × 730, 2)
monthly_spot   = round(hourly_od × 730 × 0.30, 2)   # spot ≈ 30% of OD
monthly_rec_od = round(hourly_rec × 730, 2)
monthly_rec_spot = round(hourly_rec × 730 × 0.30, 2)
```

### Potential Savings Calculation

```python
# Case 1: Stateless node with known spot pool
target_hourly = spot_pool["spot_price_hourly"]
potential_savings = max(0.0, (hourly_od - target_hourly) × 730 + resize_savings)
savings_pct = round(potential_savings / monthly_od × 100)

# Case 2: Stateless node without spot pool data
potential_savings = max(resize_savings, round(monthly_od × 0.70, 2))   # fallback: 70% savings
savings_pct = 70
```

### EV Score (Simplified for Right-Sizing)

```python
ev_pct = min(99, savings_pct) if savings_pct > 0 else 0
# Caps at 99%, defaults to 0 if no savings
```

### Impact Classification

```python
if is_upsize:
    impact = "Critical"   # over-utilized node
elif resize_savings > 10:
    impact = "High"       # > $10/month savings opportunity
else:
    impact = "Neutral"
```

### Spot Risk Probability (Right-Sizing View)

```python
risk_prob = round((spot_pool["risk_score"] if spot_pool else 0.15) × 100)
# spot_pool present: use pool's ML risk score (0–100%)
# spot_pool absent: default 15% interruption probability
```

---

## 11. Savings Calculator

**File**: `backend/workers/tasks/savings_calculator.py`

### Constants

| Constant | Value | Meaning |
|----------|-------|---------|
| `HOURS_PER_MONTH` | 730 | 365 ÷ 12 × 24 |

### Realized Savings Per Node

```python
# Per spot instance
current_spot_price = get_spot_price(region, instance_type, az)
source_od_price = action.source_od_price_hr or get_ec2_price(region, instance_type)
live_savings_hr = max(0.0, source_od_price - current_spot_price)
realized_savings += live_savings_hr × 730   # per month
```

### Baseline-Anchored Total

```python
baseline_monthly_cost = baseline_od_price_hr × node_count × 730
current_monthly_spot_cost = sum(spot_price × 730 for each spot instance)

if baseline_monthly_cost > 0 and current_monthly_spot_cost > 0:
    total_live_savings = max(0.0, baseline_monthly_cost - current_monthly_spot_cost)
    # Use the LARGER of node-level sum or baseline-anchored total
    realized_savings = max(realized_savings, total_live_savings)
```

### Potential Savings (On-Demand Instances)

```python
for od_instance in on_demand_instances:
    od_price = float(od_instance.price or get_ec2_price(region, type))
    spot_price = get_spot_price(region, type, az) or 0.0
    potential_savings += max(0.0, od_price - spot_price) × 730
```

---

## 12. ML Feature Engineering (45 Features)

**File**: `backend/services/ml_feature_service.py`

The 45-feature vector is assembled from 9 groups:

### Group 1: Temporal Features (10 features)

| # | Feature | Formula |
|---|---------|---------|
| 1 | hour | `timestamp.hour` (0–23) |
| 2 | day_of_week | `timestamp.weekday()` (0=Mon, 6=Sun) |
| 3 | day_of_month | `timestamp.day` (1–31) |
| 4 | month | `timestamp.month` (1–12) |
| 5 | is_weekend | `1.0 if weekday >= 5 else 0.0` |
| 6 | is_business_hours | `1.0 if 9 <= hour <= 17 else 0.0` |
| 7 | hour_sin | `sin(2π × hour / 24)` |
| 8 | hour_cos | `cos(2π × hour / 24)` |
| 9 | day_sin | `sin(2π × weekday / 7)` |
| 10 | day_cos | `cos(2π × weekday / 7)` |

Cyclical encoding prevents hour-23 → hour-0 discontinuity.

### Group 2: Lag Features (3 features)

Historical savings at past timepoints (10-minute interval data):

| # | Feature | Lookback |
|---|---------|----------|
| 11 | lag_1h | `history[-6]` (6 intervals × 10 min = 1 hour) |
| 12 | lag_4h | `history[-24]` (24 intervals = 4 hours) |
| 13 | lag_24h | `history[-144]` (144 intervals = 24 hours) |

Default (insufficient history): `[0.5, 0.5, 0.5]`

### Group 3: Rolling Window Features (8 features)

```python
recent_4h  = history[-24:]    # last 4 hours (24 × 10 min)
recent_24h = history[-144:]   # last 24 hours
```

| # | Feature | Window |
|---|---------|--------|
| 14 | mean_4h | `mean(recent_4h)` |
| 15 | std_4h | `std(recent_4h)` |
| 16 | min_4h | `min(recent_4h)` |
| 17 | max_4h | `max(recent_4h)` |
| 18 | mean_24h | `mean(recent_24h)` |
| 19 | std_24h | `std(recent_24h)` |
| 20 | min_24h | `min(recent_24h)` |
| 21 | max_24h | `max(recent_24h)` |

Default: `[0.5, 0.1, 0.3, 0.7, 0.5, 0.15, 0.2, 0.8]`

### Group 4: Price Dynamics Features (5 features)

```python
# Price velocity (1-hour change)
price_velocity = (price_history[-1] - price_history[-6]) / price_history[-6]

# Price volatility (6-hour std dev)
price_volatility = std(price_history[-36:])

# Headroom to on-demand
headroom = (ondemand_price - spot_price) / ondemand_price

# Pool saturation (position in price range)
min_price = min(price_history[-36:])
pool_saturation = (spot_price - min_price) / (ondemand_price - min_price)

# Consecutive stable hours (price change < 5%)
stable_hours = _calculate_consecutive_stable_hours(price_history)
```

| # | Feature | Default |
|---|---------|---------|
| 22 | price_velocity | 0.0 |
| 23 | price_volatility | 0.0 |
| 24 | headroom | 0.5 |
| 25 | pool_saturation | 0.5 |
| 26 | stable_hours | 0.0 |

### Group 5: Family-Time Pattern Features (6 features)

Pre-computed baselines per (instance_family, hour, day_of_week):

| # | Feature |
|---|---------|
| 27 | hour_avg_savings |
| 28 | hour_std_savings |
| 29 | dow_avg_savings |
| 30 | hour_deviation |
| 31 | hour_zscore |
| 32 | weekend_avg_savings |

Default: `[0.5, 0.1, 0.5, 0.0, 0.0, 0.5]`

### Group 6: Family Stress Features (3 features)

Cross-instance contagion detection (other instances in same family):

| # | Feature | Meaning |
|---|---------|---------|
| 33 | family_stress_1 | Fraction of family instances recently interrupted |
| 34 | family_stress_2 | Average price spike magnitude in family |
| 35 | family_stress_3 | Time since last family-wide interruption event |

### Group 7: Event Features (3 features)

| # | Feature | Meaning |
|---|---------|---------|
| 36 | event_1 | Recent AWS capacity event in region |
| 37 | event_2 | Recent pricing anomaly flag |
| 38 | event_3 | Recent demand spike indicator |

### Group 8: Pool Risk Feature (1 feature)

| # | Feature | Source |
|---|---------|--------|
| 39 | pool_risk | Spot Advisor rank / 5.0 (0.0 = safe, 0.8 = risky) |

### Group 9: Categorical Encodings (6 features)

| # | Feature | Encoding |
|---|---------|---------|
| 40 | instance_family_enc | Tier-based lookup (category_mapping.json) |
| 41 | instance_size_enc | Size class encoding |
| 42 | az_enc | AZ index encoding |
| 43–45 | (padding) | 0.0 if fewer categories |

**Note**: `category_mapping.json` uses a tiered dict format. Tier 1 families have full ONNX coverage; Tier 2 use proxy families; Tier 3 use size-class averages (see §1.5).

### Minimum Viable Features (Fallback)

When full history unavailable, 15 features are computed + 30 zero-padded:
- Temporal features (10) + price dynamics (5)

---

## 13. Cluster Metrics & Utilization KPIs

**File**: `backend/routers/metrics.py`

### Instance-Level Utilization

```python
cpu_util_pct = round((cpu_use / cpu_cap) × 100, 2) if cpu_cap > 0 else 0
mem_util_pct = round((mem_use / mem_cap) × 100, 2) if mem_cap > 0 else 0
# Input units: CPU in millicores, Memory in bytes
```

### Pod-Level Utilization (vs. Requests)

```python
cpu_util_pct = (cpu_use / cpu_req × 100) if cpu_req else None
mem_util_pct = (mem_use / mem_req × 100) if mem_req else None
# Measured against REQUESTED resources, not node capacity
```

### Cluster Capacity Aggregation

**Method 1** (preferred — from instance type map):
```python
total_vcpu_cores = sum(_VCPU_MAP.get(inst.instance_type, 2) for inst in instances)
total_mem_gb     = sum(_MEM_MAP.get(inst.instance_type, 4) for inst in instances)
```

**Method 2** (fallback — from raw metrics):
```python
total_vcpu_cores = int(total_cpu_capacity_millicores / 1000)
total_mem_gb     = int(total_mem_capacity_bytes / (1024**3))
```

### Cluster Utilization Percentage

```python
used_cores = sum(
    _VCPU_MAP.get(inst.instance_type, 2) × (inst.cpu_util or 0) / 100
    for inst in instances
)
cluster_cpu_util_pct = round((used_cores / total_vcpu_cores) × 100, 2)

used_gb = sum(
    _MEM_MAP.get(inst.instance_type, 4) × (inst.memory_util or 0) / 100
    for inst in instances
)
cluster_mem_util_pct = round((used_gb / total_mem_gb) × 100, 2)
```

### Metrics Cache TTLs

| Cache Key | TTL |
|-----------|-----|
| `metrics:node:{cluster_id}:{node_name}` | 300 s (5 min) |
| `metrics:cluster:{cluster_id}:summary` | 60 s (1 min) |

---

## 14. Pricing & Cache Key Contracts

**File**: `backend/services/aws_pricing_service.py`

### Freshness Thresholds

| Constant | Value | Meaning |
|----------|-------|---------|
| `FRESHNESS_THRESHOLD_MINUTES` | 15 | Max pricing age before blocking optimizations |
| `SPOT_PRICING_TTL_SECONDS` | 3600 | Spot price cache validity (1 hour) |
| `OD_PRICING_TTL_SECONDS` | 86400 | On-demand price cache validity (24 hours) |

### Spot Pricing Staleness Check

```python
age_minutes = (datetime.utcnow() - last_updated).total_seconds() / 60
if age_minutes > 15:
    raise PricingFreshnessException()   # blocks all new optimizations
```

### Coverage Percentage (Partial Staleness)

```python
coverage_pct = (_total_fetched / max(1, _total_requested × 2)) × 100
# ×2 because both spot AND OD prices needed per instance type
# If coverage_pct < 80% → sets spot:pricing:partial_stale:{cluster_id} (TTL 900s)
```

### AWS Spot Price History Fetch Window

```python
StartTime = datetime.now(timezone.utc) - timedelta(hours=2)
# Fetches most recent 2 hours of spot pricing data
```

### Redis Key Format Contracts

| Key | Value Format | TTL |
|-----|-------------|-----|
| `spot_price:{region}:{az}:{type}` | JSON `{"price": "0.026", "timestamp": "..."}` | 3600 s |
| `od_price:{region}:{type}` | plain string `"0.0464"` | 86400 s |
| `ondemand_price:{region}:{type}` | plain string `"0.0464"` | 86400 s |
| `spot_advisor:{region}:{type}:Linux` | JSON `{"interruption_index": 0-4, "savings_percentage": 0-90}` | — |
| `global_pool_rankings:{region}` | JSON array of ranked pools | 3900 s (65 min) |
| `market_view_cache:{region}` | JSON array of enriched pools | 3600 s |
| `ascpai:ml_fail_count` | integer | 600 s (10 min) |
| `ascpai:ml_degraded` | "1" | 600 s (10 min) |
| `cb:state:{cluster_id}` | circuit breaker state JSON | — |
| `cluster_cooldown:{cluster_id}` | "1" | varies |
| `spot:asserted_spot:{instance_id}` | "1" | 300 s |
| `spot:post_launch_cooldown:{ec2_id}` | "1" | 60 s |
| `spot:s2s_suppressed:{instance_id}` | "1" | 180 s |

---

## 15. Capacity Failure Probability

**File**: `backend/core/ev_model.py`

Dynamic capacity failure probability from live DryRun signals:

```python
failures = redis.get(f"spot:dryrun_failures_24h:{pool_id}")
attempts = redis.get(f"spot:dryrun_count:{region}")

probability = failures / attempts
capacity_failure_probability = min(probability, 0.50)   # never assume > 50% failure
# Fallback: 0.05 (5%) if no data available
```

Used as input to `CapacityFailureRisk = P_fail × retry_cost` in the full EV model.

---

## Quick Reference: Key Thresholds

| Threshold | Value | Where Used |
|-----------|-------|-----------|
| Hard risk filter | > 0.50 | ML scoring — reject any pool above this |
| F1-optimized threshold | 0.35 | Classifier decision boundary |
| Risk blend weight | 50/50 | ONNX vs Spot Advisor |
| Blacklist savings penalty | −20% | Flagged pool penalty |
| Staleness penalty | × 0.95 | Capacity > 80 min old |
| Momentum bonus (7d stable) | +0.05 | Scoring bonus |
| Momentum penalty (<2h uptime) | −0.10 | Scoring penalty |
| Portfolio penalty cap | 0.80 | Max concentration penalty |
| Delta threshold (BALANCED) | 3% | Minimum EV improvement to switch |
| Cascade threshold | 70% | Pool blacklist cascade trigger |
| Circuit breaker NORMAL→CONSERVATIVE | 2 rollbacks / 1h | |
| Circuit breaker CONSERVATIVE→HALT | 3 rollbacks / 1h | |
| Coverage threshold | 80% | Pricing partial staleness |
| Right-sizing buffer | 30% | Overhead padding |
| Monthly hours constant | 730 | Hours/month for cost projection |
| Savings normalizer | 70% | "Perfect savings" reference |
| AZ interruption normalizer | 25% | "Max interruption" reference |
