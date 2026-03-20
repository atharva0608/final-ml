Exactly right. This is the critical missing piece. Let me lay out the complete logic.

---

## The Core Problem With Current Approach

Market View shows pools ranked for the cluster in aggregate. But a cluster can have heterogeneous nodes:

```
Node 1: t3.medium  — 2c/4GB  — running 3 pods, 1.8c/3.2GB used
Node 2: t3.large   — 2c/8GB  — running 5 pods, 1.9c/7.1GB used  
Node 3: t3.xlarge  — 4c/16GB — running 8 pods, 3.6c/14GB used
```

A pool that's valid for Node 1 may be completely invalid for Node 3. The current system ranks pools globally and then tries to apply them to all nodes — which is wrong.

---

## The Correct Mental Model

```
Every node must independently have:
  1. At least 1 valid replacement pool (minimum safety)
  2. Ideally 3-5 ranked alternatives (for fallback resilience)
  3. Its own ranked list based on ITS actual resource usage
     not the cluster's average or the largest node's spec
```

---

## Part 1 — Per-Node Resource Profile

Before ranking pools, build a resource profile for each node:

```
NodeProfile:
  node_id
  instance_type          = t3.medium
  vcpu_total             = 2
  memory_gb_total        = 4
  vcpu_requested         = 1.8    ← sum of all pod CPU requests on this node
  memory_gb_requested    = 3.2    ← sum of all pod memory requests on this node
  vcpu_headroom_pct      = 10     ← from cluster config, default 10%
  memory_headroom_pct    = 10
  
  # Effective minimums for replacement:
  min_vcpu_required      = ceil(vcpu_requested × (1 + headroom_pct/100))
                         = ceil(1.8 × 1.10) = 2
  min_memory_required    = ceil(memory_gb_requested × (1 + headroom_pct/100))
                         = ceil(3.2 × 1.10) = 3.52 → round up to 4GB
  
  # Hard constraints from workloads:
  has_gpu_pods           = false
  has_local_pv           = false   ← if true, node cannot be rebalanced at all
  has_stateful_pods      = false
  architecture_required  = amd64
  node_selector_labels   = {team: backend}
  taint_tolerations      = [spot:NoSchedule]
```

This profile is built from live Kubernetes data — actual pod requests, not the node's total capacity.

---

## Part 2 — Per-Node Hard Gates

Each node runs its own independent gate check against every pool:

```
Gate 1: spot_price < source_od_price
        → source_od_price = OD price of THIS node's instance type
        → not the cluster average

Gate 2: candidate_vcpu >= node.min_vcpu_required
        → based on actual pod requests + headroom
        → NOT just >= source_vcpu (that's too loose for underutilized nodes
           and too tight for heavily utilized ones)

Gate 3: candidate_memory_gb >= node.min_memory_required
        → same — based on actual usage

Gate 4: interruption_rate <= profile_risk_ceiling
        → same across all nodes for a given profile

Gate 5: architecture == node.architecture_required
        → per-node, in case cluster has mixed arch nodes

Gate 6: nodeSelector compatibility
        → if node has label team=backend, replacement must support same labels
        → labels transfer to new node at launch time but instance type
           must support the workload type (GPU, EFA, etc.)

Gate 7: not blacklisted

Gate 8: subnet IPs >= 10 in node's AZ
        → check per-AZ not per-region

Gate 9: local PV check
        → if node has pods with local PersistentVolumes, 
          mark node as IMMOVABLE, skip entirely
        → cannot rebalance stateful nodes with local storage
```

---

## Part 3 — Per-Node Scoring and Alternative Pool Set

After gates, every node gets its own ranked alternative list:

```
For each node:
  1. Run all pools through per-node gates
  2. Score each passing pool:
     savings_score = (node_od_price - pool_spot_price) / node_od_price
     safety_score  = 1 - interruption_rate_normalized
     ml_score      = ONNX model output for this pool
     
     final_score = (W_savings × savings_score)
                 + (W_risk    × safety_score)
                 + (W_ml      × ml_score)
  
  3. Sort by final_score DESC
  4. Store as node.alternative_pools = [pool1, pool2, pool3 ... poolN]
  
  The execution engine uses this list for THIS node when rebalancing.
  If pool1 launch fails → try pool2, pool3, etc.
  
  Coverage check:
    len(node.alternative_pools) == 0 → node is STRANDED (no valid replacement exists)
    len(node.alternative_pools) == 1 → node is AT RISK (only one option, no fallback)
    len(node.alternative_pools) >= 3 → node is COVERED (good fallback resilience)
```

---

## Part 4 — Cluster-Wide Coverage View

After computing per-node alternatives, aggregate to cluster level:

```
ClusterCoverageReport:
  cluster_id
  total_nodes            = 5
  
  covered_nodes          = 4   (>= 3 alternatives each)
  at_risk_nodes          = 1   (1-2 alternatives only)
  stranded_nodes         = 0   (0 alternatives — cannot be rebalanced)
  immovable_nodes        = 0   (local PV — excluded from rebalancing)
  
  cluster_coverage_pct   = 80% (covered / rebalanceable nodes)
  
  per_node_summary: [
    {
      node_id: "i-abc123",
      instance_type: "t3.medium",
      status: "COVERED",
      alternative_count: 23,
      best_alternative: "t3a.medium",
      best_saving_pct: 70%,
      best_risk: "<5%"
    },
    {
      node_id: "i-def456", 
      instance_type: "t3.xlarge",
      status: "AT_RISK",
      alternative_count: 2,
      best_alternative: "t3a.xlarge",
      best_saving_pct: 35%,
      best_risk: "5-10%"
    }
  ]
```

---

## Part 5 — What Cluster Impact View Should Show

This maps directly to your existing "Cluster Impact View" tab which currently shows nothing useful:

```
CLUSTER IMPACT VIEW
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Cluster Coverage: 80% ████████░░ 4/5 nodes covered

┌──────────────┬──────────────┬────────┬──────────────┬──────────────┬─────────┐
│ Node         │ Current Type │ Status │ Alternatives │ Best Option  │ Saving  │
├──────────────┼──────────────┼────────┼──────────────┼──────────────┼─────────┤
│ i-abc123     │ t3.medium    │ ✅ 23  │ 23 options   │ t3a.medium   │ 70%     │
│ i-def456     │ t3.medium    │ ✅ 21  │ 21 options   │ t3a.medium   │ 70%     │
│ i-ghi789     │ t3.large     │ ✅ 18  │ 18 options   │ t3a.large    │ 42%     │
│ i-jkl012     │ t3.xlarge    │ ⚠️ 2   │ 2 options    │ t3a.xlarge   │ 35%     │
│ i-mno345     │ t3.2xlarge   │ 🔴 0   │ No valid     │ —            │ —       │
└──────────────┴──────────────┴────────┴──────────────┴──────────────┴─────────┘

⚠️  Node i-jkl012 has limited fallback options. 
    Consider adjusting risk profile or enabling arm64.

🔴  Node i-mno345 has no valid spot alternatives at current profile.
    All pools either cost more than OD or exceed risk ceiling.
    Options: switch to COST_FIRST profile, or keep this node On-Demand.
```

Clicking any node row expands to show its full ranked alternative list (paginated).

---

## Part 6 — Node-Specific View (The Third Tab Fixed)

Node-Specific View should show the per-node ranked pool list for a selected node:

```
NODE-SPECIFIC VIEW — i-abc123 (t3.medium)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Node Resources:   2 vCPU / 4GB RAM
Pod Usage:        1.8 vCPU / 3.2GB (actual requests)
Min Required:     2 vCPU / 4GB (with 10% headroom)
Architecture:     amd64

23 valid alternatives found  |  Page 1 of 2

Rank  Type          AZ           Size    Spot/hr   Saving  Risk    Score
1     t3a.medium    ap-south-1a  2c/4GB  $0.0139   70%     <5%     0.824
2     c5.large      ap-south-1a  2c/4GB  $0.0220   52%     <5%     0.748
3     m5.large      ap-south-1a  2c/8GB  $0.0260   44%     <5%     0.708
4     t3.large      ap-south-1a  2c/8GB  $0.0228   51%     <5%     0.732
...
20    m4.large      ap-south-1b  2c/8GB  $0.0271   42%     5-10%   0.651

[←] [1] [2] [→]
```

---

## Part 7 — Market View vs Node-Specific View vs Cluster Impact View

```
Market View:
  Shows ALL valid pools for the region
  Ranked by final_score considering the MAJORITY node type in cluster
  (or user-selected source type)
  Paginated, unlimited
  Purpose: "What are the best pools available right now?"

Node-Specific View:
  Shows valid pools for ONE selected node
  Ranked using THAT node's actual pod requests and resource profile
  Paginated, unlimited
  Purpose: "What can replace THIS specific node?"

Cluster Impact View:
  Shows coverage summary for ALL nodes
  Per-node: status, alternative count, best option, savings
  Expandable rows showing per-node alternatives
  Purpose: "Is every node in my cluster protected? 
            Which nodes have no fallback?"
```

---

## Part 8 — Backend API Changes

```
# Existing (fix this):
GET /clusters/{id}/market-view
  → Returns region-wide pools with no source context
  → Fix: use cluster's most common node type as source context

# Enhanced Node-Specific:
GET /clusters/{id}/nodes/{node_id}/alternatives
  ?page=1&page_size=20&sort_by=final_score
  → Returns per-node alternatives using actual pod requests
  → Response includes node resource profile, coverage status

# New Cluster Coverage:
GET /clusters/{id}/coverage
  → Returns ClusterCoverageReport
  → Per-node status: COVERED / AT_RISK / STRANDED / IMMOVABLE
  → Refreshed every 5 minutes by reconciliation worker
  → Cached in Redis: cluster_coverage:{cluster_id} TTL=300s

# Coverage refresh trigger:
  After every pool ranking update OR spot advisor scrape:
    invalidate cluster_coverage:{cluster_id}
    frontend re-fetches on next poll
```

---

## Part 9 — Execution Engine Uses Per-Node List

This is the most important part. When the rebalancer fires for a node, it must use that node's pre-computed alternative list, not a fresh global ranking:

```
Rebalancing sequence for node i-abc123:

1. Load node.alternative_pools (pre-computed, sorted by final_score)
   = [t3a.medium, c5.large, m5.large, t3.large, ... 23 total]

2. Check if list is stale (> 15 minutes old)
   If stale → recompute from fresh pool data before launching

3. Try alternative_pools[0] → t3a.medium
   → Launch success → done

4. If launch fails:
   → report_launch_failure(t3a.medium:ap-south-1a)
   → set dry_run:{pool_key} = fail TTL 300s
   → try alternative_pools[1] → c5.large
   → continues through list up to max_instance_type_attempts

5. If ALL attempts fail:
   → node goes to STRANDED status
   → alert sent
   → next rebalancing cycle will recompute fresh alternatives
     (blacklists will eliminate failed pools, new options may appear)
```

---

## Part 10 — Complete File Change Map

| File | Change |
|---|---|
| `backend/core/decision_engine.py` | Add `build_node_profile()` from live K8s pod requests. Add `rank_for_node(node_profile)` that uses actual min_vcpu and min_memory not just instance type totals. Remove all global caps. |
| `backend/workers/tasks/auto_rebalancer.py` | Load per-node alternative list at rebalancing time. Check staleness. Use this list for launch attempts. |
| `backend/workers/tasks/reconciliation_worker.py` | Add coverage computation every 5 min. Write ClusterCoverageReport to Redis. Mark nodes as COVERED/AT_RISK/STRANDED/IMMOVABLE. |
| `backend/api/{ranking_endpoint}` | Add `/nodes/{node_id}/alternatives` endpoint. Add `/clusters/{id}/coverage` endpoint. Fix market-view to use cluster's primary node type as source context. |
| `backend/models/cluster.py` | Add `ClusterBaseline` model. Add `NodeAlternativeCache` model storing per-node alternative list with computed_at timestamp. |
| `backend/services/workload_inspector.py` | Extend to return per-node pod resource totals (sum of requests). Already has STATELESS/STATEFUL classification — add local PV detection for IMMOVABLE flag. |
| `spot_advisor_scraper.py` | Fix KeyError→None, fix OS namespace, fix index map, write last_scraped timestamp. |
| `pool_ranking_service.py` | Add staleness gate on last_scraped. Add savings_score and safety_score components. Add profile weight table. |
| `frontend MarketView` | Add pagination, sort controls, live indicator, source node context display. |
| `frontend NodeSpecificView` | Show per-node alternatives with actual pod usage context, pagination. |
| `frontend ClusterImpactView` | Show per-node coverage table: status, alternative count, best option, savings. Expandable rows. |

---

## The Single Rule That Ties It All Together

```
Backend execution engine:
  Uses per-node alternative list
  Built from actual pod requests (not just instance type capacity)
  Contains ALL valid pools (no UI cap)
  Tries them in order until launch succeeds

Frontend display:
  Shows the same data
  Paginated for usability
  Three views: region-wide / per-node / cluster coverage
  Never constrains what the backend can use

These two systems share the same ranking logic
but are completely independent in their consumption of it.
```