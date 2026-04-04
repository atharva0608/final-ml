# Right-Sizing Algorithm — Complete Technical Reference

> Covers: In-House vs Karpenter · Workload-Level vs Node-Level · Full Algorithm Logic · Backend Services · Redis Keys · Database Schema · Frontend UI · Accuracy Model · Execution Paths

---

## Table of Contents

1. [The Core Question: In-House or Karpenter?](#1-the-core-question-in-house-or-karpenter)
2. [Dual-Engine Architecture](#2-dual-engine-architecture)
3. [Engine 1 — Workload-Level (In-House Pod Analysis)](#3-engine-1--workload-level-in-house-pod-analysis)
4. [Engine 2 — Node-Level (Instance Bin-Packing via Karpenter)](#4-engine-2--node-level-instance-bin-packing-via-karpenter)
5. [Legacy Module (Superseded)](#5-legacy-module-superseded)
6. [Side-by-Side Algorithm Comparison](#6-side-by-side-algorithm-comparison)
7. [Which Engine Is More Accurate?](#7-which-engine-is-more-accurate)
8. [Execution Paths](#8-execution-paths)
9. [Resize Guard & Safety System](#9-resize-guard--safety-system)
10. [Database Models & Schema](#10-database-models--schema)
11. [Redis Keys Reference](#11-redis-keys-reference)
12. [API Endpoints](#12-api-endpoints)
13. [Frontend UI](#13-frontend-ui)
14. [Known Limitations](#14-known-limitations)
15. [End-to-End Flow Diagram](#15-end-to-end-flow-diagram)

---

## 1. The Core Question: In-House or Karpenter?

**Short answer: Both — but they operate at different levels with different purposes.**

| | In-House Engine | Karpenter Engine |
|---|---|---|
| **What it analyses** | Container resource requests vs actual pod CPU/memory usage | Node (instance) CPU% and memory% utilization |
| **What it recommends** | Change `requests` in Deployment/StatefulSet specs | Change EC2 instance type for the node |
| **Data window** | 7 days of pod metrics (configurable, 168h default) | Real-time snapshot from last agent report |
| **Statistical method** | P95 + P99 floor + dynamic safety buffer | Raw utilization % × 1.30 buffer |
| **Karpenter required?** | NO — fully in-house, independent of Karpenter | YES — output feeds into Karpenter NodePool or node drain |
| **Execution target** | K8s `resources.requests` on controllers | EC2 instance type replacement |
| **Primary file** | `backend/services/rightsizing_service.py` | `backend/api/karpenter_routes.py` |

**They are complementary, not competing:**
- The in-house engine tells you what size workload a pod actually needs
- The Karpenter engine tells you what EC2 instance type should run those workloads
- Both are home-built algorithms — neither vendor's Karpenter autoscaler itself does the analysis

---

## 2. Dual-Engine Architecture

```
┌────────────────────────────────────────────────────────────────────┐
│                    Right-Sizing System                             │
│                                                                    │
│   ┌──────────────────────────┐   ┌──────────────────────────────┐ │
│   │  ENGINE 1 (In-House)     │   │  ENGINE 2 (Node-Level)       │ │
│   │  RightSizingService      │   │  karpenter_routes.py         │ │
│   │                          │   │                              │ │
│   │  Input: pod_metrics DB   │   │  Input: Instance.cpu_util,   │ │
│   │  (168h history)          │   │  memory_util (live)          │ │
│   │                          │   │                              │ │
│   │  P95 + safety buffer     │   │  util% × (1 + buffer)        │ │
│   │  + P99 floor             │   │  → find fitting instance     │ │
│   │                          │   │                              │ │
│   │  Output: Change pod      │   │  Output: Change EC2          │ │
│   │  resource requests       │   │  instance type               │ │
│   └──────────┬───────────────┘   └─────────────┬────────────────┘ │
│              │                                  │                  │
│              ▼                                  ▼                  │
│   RightsizingProposal (DB)          Karpenter NodePool PATCH       │
│   → OptimizerCoordinator            or CORDON→DRAIN→TERMINATE      │
└────────────────────────────────────────────────────────────────────┘
```

---

## 3. Engine 1 — Workload-Level (In-House Pod Analysis)

**File:** `backend/services/rightsizing_service.py` (975 lines)

This is a **fully custom-built statistical analysis engine**. It has no dependency on Karpenter and works on any Kubernetes cluster.

### 3.1 Entry Point: `generate_recommendations()`

```python
# Lines 68–264
def generate_recommendations(
    cluster_id: str,
    namespace: Optional[str] = None,
    analysis_window_hours: int = 168,   # 7-day default
    min_data_points: int = 100
) -> List[RightSizingRecommendation]
```

### 3.2 Step-by-Step Algorithm

#### Step 1 — Cluster Validation (lines 87–90)
Verify cluster exists in DB. Abort early if not found.

#### Step 2 — Instance-Aware Mode Check (lines 92–100)
```python
instance_aware = cluster.optimization_settings.instance_aware_rightsizing
# If True: before emitting a recommendation, verify a better spot pool actually exists
# If False: always emit recommendation regardless of spot availability
```

#### Step 3 — Metric Freshness Guard (lines 102–117)
```python
latest_metric = db.query(PodMetric)
    .filter(cluster_id=cluster_id)
    .order_by(timestamp.desc())
    .first()

metric_lag = utcnow() - latest_metric.timestamp
if metric_lag > timedelta(minutes=5):
    return []   # Stale agent data — refuse to recommend
```
**Why:** Stale data (e.g., agent disconnected) would produce dangerously wrong recommendations.

#### Step 4 — Cluster Cooldown Check (lines 119–124)
```python
can_proceed = CooldownController(redis).can_switch(cluster_id)
if not can_proceed:
    return []
```
Respects the same stabilization lock used by the auto-rebalancer. Prevents right-sizing mid-rebalance.

#### Step 5 — Node Classification Filter (lines 126–143)
```python
classification = redis.get(f"spot:node_classification:{cluster_id}")
# Filters to only STATELESS_ELIGIBLE nodes
# Stateful nodes → deferred to stateful path with approval gate
```

#### Step 6 — Controller Discovery (lines 150–151)
```python
controllers = _get_controllers(cluster_id, namespace, start_time, end_time)
# Returns list of (namespace, controller_kind, controller_name) tuples
# These are distinct workloads (Deployments, StatefulSets, DaemonSets, etc.)
```

#### Step 7 — Per-Controller Analysis Loop (lines 154–192)
For each controller, call `_analyze_controller()`. Filter out None returns (insufficient data).
If `instance_aware=True`, additionally call `_check_better_pool_exists()`.

---

### 3.3 Core Algorithm: `_analyze_controller()` (lines 305–481)

This is the statistical heart of Engine 1.

#### Step A — Fetch Pod Metrics from DB (lines 332–344)
```python
metrics = db.query(PodMetric).filter(
    PodMetric.cluster_id == cluster_id,
    PodMetric.namespace == namespace,
    PodMetric.controller_kind == controller_kind,
    PodMetric.controller_name == controller_name,
    PodMetric.timestamp >= start_time,
    PodMetric.timestamp <= end_time,
).order_by(PodMetric.timestamp).all()

if len(metrics) < min_data_points:
    return None   # Block low-sample recommendations
```

#### Step B — Statistical Calculation (lines 346–352)
```python
cpu_stats    = _calculate_statistics([m.cpu_usage_millicores for m in metrics])
memory_stats = _calculate_statistics([m.memory_usage_bytes for m in metrics])

# Returns dict: {avg, p50, p95, p99, min, max}
```

**Percentile formula (lines 484–506):**
```python
def _percentile(sorted_values, percentile):
    index = int((percentile / 100) * (len(sorted_values) - 1))
    index = min(index, len(sorted_values) - 1)
    return sorted_values[index]
```

#### Step C — Phase-Aware Safety Buffer (lines 360–370)
```python
safety_buffer = SAFETY_BUFFER_PCT   # Default: 20%

try:
    trust = OptimizerCoordinator.get_cluster_trust_phase(cluster_id)
    safety_buffer = trust["safety_buffer_pct"]
    # Phase 0 (new cluster) = 30%
    # Phase 1 (learning)    = 25%
    # Phase 2 (stable)      = 20%
except:
    pass   # Default used
```

**Trust phases** prevent aggressive right-sizing on clusters where the system hasn't observed enough history.

#### Step D — Volatility-Aware Buffer Override (lines 372–383)
```python
region = cluster.region
volatility_regime = redis.get(f"spot:volatility_regime:{region}")

if volatility_regime in (b"true", "active"):
    safety_buffer = max(safety_buffer, 35)
    # Volatile market → force 35% headroom minimum
    # Prevents OOM during spot price chaos / workload spikes
```

#### Step E — Recommendation Calculation (lines 385–396)

The **actual sizing formula:**
```python
# Base: P95 of observed usage + safety buffer
recommended_cpu_m    = int(cpu_stats['p95']    * (1 + safety_buffer / 100))
recommended_memory_b = int(memory_stats['p95'] * (1 + safety_buffer / 100))

# Floor: P99 × 1.30 — prevents OOM on burst traffic
p99_cpu_floor    = int(cpu_stats['p99'] * 1.30)
p99_memory_floor = int(memory_stats['p99'] * 1.30)

# Take the higher of P95+buffer or P99-floor
recommended_cpu_m    = max(recommended_cpu_m,    p99_cpu_floor)
recommended_memory_b = max(recommended_memory_b, p99_memory_floor)
```

**Example with real numbers:**
```
Pod observed CPU over 7 days:
  P50 = 180m, P95 = 420m, P99 = 690m
  Safety buffer = 25% (Phase 1 cluster)

P95 path:   420 × 1.25 = 525m
P99 floor:  690 × 1.30 = 897m
Final:      max(525, 897) = 897m   ← P99 floor wins
```

#### Step F — Replica Count (lines 398–404)
```python
replica_count = db.query(func.count(distinct(PodMetric.pod_name))).filter(
    cluster_id, namespace, controller_name,
    timestamp >= (end_time - timedelta(hours=1))
).scalar() or 1
```
Most recent 1-hour window for replica count — avoids using stale scaling state.

#### Step G — Cost Estimation (lines 406–420)
```python
current_cost    = _estimate_cost(current_cpu_m, current_mem_mb, replica_count)
recommended_cost = _estimate_cost(recommended_cpu_m, recommended_mem_mb, replica_count)

savings_monthly = max(0, current_cost - recommended_cost)   # floor at 0
savings_pct     = (savings_monthly / current_cost * 100) if current_cost > 0 else 0
```

#### Step H — Sizing Classification (lines 422–441)
```python
cpu_usage_pct = (cpu_stats['avg'] / current_cpu_request) * 100

OVERSIZED_THRESHOLD_PCT  = 50   # < 50% usage → REDUCE
UNDERSIZED_THRESHOLD_PCT = 95   # P99 > 95% of request → INCREASE

is_oversized  = cpu_usage_pct < OVERSIZED_THRESHOLD_PCT
is_undersized = cpu_stats['p99'] > current_cpu_request * (UNDERSIZED_THRESHOLD_PCT / 100)

if is_oversized:
    action = "REDUCE"
elif is_undersized:
    action = "INCREASE"
else:
    action = "NO_CHANGE"
```

#### Step I — Confidence Gate (lines 443–447)
```python
confidence = _calculate_confidence(len(metrics), analysis_window_hours, min_data_points)
if confidence == "LOW":
    return None   # Block low-confidence proposals entirely
```

**Confidence levels:**
| Level | Condition | Action |
|-------|-----------|--------|
| LOW | < 100 samples OR < 24hr window | Blocked — return None |
| MEDIUM | 100–500 samples AND 1–7 days | Allowed with note |
| HIGH | > 500 samples AND > 7 days | Full recommendation |

#### Step J — Volatility Gate (lines 449–454)
```python
cpu_volatility = (cpu_stats['p99'] - cpu_stats['p50']) / cpu_stats['p99']

if cpu_volatility > 0.95:
    return None   # Extreme spike workload — do not right-size
```

Only the most pathological spiky workloads are blocked (95th percentile = 20× median). Designed to skip batch jobs that are idle 99% of the time then burst massively.

---

### 3.4 Cost Estimation: `_estimate_cost()` (lines 527–614)

Engine 1 cannot directly look up instance pricing because it works at pod granularity (not instance level). It uses a **CPU + memory rate model**:

```python
# Convert to standard units
cpu_cores = cpu_millicores / 1000.0
memory_gb = memory_mb / 1024.0

# Detect workload family from CPU:memory ratio
ratio = cpu_cores / memory_gb if memory_gb > 0 else 0
if ratio >= 0.4:
    family = "c"   # Compute-optimised (e.g., c5, c6i)
elif ratio >= 0.2:
    family = "m"   # Balanced (e.g., m5, m6i)
else:
    family = "r"   # Memory-optimised (e.g., r5, r6i)

# Try Redis for live pricing
cpu_rate = redis.get(f"pricing:ec2:{family}:cpu_per_core_hour")
mem_rate = redis.get(f"pricing:ec2:{family}:mem_per_gb_hour")

# Hardcoded fallbacks (us-east-1 calibrated):
FALLBACK_RATES = {
    "c": (cpu=0.088, mem=0.024),
    "m": (cpu=0.082, mem=0.020),
    "r": (cpu=0.082, mem=0.024),
}

hourly_cost  = (cpu_cores * cpu_rate) + (memory_gb * mem_rate)
monthly_cost = hourly_cost * 730 * replica_count
```

---

### 3.5 Proposal Creation: `create_rightsizing_proposals()` (lines 636–830)

When the system creates formal proposals (deferred execution):

1. Call `generate_recommendations()` with stability window (default 24h)
2. Filter by minimum savings threshold (default 10% of monthly cost)
3. Load cluster `NodeTemplate` constraints
   - Reject proposals violating `allowed_families`, `allowed_zones`, vCPU/memory bounds
4. Validate spot pool availability (instance-aware path)
5. Create `RightsizingProposal` records with status=`PENDING`
6. `OptimizerCoordinator` evaluates three options:
   - **Option A:** Keep current size + move to new spot pool
   - **Option B:** Resize instance + move to best new pool
   - **Option C:** Do nothing
7. Selected option stored in proposal (`selected_option = "A" | "B" | "C"`)
8. Coordinator sets proposal status to `APPROVED` or `REJECTED`

---

## 4. Engine 2 — Node-Level (Instance Bin-Packing via Karpenter)

**File:** `backend/api/karpenter_routes.py` (1,473 lines)
**Core function:** `_bin_pack_instance()` (lines 73–121)

This is also a **fully in-house algorithm** — the name "Karpenter" refers to the fact that it feeds into Karpenter's NodePool CRD to provision differently-sized nodes, but the analysis logic itself is our own.

### 4.1 Instance Spec Catalogue (lines 30–55)

A hardcoded lookup table of 50+ instance types:

```python
INSTANCE_SPECS: Dict[str, Tuple[int, float, float]] = {
    # (vCPU, memory_gb, fallback_od_price_usd_per_hr)
    "t3.nano":      (2,   0.5,   0.0058),
    "t3.micro":     (2,   1.0,   0.0116),
    "t3.small":     (2,   2.0,   0.023),
    "t3.medium":    (2,   4.0,   0.0464),
    "t3.large":     (2,   8.0,   0.0928),
    "t3.xlarge":    (4,   16.0,  0.1664),
    "t3a.medium":   (2,   4.0,   0.0418),
    "m5.large":     (2,   8.0,   0.096),
    "m5.xlarge":    (4,   16.0,  0.192),
    "m5.2xlarge":   (8,   32.0,  0.384),
    "c5.large":     (2,   4.0,   0.085),
    "c5.xlarge":    (4,   8.0,   0.17),
    "c6i.large":    (2,   4.0,   0.085),
    "c6i.xlarge":   (4,   8.0,   0.17),
    "c7g.medium":   (2,   4.0,   0.0363),   # ARM/Graviton
    "r5.large":     (2,   16.0,  0.126),
    # ... 40+ more types
}
```

**Prices** here are ap-south-1 fallback prices only. Live pricing is always read from Redis first.

### 4.2 Core Function: `_bin_pack_instance()` (lines 73–121)

```python
def _bin_pack_instance(
    current_type: str,          # "m5.xlarge"
    cpu_pct: float,             # 35.0   (actual utilization %)
    mem_pct: float,             # 40.0   (actual utilization %)
    buffer_pct: float = 30.0,   # Safety headroom
    region: str = None,
    redis_client = None
) -> Tuple[str, float]:         # (recommended_type, delta_monthly_usd)
```

**Full algorithm:**

```python
# 1. Lookup current type specs
specs = INSTANCE_SPECS.get(current_type)
if not specs or (cpu_pct <= 0 and mem_pct <= 0):
    return current_type, 0.0          # No data → no change

c_vcpu, c_mem, fallback_price = specs

# 2. Get live OD price from Redis
c_hourly = _get_od_price(current_type, region, redis_client) or fallback_price

# 3. Calculate buffered requirements
buf = 1.0 + (buffer_pct / 100.0)     # 1.30 for 30% buffer

required_vcpu = max(0.25, (c_vcpu * max(cpu_pct, 0) / 100.0) * buf)
required_mem  = max(0.5,  (c_mem  * max(mem_pct, 0) / 100.0) * buf)
# Floors: 0.25 vCPU and 0.5 GB minimum — prevents recommending nano instances

# 4. Does current type still fit the buffered requirements?
current_fits = (c_vcpu >= required_vcpu and c_mem >= required_mem)

# 5. Build priced candidate list
def _priced_candidates(price_filter_fn):
    result = []
    for t, (v, m, fh) in INSTANCE_SPECS.items():
        h = _get_od_price(t, region, redis_client) or fh
        if price_filter_fn(h):
            result.append((t, v, m, h))
    return sorted(result, key=lambda x: x[3])   # sort by hourly cost ASC

# 6. Select recommendation
if not current_fits:
    # OVER-UTILISED → find cheapest UPSIZE that fits
    for t_name, vcpu, mem, hourly in _priced_candidates(lambda h: h > c_hourly):
        if vcpu >= required_vcpu and mem >= required_mem:
            delta = round((c_hourly - hourly) * 730, 2)   # negative = cost increase
            return t_name, delta
    return current_type, 0.0    # No suitable upsize found

else:
    # UNDER-UTILISED → find cheapest DOWNSIZE that still fits
    for t_name, vcpu, mem, hourly in _priced_candidates(lambda h: h < c_hourly):
        if vcpu >= required_vcpu and mem >= required_mem:
            delta = round((c_hourly - hourly) * 730, 2)   # positive = savings
            return t_name, delta
    return current_type, 0.0    # Already optimal
```

### 4.3 Worked Example

```
Input: current_type="m5.xlarge", cpu_pct=35, mem_pct=40, buffer_pct=30

Specs:  m5.xlarge → (4 vCPU, 16 GB, $0.192/hr)
c_hourly = $0.192

required_vcpu = max(0.25, (4 × 0.35) × 1.30) = max(0.25, 1.82) = 1.82
required_mem  = max(0.50, (16 × 0.40) × 1.30) = max(0.50, 8.32) = 8.32

current_fits? 4 ≥ 1.82 ✓  AND  16 ≥ 8.32 ✓  → YES → DOWNSIZE path

Candidates cheaper than $0.192/hr, sorted by price:
  t3.medium  → 2 vCPU, 4 GB,  $0.046  → 2≥1.82 ✓  but 4≥8.32 ✗  SKIP
  c5.large   → 2 vCPU, 4 GB,  $0.085  → 2≥1.82 ✓  but 4≥8.32 ✗  SKIP
  m5.large   → 2 vCPU, 8 GB,  $0.096  → 2≥1.82 ✓  and 8≥8.32 ✗  SKIP (barely!)
  r5.large   → 2 vCPU, 16 GB, $0.126  → 2≥1.82 ✓  and 16≥8.32 ✓ MATCH!

Return: ("r5.large", round((0.192 - 0.126) × 730, 2)) = ("r5.large", $48.18/mo)
```

### 4.4 Price Lookup: `_get_od_price()` (lines 55–72)

```python
def _get_od_price(instance_type, region, redis_client):
    if not redis_client or not region:
        return None
    # Try primary key
    val = redis_client.get(f"ondemand_price:{region}:{instance_type}")
    if val:
        return float(val)
    # Try fallback key
    val = redis_client.get(f"od_price:{region}:{instance_type}")
    if val:
        return float(val)
    return None
```

### 4.5 Recommendations Endpoint (lines 766–1052)

`GET /api/v1/karpenter/recommendations?cluster_id=...&status_filter=...`

**Per-node processing:**

```
1. Query instances WHERE state='running' AND lifecycle='on_demand'
2. For each instance:
   a. Get cpu_utilization_pct, memory_utilization_pct from DB
   b. Call _bin_pack_instance(cpu_pct, mem_pct, buffer_pct=30)
   c. Validate against NodeTemplate.allowed_families (if template exists)
   d. If stateless: call PoolRankingService.rank_pools() for best spot pool
   e. Combine savings: resize_savings + spot_migration_savings
   f. Classify impact: "Critical" (>20%), "High" (>10%), "Neutral"

3. Return list sorted by potential_savings DESC
```

**Response shape per node:**
```python
{
    "id": "i-0abc123...",
    "instance_id": "i-0abc123...",
    "node_name": "ip-192-168-2-212",
    "current_type": "m5.xlarge",
    "recommended_type": "r5.large",
    "cpu": 35.0,
    "memory": 40.0,
    "current_cost_monthly": 140.16,
    "recommended_cost_monthly": 91.98,
    "potential_savings": 48.18,
    "savings_pct": 34.4,
    "is_upsize": False,
    "impact": "High",
    "node_type": "stateless",
    "spot_pool": {
        "instance_type": "r5.large",
        "az": "ap-south-1b",
        "spot_price": 0.031,
        "risk_probability": 0.06
    },
    "resize_savings": 48.18,
    "spot_savings": 67.52,
    "reason": "35% CPU, 40% memory — downsize from m5.xlarge to r5.large saves $48/mo"
}
```

### 4.6 Apply Recommendation (lines 1055–1259)

`POST /api/v1/karpenter/apply-recommendation/{recommendation_id}`

```python
payload = {
    "recommended_type": "r5.large",
    "reason": "User approved",
    "is_stateful": False,
    "instance_id": "i-0abc123",
    "spot_pool": {"instance_type": "r5.large", "az": "ap-south-1b"}
}
```

**Stateless path:**
1. Check `StatefulRules.require_approval` gate (should be False for stateless)
2. Call `KarpenterService.add_allowed_instance_type(cluster_id, new_type)`
3. Karpenter will naturally provision the new type and drain old node

**Stateful path:**
1. Check `StatefulRules.require_approval` (usually True — needs human sign-off)
2. If approved: queue agent actions:
   - `CORDON` → `DRAIN` → `TERMINATE` chain
   - `termination_mode = "replacement"` (ASG detach with `ShouldDecrementDesiredCapacity=False`)
   - New node auto-provisioned at correct instance type

---

## 5. Legacy Module (Superseded)

**File:** `backend/modules/rightsizer.py` (201 lines)

This was the original right-sizing module. It is **no longer used in production paths** — superseded by `RightSizingService` (Engine 1) and `karpenter_routes.py` (Engine 2).

**Legacy algorithm (simple threshold):**
```python
def analyze_resource_usage(instances):
    for instance in instances:
        if instance.cpu_util < 50 and instance.memory_util < 50:
            # Both below 50% → overprovisioned
            smaller_type = find_smaller_instance(instance.type)
            savings = (current_price - smaller_price) * 730
```

**Why replaced:** No statistical analysis, no safety buffer, no percentile calculation, no confidence gating, no stateful handling, no volatility awareness.

---

## 6. Side-by-Side Algorithm Comparison

| Dimension | Engine 1 (In-House / Pod-Level) | Engine 2 (Node-Level / Karpenter) |
|-----------|--------------------------------|----------------------------------|
| **Primary file** | `rightsizing_service.py` | `karpenter_routes.py` |
| **Input data** | `pod_metrics` table (CPU milli, mem bytes per pod) | `instances` table (`cpu_utilization_pct`, `memory_utilization_pct`) |
| **Time window** | 168 hours (7 days) default, configurable | Single latest snapshot from agent |
| **Statistical method** | P95 base + P99 floor + dynamic buffer | `utilization% × (1 + buffer_pct)` |
| **Safety buffer** | Phase-aware (20–30%) + volatility override (35%) | Fixed 30% |
| **Buffer source** | `OptimizerCoordinator.get_cluster_trust_phase()` | Hardcoded constant |
| **Volatility awareness** | YES — checks `spot:volatility_regime:{region}` Redis key | NO |
| **Minimum data gate** | YES — requires ≥ 100 samples | NO — any instance with util% data |
| **Freshness gate** | YES — metric lag > 5 min → abort | NO |
| **Confidence scoring** | YES — LOW/MEDIUM/HIGH, blocks LOW | NO |
| **Stateful detection** | YES — uses `WorkloadInspector` classification | YES — per `is_stateful` param |
| **Cost model** | CPU rate + memory rate per family (Redis → fallback) | Full instance OD price (Redis → hardcoded) |
| **Spot pool lookup** | Via `PoolRankingService.rank_pools_for_node()` | Via `PoolRankingService.rank_pools()` |
| **Output type** | `RightSizingRecommendation` → `RightsizingProposal` DB record | JSON response + optional NodePool patch |
| **Execution method** | `OptimizerCoordinator` → agent action queue | Direct Karpenter NodePool PATCH or drain chain |
| **Karpenter dependency** | None | Uses Karpenter for provisioning only |
| **Template enforcement** | YES — `NodeTemplate.allowed_families` checked | YES — validated against template |
| **Approval gate** | `StatefulRules.require_approval` | `StatefulRules.require_approval` |
| **Proposal storage** | `RightsizingProposal` DB table | Stateless: immediate; Stateful: action queued |

---

## 7. Which Engine Is More Accurate?

### Engine 1 (Pod-Level) Is More Accurate When:

**Reason 1 — Longer history:**
- Uses 7 days of pod metrics (10,000+ data points per workload)
- Engine 2 uses a single snapshot — one unlucky reading (GC pause, batch job) distorts the result

**Reason 2 — Statistical percentiles:**
- P95/P99 correctly handles workloads with predictable daily/weekly patterns
- Engine 2's raw `util%` value could be from any moment in the agent's polling cycle

**Reason 3 — Volatility awareness:**
- Engine 1 increases safety buffer to 35% during volatile spot markets
- Engine 2 always uses 30% — may under-provision during market stress

**Reason 4 — Confidence gating:**
- Engine 1 refuses to recommend with < 100 samples or < 24hr window
- Engine 2 will recommend based on 1 minute of data

**Best for:** Production workloads with consistent traffic patterns (web servers, APIs, microservices)

### Engine 2 (Node-Level) Is More Accurate When:

**Reason 1 — Instance-level granularity:**
- Knows the exact EC2 instance type and its real specs
- Engine 1 estimates instance type from CPU:memory ratio (may pick wrong family)

**Reason 2 — Live pricing:**
- Uses `ondemand_price:{region}:{type}` Redis key for exact current pricing
- Engine 1 estimates cost from per-core/per-GB rates (approximation)

**Reason 3 — Template constraint awareness:**
- Validates against `NodeTemplate.allowed_families` before recommending
- Engine 1 validates post-recommendation (may generate proposals that get rejected)

**Reason 4 — Spot pool integration:**
- Immediately calculates combined savings: resize savings + spot migration savings
- Engine 1 calculates them separately and combines later

**Best for:** Dev/test clusters with variable workloads, clusters where pod metrics aren't available, quick right-sizing passes

### Verdict

```
For most production clusters:     Engine 1 > Engine 2  (accuracy)
For clusters without pod metrics: Engine 2 only option
For immediate spot optimization:  Engine 2 faster to act
For stateful workloads:           Both engines — Engine 1 safer (more data)
Combined (both engines):          Best results — resize pods + change instance type
```

**Ideal flow:** Run Engine 1 to right-size pod requests → then run Engine 2 / bin-pack simulation to find the correct instance size for the right-sized pods.

---

## 8. Execution Paths

### Path A — Workload Level (Engine 1) → Coordinator → Agent

```
1. RightSizingService.generate_recommendations(cluster_id)
        ↓
2. Statistical analysis per controller (P95 + P99 + buffer)
        ↓
3. create_rightsizing_proposals() → RightsizingProposal (status=PENDING)
        ↓
4. OptimizerCoordinator evaluates options A/B/C (EV model)
        ↓ status → APPROVED / REJECTED
5. Approved proposals → Agent action queue
        ↓
6. Agent executes: updates K8s Deployment resource.requests
        ↓
7. Proposal status → EXECUTED
        ↓
8. Auto-rebalancer detects changed pod footprint → re-evaluates node sizing
```

### Path B — Node Level (Engine 2) → Karpenter → EC2

```
1. GET /karpenter/recommendations
        ↓
2. Per instance: _bin_pack_instance(cpu_pct, mem_pct)
        ↓
3. Validate against NodeTemplate + find spot pool
        ↓
4. Return recommendations to frontend
        ↓
5a. Stateless → POST /apply-recommendation
      └─→ KarpenterService.add_allowed_instance_type()
      └─→ Karpenter provisions new node, drains old one
        ↓
5b. Stateful → POST /apply-recommendation (with is_stateful=True)
      └─→ Approval gate check (StatefulRules.require_approval)
      └─→ Queue: CORDON → DRAIN → TERMINATE
      └─→ ASG provisions replacement at new instance type
```

### Path C — Auto-Rebalancer Integration (lines in auto_rebalancer.py)

```python
# Resize Guard — runs every check cycle
if cluster.optimization_settings.auto_rightsizing_enabled:
    # Check: spot:cooldown:action:resize:{cluster_id}
    # Check: CPU > 85% (pod restart spike guard)
    # Check: memory pressure events < 5
    # Check: Mode 3 synergy (both auto_rebalance + auto_rightsizing ON)
    if all guards pass:
        trigger RightSizingService.generate_recommendations()
```

The Resize Guard coordinates with the rebalancer to prevent:
- Right-sizing a node that is currently being drained
- Launching a resize action while stabilization lock is active
- Concurrent resize + rebalance on same node (per-node lock)

---

## 9. Resize Guard & Safety System

The right-sizer is protected by 5 guard conditions that run **before any resize action**:

### Guard 1 — Resize Cooldown Lock
```
Redis key: spot:cooldown:action:resize:{cluster_id}
TTL: configurable (default 30 min after any resize action)
Purpose: Prevents thrashing — wait for pods to stabilise after resize
```

### Guard 2 — CPU Spike Guard
```
Threshold: cpu_utilization > 85%
Source: Instance.cpu_utilization_pct from latest agent report
Purpose: Never resize during high-CPU events — wait for workload to settle
```

### Guard 3 — Pod Restart Guard
```
Threshold: pod_restart_count > 2 × baseline
Source: PodMetric restart counter vs rolling baseline
Purpose: Pod CrashLoopBackOff may inflate CPU/memory readings
```

### Guard 4 — Memory Pressure Guard
```
Threshold: memory_pressure_events > 5 in last hour
Source: node_conditions from agent
Purpose: Memory pressure means current size is ALREADY under-provisioned
         Right-sizing down would cause OOM kills
```

### Guard 5 — Mode 3 Synergy Guard
```
Condition: auto_rebalance_enabled AND auto_rightsizing_enabled
Effect: Optimization target locked to "spot"
Purpose: When both are on, rebalancer takes precedence for node movement
         Right-sizer only adjusts pod requests, not node types
```

---

## 10. Database Models & Schema

### `RightsizingProposal` model (`backend/models/rightsizing_proposal.py`)

```python
class ProposalStatus(enum.Enum):
    PENDING  = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    EXECUTED = "executed"
    FAILED   = "failed"

class RightsizingProposal(Base):
    __tablename__ = "rightsizing_proposals"

    id = Column(String, primary_key=True)        # "rsprop_{timestamp}"
    cluster_id = Column(String, ForeignKey("clusters.id"), index=True)

    # Current state
    current_instance_type = Column(String, nullable=False)
    current_vcpu          = Column(Integer)
    current_memory_gb     = Column(Float)
    current_pool          = Column(String)       # "m5.large:us-east-1a"
    current_hourly_cost   = Column(Float)

    # Proposed state
    proposed_instance_type = Column(String, nullable=False)
    proposed_vcpu          = Column(Integer)
    proposed_memory_gb     = Column(Float)
    proposed_hourly_cost   = Column(Float)

    # Savings
    estimated_hourly_savings  = Column(Float)
    estimated_monthly_savings = Column(Float)
    savings_percentage        = Column(Float)

    # Workload metrics used for decision
    avg_cpu_utilization_pct  = Column(Float)
    p95_cpu_utilization_pct  = Column(Float)
    avg_memory_utilization_pct = Column(Float)
    p95_memory_utilization_pct = Column(Float)
    metric_sample_count      = Column(Integer)
    metric_window_hours      = Column(Integer)

    # Status + approval
    status           = Column(Enum(ProposalStatus), default=ProposalStatus.PENDING)
    rejection_reason = Column(String)
    approved_by      = Column(String)
    approved_at      = Column(DateTime)

    # Coordinator output (3-option EV model)
    combined_ev_option_a = Column(Float)   # Current size + new pool
    combined_ev_option_b = Column(Float)   # New size + best pool
    combined_ev_option_c = Column(Float)   # Do nothing
    selected_option      = Column(String)  # "A" / "B" / "C"

    # Best pool info
    best_pool_for_new_size = Column(String)
    best_pool_hourly_cost  = Column(Float)
    best_pool_risk_score   = Column(Float)

    # EV breakdown
    ev_breakdown = Column(JSON)
    net_ev       = Column(Float)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, onupdate=datetime.utcnow)
```

### `PodMetric` model (source data)

| Column | Type | Purpose |
|--------|------|---------|
| `cluster_id` | String FK | Which cluster |
| `namespace` | String | K8s namespace |
| `pod_name` | String | Pod identifier |
| `controller_kind` | String | Deployment, StatefulSet, DaemonSet, etc. |
| `controller_name` | String | Parent controller name |
| `node_name` | String | Node the pod runs on |
| `cpu_usage_millicores` | BigInt | Actual CPU consumption |
| `memory_usage_bytes` | BigInt | Actual memory consumption |
| `cpu_request_millicores` | Int | Declared resource request |
| `memory_request_bytes` | BigInt | Declared memory request |
| `timestamp` | DateTime | When metric was collected |

### `Instance` model (Engine 2 source)

| Column | Type | Purpose |
|--------|------|---------|
| `instance_type` | String | EC2 type (e.g., m5.xlarge) |
| `lifecycle` | String | `spot` or `on_demand` |
| `az` | String | Availability zone |
| `cpu_utilization_pct` | Float | Live utilization from agent |
| `memory_utilization_pct` | Float | Live utilization from agent |
| `state` | String | `running`, `terminated`, etc. |
| `node_name` | String | K8s node hostname |

### `ClusterOptimizationSettings` (control flags)

| Column | Default | Purpose |
|--------|---------|---------|
| `auto_rightsizing_enabled` | False | Master switch for both engines |
| `auto_stateful_rightsizing_enabled` | False | Allow right-sizing stateful nodes |
| `instance_aware_rightsizing` | False | Only recommend if better spot pool also exists |

### `StatefulRules`

| Column | Default | Purpose |
|--------|---------|---------|
| `require_approval` | False | Human approval gate for stateful node resize |
| `max_downscale_percent` | 25 | Max resource reduction allowed per resize |

---

## 11. Redis Keys Reference

| Key | TTL | Value | Purpose |
|-----|-----|-------|---------|
| `spot:volatility_regime:{region}` | Variable | `"true"` / `"active"` | Increase Engine 1 safety buffer to 35% |
| `pricing:ec2:{family}:cpu_per_core_hour` | Variable | float string | Engine 1 cost estimation — CPU rate by family |
| `pricing:ec2:{family}:mem_per_gb_hour` | Variable | float string | Engine 1 cost estimation — memory rate by family |
| `ondemand_price:{region}:{type}` | Variable | `"0.192"` | Engine 2 OD price lookup (primary key) |
| `od_price:{region}:{type}` | Variable | `"0.192"` | Engine 2 OD price lookup (fallback key) |
| `spot:node_classification:{cluster_id}` | Variable | JSON map | Node → workload type (stateless / stateful / system) |
| `spot:cooldown:action:resize:{cluster_id}` | 1800s | timestamp | Resize cooldown after last action |
| `market_view_cache:{region}` | 3600s | JSON array | 500 cheapest pools — used for spot pool lookup in both engines |
| `global_pool_rankings:{region}` | 3900s | JSON array | ML-ranked pools — used by PoolRankingService |

---

## 12. API Endpoints

### Engine 1 (Pod-Level / In-House)

| Method | Path | Purpose |
|--------|------|---------|
| `GET` | `/api/v1/pod-metrics/rightsizing/enriched?cluster_id=...` | Get enriched workload-level recommendations |
| `POST` | `/api/v1/optimization/apply/{id}` | Apply a single proposal |
| `POST` | `/api/v1/optimization/rightsizing/batch-apply` | Apply multiple proposals |

### Engine 2 (Node-Level / Karpenter)

| Method | Path | Purpose |
|--------|------|---------|
| `GET` | `/api/v1/karpenter/recommendations?cluster_id=...` | Get per-node instance right-sizing recommendations |
| `POST` | `/api/v1/karpenter/apply-recommendation/{id}` | Apply a specific recommendation |

### Combined (Simulation)

| Method | Path | Purpose |
|--------|------|---------|
| `GET` | `/api/v1/ascpai/clusters/{id}/node-recommendations?use_rightsized=true` | Node recs + karpenter simulation with right-sizing applied |

---

## 13. Frontend UI

### 13.1 Right-Sizing Dashboard (`RightSizingDashboard.jsx`)

**File:** `frontend/src/components/right-sizing/RightSizingDashboard.jsx`

**Sections:**

**AutoModeBanner** (lines 60–112)
- Shows toggle state for `auto_rebalance_enabled` and `auto_rightsizing_enabled`
- Green when both on (Mode 3 / Synergy), blue when rebalance only, amber when rightsizing only

**ClusterHealthExposureBar** (lines 115–167)
- Total nodes, stateless/stateful split, eligible count, cooldown count
- Source: `karpenterAPI.getRecommendations(selectedClusterId)`

**ResizeGuardMonitoringPanel** (lines 170–208)
- Shows which guards are active: CPU spike, memory pressure, cooldown, concurrent actions
- Updates every 15s

**StatelessDetailedDrawer** (lines 211–255)
- Node details modal: current vs recommended type, CPU/mem utilization sparkline
- Shows: headroom applied, dry-run result, diversification check

**StatefulProposalModal** (lines 258–320)
- Manual approval flow for stateful resize
- Warning: "Spot lock will be applied — node will run on-demand until migration completes"
- Shows: current type, proposed type, P95 CPU%, P95 mem%, monthly savings estimate

### 13.2 Karpenter Right-Sizing Tab (`RightSizingKarpenterTab.jsx`)

**File:** `frontend/src/components/right-sizing/RightSizingKarpenterTab.jsx`

**Top KPI cards:**
| Card | Source |
|------|--------|
| Total Clusters | `clusterAPI.listClusters().length` |
| Active Targets | Count of recommendations with `impact != "Neutral"` |
| Monthly Savings | Sum of `potential_savings` across all recommendations |
| Impact Score | Weighted average of savings percentages |

**Main table columns:**
| Column | Source |
|--------|--------|
| Node | `rec.node_name` |
| Current Type | `rec.current_type` |
| Recommended Type | `rec.recommended_type` |
| CPU% | `rec.cpu` |
| Memory% | `rec.memory` |
| Monthly Savings | `rec.potential_savings` |
| Impact | `rec.impact` ("Critical" / "High" / "Neutral") |
| Action | "Apply" button → `karpenterAPI.applyRecommendation()` |

**Polling:** Every 15s — `ascpaiAPI.getRebalancingStatus()` for live action updates

### 13.3 Settings Tab — Karpenter Guard (ClusterDetails.jsx)

Added 2026-04-02: When enabling `auto_rightsizing_enabled` toggle:
1. Checks `karpenterInstallStatus?.karpenter_installed`
2. If NOT installed → opens `KarpenterRequiredModal`
3. Modal polls `getInstallStatus()` every 5s
4. Auto-closes and enables toggle when Karpenter detected

---

## 14. Known Limitations

### Engine 1 Limitations

1. **Long warm-up period:** Needs 100+ data points (~1.5 hours at 30s polling). New clusters have no recommendations until warmed up.
2. **Request ≠ usage:** If pods have no `resources.requests` set, Engine 1 uses `usage × 1.5` as synthetic request — may differ from true sizing need.
3. **Replica count snapshot:** Counted from last 1 hour — misses scaling events (HPA scale-up at hour 5 not captured).
4. **Cost model approximation:** Uses CPU+memory rate model, not actual instance pricing. A 4vCPU/8GB pod doesn't know it's on a `c5.xlarge` vs `c5.2xlarge`.
5. **No affinity awareness:** Recommendations don't account for pod anti-affinity, node selectors, or taints — may produce proposals that can't schedule.
6. **Stateful: OD only:** Stateful workloads are never recommended for spot — even if they use PVCs that support multi-AZ.

### Engine 2 Limitations

1. **Single snapshot:** Uses `cpu_utilization_pct` from the most recent agent report. A GC pause or idle moment produces misleading utilization.
2. **No percentile smoothing:** 35% utilization at the moment of the snapshot — not P95 over a week.
3. **INSTANCE_SPECS coverage:** Hardcoded to ~50 instance types. Newer types (c7i, m7i, Graviton 3) may not be in the catalogue.
4. **No multi-AZ awareness:** `_bin_pack_instance` doesn't account for AZ-level spot capacity.
5. **OD prices only:** Downsize recommendation is based on OD price comparison. The actual node may be running spot, making the actual saving different.
6. **No Graviton cross-recommendation:** Won't recommend switching from x86 to ARM even if it would be cheaper and compatible.

### Shared Limitations

1. **No PodDisruptionBudget awareness:** Neither engine checks if `minAvailable` constraints allow draining a node during resize.
2. **No resource limits enforcement:** Both engines use `requests` not `limits`. A pod with `requests: 100m` but `limits: 4000m` may burst and hit OOM after downsizing.

---

## 15. End-to-End Flow Diagram

```
┌────────────────────────────────────────────────────────────────────┐
│  ENGINE 1 FLOW (In-House Pod-Level)                                │
│                                                                    │
│  Agent DaemonSet                                                   │
│  └─ Reports PodMetric to backend every 30s                         │
│     └─ Stored in pod_metrics table                                 │
│                                                                    │
│  Auto-Rebalancer cycle (or manual API call)                        │
│  └─ Checks: auto_rightsizing_enabled + all 5 guards                │
│     └─ Calls RightSizingService.generate_recommendations()         │
│        │                                                           │
│        ├─ [DB] Query pod_metrics (last 168h)                       │
│        ├─ [DB] Get cluster classification                          │
│        ├─ [Redis] Check spot:volatility_regime:{region}            │
│        ├─ [Redis] Check cooldown key                               │
│        ├─ Per controller:                                          │
│        │   ├─ P95 + P99 floor + dynamic buffer                     │
│        │   ├─ Confidence gate (≥100 samples)                       │
│        │   ├─ Volatility gate (cpu_volatility < 0.95)              │
│        │   └─ Cost estimate (CPU+mem rates from Redis)             │
│        └─ Returns List[RightSizingRecommendation]                  │
│           └─ create_rightsizing_proposals() → DB                   │
│              └─ OptimizerCoordinator evaluates A/B/C               │
│                 └─ APPROVED → Agent action queue                   │
│                    └─ Agent updates K8s resource.requests          │
└────────────────────────────────────────────────────────────────────┘

┌────────────────────────────────────────────────────────────────────┐
│  ENGINE 2 FLOW (Node-Level / Karpenter)                            │
│                                                                    │
│  Frontend: RightSizingKarpenterTab.jsx                             │
│  └─ GET /karpenter/recommendations?cluster_id=...                  │
│     │                                                              │
│     ├─ [DB] Query instances (state=running, lifecycle=on_demand)   │
│     ├─ [Redis] ondemand_price:{region}:{type}                      │
│     ├─ Per instance:                                               │
│     │   ├─ _bin_pack_instance(cpu_pct, mem_pct, buffer=30%)        │
│     │   │   ├─ required = util% × 1.30                             │
│     │   │   ├─ current_fits? → DOWNSIZE or UPSIZE path             │
│     │   │   └─ First fitting type in sorted candidates             │
│     │   ├─ Validate vs NodeTemplate.allowed_families               │
│     │   └─ PoolRankingService.rank_pools() → spot_pool             │
│     └─ Return recommendation list                                  │
│        │                                                           │
│        └─ User clicks "Apply"                                      │
│           └─ POST /karpenter/apply-recommendation/{id}             │
│              ├─ Stateless: KarpenterService.add_allowed_type()     │
│              │   └─ Karpenter provisions new node, drains old      │
│              └─ Stateful: Queue CORDON → DRAIN → TERMINATE         │
│                  └─ ASG provisions replacement at new type         │
└────────────────────────────────────────────────────────────────────┘

┌────────────────────────────────────────────────────────────────────┐
│  COMBINED FLOW (Best of both engines)                              │
│                                                                    │
│  1. Engine 1 right-sizes pod requests (resource.requests reduced)  │
│  2. Rebalancer detects reduced pod footprint                       │
│  3. Bin-pack simulation re-runs with right-sized pod values        │
│     (GET /node-recommendations?use_rightsized=true)                │
│  4. Karpenter simulation shows new optimal node consolidation      │
│  5. Engine 2 recommends smaller instance types for new footprint   │
│  6. Result: fewer, smaller, cheaper spot nodes                     │
└────────────────────────────────────────────────────────────────────┘
```

---

*Document generated: 2026-04-03*
*Primary source files: `backend/services/rightsizing_service.py`, `backend/api/karpenter_routes.py`, `backend/models/rightsizing_proposal.py`, `frontend/src/components/right-sizing/RightSizingKarpenterTab.jsx`, `frontend/src/components/right-sizing/RightSizingDashboard.jsx`*
