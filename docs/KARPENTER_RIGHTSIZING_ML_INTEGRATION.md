# Karpenter + Right-Sizing + ML Integration — System Architecture

> **Document Scope:** How Karpenter NodePool management, right-sizing recommendations, and ONNX ML scoring work together as a unified pipeline. Covers data flow, configuration, scheduled tasks, known limitations, and operational status.

---

## 1. Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────┐
│                       EVERY 30 MIN (Celery Beat)                    │
│  AWS Pricing API + Spot Advisor                                      │
│         │                                                            │
│         ▼                                                            │
│  PoolRankingService (8-step pipeline)                                │
│         │  Step 7: ONNX classifier_6 + regressor_6                  │
│         │  ml_score = savings×0.4 − risk×0.6                        │
│         ▼                                                            │
│  Redis: global_pool_rankings:{region}  (TTL 65 min, top 1500 pools) │
└──────────────────────────┬──────────────────────────────────────────┘
                           │
          ┌────────────────┼─────────────────────┐
          ▼                ▼                     ▼
 ─────────────────  ───────────────────  ─────────────────────
 EVERY 1 HR        EVERY 15s             ON DEMAND (user click)
 Karpenter Sync    Auto-Rebalancer       Right-Sizing Apply
 ─────────────────  ───────────────────  ─────────────────────
 Top 10 ML pools   Per-node ranking      Apply recommendation
 → PATCH NodePool  → CORDON/DRAIN        → PATCH_KARPENTER_
   CRD (instance-    /TERMINATE            NODEPOOL action
   type requirements)                    → Karpenter provisions
                                           right-sized type
```

---

## 2. ML Scoring Pipeline

### 2.1 Model Files

| File | Type | Inputs | Output |
|------|------|--------|--------|
| `ml_model/model/classifier_6.onnx` | Binary classifier | 25 features | Float 0-1 (interruption risk probability) |
| `ml_model/model/regressor_6.onnx` | Savings regressor | 25 features | Float 0-1 (normalized savings vs OD baseline) |
| `ml_model/risk_threshold.json` | Config | — | `optimal_threshold: 0.35` (F1-optimized) |

### 2.2 Feature Vector (25 features)

Built by `PoolRankingService._build_feature_vector()` from:
- Instance family (encoded via `category_mapping.json`)
- vCPU count, memory GB, CPU:memory ratio
- Availability zone, AWS region
- Spot Advisor interruption frequency rank (0–5)
- Current spot price, on-demand price, savings %
- Global EMA interruption rate for this pool
- Market volatility signal

### 2.3 Composite Score

```python
ml_score = (savings_pred × 0.4) − (risk_prob × 0.6)
# Higher = better. Pools sorted descending by ml_score.
# Risk gate: pools with risk_prob > risk_ceiling_percent are eliminated before scoring.
```

### 2.4 Pool Ranking Pipeline (8 Steps)

| Step | Name | Purpose |
|------|------|---------|
| 1 | Node Template Filter | Enforce cluster template constraints (vCPU, memory, allowed families) |
| 2 | AZ Filter | Restrict to preferred availability zones |
| 3 | Spot Advisor | Remove pools with AWS interruption rank ≥ 4 |
| 4 | Global Blacklist | Remove Redis-flagged risky pools |
| 5 | Capacity Check | Live AWS capacity validation |
| 6 | Price Fetch | AWS Pricing API: spot + on-demand prices |
| 7 | **ONNX ML Scoring** | classifier_6 + regressor_6 → composite ml_score |
| 8 | Final Ranking | Sort by ml_score, cache to Redis, return top N |

---

## 3. Karpenter Management

### 3.1 KarpenterService Core Methods

#### `sync_ml_rankings_to_nodepool(cluster_id, top_pools, nodepool_name="default")`
- **When called:** Every 1 hour by Celery task `workers.ascpai.sync_karpenter_nodepools`
- **What it does:**
  1. Reads top 10 ML-scored pools from Redis global rankings
  2. Extracts unique instance types and AZs
  3. PATCHes Kubernetes NodePool CRD:
     ```yaml
     spec.template.spec.requirements:
       - key: node.kubernetes.io/instance-type
         operator: In
         values: [c7g.medium, c6g.medium, t3a.medium, ...]  # ML-approved list
       - key: karpenter.sh/capacity-type
         operator: In
         values: [spot]
     ```

#### `switch_to_ondemand(cluster_id)`
- **When called:** Auto-rebalancer finds zero safe spot pools after all filtering
- **What it does:** Patches NodePool `capacity-type: ["on-demand"]`, sets Redis key `spot:ondemand_fallback:{cluster_id}` with 12-hour TTL
- **Auto-revert:** `global_ema.decay` Celery task checks TTL nightly → calls `revert_to_spot()`

#### `detect_karpenter_in_cluster(cluster_id, db)`
- **Checks:** `cluster.karpenter_mode` column → Redis detection key `spot:karpenter:installed:{cluster_id}` → NodePool CRD presence
- **Caches result:** Redis key `karpenter:detected:{cluster_id}` with 5-minute TTL
- **Also sets:** `spot:karpenter:installed:{cluster_id}` (1-hour TTL) for other services

### 3.2 AgentAction Types for Karpenter

| Action Type | Trigger | Effect |
|-------------|---------|--------|
| `INSTALL_KARPENTER` | User clicks "Install" in UI | Helm deploy via agent |
| `UNINSTALL_KARPENTER` | User clicks "Uninstall" | Clean up Karpenter CRDs and controller |
| `PATCH_KARPENTER_NODEPOOL` | ML sync or apply right-sizing | Update NodePool instance-type requirements |

### 3.3 Install Status Detection (Multi-Tier Fallback)

The `/api/v1/karpenter/clusters/{id}/install-status` endpoint checks in order:

1. **AgentAction history** — looks for completed `INSTALL_KARPENTER` action (platform-managed installs)
2. **`cluster.karpenter_mode` column** — set by detect flow; catches config-managed installs
3. **Redis key** `spot:karpenter:installed:{cluster_id}` — set by live detection
4. **Live detection** — `detect_karpenter_in_cluster()` runs NodePool CRD check on demand

> **Result:** Manually installed Karpenter (outside the platform) is correctly shown as INSTALLED.

---

## 4. Right-Sizing Flow

### 4.1 Recommendation Generation

`RightsizingService.generate_recommendations()` follows this process:

```
For each running instance:
    1. Fetch actual K8s pod CPU + memory usage (P95 + 30% headroom)
    2. Call _bin_pack_instance() → recommended vCPU + memory target
    3. Validate against ClusterTemplateMapping constraints (FIX-1)
       → reject if: out of vCPU range, out of memory range, excluded family
    4. Call PoolRankingService.rank_pools_for_size() for best spot pool at new size
    5. Combine: downsize savings + spot migration savings
    6. Create RightsizingProposal record
```

**Output fields per recommendation:**
```json
{
  "current_type": "m5.4xlarge",
  "recommended_type": "m5.xlarge",
  "current_cost_monthly": 560,
  "potential_savings": 420,
  "savings_pct": 75,
  "spot_pool": { "instance_type": "c6i.xlarge", "risk_score": 0.12 },
  "is_upsize": false,
  "reason": "Downsize + spot migration recommended"
}
```

### 4.2 Apply Flow

#### Stateless Nodes (Karpenter-managed)
```
User clicks Apply
  → POST /karpenter/apply-recommendation/{id}
  → Queue PATCH_KARPENTER_NODEPOOL AgentAction
     (instance_types: [recommended_type])
  → Agent patches NodePool CRD
  → Auto-rebalancer queues CORDON → DRAIN → TERMINATE on old node
  → Karpenter provisions replacement on recommended type automatically
```

#### Stateful Nodes (ASG-managed)
```
User clicks Apply
  → Queue CORDON_NODE → DRAIN_NODE → TERMINATE_NODE
  → ASG launches replacement on ORIGINAL instance type
  ⚠️  Right-sizing only takes effect if launch template is manually updated
```

> **Limitation:** Stateful right-sizing does not automatically update the ASG launch template. The user must update it manually for actual size change to persist.

### 4.3 Template Constraint Enforcement

`RightsizingService` enforces `NodeTemplateVersion.constraints_json` which includes:
- `min_vcpu`, `max_vcpu`
- `min_memory_gb`, `max_memory_gb`
- `allowed_families` list (e.g., `["c", "m", "r"]`)
- `excluded_families` list

> **Note:** The global pool rankings cache (TTL 65 min) does NOT enforce template constraints. Client-specific filtering happens at query time on top of the cache.

---

## 5. Global EMA — Cross-Cluster Interruption Tracking

`GlobalEMAService` tracks spot pool reliability across all customers:

| Method | Formula | Purpose |
|--------|---------|---------|
| `update_ema_on_interruption(pool_key, region)` | `new_rate = old_rate × 0.9 + max_rate × 0.1` | Increment on spot interrupt event |
| `apply_decay(pool_key)` | `value *= 0.5 ^ (days / 30)` | 30-day half-life keeps history fresh |
| `get_ema_stats(pool_key)` | Redis → DB fallback | Read-through for current rate |

EMA values feed into the ML feature vector (feature: `global_ema_interrupt_rate`), making the ONNX model aware of observed cross-cluster interruption history — not just AWS Spot Advisor scores.

**Persistence cycle:**
- Redis → `global_ema.persist` task → `GlobalPoolEMA` PostgreSQL table (nightly)
- `global_ema.decay` task applies half-life decay to all entries nightly

---

## 6. Celery Scheduled Tasks

| Task | Schedule | Purpose |
|------|----------|---------|
| `workers.ascpai.execute_pool_ranking_pipeline` | Every 30 min | Regenerate ML-ranked global pool list |
| `workers.ascpai.collect_spot_prices` | Every 30 min | Refresh AWS spot prices in Redis |
| `workers.ascpai.sync_karpenter_nodepools` | Every 1 hour | Patch Karpenter NodePool with top 10 ML pools |
| `workers.rebalancer.execute_rebalancing` | Every 15 sec | Main auto-rebalancer loop per cluster |
| `global_ema.persist` | Nightly | Persist Redis EMA → PostgreSQL |
| `global_ema.decay` | Nightly | Apply 30-day half-life decay to EMA |

---

## 7. Configuration Settings

### ClusterOptimizationSettings

| Field | Default | Effect |
|-------|---------|--------|
| `auto_rebalance_enabled` | `false` | Enables auto-rebalancer Celery task |
| `auto_rightsizing_enabled` | `false` | Enables Karpenter NodePool hourly sync + bin-pack recommendations |
| `auto_stateful_rightsizing_enabled` | `false` | Permits right-sizing proposals for stateful nodes |
| `diversify_pools` | `false` | Enforces max 50% AZ concentration, 40% family concentration |
| `check_interval_seconds` | `15` | How often the rebalancer cycle fires for this cluster |
| `drain_timeout_minutes` | `15` | Graceful pod eviction timeout per node |
| `architecture_preference` | `"both"` | Filter pools to `amd64` / `arm64` / `both` |
| `attach_to_asg_enabled` | `false` | CAST-like: attach replacement node to ASG |
| `max_concurrent_rebalance_actions` | `1` | Parallel rebalancing cap |

### OptimizationStrategy

| Field | Default | Effect |
|-------|---------|--------|
| `strategy_type` | `"BALANCED"` | `COST_FIRST` / `BALANCED` / `NO_DOWNTIME_FIRST` |
| `risk_ceiling_percent` | `25` | Max interruption probability for any selected pool |
| `min_savings_percent` | `15` | Minimum savings required to trigger action |
| `risk_savings_tradeoff_pct` | `20` | Accept pool up to 20% costlier if it's safer |

---

## 8. KarpenterMode Values

| Value | Meaning |
|-------|---------|
| `none` (NULL) | Karpenter not installed or not configured |
| `dry_run` | Karpenter installed; ML rankings computed but NodePool not patched |
| `auto` | Karpenter installed and fully managed; NodePool updated every hour with ML rankings |

---

## 9. End-to-End Flow (Complete Path)

```
[AWS Spot Market]
      │  Prices + Spot Advisor data
      ▼
[PoolRankingService — every 30 min]
  Step 1-6: Filter candidates (template, AZ, Spot Advisor, blacklist, capacity, price)
  Step 7:   ONNX inference → risk_prob, savings_pred → ml_score
  Step 8:   Sort + cache → Redis global_pool_rankings:{region}
      │
      ├──────────────────────────────────────┐
      ▼                                      ▼
[sync_karpenter_nodepools — every 1h]   [Auto-Rebalancer — every 15s]
  Load top 10 pools from Redis           For each ON-DEMAND node:
  Call KarpenterService                    rank_pools_for_node()
  PATCH NodePool CRD                       DecisionEngine policy gates
  → Karpenter can now provision              risk_ceiling, delta_threshold
    only ML-approved types                   diversity check
                                           Queue CORDON→DRAIN→TERMINATE
      │                                        │
      │                              [Agent on node]
      │                                Cordons K8s node
      │                                Drains pods gracefully
      │                                Terminates EC2
      │                                        │
      ▼                                        ▼
[Karpenter Controller]              [Karpenter Controller]
  Watches NodePool CRD                Sees pending pods
  Provisions replacement node         Launches replacement on
  from ML-approved type list          best available ML-approved type
      │
      ▼
[Right-Sizing (user-triggered)]
  RightsizingService.generate_recommendations()
  User clicks Apply →
    Stateless: PATCH_KARPENTER_NODEPOOL + CORDON/DRAIN/TERMINATE
    Stateful:  CORDON/DRAIN/TERMINATE (launch template must be updated manually)
      │
      ▼
[Global EMA — nightly]
  Interruption events update EMA rates
  EMA feeds back into ML feature vector next run
  Decay applied to maintain 30-day relevance window
```

---

## 10. Known Limitations & Gaps

| # | Issue | Impact | Status |
|---|-------|--------|--------|
| 1 | **ML→Karpenter lag**: Rankings cached 65 min; Karpenter sync is 1 hour → effective lag of up to 125 min before new ML scores reach NodePool | New high-risk pools may be provisioned during lag window | Acceptable in current design. To fix: reduce cache TTL or trigger immediate sync after ranking update |
| 2 | **Stateful right-sizing incomplete**: ASG doesn't update launch template automatically | Stateful nodes keep original size after drain/terminate cycle | Requires `backend/utils/aws/user_data.py` + ASG launch template update on apply |
| 3 | **Global cache vs template mismatch**: `global_pool_rankings` caches all region pools; template constraints applied per-request → cache may include types a specific template forbids | Ranking latency slightly higher; no correctness issue | Intentional design. Template filtering runs at query time on cache |
| 4 | **On-demand fallback visibility**: If `spot:ondemand_fallback:{cluster_id}` TTL expires silently (Redis restart), cluster stays in on-demand mode with no notification | Elevated cost | Add monitoring alert on Redis key re-hydrate on rebalancer startup |
| 5 | **Stateful rightsizing UI**: `RightSizingKarpenterTab.jsx` shows recommendations but apply button queues drain without Karpenter patch | Misleading if user expects Karpenter to resize | UI should indicate "ASG launch template update required" for stateful nodes |

---

## 11. Operational Checklist

For Karpenter + rightsizing + ML to run fully:

```
☐ cluster.karpenter_mode = 'auto'               (set via Karpenter Manager UI)
☐ auto_rebalance_enabled = true                  (Automation Settings)
☐ auto_rightsizing_enabled = true               (Automation Settings)
☐ Agent DaemonSet: 2/2 Running (all nodes)      (kubectl get pods -n spot-optimizer)
☐ Celery worker + beat: both healthy            (docker ps)
☐ Redis responsive                              (docker exec spot-optimizer-redis redis-cli ping)
☐ ONNX model files present:
    ml_model/model/classifier_6.onnx
    ml_model/model/regressor_6.onnx
    ml_model/risk_threshold.json
☐ global_pool_rankings:{region} key in Redis    (redis-cli keys "global_pool_rankings:*")
☐ NodePool CRD exists in cluster:               (kubectl get nodepools)
```
