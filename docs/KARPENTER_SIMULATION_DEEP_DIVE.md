# Karpenter Simulation — Complete Technical Reference

> Covers: Bin-Packing Simulation · Right-Sizing Engine · NodePool Sync · UI Display · Database Schema · Redis Keys · Accuracy Model · Known Limitations

---

## Table of Contents

1. [System Overview](#1-system-overview)
2. [Architecture Layers](#2-architecture-layers)
3. [Data Sources](#3-data-sources)
4. [Node Recommendations Endpoint — Full Flow](#4-node-recommendations-endpoint--full-flow)
5. [Bin-Packing Simulation Algorithm](#5-bin-packing-simulation-algorithm)
6. [Right-Sizing Engine](#6-right-sizing-engine)
7. [Karpenter NodePool Sync](#7-karpenter-nodepool-sync)
8. [On-Demand Fallback & Circuit Breaker](#8-on-demand-fallback--circuit-breaker)
9. [Database Models](#9-database-models)
10. [Redis Keys Reference](#10-redis-keys-reference)
11. [API Endpoints](#11-api-endpoints)
12. [Frontend Display](#12-frontend-display)
13. [Accuracy Model & Precision Framework](#13-accuracy-model--precision-framework)
14. [Known Limitations & Assumptions](#14-known-limitations--assumptions)
15. [End-to-End Data Flow Diagram](#15-end-to-end-data-flow-diagram)

---

## 1. System Overview

The Karpenter simulation is a **what-if consolidation engine** that answers the question:

> *"If Karpenter were to repack all running workloads onto optimal spot instances right now, what would the cluster look like and how much would it cost?"*

It runs as part of every `/node-recommendations` API response when the cluster has `karpenter_mode` set (i.e., Karpenter is installed). The result is the `karpenter_simulation` object returned alongside per-node recommendations.

The system has three distinct but connected subsystems:

| Subsystem | Purpose | Trigger |
|-----------|---------|---------|
| **Node Recommendations Engine** | Per-node: current type → target spot pool | Every UI poll (30s) |
| **Bin-Packing Simulator** | Cluster-wide: optimal node consolidation | Embedded in node-rec response |
| **Karpenter Service** | Real K8s: sync ML rankings → NodePool CRD | Auto-rebalancer cycle (30s beat) |

---

## 2. Architecture Layers

```
┌─────────────────────────────────────────────────────────────────┐
│                        Frontend UI                              │
│  PoolRankings.jsx (Fleet View table + Simulation Panel)        │
│  OverviewTab.jsx  (Karpenter status card + install button)     │
└────────────────────────┬────────────────────────────────────────┘
                         │ GET /api/v1/ascpai/clusters/{id}/node-recommendations
                         ▼
┌─────────────────────────────────────────────────────────────────┐
│              ascpai_routes.py  (lines 1366–2308)               │
│  ┌──────────────────┐   ┌──────────────────────────────────┐  │
│  │ Node Rec Engine  │   │   Karpenter Bin-Pack Simulation  │  │
│  │  Phase 1–3       │   │   Phase 4 (if karpenter_mode set)│  │
│  └──────────────────┘   └──────────────────────────────────┘  │
└────────────────────────┬────────────────────────────────────────┘
                         │
       ┌─────────────────┼──────────────────────┐
       ▼                 ▼                        ▼
  PostgreSQL DB      Redis Cache           AWS EC2 API
  (instances,        (market_view_         (spot prices,
   pod_metrics,       cache, spot_price,    DryRun checks)
   rightsizing)       ondemand_price)
```

---

## 3. Data Sources

### 3.1 Market View Cache (`market_view_cache:{region}`)

- **Built by:** `cache_builder.py` (Celery task, runs every hour)
- **Content:** JSON array of the 500 cheapest spot pools in the region
- **Fields per pool:**
  ```json
  {
    "instance_type": "c6i.xlarge",
    "az": "ap-south-1a",
    "vcpu": 4,
    "memory_gb": 8,
    "architecture": "amd64",
    "spot_price": 0.0342,
    "od_price": 0.17,
    "risk_probability": 0.08,
    "interruption_rate_pct": 3,
    "savings_pct": 79.9,
    "ml_score": 0.184
  }
  ```
- **TTL:** 3600 seconds
- **Fallback:** If cache miss, simulation skips (returns null karpenter_simulation)

### 3.2 Pod Metrics (`pod_metrics` table)

- **Query window:** Last 10 minutes (`timestamp >= now - 10min`)
- **Fields used:** `pod_name`, `namespace`, `controller_kind`, `controller_name`, `node_name`, `cpu_request_millicores`, `memory_request_bytes`, `cpu_usage_millicores`, `memory_usage_bytes`
- **Populated by:** Agent DaemonSet running on every node — reports metrics every 30s
- **Used for:** Actual pod resource demands for bin-packing

### 3.3 Instance Records (`instances` table)

- **Query:** `state='running'`, has `instance_type`, has `instance_id`
- **Deduplication:** Collapse records where `node_name` matches `ip-192-168-x-x` and `i-xxxxxxxx` for same physical node; prefer EC2 record
- **Fields used:** `instance_type`, `lifecycle`, `az`, `instance_id`, `node_name`, `cpu_utilization_pct`, `memory_utilization_pct`

### 3.4 Spot Prices (Redis)

- **Primary key:** `spot_price:{region}:{az}:{instance_type}` → JSON `{"price": "0.0342", "timestamp": "..."}`
- **OD price key:** `ondemand_price:{region}:{instance_type}` → plain string `"0.17"`
- **Fallback OD key:** `od_price:{region}:{instance_type}` → plain string (internal use)

---

## 4. Node Recommendations Endpoint — Full Flow

**Endpoint:** `GET /api/v1/ascpai/clusters/{cluster_id}/node-recommendations`

**Query params:**
- `use_rightsized` (bool, default `false`) — substitute right-sized pod resource requests before packing

### Phase 1: Instance & Pricing Data Collection

```
ascpai_routes.py lines 1388–1443
```

1. Query all `Instance` records for cluster (`state='running'`, `instance_type` not null, `instance_id` not null)
2. Deduplicate by K8s node hostname — one record per physical node
3. Fetch pricing data in bulk:
   - `bulk_get_hourly_prices(instance_types, region, redis)` → OD hourly $/hr per type
   - `bulk_get_vcpu_counts(instance_types, region, redis)` → vCPU per type
   - `bulk_get_memory_gb(instance_types, region, redis)` → memory GB per type
   - Hardcoded fallback tables used when Redis miss

### Phase 2: Pool Candidate Assembly

```
ascpai_routes.py lines 1445–1590
```

**Step 1:** Load `market_view_cache:{region}` (500 pools)

**Step 2:** For any current instance type NOT in the cache — scan all AZs:
```
spot_price:{region}:ap-south-1a:{type}
spot_price:{region}:ap-south-1b:{type}
spot_price:{region}:ap-south-1c:{type}
```
Build synthetic pool entry if found. This ensures same-type options are always represented.

**Step 3:** Wrap each pool in `_ScoredPoolWrapper`:
```python
class _ScoredPoolWrapper:
    risk_probability: float
    predicted_savings: float
    ml_score: float = predicted_savings × (1 - risk_probability)
```

**Step 4:** Sort by `(risk_probability ASC, predicted_savings DESC)`

### Phase 3: Per-Node Analysis

```
ascpai_routes.py lines 1592–1915
```

For each node:

**a) Workload Classification:**
- Read `spot:node_classification:{cluster_id}` from Redis
- Categories `STATEFUL_PROTECTED`, `SYSTEM_PROTECTED` → `"stateful"`
- All others → `"stateless"`

**b) Resource Requirements with Safety Headroom:**
```python
cpu_util  = max(node.cpu_utilization_pct or 10, 10)   # 10% floor
mem_util  = max(node.memory_utilization_pct or 10, 10)

required_vcpu = max(current_vcpu,
                    current_vcpu × (cpu_util / 100) × 1.25)
required_mem  = max(current_mem,
                    current_mem  × (mem_util / 100) × 1.25)
```
- Floor at current specs (never recommend smaller)
- 25% safety headroom above observed utilization

**c) Target Pool Selection:**
- For OD nodes: call `PoolRankingService.rank_pools_for_node()`
  - Params: `min_vcpu`, `min_memory`, `architecture`, `cluster_id`
  - Returns: top-5 ML-ranked pools satisfying constraints
- Price ceiling checks:
  - OD→SPOT: target must be cheaper than current OD price
  - SPOT→SPOT (S2S): target allowed up to 20% premium over current spot (for stability gain)

**d) Diversification Enforcement** (when `diversify_pools=True`):
```python
# Max nodes sharing same type
_max_same_type = max(1, round(total_nodes × (1.0 - inst_type_div_pct / 100.0)))

# Track occupied pools and types
_occupied_pools: set[tuple[str, str]]  # (instance_type, az)
_occupied_types: dict[str, int]        # instance_type → count
```

**e) S2S Candidate Detection:**
Marks node as S2S (SPOT→SPOT rebalance) when ANY of:
1. Cross-AZ same-type: `target_type == current_type AND target_az != current_az`
2. Duplicate pool and diversify enabled
3. `risk_score > risk_ceiling` (default 25%)

**f) Per-Node Savings Calculation:**
```python
# OD node
savings_pct = (od_price - spot_price) / od_price × 100

# Spot node (S2S candidate)
savings_pct = (current_spot_price - target_spot_price) / od_price × 100
```

---

## 5. Bin-Packing Simulation Algorithm

```
ascpai_routes.py lines 1937–2308
```

**Only runs when** `cluster.karpenter_mode IS NOT NULL`

### Step 1: Pod Metrics Query

```python
pod_metrics = db.query(PodMetric)
    .filter(PodMetric.cluster_id == cluster_id,
            PodMetric.timestamp >= datetime.utcnow() - timedelta(minutes=10))
    .all()
```

### Step 2: DaemonSet vs User Pod Separation

**System namespaces:**
```python
SYSTEM_NAMESPACES = {'kube-system', 'kube-public', 'kube-node-lease'}
```

**Classification rules:**
- `namespace in SYSTEM_NAMESPACES` → DaemonSet/system pod
- `controller_kind in {'DaemonSet', 'daemonset'}` → DaemonSet pod
- Everything else → user workload pod

**DaemonSet deduplication:** Each unique `controller_name` counted once across all nodes (prevents double-counting when same DS runs on multiple nodes).

### Step 3: Per-Node Fixed Overhead

```python
_ds_cpu_overhead  = sum(d['cpu_millicores']  for d in _daemonset_demands)
_ds_mem_overhead  = sum(d['memory_bytes']    for d in _daemonset_demands)

# Base system processes
_KUBELET_CPU_M     = 100          # millicores
_KUBELET_MEM_BYTES = 256 × 1024³  # 256 MB

_total_per_node_cpu_overhead = _ds_cpu_overhead + _KUBELET_CPU_M
_total_per_node_mem_overhead = _ds_mem_overhead + _KUBELET_MEM_BYTES
```

This overhead is **subtracted from every candidate pool's allocatable capacity**.

### Step 4: Candidate Pool Selection

Load from `market_view_cache:{region}`. For each pool:

**Spot price validation (reject if):**
```python
spot_price <= 0                           # stale/missing
od_price   <= 0                           # no baseline
discount_pct < 5                          # trivial savings
discount_pct > 90                         # suspiciously cheap
```

**Allocatable capacity calculation:**
```python
allocatable_cpu_m    = (vcpu × 1000 × 0.95) - _total_per_node_cpu_overhead
allocatable_mem_bytes = (memory_gb × 1024³  × 0.95) - _total_per_node_mem_overhead
```
- 5% reserved for kubelet overhead

**ML score sorting:**
```python
ml_score = predicted_savings × (1 - risk_probability)
```
Primary sort: `spot_price ASC` → Secondary: `ml_score DESC`

### Step 5: Multi-Architecture Detection

```python
_nd_family = instance_type.split(".")[0]    # e.g. "m6g"
_nd_arch = 'arm64' if (
    bool(re.search(r'\dg', _nd_family)) or _nd_family == "a1"
) else 'amd64'
```

If cluster runs any ARM64 nodes → simulation allows **both** amd64 and arm64 candidates (unlocks cheaper Graviton pools).

### Step 6: Right-Sizing Substitution (optional)

When `use_rightsized=true`:
1. Call `RightSizingService.get_recommendations(cluster_id)`
2. Build lookup: `(namespace, controller_name)` → `(recommended_cpu_m, recommended_mem_bytes)`
3. Replace pod resource requests with right-sized values
4. Produces "what-if after right-sizing" consolidation model

### Step 7: First-Fit Decreasing (FFD) Bin-Packing

**Sort user pods descending by resource footprint:**
```python
_user_pod_demands.sort(key=lambda p: (-p['cpu_millicores'], -p['memory_bytes']))
```

**For each pod in sorted order:**

```
1. Find first existing bin where:
   (bin.remaining_cpu  >= pod.cpu_millicores)  AND
   (bin.remaining_mem  >= pod.memory_bytes)

2. If found → place pod in that bin (FIRST-FIT)

3. If not found → select new pool candidate:
   a. Find all pools where allocatable_cpu >= pod.cpu AND allocatable_mem >= pod.mem
   b. Pick SMALLEST matching pool (sort by spot_price ASC, then allocatable_cpu ASC)
      — prevents placing 2-vCPU pod on 96-vCPU metal node
   c. Open new bin with that pool type

4. If NO pool can fit this pod → use largest available pool as safety fallback
```

### Step 8: HA Constraint — Minimum 2 Nodes

```python
_MIN_NODES = min(2, len(_node_list))  # at least 2 unless cluster is <2 nodes

if len(_bins) < _MIN_NODES and _bins and _karp_candidates:
    # Split largest bin: divide its pods across 2 nodes of same type
    largest_bin = max(_bins, key=lambda b: len(b.pods))
    half = len(largest_bin.pods) // 2
    new_bin = Bin(same_pool_type)
    new_bin.pods = largest_bin.pods[:half]
    largest_bin.pods = largest_bin.pods[half:]
```

Prevents single-node simulation (single spot = SPOF).

### Step 9: Result Aggregation

Group bins by instance type → count occurrences. Build `consolidated_nodes` list:

```python
{
    'instance_type': 'c6i.xlarge',
    'az': 'ap-south-1a',
    'architecture': 'amd64',
    'vcpu': 4,
    'memory_gb': 8,
    'spot_price': 0.0342,
    'od_price': 0.17,
    'risk_probability': 0.08,
    'ml_score': 0.184,
    'count': 2,          # number of nodes of this type in simulation
    'total_pods': 18,    # pods placed on this node type
}
```

### Full Simulation Output Object

```python
karpenter_simulation = {
    'mode': 'dry_run' | 'auto',
    'rightsized': bool,

    # Optimized fleet
    'consolidated_nodes': [...],
    'total_node_count': 5,
    'total_hourly_cost': 0.337,
    'total_monthly_cost': 245.80,

    # Workload accounting
    'total_pods_packed': 47,
    'total_pods_in_cluster': 52,
    'user_pods': 47,
    'daemonset_pods': 5,
    'daemonset_overhead_cpu_m': 450,
    'daemonset_overhead_mem_mb': 320,

    # Savings vs current
    'current_node_count': 12,
    'current_monthly_cost': 742.56,
    'monthly_savings': 496.76,         # max(0, current - simulated)
    'nodes_eliminated': 7,

    # Architecture
    'multi_arch': True,
    'architectures_used': ['amd64', 'arm64'],
}
```

`monthly_savings` is floored at 0 — simulation never shows negative savings.

---

## 6. Right-Sizing Engine

### 6.1 Instance-Level Right-Sizing (`karpenter_routes.py`)

**Function:** `_bin_pack_instance(current_type, cpu_pct, mem_pct, buffer_pct=30, region, redis)`

```python
specs = INSTANCE_SPECS[current_type]   # (vcpu, memory_gb, fallback_od_price)
c_hourly = _get_od_price(current_type, region, redis)

# Required resources with configurable safety buffer (default 30%)
required_vcpu = max(0.25, (c_vcpu × max(cpu_pct, 0) / 100) × 1.30)
required_mem  = max(0.5,  (c_mem  × max(mem_pct, 0) / 100) × 1.30)

# Does the current type still fit?
if c_vcpu >= required_vcpu and c_mem >= required_mem:
    # Under-utilised: find the largest DOWNSIZE that still fits
    candidates = [(t, s) for t, s in INSTANCE_SPECS.items()
                  if s.vcpu >= required_vcpu
                  and s.mem >= required_mem
                  and _get_od_price(t) < c_hourly]
    best = min(candidates, key=lambda x: _get_od_price(x[0]))  # cheapest fit
else:
    # Over-utilised: find smallest UPSIZE
    candidates = [(t, s) for t, s in INSTANCE_SPECS.items()
                  if s.vcpu >= required_vcpu and s.mem >= required_mem]
    best = min(candidates, key=lambda x: _get_od_price(x[0]))

monthly_savings = (c_hourly - t_hourly) × 730   # negative = cost increase
```

**Endpoint:** `GET /api/v1/karpenter/recommendations?cluster_id=...`

**Returns per node:**
```python
{
    'node_name': 'ip-192-168-2-212',
    'current_type': 't3.medium',
    'recommended_type': 't3a.medium',
    'cpu_utilization': 34.2,
    'memory_utilization': 51.8,
    'current_cost_monthly': 33.58,
    'recommended_cost_monthly': 27.01,
    'potential_savings': 6.57,
    'savings_pct': 19.6,
    'is_upsize': False,
    'spot_pool': {'instance_type': 'c7g.medium', 'az': 'ap-south-1c', 'spot_price': 0.0042},
    'risk_probability': 0.07,
    'node_type': 'stateless',
    'reason': 'Underutilised: 34% CPU, 52% memory — downsize saves $6.57/mo'
}
```

### 6.2 Simulation Right-Sizing Integration

When `use_rightsized=true` is passed to `/node-recommendations`:
1. `RightSizingService.get_recommendations(cluster_id)` is called
2. Returns map: `(namespace, controller_name)` → `(cpu_millicores, memory_bytes)`
3. Before packing, each pod's resource request is replaced with right-sized value
4. Remaining logic (FFD, pool selection) unchanged
5. `karpenter_simulation.rightsized = true` in response

---

## 7. Karpenter NodePool Sync

**File:** `backend/services/karpenter_service.py`

**Beat trigger:** `karpenter-nodepool-sync` — 30s interval (registered in `app.py`)

**Function:** `sync_ml_rankings_to_nodepool(cluster_id, top_pools, db)`

### Sync Flow:

```
1. Read top_pools from auto_rebalancer cycle output
   (global_pool_rankings:{region} filtered to cluster's region + AZs)

2. Extract:
   instance_types = [p['instance_type'] for p in top_pools][:20]
   azs = list(set(p['az'] for p in top_pools))

3. Build NodePool patch body:
   {
     "spec": {
       "requirements": [
         {"key": "karpenter.sh/capacity-type",
          "operator": "In", "values": ["spot"]},
         {"key": "node.kubernetes.io/instance-type",
          "operator": "In", "values": instance_types},
         {"key": "topology.kubernetes.io/zone",
          "operator": "In", "values": azs}
       ]
     }
   }

4. Patch via Kubernetes custom API:
   custom_api.patch_cluster_custom_object(
       group="karpenter.sh",
       version="v1",
       plural="nodepools",
       name="default",
       body=patch_body
   )

5. Retry logic: 2 retries, 5s then 15s delays
   Pre-patch state captured for rollback on failure

6. Set cooldown key: spot:karpenter:nodepool_updated:{cluster_id}
   TTL: 300s (prevents thrashing)
```

**Authentication:** Uses cluster's `role_arn` for cross-account STS assume_role. Falls back to platform credentials for same-account clusters.

**No AgentAction records created** — this is a direct K8s API call, not an agent-mediated action.

---

## 8. On-Demand Fallback & Circuit Breaker

### 8.1 On-Demand Fallback

**Trigger:** When ML pool ranking returns empty (no safe spot pools found)

```python
# Switch NodePool to on-demand
karpenter_service.switch_to_ondemand(cluster_id, db)

# Redis marker
redis.set(f"spot:ondemand_fallback:{cluster_id}",
          json.dumps({
              'activated_at': utcnow().isoformat(),
              'instance_types': [...],
              'azs': [...]
          }),
          ex=43200)  # 12-hour TTL
```

**Auto-revert:** After 12h TTL expires, cleanup task calls `revert_to_spot()`.
**Manual revert:** Available via `POST /karpenter/clusters/{id}/revert-to-spot`.

### 8.2 Execution-Level DryRun Check

Per-pool capacity validation before any real provisioning:

```python
ec2.run_instances(
    ImageId=...,
    InstanceType=pool['instance_type'],
    MinCount=1, MaxCount=1,
    Placement={'AvailabilityZone': pool['az']},
    InstanceMarketOptions={'MarketType': 'spot'},
    DryRun=True   # ← key flag
)
```

- `DryRunOperation` → capacity confirmed, pool usable
- `InsufficientInstanceCapacity` → block pool 6h via BlacklistService
- Failure counter: `spot:execution_fail:{pool_id}` (TTL 3600s)
- On 2+ failures in 1h window → 6-hour blacklist

### 8.3 Per-Cluster Circuit Breaker

```python
# Key: spot:cluster_circuit_breaker:{cluster_id}
# TTL: 1800s (30 min)
# Trips when: >= 10 execution failures in rolling 10-minute window
```

When tripped — ALL spot provisioning for that cluster pauses for 30 minutes.

---

## 9. Database Models

### `Cluster` (`clusters` table)

| Column | Type | Purpose |
|--------|------|---------|
| `karpenter_mode` | `Enum(KarpenterMode)` | `null`=not installed, `dry_run`=insights only, `auto`=full management |
| `karpenter_version` | `String` | Detected Karpenter version |
| `node_count` | `Integer` | Total nodes (updated by discovery) |
| `spot_count` | `Integer` | Current spot nodes |
| `optimization_settings` | FK | → `ClusterOptimizationSettings` |

### `ClusterOptimizationSettings` (`cluster_optimization_settings` table)

| Column | Type | Default | Purpose |
|--------|------|---------|---------|
| `auto_rebalance_enabled` | Boolean | False | Master switch for ML rebalancing |
| `auto_rightsizing_enabled` | Boolean | False | Enable right-sizing |
| `auto_stateful_rightsizing_enabled` | Boolean | False | Right-size stateful nodes |
| `diversify_pools` | Boolean | False | Enforce pool diversity |
| `instance_type_diversification_pct` | Integer | 50 | % uniqueness required |
| `risk_ceiling_percent` | Integer | 25 | Max acceptable interruption % |
| `check_interval_seconds` | Integer | 15 | Rebalancer cycle frequency |
| `optimization_target` | String | `spot` | `spot` or `on_demand` |

### `Instance` (`instances` table)

| Column | Purpose |
|--------|---------|
| `instance_type` | e.g. `t3.medium` |
| `lifecycle` | `spot` or `on_demand` |
| `az` | Availability zone |
| `cpu_utilization_pct` | From agent metrics |
| `memory_utilization_pct` | From agent metrics |
| `node_name` | K8s node hostname |
| `state` | `running`, `terminated`, etc. |

### `PodMetric` (`pod_metrics` table)

| Column | Purpose |
|--------|---------|
| `pod_name` | K8s pod name |
| `namespace` | K8s namespace |
| `controller_kind` | `Deployment`, `DaemonSet`, etc. |
| `controller_name` | Controller owning this pod |
| `node_name` | Node this pod runs on |
| `cpu_request_millicores` | Requested CPU |
| `memory_request_bytes` | Requested memory |
| `cpu_usage_millicores` | Actual CPU usage |
| `memory_usage_bytes` | Actual memory usage |
| `timestamp` | Metric collection time |

### `RightsizingProposal` (`rightsizing_proposals` table)

| Column | Purpose |
|--------|---------|
| `cluster_id` | FK to Cluster |
| `controller_name` | K8s Deployment/StatefulSet name |
| `namespace` | K8s namespace |
| `recommended_cpu_millicores` | Right-sized CPU request |
| `recommended_memory_bytes` | Right-sized memory request |
| `confidence_score` | ML confidence (0–1) |
| `created_at` | When proposal was generated |

### `StatefulRules` (`stateful_rules` table)

| Column | Default | Purpose |
|--------|---------|---------|
| `require_approval` | False | Manual approval for stateful resize |
| `max_downscale_percent` | 25 | Max resource reduction allowed |

---

## 10. Redis Keys Reference

| Key Pattern | TTL | Value Format | Purpose |
|-------------|-----|--------------|---------|
| `market_view_cache:{region}` | 3600s | JSON array | 500 cheapest pools, built hourly |
| `global_pool_rankings:{region}` | 3900s | JSON array | ML-ranked pools (all sizes) |
| `spot_price:{region}:{az}:{type}` | variable | `{"price":"0.034","timestamp":"..."}` | Live spot price |
| `ondemand_price:{region}:{type}` | variable | `"0.17"` | OD price (cache_builder key) |
| `od_price:{region}:{type}` | variable | `"0.17"` | OD price (aws_pricing_service key) |
| `spot:node_classification:{cluster_id}` | variable | JSON map | WorkloadInspector output |
| `spot:ondemand_fallback:{cluster_id}` | 43200s | JSON dict | OD fallback active marker |
| `spot:karpenter:nodepool_updated:{cluster_id}` | 300s | timestamp | NodePool sync cooldown |
| `spot:execution_fail:{pool_id}` | 3600s | integer counter | DryRun failure count |
| `spot:cluster_circuit_breaker:{cluster_id}` | 1800s | `"1"` | Circuit breaker active |
| `karpenter:detected:{cluster_id}` | 300s | JSON | Detection result cache |
| `spot:karpenter:installed:{cluster_id}` | 3600s | `"true"` | Install confirmation cache |

---

## 11. API Endpoints

### Simulation & Recommendations

| Method | Path | Purpose |
|--------|------|---------|
| `GET` | `/api/v1/ascpai/clusters/{id}/node-recommendations` | Node recs + karpenter simulation |
| `GET` | `/api/v1/karpenter/recommendations?cluster_id=...` | Right-sizing recommendations per node |
| `POST` | `/api/v1/karpenter/apply-recommendation/{id}` | Apply right-sizing to a node |

### Karpenter Installation & Status

| Method | Path | Purpose |
|--------|------|---------|
| `GET` | `/api/v1/karpenter/clusters/{id}/install-status` | Karpenter installed? Mode? Version? |
| `POST` | `/api/v1/karpenter/clusters/{id}/install` | Trigger Karpenter installation |
| `GET` | `/api/v1/karpenter/detect/{cluster_id}` | Force re-detect Karpenter presence |
| `POST` | `/api/v1/karpenter/clusters/{id}/revert-to-spot` | Manual revert from OD fallback |

### NodePool Management

| Method | Path | Purpose |
|--------|------|---------|
| `GET` | `/api/v1/karpenter/clusters/{id}/nodepool` | Current NodePool CRD spec |
| `PATCH` | `/api/v1/karpenter/clusters/{id}/nodepool` | Update NodePool directly |
| `GET` | `/api/v1/karpenter/clusters/{id}/nodeclaims` | List active NodeClaims |

### Karpenter Routes Auth

- All karpenter routes: Bearer JWT (user auth)
- Internal sync calls (from auto_rebalancer): direct service method call, no HTTP

---

## 12. Frontend Display

### 12.1 PoolRankings.jsx — Fleet View Table

**Data source:** `ascpaiAPI.getNodeRecommendations(clusterId)`

**Polling:** Called on initial load + every 30s (light poll in ClusterDetails)

**Table columns:**
| Column | Source field | Notes |
|--------|-------------|-------|
| NODE | `rec.node_name` | K8s hostname |
| CURRENT TYPE | `rec.current_type` | Running instance type |
| TARGET POOL | `rec.recommended_type` + `rec.target_az` | Best ML pool |
| STATUS | `rec.status` + live rebalancing actions | READY / REBALANCING / etc. |
| COST/HR | `rec.current_cost` | Current hourly cost |
| COST TREND | Sparkline SVG | Hardcoded descending curve (visual indicator) |
| ACTION | `OD→SPOT` or `SPOT→SPOT` button | Based on `rec.lifecycle` + `rec.s2s_candidate` |
| SAVINGS | `(rec.od_cost - rec.target_spot_price) × 730` | Monthly projection |

**Fleet View header** (added 2026-04-02):
```jsx
<div className="flex items-center justify-between px-6 py-3 border-b border-slate-100 bg-slate-50">
    <span className="text-xs font-bold text-slate-700 uppercase tracking-widest">Fleet View</span>
    <span className="text-[10px] text-slate-400 font-medium">— Node-Specific Pool Rankings</span>
    <span className="text-[10px] text-slate-400">{nodeRecommendations.length} nodes</span>
</div>
```

### 12.2 OverviewTab.jsx — Karpenter Management Card

**Data source:** `karpenterAPI.getInstallStatus(clusterId)`

**Polling:** Fetched on initial load only (not re-polled during session)

**Displays:**
- Installation status badge (`INSTALLED` / `NOT INSTALLED`)
- Karpenter mode badge (`DRY_RUN` / `AUTO`)
- Detected-via method (CRD presence, namespace, etc.)
- Active NodeClaim count
- Install button (when not installed)

### 12.3 Simulation Panel

When `karpenter_simulation` is present in the node-recommendations response:

| UI Element | Source field |
|-----------|-------------|
| Current nodes | `karpenter_simulation.current_node_count` |
| Simulated nodes | `karpenter_simulation.total_node_count` |
| Nodes eliminated | `karpenter_simulation.nodes_eliminated` |
| Current monthly cost | `karpenter_simulation.current_monthly_cost` |
| Simulated monthly cost | `karpenter_simulation.total_monthly_cost` |
| Monthly savings | `karpenter_simulation.monthly_savings` |
| Pods packed | `karpenter_simulation.total_pods_packed` / `total_pods_in_cluster` |
| DaemonSet overhead | `karpenter_simulation.daemonset_overhead_cpu_m` + `_mem_mb` |
| Consolidated fleet | `karpenter_simulation.consolidated_nodes[]` |
| Multi-arch flag | `karpenter_simulation.multi_arch` |

### 12.4 Settings Tab — Karpenter Guard

**Added 2026-04-02:** When enabling Auto Rebalance or Auto Right-Sizing toggles:

1. Check `karpenterInstallStatus?.karpenter_installed`
2. If NOT installed → show `KarpenterRequiredModal`:
   - Warning description
   - Real-time install status (polls `getInstallStatus()` every 5s)
   - Install Karpenter button (same call as Overview tab)
   - Auto-closes and enables toggle when Karpenter detected

---

## 13. Accuracy Model & Precision Framework

The simulation applies 7 precision fixes to avoid common bin-packing inaccuracies:

### Fix 1 & 2: DaemonSet Separation
**Problem:** Including DaemonSet pods in the "packable" workload inflates consolidation savings (DaemonSets run on every node, not just packed bins).

**Solution:** Separate by `controller_kind == 'DaemonSet'` OR `namespace in SYSTEM_NAMESPACES`. DaemonSets become fixed per-node overhead, not packed.

**Impact:** Prevents 20–40% overestimation of consolidation savings.

### Fix 3: Real Overhead Accounting
**Problem:** Ignoring kubelet + DaemonSet CPU/memory means bins appear to have more free space than they do.

**Solution:** Deduct actual measured DaemonSet resource usage + 100m CPU + 256MB RAM kubelet overhead from every node's allocatable capacity.

**Impact:** Eliminates "too-tight" bins that would fail to schedule in production.

### Fix 4: ML Composite Scoring
**Problem:** Sorting only by spot price picks cheapest pools with highest interruption rates.

**Solution:** `ml_score = savings × (1 - risk_probability)`. Tiebreaker after price sort.

**Impact:** Simulation tends toward stable pools, not just cheap ones.

### Fix 5: HA Minimum Node Constraint
**Problem:** FFD algorithm with small workloads might pack everything into 1 node.

**Solution:** Post-pack check: if `bins < 2`, split largest bin across 2 identical nodes.

**Impact:** Simulation never recommends single-node configuration (spot SPOF).

### Fix 6: Spot Price Outlier Rejection
**Problem:** Transient spot price spikes or missing prices corrupt savings projections.

**Solution:** Reject pools where `discount < 5%` OR `discount > 90%` OR `price <= 0`.

**Impact:** Prevents simulation from using temporarily mispriced data.

### Fix 7: Multi-Architecture Opportunity
**Problem:** Forcing simulation to amd64-only misses cheaper Graviton (arm64) instances.

**Solution:** If any node in cluster uses Graviton family → allow all architectures in simulation.

**Impact:** Graviton typically 20–40% cheaper than equivalent x86 for same workload.

### Simulation Accuracy Summary

| Scenario | Expected Accuracy |
|----------|------------------|
| CPU/memory utilization data < 10 min old | ±5% of real consolidation |
| Utilization data 10–60 min old | ±15% of real consolidation |
| No pod metrics (agent not installed) | Not computed (returns null) |
| Right-sizing disabled | Conservative (actual may be better) |
| Right-sizing enabled | Optimistic (assumes all proposals accepted) |
| Multi-arch cluster | ±8% (arch mix may shift) |

---

## 14. Known Limitations & Assumptions

### Pod Scheduling Constraints Not Modeled

The simulation does NOT account for:
- **Pod affinity/anti-affinity rules** — may result in infeasible placement
- **Node selectors and taints/tolerations** — may restrict actual node types
- **Custom scheduling policies** — Karpenter webhook overrides not considered
- **PodDisruptionBudgets** — live drain order not simulated

### Resource Request Assumptions

- Uses **requests** only, ignores **limits** — actual usage may require limits headroom
- When pod has no request set → uses `max(usage × 1.5, minimum)` as conservative estimate
- Stateful pods with local PVCs are excluded from packing (never recommended for spot)

### Pricing Assumptions

- OD prices fetched from Redis; stale if pricing worker missed a run
- Spot prices from `market_view_cache` — up to 1 hour old
- Graviton pricing estimated from AWS US calibration table when region price unavailable

### Workload Classification Staleness

- `spot:node_classification:{cluster_id}` cached by WorkloadInspector
- Not refreshed on every simulation run — may be stale if pods added mid-cycle
- Stale classification risk: incorrectly classifying a stateful pod as stateless

### Right-Sizing Over-Optimism

When `use_rightsized=true`, the simulation assumes **all** right-sizing proposals are accepted simultaneously. In practice:
- Some proposals require manual approval
- Some workloads have burst patterns not captured in P95 window
- Recommendation: treat right-sized simulation as theoretical ceiling

---

## 15. End-to-End Data Flow Diagram

```
                         ┌──────────────────────────────────┐
                         │  Frontend: PoolRankings.jsx       │
                         │  GET /node-recommendations?       │
                         │       cluster_id=xxx              │
                         └─────────────┬────────────────────┘
                                       │
                         ┌─────────────▼────────────────────┐
                         │   ascpai_routes.py               │
                         │                                  │
    ┌────────────────────►  Phase 1: Instance Collection    │
    │                    │  ─ DB: instances WHERE state=     │
    │                    │    running, deduplicate by node   │
    │                    │  ─ Redis: bulk OD prices          │
    │                    │  ─ Redis: vCPU/memory specs       │
    │                    │                                  │
    │    ┌───────────────►  Phase 2: Pool Assembly           │
    │    │               │  ─ Redis: market_view_cache       │
    │    │               │  ─ Redis: spot_price:* (suppl)    │
    │    │               │  ─ Build _ScoredPoolWrapper[]     │
    │    │               │                                  │
    │    │    ┌──────────►  Phase 3: Per-Node Analysis       │
    │    │    │          │  ─ Redis: node_classification     │
    │    │    │          │  ─ PoolRankingService.rank()      │
    │    │    │          │  ─ Diversity + S2S checks         │
    │    │    │          │                                  │
    │    │    │    ┌─────►  Phase 4: Bin-Pack Simulation     │
    │    │    │    │     │  (only when karpenter_mode != null)│
    │    │    │    │     │                                  │
    │    │    │    │     │  [1] DB: pod_metrics (last 10m)   │
    │    │    │    │     │  [2] Separate DS / user pods      │
    │    │    │    │     │  [3] Calc per-node overhead       │
    │    │    │    │     │  [4] Load & validate candidates   │
    │    │    │    │     │  [5] Detect multi-arch            │
    │    │    │    │     │  [6] (opt) right-size pod reqs    │
    │    │    │    │     │  [7] FFD bin-pack                 │
    │    │    │    │     │  [8] HA: enforce >= 2 nodes       │
    │    │    │    │     │  [9] Aggregate output             │
    │    │    │    │     │                                  │
    │    │    │    │     │  ◄── karpenter_simulation{}       │
    │    │    │    │     └──────────────────────────────────┘
    │    │    │    │
   DB  Redis Redis  Redis/DB
   inst  cache  spot_price  pod_metrics


┌─────────────────────────────────────────────────────────────┐
│  Parallel: auto_rebalancer.py (30s beat)                   │
│                                                             │
│  ─ Load global_pool_rankings:{region}                       │
│  ─ Filter to cluster region + AZs                           │
│  ─ Call karpenter_service.sync_ml_rankings_to_nodepool()    │
│     ─ PATCH karpenter.sh/v1/nodepools/default via K8s API  │
│     ─ Set cooldown: spot:karpenter:nodepool_updated:{id}    │
│                                                             │
│  Separate from simulation — this is REAL NodePool update   │
└─────────────────────────────────────────────────────────────┘
```

---

*Document generated: 2026-04-02*
*Primary source files: `backend/api/ascpai_routes.py`, `backend/services/karpenter_service.py`, `backend/api/karpenter_routes.py`, `frontend/src/components/ascpai/PoolRankings.jsx`*
