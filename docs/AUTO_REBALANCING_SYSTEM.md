# Auto-Rebalancing System — Complete Technical Reference

> **Scope:** Non-Karpenter (direct EC2 launch) auto-rebalancing pipeline, cluster settings, DB/Redis state management, rollback, locks, cooldowns, cleanup, AMI selection, spot request method, and AWS permissions.

---

## Table of Contents

1. [System Overview](#1-system-overview)
2. [Architecture Diagram](#2-architecture-diagram)
3. [Celery Task Schedule](#3-celery-task-schedule)
4. [Cluster Optimization Settings](#4-cluster-optimization-settings)
5. [Auto-Rebalancer: Step-by-Step Execution](#5-auto-rebalancer-step-by-step-execution)
6. [Security Gates & Pre-Checks](#6-security-gates--pre-checks)
7. [Instance Selection & Pool Ranking](#7-instance-selection--pool-ranking)
8. [Diversification Logic](#8-diversification-logic)
9. [Decision Engine V3 — 15-Step Pipeline](#9-decision-engine-v3--15-step-pipeline)
10. [Spot Instance Launch (boto3)](#10-spot-instance-launch-boto3)
11. [AMI Selection & User-Data](#11-ami-selection--user-data)
12. [ASG Handling (Atomic Terminate with Decrement)](#12-asg-handling-atomic-terminate-with-decrement)
13. [2-Phase Provision-and-Wait Architecture](#13-2-phase-provision-and-wait-architecture)
14. [Rollback & Failure Handling](#14-rollback--failure-handling)
15. [State Machine (RebalancingAction)](#15-state-machine-rebalancingaction)
16. [DB Models](#16-db-models)
17. [Redis State Management](#17-redis-state-management)
18. [Stale Data Prevention](#18-stale-data-prevention)
19. [Cleanup Mechanisms](#19-cleanup-mechanisms)
20. [Blacklist & Reputation System](#20-blacklist--reputation-system)
21. [Cache Builder (market_view_cache)](#21-cache-builder-market_view_cache)
22. [Global Pool Cache Builder — 8-Step Pipeline](#22-global-pool-cache-builder--8-step-pipeline)
23. [Termination Monitor (Spot Interruptions)](#23-termination-monitor-spot-interruptions)
24. [Recovery Monitor (Orphan & Stall Detection)](#24-recovery-monitor-orphan--stall-detection)
25. [Reconciliation Worker](#25-reconciliation-worker)
26. [AWS Permissions Required](#26-aws-permissions-required)
27. [Key Formulas & Constants](#27-key-formulas--constants)
28. [Complete Redis Key Reference](#28-complete-redis-key-reference)

---

## 1. System Overview

The auto-rebalancing system converts On-Demand (OD) EKS nodes to Spot instances to reduce costs by 40–80%. It runs **without Karpenter** — the backend directly launches EC2 spot instances, copies the source node's AMI/user-data/security-groups, then cordons → drains → terminates the OD node via an in-cluster agent.

**Core Components:**

| Component | Container | Purpose |
|-----------|-----------|---------|
| `auto_rebalancer` | `celery-worker` | Main rebalancing loop (every 15s) |
| `termination_monitor` | `celery-worker` | Detect spot interruptions (every 30s) |
| `recovery_monitor` | `celery-worker` | Orphan cleanup & stall detection (every 60s) |
| `reconciliation_worker` | `celery-worker` | DB↔AWS state sync (every 5 min) |
| `discovery_worker` | `celery-worker` | EC2/EKS discovery & stale cleanup (every 5 min) |
| `cache_builder` | `celery-worker` | Build pool rankings cache (every 60 min) |
| `health_worker` | `celery-worker` | Zombie node & stale agent cleanup (every 1–2 min) |
| `in-cluster agent` | K8s DaemonSet | Sends metrics, executes cordon/drain/terminate |

**Data Flow:**
```
Agent (metrics/heartbeat) → Backend API → PostgreSQL (instances, clusters)
                                       → Redis (cache, locks, state)
Celery Beat (schedule) → Celery Worker → auto_rebalancer
                                       → boto3 EC2 (launch spot)
                                       → Agent WebSocket (cordon/drain/terminate)
```

---

## 2. Architecture Diagram

```
┌─────────────────────────────────────────────────────────────┐
│                    CELERY BEAT (Scheduler)                    │
│  auto_rebalancer (15s) • discovery (5m) • reconcile (5m)    │
│  termination_monitor (30s) • recovery (60s) • health (2m)   │
└──────────────┬──────────────────────────────────────────────┘
               │ dispatches tasks
               ▼
┌─────────────────────────────────────────────────────────────┐
│                    CELERY WORKER                             │
│                                                              │
│  ┌────────────────────┐     ┌────────────────────────────┐  │
│  │  auto_rebalancer   │     │  Pool Ranking Service      │  │
│  │  ┌──────────────┐  │     │  • ML/ONNX scoring         │  │
│  │  │ 6 Safety     │  │◄────│  • 3-signal blended risk     │  │
│  │  │ Gates        │  │     │  • capacity validation     │  │
│  │  └──────┬───────┘  │     └────────────────────────────┘  │
│  │         │          │                                      │
│  │  ┌──────▼───────┐  │     ┌────────────────────────────┐  │
│  │  │ Select OD    │  │     │  Decision Engine V3        │  │
│  │  │ Instance     │──┼────►│  • 15-step pipeline        │  │
│  │  └──────┬───────┘  │     │  • EV formula              │  │
│  │         │          │     │  • risk ceiling             │  │
│  │  ┌──────▼───────┐  │     └────────────────────────────┘  │
│  │  │ boto3        │  │                                      │
│  │  │ run_instances│──┼────► AWS EC2 (Spot)                  │
│  │  └──────┬───────┘  │                                      │
│  │         │          │     ┌────────────────────────────┐  │
│  │  ┌──────▼───────┐  │     │  Diversity Enforcer        │  │
│  │  │ Wait for     │  │     │  • family ratio cap        │  │
│  │  │ K8s join     │──┼────►│  • AZ ratio cap            │  │
│  │  └──────┬───────┘  │     │  • instance_type dedup     │  │
│  │         │          │     └────────────────────────────┘  │
│  │  ┌──────▼───────┐  │                                      │
│  │  │ Agent Actions│──┼────► In-Cluster Agent (WebSocket)    │
│  │  │ CORDON→DRAIN │  │     │  cordon → drain → terminate   │
│  │  │ →TERMINATE   │  │     └────────────────────────────┘  │
│  │  └──────────────┘  │                                      │
│  └────────────────────┘                                      │
│                                                              │
│  ┌────────────────┐  ┌──────────────┐  ┌─────────────────┐  │
│  │ reconciliation │  │ recovery     │  │ termination     │  │
│  │ worker         │  │ monitor      │  │ monitor         │  │
│  │ (DB ↔ AWS)     │  │ (orphans)    │  │ (interruptions) │  │
│  └────────────────┘  └──────────────┘  └─────────────────┘  │
└──────────────────────────────────────────────────────────────┘
               │                    │
               ▼                    ▼
┌──────────────────┐    ┌──────────────────┐
│   PostgreSQL     │    │      Redis       │
│  • instances     │    │  • locks         │
│  • clusters      │    │  • cooldowns     │
│  • rebalancing   │    │  • cache         │
│    _actions      │    │  • state         │
│  • accounts      │    │  • blacklists    │
└──────────────────┘    └──────────────────┘
```

---

## 3. Celery Task Schedule

Defined in `backend/workers/app.py`:

| Task Name | Schedule | Celery Task ID | Purpose |
|-----------|----------|----------------|---------|
| `auto-rebalancer-every-15-secs` | 15s | `workers.auto_rebalancer` | Main rebalance loop |
| `termination-monitor-every-30-secs` | 30s | `workers.termination_monitor` | Spot interruption detection |
| `ascp-auto-scaler-every-30-secs` | 30s | `workers.auto_scaler.run` | Horizontal scaling |
| `ee-recovery-monitor-every-60-secs` | 60s | `recovery_monitor` | Orphan + stall recovery |
| `reset-stale-agents-every-minute` | 60s | `backend.workers.tasks.health.reset_stale_agents` | Agent heartbeat check; cancels PENDING/PICKED_UP AgentActions + marks in_progress/waiting_agent RebalancingActions as failed with `AGENT_WENT_OFFLINE`; deletes `action_heartbeat:{id}` keys (BUG-9) |
| `zombie-cleanup-every-2-mins` | 120s | `backend.workers.tasks.health.cleanup_zombie_nodes` | Zombie node detection |
| `zombie-od-cleanup-every-hour` | 3600s | `backend.workers.tasks.health.cleanup_zombie_od_instances` | Z1 fix: Terminate OD instances with no K8s node after 10 min |
| `cluster-pools-sync-every-30-mins` | 1800s | `backend.workers.tasks.health.sync_cluster_pools` | Z5 fix: Rebuild `cluster_pools` Redis set from DB state |
| `discovery-every-5-mins` | 300s | `workers.discovery.scan_all_accounts` | EC2/EKS resource sync |
| `reconciliation-every-5-mins` | 300s | `workers.reconciliation_worker` | DB ↔ AWS state sync |
| `karpenter-nodepool-sync-every-30-secs` | 30s | `workers.ascpai.sync_karpenter_nodepools` | NodePool sync |
| `sqs-interrupt-consumer-every-30-secs` | 30s | `workers.sqs_consumer.poll_interruption_queues` | SQS interruption events |
| `hibernation-scheduler-every-1-min` | 60s | `execute_hibernation_scheduler` | Hibernation schedule |

---

## 4. Cluster Optimization Settings

Stored in `ClusterOptimizationSettings` (1:1 with Cluster):

### Diversification Settings

| Column | Type | Default | Description |
|--------|------|---------|-------------|
| `diversify_pools` | Boolean | `False` | Enable pool-level diversification |
| `instance_type_diversification_pct` | Integer | `100` | 100% = every node gets a unique type; 0% = no constraint |
| `architecture_preference` | String | `"both"` | `"amd64"` / `"arm64"` / `"both"` — filter candidate pools |
| `max_family_diversification_cap_pct` | Integer | `40` | Max % of cluster nodes in one instance family |

### Rebalancing Settings

| Column | Type | Default | Description |
|--------|------|---------|-------------|
| `max_instance_type_attempts` | Integer | `6` | Cascade fallback limit per launch |
| `spot_join_timeout_minutes` | Integer | `30` | Max time waiting for spot to join K8s |
| `drain_timeout_minutes` | Integer | `15` | Max pod drain wait before forced termination (Problem #11) |
| `max_concurrent_rebalance_actions` | Integer | `NULL` (=1) | Concurrent rebalances per cluster. Enforced per-cluster via `rebalance:active_count:{cluster_id}` Redis semaphore with atomic INCR/DECR (BUG-7 fix) |
| `check_interval_seconds` | Integer | `15` | Per-cluster rebalance interval gate |

### Scaling Settings

| Column | Type | Default | Description |
|--------|------|---------|-------------|
| `min_node_count` | Integer | — | Floor for scale-down |
| `scale_down_threshold_pct` | Integer | — | CPU threshold for scale-down |
| `scale_down_stabilization_minutes` | Integer | — | Wait time before scale-down |
| `enable_ascp_auto_scaler` | Boolean | — | Enable/disable auto-scaler |

### Optimization Strategy (separate model)

| Column | Type | Purpose |
|--------|------|---------|
| `risk_ceiling_percent` | Integer | Max acceptable risk (per profile) |
| `min_savings_percent` | Integer | Minimum savings to justify rebalance |
| `volatility_tolerance_percent` | Integer | Market volatility tolerance |
| `risk_savings_tradeoff_pct` | Integer | Accept X% more expensive if safer |

### Optimization Profiles

| Profile | Risk Ceiling | Delta Threshold | Description |
|---------|-------------|-----------------|-------------|
| `COST_FIRST` | 25% | 2% EV improvement | Maximize savings, accept higher risk |
| `BALANCED` | 20% | 3% EV improvement | Balance cost and stability |
| `NO_DOWNTIME_FIRST` | 10% | 4% EV improvement | Minimize disruption risk |

---

## 5. Auto-Rebalancer: Step-by-Step Execution

**Entry Point:** `execute_rebalancing()` in `backend/workers/tasks/auto_rebalancer.py`  
**Frequency:** Every 15 seconds  
**Lock:** `lock:workers.auto_rebalancer` (HeartbeatLock, 300s timeout, 150s heartbeat renewal)

### Step 0: Stale Action Expiry
- Check `in_progress` / `waiting_agent` actions older than **45 minutes**
- **Per-state timeouts (Problem #19):** Also check actions within 45-min window against per-state limits:
  - `waiting_for_spot_node`: 28 min (must be ≤ `spot_join_timeout_minutes` default of 30 min)
  - `cordoning_node`: 10 min
  - `draining_pods`: 20 min
  - `verifying_pod_readiness`: 20 min
  - `terminating_source`: 10 min
- **Action heartbeat:** Two writers keep the key alive: the backend Celery worker refreshes it every ~15s (each rebalancer cycle) AND the agent's `_action_heartbeat_loop()` POSTs to the backend every 30s during execution (N5 fix). If both stop refreshing for >2 min, action is marked failed.
- Mark as `failed`
- **Rollback:** Terminate orphaned spot EC2 instance if one was launched (via `rollback_terminated_spot()`)

### Step 1: Resolve `waiting_agent` Actions (Phase 2)
- Find actions in `waiting_agent` status
- Check if replacement spot has joined K8s
- **Proactive polling (Problem #12):** If pinned instance not found as `running` in DB:
  - Check DB for `node_name` (agent heartbeat may have set it)
  - Check Redis `node_joined:{instance_id}` key as fallback
  - If either present, consider instance joined and proceed
- If joined → create AgentActions: `CORDON → DRAIN → TERMINATE`
- If timeout (30 min default) → mark `failed` + terminate spot

### Step 2: Gate Checks (6 Sequential Gates)
1. **Cluster Cooldown** — `spot:cooldown:action:{cluster_id}` (3600s+ TTL)
2. **Concurrency Lock** — `rebalance:lock:{cluster_id}` (NX SET, **2700s TTL** with heartbeat renewal every 60s — Problem #1/#7, NEW-3 fix; matches the 45-min stale action threshold exactly — lock cannot expire before stale detection fires)
3. **Stabilization Lock** — `spot:stabilization_lock:{cluster_id}` (60–90s TTL)
4. **Warm Spare Mutex** — `spot:substitute:state:{cluster_id}`
5. **Resize Cooldown** — `spot:cooldown:action:resize:{cluster_id}`
6. **Double-Launch Guard** — Check `action_metadata['replacement_spot_instance_id']`

### Step 3: Select OD Instance to Rebalance
```python
db.query(Instance).filter(
    Instance.cluster_id == cluster_id,
    Instance.lifecycle == InstanceLifecycle.ON_DEMAND,
    Instance.state == 'running',
    Instance.instance_id.like('i-%')   # Exclude ip- placeholders
)
```
- Filter out instances with per-instance cooldown: `spot:rebalanced:instance:{instance_id}` (24h)
- Filter out instances with active action: `spot:node_active_action:{instance_id}`
- Filter out instances with exponential backoff from failures

### Step 4: Rank Pools & Select Target
- Call `PoolRankingService.rank_pools_for_node(node_info, cluster_id, region, include_dynamic_filters=True)`
- Applies all filters internally: blacklist, vCPU/memory floors, architecture, risk ceiling, NodeTemplate families/zones/cross-AZ, occupancy, family diversification cap
- Sort key: `expected_value = savings_pct × (1 − risk_probability)` DESC
- Apply per-cluster block list check: `spot:launch_blocked:{cluster_id}:{type}:{az}` (`spot_join_timeout_minutes × 60` after no-join timeout, default 1800s; 1800s/30 min after ≥3 capacity failures for same pool+cluster)
- Cascade through up to `max_instance_type_attempts` (default: 6) types

### Step 5: Launch Spot Instance (Phase 1)
- Call `_launch_spot_instance_direct()` (see §10)
- On success → set action to `waiting_agent` status
- On failure → cascade to next instance type

### Step 6: Wait for K8s Join (Phase 2)
- 90s stabilization window + up to 30 min total
- Check by pinned instance ID: `replacement_spot_instance_id` in metadata
- When joined → proceed to cordon/drain/terminate

### Step 7: Cordon → Drain → Terminate
- Create AgentActions sent to in-cluster agent via WebSocket:
  1. `CORDON` — Mark node unschedulable
  2. `DRAIN` — Evict pods with PDB respect controlled by `respect_pdb_enabled` in `StatelessRuntimeRules` (N1 fix): `force=True` (bypass PDB) when `respect_pdb_enabled=False`; `force=False` (respect PDB, 5 retries) when `respect_pdb_enabled=True`
  3. `TERMINATE` — `kubectl delete node` + EC2 terminate
- **20-second grace period** after drain for pod evacuation
- **Configurable drain timeout (Problem #11):** Default 15 min, per-cluster via `ClusterOptimizationSettings.drain_timeout_minutes`
- Progressive pod monitoring via pod_metrics

### Step 8: ASG Atomic Terminate
- Call `terminate_instance_in_auto_scaling_group(InstanceId=source_id, ShouldDecrementDesiredCapacity=True)`
- Single atomic call: terminates EC2 + decrements ASG DesiredCapacity (see §12)
- No ASG process suspension or manual capacity update needed
- Retries up to 3 times on throttling; falls back to direct EC2 terminate on ValidationError (instance already detached)

### Step 9: Final Cleanup
- Mark action `completed`
- Set per-instance cooldown: `spot:rebalanced:instance:{source_id}` (24h)
- Set stabilization lock: `spot:stabilization_lock:{cluster_id}` (90s)
- Release concurrency lock
- Calculate realized savings

---

## 6. Security Gates & Pre-Checks

| # | Gate | Redis Key | TTL | Rule |
|---|------|-----------|-----|------|
| 1 | Cluster Cooldown | `spot:cooldown:action:{cluster_id}` | 3600s+ | Bypass allowed for OD→SPOT |
| 2 | Concurrency Lock | `rebalance:lock:{cluster_id}` | 2700s | NX SET — only 1 rebalance/cluster (heartbeat renewed every 60s; matches 45-min stale threshold exactly — NEW-3 fix) |
| 3 | Stabilization Lock | `spot:stabilization_lock:{cluster_id}` | 60–90s | Post-action grace period |
| 4 | Warm Spare Mutex | `spot:substitute:state:{cluster_id}` | varies | Block if prewarming/releasing |
| 5 | Resize Cooldown | `spot:cooldown:action:resize:{cluster_id}` | varies | Don't drain during right-sizing |
| 6 | Double-Launch Guard | `action_metadata['replacement_spot_instance_id']` | — | Skip Phase 1 if spot already launched |

**Per-Instance Gates:**

| Gate | Redis Key | TTL | Rule |
|------|-----------|-----|------|
| Recently Rebalanced | `spot:rebalanced:instance:{instance_id}` | 86400s (24h) | Don't re-target same OD node |
| Active Action | `spot:node_active_action:{instance_id}` | 86400s | Node has in-flight rebalance (Z6 fix: 24h safety-net TTL; deleted on stale expiry) |
| Failure Backoff | `rebalance_failures:{instance_id}` | 86400s | Exponential backoff counter |
| Post-Launch Cooldown | `spot:post_launch_cooldown:{instance_id}` | 60s | New spot settlement grace |
| S2S Suppressed | `spot:s2s_suppressed:{instance_id}` | 180s | Post-fallback suppress |

### Agent Endpoint Authentication (BUG-10 fix)

All 5 agent endpoints (`/register`, `/heartbeat`, `/actions/{id}/heartbeat`, `/actions/{id}/result`, `/deregister`) require `Authorization: Bearer {AGENT_API_KEY}`. Token is validated via `Depends(verify_agent_token)` in `backend/routers/agents.py`. Unauthenticated requests return HTTP 401. `AGENT_API_KEY` must be set as a backend environment variable — same value as the agent’s `API_KEY` env var (the agent already sends `Authorization: Bearer {API_KEY}` on all HTTP calls).

---

## 7. Instance Selection & Pool Ranking

### Source Node Selection
```python
# Query all running OD instances with real EC2 IDs
on_demand_instances = db.query(Instance).filter(
    Instance.cluster_id == cluster_id,
    Instance.lifecycle == InstanceLifecycle.ON_DEMAND,
    Instance.state == 'running',
    Instance.instance_id.like('i-%')
).all()

# Filter out recently rebalanced (24h cooldown)
# Filter out nodes with active actions
# Filter out nodes in exponential backoff
```

### Pool Selection Pipeline

1. **Unified Ranking** — `PoolRankingService.rank_pools_for_node(node_info, cluster_id, region, include_dynamic_filters=True)` applies all filters internally and returns pools sorted by `expected_value = savings_pct × (1 − risk_probability)` DESC.  
   Filters applied **inside** this single function call: blacklist, vCPU/memory floors, architecture (from node `resource_profile`), risk ceiling, NodeTemplate `allowed_families`/`excluded_families`/`allowed_zones`/`cross_az_rebalance`, occupancy dedup (skip `(type, az)` already running/pending), family diversification cap (max 2 pools per family when `diversify_pools=True`), `min_savings_percent` threshold (N2 fix — now enforced).

   > **Fallback abort (NEW-2 fix):** If the source node’s instance type is not in the spec table and falls back to heuristic derivation, `_lookup_specs()` returns `is_fallback=True`. In that case, `rank_pools_for_node()` logs CRITICAL, returns an empty list, and the node is skipped this cycle. This prevents ranking against inaccurate vCPU/memory baselines.

2. **Block List** — After ranking, skip pools in `spot:launch_blocked:{cluster_id}:{type}:{az}` (`spot_join_timeout_minutes × 60` after no-join timeout, default 1800s; 1800s after ≥3 capacity failures for same pool+cluster).

3. **Cascade Fallback** — Try up to `max_instance_type_attempts` (default: 6) types from the ranked list.

> **Note on `rank_pools_for_size()`:** A separate legacy function `rank_pools_for_size()` exists in `pool_ranking_service.py` and is used in secondary paths: standby warm-spare, opportunistic spot, and OD→Spot Pass 1/2. It does **not** apply NodeTemplate constraints. It should not be confused with `rank_pools_for_node()`, which is the primary per-rebalance pipeline.

### Cascade Fallback
- Try up to `max_instance_type_attempts` (default: 6) types
- Deterministic idempotency token: `sha256(source_id:type)` for each attempt
- On capacity failure → blacklist for 6 hours, try next type
- If all fail → mark action `failed`, set exponential backoff

---

## 8. Diversification Logic

### In the Main Rebalancing Loop (`auto_rebalancer.py`)

Diversification is handled **inside `rank_pools_for_node()`** — there is no separate enforcement layer in the main loop.

**Occupancy Dedup (always applied):**
- Build `_occupied_pools` set: all `(instance_type, az)` pairs already running/pending in the cluster.
- Skip any candidate pool whose `(type, az)` is already in `_occupied_pools`.

**Family Diversification Cap (when `diversify_pools = True`):**
- Track how many selected pools belong to each instance family (`m`, `c`, `r`, etc.).
- Apply a **fixed cap of max 2 pools per family** in the returned ranked list.
- The `instance_type_diversification_pct` setting has **no effect** in the rebalancer — it applies only in the UI alternatives list endpoint (`ascpai_routes.py:1554`).

**When `diversify_pools = False`:**
- Occupancy dedup is still applied.
- Family cap is disabled — multiple pools in the same family are eligible.

---

### `DiversityEnforcer` (NOT used in main rebalancing loop)

`DiversityEnforcer` (in `backend/services/diversity_enforcer.py`) applies profile-specific family/AZ ratio caps. It is called from **`DecisionEngine.evaluate_action_plan()`** (Karpenter integration and API recommendation paths) and **`SubstituteManager`**, but is **not called** from `auto_rebalancer.py`.

Profile-specific thresholds (for reference — only applied via `evaluate_action_plan` and `SubstituteManager`):

| Profile | max_family_ratio | max_az_ratio |
|---------|-----------------|--------------|
| COST_FIRST | 40% | 50% |
| BALANCED | 40% | 50% |
| NO_DOWNTIME_FIRST | 30% | 40% |

---

## 9. Decision Engine V3 — Policy Evaluation Pipeline

Located in `backend/core/decision_engine.py`:

> **Note:** The `evaluate_action_plan` function is a **policy-evaluation utility** — it is NOT called in the main `auto_rebalancer.py` execution loop. The main rebalancing loop calls `PoolRankingService.rank_pools_for_node()` directly (see §7). `evaluate_action_plan` is available for API-driven recommendations and Karpenter evaluation paths.

| Step | Name | Gate Type | Action |
|------|------|-----------|--------|
| 1 | Cluster Cooldown | CooldownController | Skip if cooling |
| 2 | Pricing Freshness | Staleness check | Penalty 0.95 if >15 min old |
| 3 | Pool Cooldown Filter | Per-pool cooldown | Remove cooled pools |
| 4 | Node Classification | WorkloadInspector | Get cached status |
| 5 | Eligibility Filter | STATELESS_ELIGIBLE | Only move stateless |
| 6 | Model Version Check | Validation | Must be model v6 |
| 7 | Load Optimization Mode | Profile select | COST_FIRST/BALANCED/NO_DOWNTIME |
| 8 | Load Global Rankings | Redis cache | `global_pool_rankings:{region}` |
| 9 | Three-Layer Risk Ceiling | Composite | Profile + volatility + trust |
| 10 | Capacity Freshness | Staleness check | Penalty if >80 min stale |
| 11 | Re-score Pools | `evaluate_candidate_ev()` | Economic model |
| 12 | Score Current Pool | `compute_expected_value()` | Baseline EV |
| 13 | Template & Arch Filters | Whitelist/blacklist | Family/arch |
| 14 | Diversity Check | DiversityEnforcer | Per profile |
| 15 | Delta Threshold | Min improvement | COST=2%, BAL=3%, ND=4% |

### Three-Layer Risk Ceiling (Step 9)
```
Layer 1: Profile ceiling (COST_FIRST=0.25, BALANCED=0.20, NO_DOWNTIME=0.10)
Layer 2: Volatility adjustment (if volatile market, subtract 5%)
Layer 3: Trust-phase override (use minimum effective ceiling)
```

> **Historical note:** The old 9-gate `rank_for_node()` and its helpers (`_apply_filters`, `_apply_double_gate`, `_relax_with_trade_off`, `_relax_with_tier_expansion`, `_get_same_type_az_alternatives`, `_derive_specs_heuristic`) have been **removed** from `decision_engine.py`. Pool selection in the rebalancing loop is handled exclusively by `PoolRankingService.rank_pools_for_node()` (see §7).

---

## 10. Spot Instance Launch (boto3)

**Function:** `_launch_spot_instance_direct()` in `auto_rebalancer.py`

### Method
```python
ec2.run_instances(
    ImageId=ami_id,                        # Copied from source instance
    InstanceType=target_type,              # From pool ranking
    MinCount=1, MaxCount=1,
    ClientToken=sha256_hash,               # Idempotent (source_id:type)
    NetworkInterfaces=[{
        "DeviceIndex": 0,
        "SubnetId": target_subnet,         # Same VPC, target AZ
        "Groups": source_security_groups,  # Copied from source
        "AssociatePublicIpAddress": source_public_ip_setting,
    }],
    IamInstanceProfile={
        "Arn": source_iam_profile_arn,    # Copied from source
    },
    InstanceMarketOptions={
        "MarketType": "spot",
        "SpotOptions": {
            "SpotInstanceType": "one-time"  # No persistent request
        }
    },
    TagSpecifications=[{
        "ResourceType": "instance",
        "Tags": [
            # Kubernetes cluster tag
            {"Key": f"kubernetes.io/cluster/{cluster_name}", "Value": "owned"},
            # Spot optimizer tracking tags
            {"Key": "spot-optimizer:status", "Value": "pending"},
            {"Key": "spot-optimizer:template-id", "Value": source_id[:20]},
            {"Key": "spot-optimizer:termination-mode", "Value": "replacement"},
            {"Key": "spot-optimizer:allowed-architectures", "Value": "arm64|x86_64"},
            {"Key": "spot-optimizer:launched-by", "Value": "spot-optimizer-direct"},
        ]
    }],
    UserData=user_data_b64,                # 3-tier retrieval (see §11)
)
```

### Cascade Fallback Loop
```python
for _itype in target_instance_types[:max_attempts]:  # max_attempts=6 default
    _client_token = hashlib.sha256(f"{source_id}:{_itype}".encode()).hexdigest()
    try:
        response = ec2.run_instances(...)
        return (new_id, _itype, actual_az, None, skipped_dict)
    except ClientError as e:
        if e.code in ("InsufficientInstanceCapacity", "SpotMaxPriceTooLow", "Unsupported"):
            skipped_dict[_itype] = f"{code}: {msg}"
            # Per-cluster capacity block: increment failure counter;
            # hard-block pool after 3 failures (30 min, per-cluster only).
            # Does NOT use global BlacklistService.
            redis.incr(f"spot:capacity_failures:{cluster_id}:{_itype}:{az}")
            redis.expire(f"spot:capacity_failures:{cluster_id}:{_itype}:{az}", 3600)
            # Invalidate dry-run cache
            invalidate_dry_run_cache(_itype, target_az, redis, mark_failed=True)
            continue  # Try next type
        raise  # Unexpected error — fail the action
```

### Post-Launch Actions (on success)
1. **Pre-register in DB** — `Instance(state='pending', lifecycle=SPOT)` — prevents discovery from mis-classifying
2. **Set assertion guard** — `spot:asserted_spot:{instance_id}` (600s TTL — Problem #14) — RC3 lifecycle guard won't downgrade
3. **Register in global EMA** — `get_or_create_ema(redis, db, pool_key, ...)`
4. **Post-launch cooldown** — `spot:post_launch_cooldown:{instance_id}` (60s TTL) — suppress S2S
5. **Update action metadata** — Store `replacement_spot_instance_id` + fallback info if type changed

### Post-Launch Actions (on failure)
1. **Per-cluster capacity block** — increment `spot:capacity_failures:{cluster_id}:{type}:{az}` counter (1h TTL); hard-block pool for 30 min after 3 failures (per-cluster only, not global)
2. **Invalidate dry-run cache** — Mark as FAIL
3. **Suppress S2S** — `spot:s2s_suppressed:{instance_id}` (180s)
4. **Report to Decision Engine** — `DecisionEngineService.report_launch_failure(pool_key, reason)`
5. **Exponential backoff** on the source instance:
   ```python
   _failure_count = redis.incr(f"rebalance_failures:{instance_id}")
   _backoff_s = min(300 * (2 ** (_failure_count - 1)), 3600)
   # 1→5m, 2→10m, 3→20m, 4→40m, 5+→60m (max)
   redis.setex(f"spot:rebalanced:instance:{instance_id}", _backoff_s, "failure_backoff")
   ```

---

## 11. AMI Selection & User-Data

### AMI Source
The AMI is **always copied from the source OD instance** — NOT selected independently:
```python
source_instance = ec2.describe_instances(InstanceIds=[source_instance_id])
ami_id = source_instance['Reservations'][0]['Instances'][0]['ImageId']
```

### User-Data (3-Tier Retrieval)
User-data contains `/etc/eks/bootstrap.sh` which configures kubelet — **critical for K8s join**.

| Tier | Method | When Used |
|------|--------|-----------|
| 1 | `ec2.describe_instance_attribute(Attribute='userData', InstanceId=source_id)` | Primary — most reliable |
| 2 | Source instance's LaunchTemplate version → LaunchTemplate.UserData | Fallback if Tier 1 empty |
| 3 | EKS managed nodegroup LaunchTemplate | Final fallback for managed nodegroups |

**Why 3-tier?** User-data is NOT baked into the AMI. Without it, kubelet never starts, and the spot instance never joins the K8s cluster — causing a timeout and orphan cleanup.

**User-Data Validation (Problem #6):**
- After retrieval, user-data is validated before launch:
  - Must be non-empty (abort with `MISSING_USERDATA` error code if empty)
  - Base64-decoded content must contain `/etc/eks/bootstrap.sh`
  - If validation fails, action is marked `failed` — no spot instance is launched

### Other Copied Parameters

| Parameter | Source |
|-----------|--------|
| AMI ID | `source_instance.ImageId` |
| Subnet | Same VPC, mapped to target AZ |
| Security Groups | `source_instance.SecurityGroups[*].GroupId` |
| IAM Instance Profile | `source_instance.IamInstanceProfile.Arn` |
| Public IP setting | `source_instance.NetworkInterfaces[0].Association.PublicIp` |
| Tags | Copied + spot-optimizer markers added |

---

## 12. ASG Handling (Atomic Terminate with Decrement)

When the source OD instance belongs to an Auto Scaling Group, a **single atomic API call** handles both termination and capacity adjustment:

### Phase 1 — ASG Detection (Pre-Launch)
- Detect whether source instance belongs to an ASG via `get_asg_for_instance()`
- Store `asg_name_used` in `action_metadata` for Phase 2
- **No ASG process suspension** — the atomic API in Phase 2 handles everything

### Phase 2 — Atomic Terminate (Post-Drain)
```python
if source_instance_in_asg:
    # Single atomic call: terminate + decrement DesiredCapacity
    autoscaling.terminate_instance_in_auto_scaling_group(
        InstanceId=source_instance_id,
        ShouldDecrementDesiredCapacity=True
    )
else:
    # Non-ASG node (Karpenter-managed): direct EC2 only
    ec2.terminate_instances(InstanceIds=[source_instance_id])
```

**Why atomic?** The previous multi-step approach (suspend → detach → terminate → decrement → resume) had multiple failure points where partial execution could leave the ASG in an inconsistent state. The atomic API eliminates this entire class of bugs.

**Retry Logic:**
- Up to 3 retries on `Throttling` / `RequestLimitExceeded` with exponential backoff (1s, 2s, 4s)
- On `ValidationError` (instance already removed from ASG by EKS MNG after `kubectl delete node`): falls back to direct `ec2.terminate_instances()`
- On any other error: raises immediately → action marked `failed`

**Cluster size math:** Before=N nodes. Launch spot→N+1. Drain OD→atomic terminate+decrement→N. Spot fills gap. ✓

### What Was Removed
- No more `suspend_processes()` / `resume_processes()` calls
- No more `asg:suspend_lock:{asg_name}` Redis key
- No more `asg_suspended` flag in action metadata
- No more manual `update_auto_scaling_group()` capacity decrement
- No more rollback logic to resume suspended ASG processes

---

## 13. 2-Phase Provision-and-Wait Architecture

### Phase 1 — Launch (Synchronous)
1. Select target pool (see §7)
2. Call `_launch_spot_instance_direct()` (boto3 `run_instances`)
3. Pre-register instance in DB with `state='pending'`
4. Set action status to `waiting_agent`
5. **Return immediately** — don't block the worker

### Phase 2 — Resolve (Next Cycle)
1. Find actions in `waiting_agent` status
2. Check if spot has joined K8s:
   - **Primary:** Check by pinned instance ID (`replacement_spot_instance_id` in metadata)
   - **Legacy fallback:** Compare `spot_count > baseline` (warns in logs)
3. **90s stabilization window** — Let node fully initialize
4. **30 min max timeout** (configurable: `spot_join_timeout_minutes`)
5. On join → create AgentActions: `PATCH_NODEPOOL` (completed) → `CORDON` → `DRAIN` → `TERMINATE`
6. On timeout → `failed` + terminate orphan spot

### Post-Drain Verification
- **20-second grace period** for pod evacuation
- Check `pod_metrics` for workloads still on old node
- **5-minute max wait** before forced EC2 terminate
- At this stage, K8s node is already deleted — uncordon is NOT possible

---

## 14. Rollback & Failure Handling

### Failure at Any Stage

| Failure Point | Rollback Action |
|---------------|-----------------|
| **Gate check fails** | No action taken — skip this cycle |
| **No suitable pool** | Log + defer — retry next cycle |
| **All cascade types fail** | Marking action `failed`, exponential backoff on source instance |
| **Spot launch fails** (capacity) | Per-cluster block: `spot:launch_blocked:{cluster_id}:{type}:{az}` (30 min after 3 failures — Problem #5) |
| **Spot launched but never joins K8s** | Terminate orphan spot (`ec2.terminate_instances`), block pool for `spot_join_timeout_minutes` (default 30 min) |
| **Spot joined but drain fails** | Terminate orphan spot + clear metadata (Problem #3/#9), mark `failed` |
| **Source EC2 terminate fails** | Log error, mark action `failed`, release locks |
| **ASG atomic terminate fails** | Action marked `failed`, source instance untouched, exponential backoff |
| **CORDON fails with NOT_FOUND/404** | **Z4 fix:** Source K8s node is gone (zombie EC2). Terminate EC2 via boto3, clear `rebalance_failures` + `spot:node_active_action` keys, mark action `ZOMBIE_EC2_TERMINATED`, run `_do_rollback_terminate_orphan_spot` |
| **Any unhandled exception** | `_do_rollback_uncordon_and_terminate()` — uncordon node + terminate orphan spot + clear metadata (Problem #3/#9) |

### `_do_rollback_uncordon_and_terminate(action)` Function
```python
# 1. Queue UNCORDON_NODE so old OD node is schedulable again
agent_action = AgentAction(action_type=UNCORDON_NODE, payload={"node_name": target_node})
# 2. Terminate orphan spot instance if launched
if action.action_metadata.get('replacement_spot_instance_id'):
    ec2.terminate_instances(InstanceIds=[spot_id])
    # Problem #3/#9: Clear metadata + Redis keys after termination
    action.action_metadata.pop('replacement_spot_instance_id', None)
    redis.delete(f"spot:asserted_spot:{spot_id}")
    redis.delete(f"node_joined:{spot_id}")  # Z12 fix: skipped if spot age < 180s
    redis.delete(f"spot:node_active_action:{spot_id}")
# No ASG resume needed — ASG was never suspended
# Release concurrency lock
redis.delete(f"rebalance:lock:{cluster_id}")
```

### Stale Action Expiry (Step 0)
Actions stuck in `in_progress` or `waiting_agent` for **>45 minutes** (or exceeding per-state timeouts — Problem #19) are:
1. Marked `failed` with error message
2. Orphan spot EC2 terminated (if launched) + metadata cleared
3. Concurrency lock released
4. Per-state timeouts checked for actions within the 45-min window
5. **Z6 fix:** `spot:node_active_action:{source_id}` Redis key deleted (prevents permanent exclusion from rebalancing)

### Exponential Backoff on Failure
```python
failure_count = redis.incr(f"rebalance_failures:{instance_id}")  # Persistent 24h counter
backoff_s = min(300 * (2 ** (failure_count - 1)), 3600)
# 1st fail → 5 min
# 2nd fail → 10 min
# 3rd fail → 20 min
# 4th fail → 40 min
# 5th+ fail → 60 min (max)
redis.setex(f"spot:rebalanced:instance:{instance_id}", backoff_s, "failure_backoff")
# Problem #16: Track last failure timestamp for sliding window reset
redis.setex(f"rebalance_last_failure:{instance_id}", 86400, str(now.timestamp()))
```
On success: failure counter AND last_failure timestamp are reset.
**Sliding window (Problem #16):** If no failure occurs for 24 hours, the counter is automatically reset before the next increment — preventing permanent max backoff for intermittently failing nodes.

### Agent Self-Termination Guard (Z3 Fix)
The agent (`agent/actuator.py`) refuses to execute any destructive operation on the node it is running on. All three functions — `cordon_node()`, `drain_node()`, and `force_delete_node()` — check `os.getenv('NODE_NAME')` at the top and return `SELF_CORDON_ATTEMPT` / `SELF_DRAIN_ATTEMPT` / `SELF_DELETE_ATTEMPT` respectively if the target matches. `NODE_NAME` is injected via K8s downward API.

---

## 15. State Machine (RebalancingAction)

### States & Transitions
```
CREATED → POOL_SELECTED → SOURCE_CORDONED → SOURCE_DRAINED
        → REPLACEMENT_LAUNCHING → REPLACEMENT_READY → SOURCE_TERMINATING
        → COMPLETED
        
Any state → FAILED (on error)
SOURCE_DRAINED → DRAIN_TIMEOUT (if drain exceeds limit)
```

### Atomic Transition (Optimistic Locking)
```python
def _sm_transition(db, action_id, from_state, to_state, max_retries=2) -> bool:
    # BUG-8 fix: Retries up to max_retries times with 100ms/200ms backoff.
    # Re-reads current state before each retry to detect if another worker won.
    for attempt in range(max_retries + 1):
        result = db.execute(
            """UPDATE rebalancing_actions 
               SET current_state = :to_state
               WHERE id = :action_id AND current_state = :from_state""",
            {"to_state": to_state, "action_id": action_id, "from_state": from_state}
        )
        if result.rowcount == 1:
            return True
        if attempt < max_retries:
            time.sleep(0.1 * (attempt + 1))  # 100ms, 200ms
            current = db.query(RebalancingAction).get(action_id)
            if current and current.current_state != from_state:
                return False  # another worker already transitioned — clean exit
    return False
```
- **Multi-worker safe:** If state doesn't match, UPDATE affects 0 rows — first worker wins
- **Retry with re-read:** On failure, re-reads current state before retrying. If another worker already transitioned, returns False cleanly without logging an error (BUG-8 fix)
- **State history** tracked in `state_history` JSONB column: `[{state, entered_at, exited_at}, ...]`
- **Lock version** column for additional optimistic locking

---

## 16. DB Models

### Instance Model (`instances` table)

| Column | Type | Description |
|--------|------|-------------|
| `id` | UUID (PK) | Auto-generated |
| `cluster_id` | FK → clusters | Nullable for standalone EC2 |
| `account_id` | FK → accounts | NULL for agent-reported nodes |
| `instance_id` | VARCHAR(20), UNIQUE | EC2 ID (e.g., `i-0123456789abcdef0`) |
| `instance_type` | VARCHAR(50) | `m5.xlarge`, `t3.medium`, etc. |
| `lifecycle` | Enum | `ON_DEMAND` or `SPOT` |
| `az` | VARCHAR(50) | Availability Zone |
| `price` | Float | Hourly price |
| `cpu_util` | Float | CPU utilization % (0–100) |
| `memory_util` | Float | Memory utilization % (0–100) |
| `state` | VARCHAR(20) | `running`, `terminated`, `stopped` |
| `status` | VARCHAR(20) | `READY`, `CALIBRATING`, `UNKNOWN`, `TERMINATED` |
| `architecture` | VARCHAR(20) | `amd64` or `arm64` |
| `node_name` | VARCHAR(255) | K8s FQDN (e.g., `ip-10-0-1-234.ec2.internal`) |
| `launched_by` | VARCHAR(50) | `platform` if launched by rebalancer |
| `standby` | Boolean | Hot standby node (cordoned, ready for emergency) |
| `last_heartbeat` | DateTime | For zombie node detection |
| `created_at` | DateTime | Row creation time |
| `updated_at` | DateTime | Last modification time |

**Composite Indexes:** `(cluster_id, lifecycle)`, `(cluster_id, instance_type)`, `(account_id, state)`

### RebalancingAction Model (`rebalancing_actions` table)

| Column | Type | Description |
|--------|------|-------------|
| `id` | Integer (PK) | Auto-increment |
| `cluster_id` | FK → clusters | Target cluster |
| `trigger` | VARCHAR(20) | `emergency` or `graceful` |
| `source_pool` | VARCHAR(100) | `instance_type:az` format |
| `target_pool` | VARCHAR(100) | `instance_type:az` format |
| `status` | VARCHAR(20) | `in_progress`, `completed`, `failed` |
| `current_state` | VARCHAR(30) | State machine state |
| `state_entered_at` | DateTime | When current_state was set |
| `state_history` | JSONB | Full trace of state transitions |
| `lock_version` | Integer | Optimistic lock counter |
| `source_instance_id` | VARCHAR(50) | EC2 ID of replaced node |
| `nodes_affected` | Integer | Nodes moved |
| `pods_migrated` | Integer | Pods drained |
| `started_at` | DateTime | Action start |
| `completed_at` | DateTime | Action end |
| `duration_seconds` | Integer | Total elapsed |
| `error_message` | Text | Failure reason |
| `action_metadata` | JSONB | Context (spot ID, fallback info, ASG name, etc.) |
| `source_od_price_hr` | Float | OD price at decision time |
| `target_spot_price_hr` | Float | Target spot price at decision time |
| `estimated_savings_hr` | Float | Estimated hourly savings |
| `estimated_savings_mo` | Float | Estimated monthly savings |
| `actual_instance_type` | VARCHAR(50) | Actual type (may differ if fallback) |
| `actual_az` | VARCHAR(50) | Actual AZ |
| `actual_spot_price_hr` | Float | Actual spot price at launch |
| `realized_savings_hr` | Float | Actual hourly savings |
| `realized_savings_mo` | Float | Actual monthly savings |
| `realized_savings_pct` | Float | Percentage savings vs OD |
| `savings_gap_hr` | Float | Estimated − realized (0 if no fallback) |

---

## 17. Redis State Management

Redis serves as the fast coordination layer for:
- **Distributed locks** (prevent double-actions)
- **Cooldowns** (prevent hammer-rebalancing)
- **State tracking** (spot lifecycle assertions)
- **Caching** (pool rankings, pricing, capacity)
- **Counters** (failure tracking, daily limits)

### Lock Hierarchy
```
lock:workers.auto_rebalancer          (global task lock, 300s)
  └─ rebalance:lock:{cluster_id} (per-cluster lock, 2400s, heartbeat renewed every 60s)
       └─ lock:node_action:{cluster_id}  (K8s drain serialization, 1200s — Z10 fix)
```
> **Note:** `asg:suspend_lock` was removed — ASG process suspension is no longer performed. The atomic `terminate_instance_in_auto_scaling_group` API eliminates the need for it.

### State Lifecycle for a Single Rebalance
```
SET rebalance:lock:{cluster_id}               # Acquire cluster lock
SETEX spot:node_active_action:{source_id} 86400  # Mark source as busy (24h safety-net TTL — Z6)
→ Launch spot
SET spot:asserted_spot:{new_spot_id}          # RC3 guard (5m)
SET spot:post_launch_cooldown:{new_spot_id}   # Settlement (60s)
→ Wait for K8s join
→ Cordon, Drain, Terminate
SET spot:rebalanced:instance:{source_id}      # 24h cooldown
SET spot:stabilization_lock:{cluster_id}      # 90s grace
DEL rebalance:lock:{cluster_id}               # Release cluster lock
DEL spot:node_active_action:{source_id}       # Release source lock
```

> **Atomicity Note (BUG-3 fix):** All Redis counter increments use atomic `INCR`. All one-time key creation uses `SET ... NX EX` (atomic). Non-atomic `GET → check → SET` patterns have been removed to prevent race conditions between concurrent Celery workers.

---

## 18. Stale Data Prevention

### 4 Layers of Stale Data Protection

**Layer 1 — Discovery Worker (every 5 min)**
- Scans AWS EC2 via `describe_instances` per account
- **RC4 fix:** Any `state='running'` instance NOT found in the scan → mark `terminated`
- Uses `SELECT ... FOR UPDATE` advisory lock to prevent concurrent marking
- Only processes instances with real EC2 IDs (`i-*` prefix)

**Layer 2 — Agent-Node Stale Cleanup (every 5 min)**
- Handles instances with `account_id=NULL` (created by in-cluster agent, not discovery)
- Cutoff: `updated_at < now() - 10 minutes`
- Logic: Agent sends metrics every ~30s → 10 min without update = node is gone
- Marks as `terminated`

**Layer 3 — Reconciliation Worker (every 5 min)**
- For clusters with `status='active'`:
  - Queries live EC2 via `describe_instances` with cluster tag filter
  - Uses **2-miss Redis counter** before marking terminated:
    ```
    Key:       reconcile:miss:{instance_id}
    Threshold: 2 misses
    TTL:       600s (10 min — auto-clears if instance reappears)
    ```
  - Prevents false positives from transient AWS API failures

**Layer 4 — Health Worker (every 2 min)**
- `cleanup_zombie_nodes`: Marks instances as `status='UNKNOWN'` if `last_heartbeat < now() - 5 min`
- `reset_stale_agents`: If cluster heartbeat >5 min old → set `agent_installed='N'`, clear utilization data, bust cache. Additionally (BUG-9 fix): cancels all `PENDING`/`PICKED_UP` `AgentAction`s for the cluster (`status → CANCELLED`), marks all `in_progress`/`waiting_agent` `RebalancingAction`s as `failed` with error `AGENT_WENT_OFFLINE`, and deletes all `action_heartbeat:{id}` Redis keys for those actions. This frees the cluster within 5 minutes instead of up to 45 minutes.

### RC3 Lifecycle Guard (SPOT→OD Downgrade Prevention)
- Redis key: `rc3:od_streak:{instance_id}` (TTL: 30 min)
- Requires **3 consecutive OD observations** before allowing SPOT→OD downgrade
- Prevents false downgrades from AWS API propagation delay (~10-30s for lifecycle field)
- **Assertion guard:** `spot:asserted_spot:{instance_id}` (5 min) — overrides discovery for freshly launched spots

**Two RC3 streak keys exist (NEW-5 verification):**
- `rc3:od_streak:{instance_id}` (1800s): Main discovery-path OD streak. Requires 3 consecutive OD observations from the discovery worker.
- `rc3:metrics_od_streak:{instance_id}` (300s): Metrics-path OD streak. Set every ~60s by the metrics endpoint. 5-min TTL allows accumulation of 3 observations within the window (3 × 60s = 180s < 300s TTL).

### Cache Freshness
- `market_view_cache:{region}` — 1 hour TTL, rebuilt by cache_builder
- `global_pool_rankings:{region}` — 65 min TTL
- Pool pricing staleness penalty: 0.95 multiplier if >15 min old
- Capacity staleness penalty if >80 min old

---

## 19. Cleanup Mechanisms

### Orphan Spot Instance Cleanup (recovery_monitor, every 60s)
```python
# Find instances tagged by spot-optimizer but never joined K8s
Filters = [
    {"Name": "tag:spot-optimizer:status", "Values": ["pending"]},
    {"Name": "instance-state-name", "Values": ["running"]},
]
# If age > 15 minutes AND no Redis key node_joined:{instance_id}:
ec2.terminate_instances(InstanceIds=[orphan_id])
```
**15-minute threshold rationale:** Bootstrap+CNI ~5m + kubelet join ~5m + network buffer ~5m

### Terminated Instance Deletion (discovery, every 5 min)
```python
# Delete DB rows for instances terminated > 5 minutes ago
db.query(Instance).filter(
    Instance.account_id == account.id,
    Instance.state == 'terminated',
    Instance.updated_at <= (now() - 5 minutes)
).delete()
```

### Nightly Terminated Cleanup (cleanup_terminated_instances)
```python
# Delete instances where state='terminated' AND updated_at < now() - 30 days
```

### Stale Action Expiry (auto_rebalancer, every 15s)
- Actions in `in_progress`/`waiting_agent` for >45 min → failed + rollback

### Karpenter Stall Detection (recovery_monitor)
- Completed TERMINATE_NODE actions 15–120 min old
- Check if instance still running in AWS
- If yes → force terminate via EC2 API (Karpenter lost track)

---

## 20. Blacklist & Reputation System

### Blacklist Service

**Exponential Backoff TTL:**
```python
BASE_TTL = 24 hours
MAX_TTL = 168 hours (7 days)
MULTIPLIER = 2
ttl = min(24 × 2^(failures-1), 168) hours
# 1st: 24h, 2nd: 48h, 3rd: 96h, 4th: 168h (max)
```

**Redis Keys:**
| Key | Type | Purpose |
|-----|------|---------|
| `risky_pools:{region}` | SET | Active blacklist members |
| `risky_pool_meta:{pool_key}` | STRING (JSON) | Metadata + expiry |
| `blacklist_failures:{pool_key}` | STRING (counter) | Failure count (30d TTL) |

**Tiered Blacklist Policy:**
| Trigger | Duration |
|---------|----------|
| DryRun fail 1-2×/24h | 6 hours |
| DryRun fail 3+/24h | 12 hours |
| ML high risk (>0.45) | 24 hours |
| Termination event | 24 hours |
| Execution DryRun fail | Penalty only (no blacklist) |

**Hard vs Soft Reject:**
- **Hard reject (≥3 failures):** Pool completely excluded
- **Soft flag (1-2 failures):** -20% savings penalty applied

**Cascade Dampener:**
- Triggers if >70% of candidate pool is blacklisted
- Suspends PREDICTIVE blacklisting for 30 min (`spot:blacklist_suspended:{region}`)
- Does NOT affect real termination events or rebalance-rec blacklists

### Reputation System (EMA-based)
- Redis key: `pool_reputation:{pool_key}` — tracks `success_rate` + `avg_uptime_hours`
- Window: 7-day EMA (Exponential Moving Average)
- Multiplier: 0.5 (all fail) → 1.0 (average) → 1.2 (all succeed)
- Feeds into unified scoring formula

### Cluster Deletion Redis Cleanup (BUG-5 fix)

When a cluster is deleted via `DELETE /clusters/{cluster_id}` (`cluster_routes.py`), the backend performs comprehensive Redis cleanup to prevent orphaned keys:

1. **Direct key deletion:** Explicitly listed keys — `rebalance:lock:{cluster_id}`, `rebalance:active:{cluster_id}:*`, `rebalance:active_count:{cluster_id}`, `cluster_config:{cluster_id}`, `spot:discovery:{cluster_id}`, `karpenter:config:{cluster_id}`.
2. **Wildcard scan-delete:** `SCAN` + `DELETE` for patterns — `spot:*:{cluster_id}:*`, `rc3:*:{cluster_id}:*`, `emergency:*:{cluster_id}:*`.

This ensures no stale Redis state remains that could interfere if the cluster is re-onboarded later.

---

## 21. Cache Builder (market_view_cache)

**Task:** `build_global_pool_cache` in `backend/workers/tasks/cache_builder.py`  
**Schedule:** Every 60 minutes  
**Lock:** `cache_builder:market_view_cache:{region}` (distributed lock)

### Build Process

1. **Scan spot prices** — Redis `spot_price:{region}:*` keys
   - Fallback: `spot_advisor:{region}:*:Linux` when spot_price empty

2. **Enrich each pool:**
   - OD price: Redis → family estimate → skip if 0
   - Interruption rate: Redis → DB SpotAdvisorData → family avg → default 15%
   - Risk tier: `assign_risk_tier(interruption_rate_pct)`
   - Specs: `_lookup_specs()` → `_FALLBACK_SPECS` dict (2000+ entries including t2 family)

3. **Filter:**
   - Remove: savings_pct ≤ 0
   - Remove: OD price = 0

4. **Optional ONNX scoring** (if available):
   - PoolRankingService with `risk_threshold=1.0` (no hard gate)
   - Populate: `predicted_savings`, `risk_probability`, `ml_score`

5. **Sort** within risk tiers by price ascending

6. **Store in Redis:**
   - `market_view_cache:{region}` — 500+ pools, **1 hour TTL**
   - `global_pool_rankings:{region}` — for pool ranking API, **65 min TTL**

### Output Payload Schema
```json
{
  "data": [
    {
      "instance_type": "c7g.medium",
      "az": "ap-south-1c",
      "spot_price": 0.0106,
      "ondemand_price": 0.0448,
      "savings_pct": 76.34,
      "interruption_rate_pct": 8.5,
      "risk_tier": "LOW",
      "vcpu": 2,
      "memory_gb": 4.0,
      "architecture": "arm64",
      "ml_score": 0.85,
      "is_flagged": false,
      "risk_probability": 0.226
    }
  ],
  "last_updated": "2026-03-27T15:00:00Z",
  "count": 1954,
  "region": "ap-south-1"
}
```

### `_lookup_specs(instance_type)` Resolution Order
1. `_FALLBACK_SPECS` dict (hardcoded — all common types including t2 family)
2. `_derive_specs_from_type()` — parse family name for vCPU/memory estimate
3. Default (unknown type): `(2, 8.0, "amd64", is_fallback=True)` — callers check the `is_fallback` sentinel and abort ranking rather than proceeding with a floor that doesn't match the actual node. Add the instance type to `_FALLBACK_SPECS` to re-enable rebalancing.

---

## 22. Global Pool Cache Builder — 8-Step Pipeline

Located in `backend/services/pool_ranking_service.py` (executed by the `cache_builder` Celery task every 60 min):

> **Note:** This section describes the **global cache-building pipeline** that pre-scores all catalog pools and writes `market_view_cache:{region}` (TTL 3600 s) and `global_pool_rankings:{region}` (TTL 3900 s). It is **NOT** the per-node ranking function. Per-node ranking — which applies NodeTemplate constraints, cluster-specific filters, and occupancy dedup — is performed at request time by `rank_pools_for_node()`. See §7 for the per-node pipeline.

### Two-Tier Architecture
- **Tier 1 (Global):** Full ML on ALL catalog → cache top 1500 pools (65 min TTL)
- **Tier 2 (Per-request):** Apply template filters to cached pools in-memory

### 8-Step Filter Pipeline

| Step | Name | Action |
|------|------|--------|
| 1 | Node Template Filter | Arch, vCPU, memory, families, sizes, AZs |
| 2 | AZ Filter | User-specified AZs only |
| 3 | Spot Advisor Filter | 5-pass tiered expansion (rank 0→4) |
| 4 | Blacklist Check | Hard reject (≥3 fails) or soft flag (-20% penalty) |
| 5 | Capacity Check | Parallel ThreadPoolExecutor with timeout |
| 6 | Price Fetch | Redis → DB → family estimate fallback |
| 7 | ML Scoring | ONNX classifier (risk) + regressor (savings) |
| 8 | Final Ranking | Sort by score desc, deduplicate by type |

### ML Scoring Details

**3-Signal Blended Risk (with EMA Smoothing):**
```
base = 0.40 × onnx_risk + 0.35 × price_pressure + 0.25 × spot_advisor_risk
final = (1 - ema_weight) × base + ema_weight × ema_risk   # EMA is an interpolation modifier, not a 4th signal
if blacklisted: final = max(0.75, final)
if dryrun_failed: final = max(0.65, final)
```

**Unified Score:**
```
score = (savings × 0.8) × (1 - blended_risk) × reputation_mult × capacity_mult
```

**ML Scoring Tiers:**
| Tier | Method | Penalty |
|------|--------|---------|
| 1 | Direct ONNX (trained families) | 1.0 |
| 2 | Proxy family + penalty | 0.85–0.90 |
| 3 | Size-class average | 0.75 |

**Circuit Breaker:** >5 ML failures in 10 min → fallback scoring

### Post-Pipeline Capacity Validation (Top 10 only)
- Budget: `min(200, max(25, active_clusters × 2))`
- Per-cluster cap: 5 dryruns
- Uses `DescribeInstanceTypeOfferings` (not RunInstances dryrun)
- Cache: `spot:validated:{region}:{itype}:{az}` (1h TTL)

---

## 23. Termination Monitor (Spot Interruptions)

**Task:** `detect_termination_notice()` in `backend/workers/tasks/termination_monitor.py`  
**Sources:** DaemonSet (IMDS), EventBridge (SQS), Manual API

### Deduplication
```python
# Key: emergency:dedup:{instance_id} (TTL: 300s — Problem #20, extended from 120s)
# SQS, IMDS, and EventBridge all fire for same event → NX SET suppresses duplicates
# Per-node emergency lock: emergency:rebalance:{instance_id} (TTL: 120s — Z13 fix, was 600s)
# DB check: skip if active rebalancing action exists for same source node
```

**Two distinct keys serve different purposes (NEW-4 clarification):**
- `emergency:dedup:{instance_id}` (300s): Event-level dedup. Suppresses duplicate interruption signals from SQS, IMDS, and EventBridge for the same instance. One termination event = one processing attempt.
- `emergency:rebalance:{instance_id}` (120s — Z13 fix, was 600s): Per-node action lock. Prevents a second emergency rebalance from starting while the first is still running. Short TTL (120s) allows retry within the 2-minute AWS termination notice window.

### Actions on Detection

1. **Flag pool in blacklist:**
   ```python
   redis.sadd("risky_pools", f"{instance_type}:{az}")
   redis.setex(f"risky_pool_meta:{pool_key}", 900, metadata_json)  # 15 min
   ```

2. **Log termination event** in DB (`TerminationEvent` table)

3. **Update global EMA** — `update_ema_on_interruption(redis, db, pool_key, ...)`

4. **Trigger emergency rebalancing:**
   ```python
   EmergencyEventProcessor().process(
       event_type='termination',
       instance_id=instance_id,
       cluster_id=cluster_id,
   )
   ```

---

## 24. Recovery Monitor (Orphan & Stall Detection)

**Task:** `recovery_monitor` in `backend/workers/tasks/recovery_monitor.py`  
**Schedule:** Every 60 seconds

### Task 1: Orphan Instance Cleanup (`scan_orphans`)
- Find EC2 instances with tag `spot-optimizer:status=pending` + state=`running`
- If age > **15 minutes** AND no Redis key `node_joined:{instance_id}`
- **Double-check before termination (Problem #18):**
  - Skip if `spot:prevent_orphan_termination:{instance_id}` override key exists (TTL: 3600s — set by operator for debugging via Redis CLI SETEX; expires automatically after 1 hour; must be renewed for longer protection)
  - Skip if instance has `node_name` in DB (agent heartbeat confirmed join)
  - Skip if agent heartbeat is recent (< 5 minutes)
- **Action:** `ec2.terminate_instances(InstanceIds=[orphan_id])`
- **Two passes:** Pass 1 (platform creds for same-account), Pass 2 (assumed role for cross-account)

### Task 2: Karpenter Stall Detection (`detect_karpenter_stalls`)
- Target: COMPLETED TERMINATE_NODE actions, 15–120 min old, mode=karpenter
- Check if instance still running in AWS
- If yes → force `ec2.terminate_instances()` (Karpenter lost track)

### Task 3: Instance State Sync (`sync_instance_states`)
- Batch `ec2.describe_instances` for all running instances
- Mark `terminated` / `shutting-down` instances accordingly
- Handles InvalidInstanceID gracefully (fall back to individual describe)

### Task 4: Cluster Coverage (`compute_cluster_coverage`)
- Per-node: COVERED (≥3 alternatives), AT_RISK (1-2), STRANDED (0), STATEFUL
- Stored in Redis: `cluster_coverage:{cluster_id}` (300s TTL)

### Task 5: Stuck Cordon Recovery (`recover_stuck_cordoned_nodes`) — Z2 Fix
- **Problem:** Network partition or worker crash can leave a node permanently cordoned.
- Find failed RebalancingActions where cordon was applied (`step_2_cordon` in metadata) in last 2 hours.
- Also find in_progress/waiting_agent actions stuck > 20 min past cordon.
- For each: verify cluster agent online (heartbeat < 5 min), no pending UNCORDON already exists.
- **Action:** Dispatch new `UNCORDON_NODE` AgentAction with `recovery_reason: Z2_stuck_cordon`.
- DB-only approach — no direct K8s API needed.

---

## 25. Reconciliation Worker

**Task:** `reconciliation_worker` in `backend/workers/tasks/reconciliation_worker.py`  
**Schedule:** Every 5 minutes

### Logic
1. Query all clusters with `status='active'`
2. For each cluster:
   - **Z14 fix:** Collect instance IDs involved in active actions (source + replacement) → skip only those specific instances during reconciliation (replaces previous cluster-wide skip)
   - Get AWS account → assume role → get EC2 client
   - Paginate live instances with K8s cluster tag
   - Compare DB `state='running'` instances with live EC2

### 2-Miss Counter (prevents false positives)
```python
miss_key = f"reconcile:miss:{instance_id}"
if instance_id not in live_ids:
    miss_count = redis.incr(miss_key)
    redis.expire(miss_key, 600)  # 10 min TTL
    if miss_count >= 2:          # 2-miss threshold
        instance.state = 'terminated'
        instance.terminated_at = now()
        redis.delete(miss_key)
else:
    redis.delete(miss_key)       # Instance alive — clear counter
```

**Why 2-miss?** AWS describe_instances can transiently omit instances during API pagination or regional propagation. Requiring 2 consecutive misses (10+ minutes apart) prevents false termination marking.

---

## 26. AWS Permissions Required

### Client-Side (Cross-Account Assume Role)

**EC2:**
```
ec2:DescribeInstances, ec2:DescribeInstanceTypes, ec2:DescribeInstanceStatus,
ec2:DescribeRegions, ec2:DescribeAvailabilityZones, ec2:DescribeVpcs,
ec2:DescribeSubnets, ec2:DescribeSecurityGroups, ec2:DescribeVolumes,
ec2:DescribeSnapshots, ec2:DescribeImages, ec2:DescribeKeyPairs,
ec2:DescribeTags, ec2:DescribeSpotInstanceRequests,
ec2:DescribeReservedInstances, ec2:RunInstances, ec2:TerminateInstances,
ec2:StopInstances, ec2:StartInstances, ec2:ModifyInstanceAttribute,
ec2:CreateTags, ec2:DeleteTags
```

**EKS:**
```
eks:DescribeCluster, eks:ListClusters, eks:DescribeNodegroup,
eks:ListNodegroups, eks:DescribeUpdate, eks:ListUpdates,
eks:DescribeFargateProfile, eks:ListFargateProfiles, eks:AccessKubernetesApi
```

**Auto Scaling:**
```
autoscaling:DescribeAutoScalingGroups, autoscaling:DescribeAutoScalingInstances,
autoscaling:DescribeLaunchConfigurations, autoscaling:DescribeScalingActivities,
autoscaling:DescribeTags, autoscaling:UpdateAutoScalingGroup,
autoscaling:SetDesiredCapacity, autoscaling:TerminateInstanceInAutoScalingGroup
```

**CloudWatch:**
```
cloudwatch:GetMetricStatistics, cloudwatch:ListMetrics, cloudwatch:GetMetricData
```

**IAM (read-only):**
```
iam:GetRole, iam:GetInstanceProfile, iam:ListAttachedRolePolicies
```

**STS:**
```
sts:GetCallerIdentity
```

**Cost Explorer (optional):**
```
ce:GetCostAndUsage, ce:GetCostForecast,
ce:GetReservationUtilization, ce:GetSavingsPlansUtilization
```

### Platform-Side (Own Credentials)

**Pricing & Discovery:**
```
pricing:GetProducts, pricing:DescribeServices, pricing:GetAttributeValues,
ec2:DescribeSpotPriceHistory, ec2:DescribeInstanceTypes,
ec2:DescribeInstanceTypeOfferings, ec2:DescribeRegions,
ec2:DescribeAvailabilityZones
```

**Cross-Account:**
```
sts:GetCallerIdentity, sts:AssumeRole
```

### Trust Relationship (Client Account)
```json
{
  "Version": "2012-10-17",
  "Statement": [{
    "Effect": "Allow",
    "Principal": { "AWS": "arn:aws:iam::<PLATFORM_ACCOUNT_ID>:root" },
    "Action": "sts:AssumeRole",
    "Condition": {
      "StringEquals": { "sts:ExternalId": "<UNIQUE_EXTERNAL_ID>" }
    }
  }]
}
```

---

## 27. Key Formulas & Constants

### Expected Value (EV) Score
```
EV = savings_pct × (1 - risk_probability)
```
Used for ranking pools in both the node-recommendations endpoint and Per-Node Alternative Pools table.

### Unified ML Score
```
score = (savings × 0.8) × (1 - blended_risk) × reputation_mult × capacity_mult
```

### 3-Signal Blended Risk (with EMA Smoothing)
```
base = 0.40 × onnx_risk + 0.35 × price_pressure + 0.25 × spot_advisor_risk
final = (1 - ema_weight) × base + ema_weight × ema_risk
Hard overrides: blacklisted → max(0.75, final), dryrun_failed → max(0.65, final)
```

### Savings Calculation
```
savings_pct = (on_demand_hourly - spot_price) / on_demand_hourly × 100
```

### Instance Type Diversification Cap
```
max_same_type = max(1, round(total_nodes × (1 - diversification_pct / 100)))
```

### Exponential Backoff (failures)
```
backoff_seconds = min(300 × 2^(failure_count - 1), 3600)
```

### Key Constants

| Constant | Value | Location |
|----------|-------|----------|
| Rebalancer interval | 15 seconds | app.py |
| Cluster cooldown | 3600s (1h) | auto_rebalancer |
| Concurrency lock TTL | 2700s (45m) with heartbeat renewal every 60s; matches stale action timeout exactly (NEW-3 fix) | auto_rebalancer |
| Stabilization lock | 60–90s | auto_rebalancer |
| Instance cooldown | 86400s (24h) | auto_rebalancer |
| Spot assertion guard | 600s (10m) — Problem #14 | auto_rebalancer |
| Dry-run pass TTL | 900s (15m) — Problem #4 | dry_run.py |
| Dry-run fail TTL | 60s (1m) — N8 fix (was 300s), reduced to limit cross-cluster starvation from transient failures | dry_run.py |
| Dry-run max API checks | 5 per cycle — Problem #17 | auto_rebalancer |
| Drain timeout | 15 min default, configurable per cluster — Problem #11 | auto_rebalancer |
| Per-cluster capacity block | 30 min after 3 failures — Problem #5 | auto_rebalancer |
| Architecture cache TTL | 7 days — Problem #10 | auto_rebalancer |
| RC3 threshold | 3 consecutive observations | discovery |
| RC3 streak TTL | 1800s (30m) | discovery |
| Stale action timeout | 45 minutes (with per-state timeouts — Problem #19) | auto_rebalancer |
| Orphan timeout | 15 minutes | recovery_monitor |
| Emergency dedup TTL | 300s (5m) — Problem #20 | termination_monitor |
| Emergency per-node lock | 120s (2m) — Z13 fix (was 600s) | termination_monitor |
| Backoff sliding window | 24h reset — Problem #16 | auto_rebalancer |
| Reconcile miss threshold | 2 misses | reconciliation_worker |
| Reconcile miss TTL | 600s (10m) | reconciliation_worker |
| Agent stale cutoff | 10 minutes | discovery |
| Zombie cleanup threshold | 5 minutes | health |
| Blacklist base TTL | 24 hours | blacklist_service |
| Blacklist max TTL | 168 hours (7d) | blacklist_service |
| Market view cache TTL | 3600s (1h) | cache_builder |
| Global pool rankings TTL | 3900s (65m) | cache_builder |
| ML circuit breaker | 5 failures in 10m | pool_ranking_service |

---

## 28. Complete Redis Key Reference

### Locks & Concurrency

| Key | TTL | Type | Purpose |
|-----|-----|------|---------|
| `lock:workers.auto_rebalancer` | 300s | HeartbeatLock | Global task mutex |
| `rebalance:lock:{cluster_id}` | 2700s | NX SET | Per-cluster concurrency (heartbeat renewed every 60s; matches 45-min stale threshold exactly — NEW-3 fix) |
| `lock:node_action:{cluster_id}` | 1200s | distributed_lock | K8s drain serialization (Z10 fix: 180→1200s) |
| ~~`asg:suspend_lock:{asg_name}`~~ | ~~60s~~ | ~~Redis lock~~ | **REMOVED** — atomic `terminate_instance_in_auto_scaling_group` eliminates the need |
| `cache_builder:market_view_cache:{region}` | varies | distributed_lock | Cache rebuild mutex |

### Cooldowns

| Key | TTL | Purpose |
|-----|-----|---------|
| `spot:cooldown:action:{cluster_id}` | 3600s+ | Cluster rebalance cooldown |
| `spot:cooldown:action:resize:{cluster_id}` | varies | Resize cooldown |
| `spot:stabilization_lock:{cluster_id}` | 60–90s | Post-action grace period |
| `spot:rebalanced:instance:{instance_id}` | 86400s | Per-instance 24h cooldown |
| `spot:post_launch_cooldown:{instance_id}` | 60s | New spot settlement |
| `spot:s2s_suppressed:{instance_id}` | 180s | Post-fallback S2S suppress |
| `spot:launch_blocked:{cluster_id}:{type}:{az}` | `spot_join_timeout_minutes × 60` (no-join, default 1800s) or 1800s (≥3 capacity failures) | Per-cluster block. No-join TTL matches configured join timeout. Capacity failure TTL fixed at 30 min (Problem #5, N7 fix) |

### State Tracking

| Key | TTL | Purpose |
|-----|-----|---------|
| `spot:asserted_spot:{instance_id}` | 600s | RC3 lifecycle guard override (10 min — Problem #14) |
| `spot:node_active_action:{instance_id}` | 86400s | Node has in-flight rebalance (Z6 fix: 24h safety-net TTL; deleted on stale expiry) |
| `action_heartbeat:{action_id}` | 120s | Dual-writer liveness heartbeat — refreshed by backend Celery worker every ~15s AND by agent `_action_heartbeat_loop()` every 30s during execution (N5 fix, Problem #19) |
| `spot:prevent_orphan_termination:{instance_id}` | 3600s (1h) | Operator override: exempt from orphan termination (Problem #18). Set manually via Redis CLI with SETEX, not SET. Expires automatically after 1 hour; must be renewed if longer protection needed |
| `spot:substitute:state:{cluster_id}` | varies | Warm spare FSM state |
| `node_joined:{instance_id}` | varies | Node joined K8s confirmation |
| `rc3:od_streak:{instance_id}` | 1800s | SPOT→OD downgrade streak counter |
| `rc3:metrics_od_streak:{instance_id}` | 300s | Metrics-path OD streak (Issue 3c). Set every ~60s by metrics endpoint; 5-min TTL allows accumulation of 3 observations within the window |

### Counters & Tracking

| Key | TTL | Purpose |
|-----|-----|---------|
| `rebalance_failures:{instance_id}` | 86400s | Failure counter (exp backoff) |
| `rebalance_last_failure:{instance_id}` | 86400s | Last failure timestamp (sliding window reset — Problem #16) |
| `spot:daily_count:{cluster_id}` | 86400s | Daily rebalance counter |
| `spot:skip_streak:{cluster_id}` | 300s | Consecutive skips (stall detect) |
| `emergency:dedup:{instance_id}` | 300s | Event-level dedup: suppresses duplicate SQS/IMDS/EventBridge interruption signals for the same instance (5 min — Problem #20) |
| `emergency:rebalance:{instance_id}` | 120s | Per-node action lock: prevents a second emergency rebalance while first is running. Short TTL allows retry within 2-min AWS termination window (Z13 fix, was 600s) |
| `spot:recovery:{instance_id}` | 3600s | Spot recovery dedup |
| `spot:recovery:cluster:{cluster_id}` | 120s | Cluster recovery rate limit |
| `reconcile:miss:{instance_id}` | 600s | 2-miss counter |
| `last_check:{cluster_id}` | varies | Per-cluster interval gate |

### Cache

| Key | TTL | Purpose |
|-----|-----|---------|
| `market_view_cache:{region}` | 3600s | 500+ pools with pricing |
| `global_pool_rankings:{region}` | 3900s | Top ~42 ML-scored pools |
| `dry_run:{type}:{az}` | 900s (pass) / 60s (fail) | Capacity check (pass=15m, fail=1m — Problem #4, N8 fix: fail was 5m, reduced to limit cross-cluster starvation) |
| `spot:validated:{region}:{type}:{az}` | 3600s | Capacity validated |
| `instance_type_arch:{type}` | 604800s (7d) | Architecture cache: arm64/x86_64 (Problem #10) |
| `spot_price:{region}:{az}:{type}` | varies | Real-time spot price |
| `ondemand_price:{region}:{type}` | varies | On-demand price |
| `spot_advisor:{region}:{type}:Linux` | 3600s | Interruption + savings data |
| `cluster_coverage:{cluster_id}` | 300s | Node coverage report |
| `cluster_pools:{cluster_id}` | varies | Active pools in cluster (Z5 fix: synced every 30 min, srem on launch failure) |

### Blacklist & Reputation

| Key | TTL | Purpose |
|-----|-----|---------|
| `risky_pools:{region}` | — | Active blacklist SET |
| `risky_pool_meta:{pool_key}` | 900s–168h | Blacklist metadata |
| `blacklist_failures:{pool_key}` | 30d | Failure counter |
| `pool_reputation:{pool_key}` | 7d | Success rate + uptime EMA |
| `spot:blacklist_suspended:{region}` | 1800s | Cascade dampener |
| `spot:capacity_failures:{cluster_id}:{type}:{az}` | 3600s | Per-cluster failure counter (Problem #5) |
| `spot:rejection_counters:{cluster_id}` | 86400s | Rejection breakdown HSET |
| `pool_audit:{cluster_id}:{node}` | 300s | Pool filter rejection audit |
