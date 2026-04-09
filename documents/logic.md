# ASCP.AI Spot Optimizer — System Logic Reference

> **Last validated**: June 2026 · **Source of truth**: `backend/` source code
>
> This document covers every production subsystem. Each section references the exact source file so future audits can re-validate.

---

## Table of Contents

1. [Architecture Overview](#1-architecture-overview)
2. [System A — Pool Ranking (ML Pipeline)](#2-system-a--pool-ranking-ml-pipeline)
3. [System B — Auto-Rebalancer](#3-system-b--auto-rebalancer)
4. [System 3 — Karpenter Integration](#4-system-3--karpenter-integration)
5. [Decision Engine v3](#5-decision-engine-v3)
6. [Risk Engine](#6-risk-engine)
7. [EV Model (Expected Value)](#7-ev-model-expected-value)
8. [Execution Controller (13-Step Pipeline)](#8-execution-controller-13-step-pipeline)
9. [Guardrail Engine](#9-guardrail-engine)
10. [Circuit Breaker (Pillar 1 State Machine)](#10-circuit-breaker-pillar-1-state-machine)
11. [Blacklist Service](#11-blacklist-service)
12. [Cooldown Controller](#12-cooldown-controller)
13. [Recovery Monitor](#13-recovery-monitor)
14. [Discovery Worker](#14-discovery-worker)
15. [Hibernation Service](#15-hibernation-service)
16. [Background Schedules (Celery Beat + APScheduler)](#16-background-schedules)
17. [API Gateway & Routes](#17-api-gateway--routes)
18. [Data Models (Key Tables)](#18-data-models)
19. [Pillar 1 — Rebalancing State Machine](#19-pillar-1--rebalancing-state-machine)
20. [Pillar 6 — Schema Validation](#20-pillar-6--schema-validation)
21. [Cross-System Safety Gates](#21-cross-system-safety-gates)
22. [Redis Key Reference](#22-redis-key-reference)

---

## 1. Architecture Overview

**Source**: `backend/core/api_gateway.py`, `backend/workers/app.py`, `backend/scheduler.py`

```
┌─────────────────────────────────────────────────────────────────────┐
│                        FastAPI API Gateway                          │
│  (826 lines · 30+ routes · WebSocket · CORS · JWT · Rate Limiting) │
└────────────────────────┬────────────────────────────────────────────┘
                         │
        ┌────────────────┼────────────────┐
        ▼                ▼                ▼
┌──────────────┐ ┌──────────────┐ ┌──────────────┐
│  PostgreSQL  │ │    Redis     │ │ Celery Beat  │
│  (SQLAlchemy)│ │  (State/Cache│ │ (42+ tasks)  │
│              │ │   /Locks)    │ │              │
└──────────────┘ └──────────────┘ └──────┬───────┘
                                         │
                    ┌────────────────────┼────────────────────┐
                    ▼                    ▼                    ▼
             ┌────────────┐      ┌────────────┐      ┌────────────┐
             │  Discovery  │      │Auto-Rebal. │      │  Recovery  │
             │  Worker     │      │  Worker    │      │  Monitor   │
             └────────────┘      └────────────┘      └────────────┘
```

**Core Stack:**

| Layer | Technology | Purpose |
|-------|-----------|---------|
| API | FastAPI + Uvicorn | REST + WebSocket serving |
| Auth | JWT (HS256) + API keys | User auth + agent auth |
| DB | PostgreSQL via SQLAlchemy | Persistent state |
| Cache/State | Redis | Ephemeral state, locks, caches, pub/sub |
| Workers | Celery (Redis broker) | Async background tasks |
| Scheduler | APScheduler (in-process) | Lightweight recurring jobs |
| Cloud | AWS (EC2, EKS, STS, Cost Explorer) | Infrastructure management |
| K8s | Karpenter v1 | Node provisioning |

**Middleware Chain** (registered in `api_gateway.py`):
1. CORS (configurable origins)
2. Request timing header (`X-Process-Time`)
3. Rate limiter (Redis-backed, per-IP)
4. JWT token validation
5. Global exception handlers (HTTP + unhandled)

---

## 2. System A — Pool Ranking (ML Pipeline)

**Source**: `backend/services/pool_ranking_service.py` (2886 lines)

The 8-step filtering and scoring pipeline ranks all EC2 spot pools for a cluster, producing a scored shortlist used by Karpenter and the auto-rebalancer.

### 2.1 Pipeline Steps

```
Step 1: Load Candidate Pools
  └─ All instance_type:az combinations from pricing data for the cluster's region

Step 2: Blacklist Filter
  └─ Remove pools matching any active Redis blacklist key
  └─ Source: BlacklistService.is_blacklisted()

Step 3: Capacity Verification (DryRun)
  └─ EC2 RunInstances(DryRun=True) per pool
  └─ Cache results in Redis: spot:dryrun_failures_24h:{pool} (TTL 24h)
  └─ Track API call count: spot:dryrun_count:{region} (TTL 24h)

Step 4: Risk Scoring
  └─ RiskEngine.calculate_pool_risk() returns 0.0–1.0
  └─ Composite of: Bayesian pressure, AZ instability, price volatility, frequency score

Step 5: Price Scoring
  └─ Spot-to-OD ratio: spot_price / on_demand_price
  └─ Lower ratio = better score

Step 6: Guardrail Filtering
  └─ GuardrailEngine hard constraints:
     - Spot ratio cap (default 80%)
     - AZ concentration limit (max 60% per AZ)
     - Instance family concentration (max 40% per family)
     - Monthly spend cap

Step 7: Composite Scoring
  └─ final_score = (risk_weight × risk_score) + (price_weight × price_score)
                   + (diversity_bonus) + (stability_bonus)
  └─ Weights from OptimizationStrategy profile per cluster
  └─ diversity_bonus: penalises family/AZ concentration
  └─ stability_bonus: rewards pools with historical uptime

Step 8: Output Top-N Ranked Pools
  └─ Default: Top 10
  └─ Stored in Redis sorted set: verified_pools:{cluster_id}
  └─ Fed to: KarpenterService, DecisionEngine, AutoRebalancer
```

### 2.2 Two-Tier Global Cache

| Tier | Key Pattern | TTL | Purpose |
|------|------------|-----|---------|
| L1 | `spot:pool_rank:{cluster_id}` | 300s | Full ranked list |
| L2 | `spot:pool_score:{pool_id}` | 600s | Individual pool scores |

### 2.3 n=n Blacklist Replacement

When a pool in the top-N is blacklisted mid-cycle, the pipeline pulls the next-best pool from the L1 cache rather than re-running the full pipeline. The replacement inherits the blacklisted pool's slot position.

---

## 3. System B — Auto-Rebalancer

**Source**: `backend/workers/tasks/auto_rebalancer.py` (5948 lines)

The auto-rebalancer executes node migrations from on-demand to spot (or unsafe-spot to safer-spot). It runs every **15 seconds** via Celery beat.

### 3.1 Rebalancing Modes

| Mode | Trigger | Time Budget | Description |
|------|---------|-------------|-------------|
| Emergency | Termination notice | 90 seconds | Immediate migration on spot interruption |
| Graceful | Proactive ML signal | 10 minutes | Scheduled migration to safer/cheaper pool |

### 3.2 Execution Flow

```
1. Query rebalancing_actions table for status='in_progress'
2. For each action:
   a. Load cluster from DB
   b. Check cluster cooldown (Redis key)
   c. Acquire per-cluster rebalance lock (Redis SET NX, TTL 2700s/45min)
   d. Start lock heartbeat thread (renews every 60s)
   e. Cross-system safety gates (§21)
   f. Double-launch guard (check replacement_spot_instance_id in metadata)
   g. Acquire distributed lock: lock:node_action:{cluster_id} (TTL 1200s/20min)
   h. Resolve source/target instance types and AZs
   i. Sync AWS instance state (_sync_instance_state_from_aws)
   j. Execute via Karpenter NodePool patch
   k. Create AgentAction (CORDON → DRAIN → TERMINATE)
   l. Transition action to 'waiting_agent'
   m. On completion: set stabilization lock, update cooldowns
   n. On failure: uncordon node, mark action failed
```

### 3.3 AWS State Sync (`_sync_instance_state_from_aws`)

Before any rebalancing, the worker pulls real EC2 state via `DescribeInstances` (using STS assumed-role credentials) and syncs to the DB:

- **New instances**: Created in DB with lifecycle derived from EC2 API
- **Lifecycle corrections**: SPOT↔OD with RC3 guard (3 consecutive observations required for SPOT→OD downgrade, 600s Redis TTL)
- **Terminated instances**: Marked in DB if missing from AWS running set
- **Empty-result protection**: 3-consecutive-empty-streak guard before mass-termination (prevents false eviction on transient API hiccups)
- **K8s hostname derivation**: `ip-{ip}.{region}.compute.internal` from `PrivateIpAddress`
- **Placeholder merge**: Deletes `ip-` placeholder records and transfers utilisation data to real EC2 records

### 3.4 Architecture-Aware AMI Resolution

**Source**: `auto_rebalancer.py` lines 116–247

When migrating across architectures (x86↔arm64):
1. `_get_instance_arch()`: Calls `DescribeInstanceTypes` API with 7-day Redis cache, falls back to static ARM family set
2. `_resolve_arch_compatible_ami()`: 3-strategy AMI resolution:
   - Exact source-name architecture swap (e.g., `amazon-eks-node` → `amazon-eks-arm64-node`)
   - Version-aware wildcard search across EKS naming schemes
   - Generic architecture wildcard as last resort

---

## 4. System 3 — Karpenter Integration

**Source**: `backend/services/karpenter_service.py` (1016 lines)

### 4.1 Core Flow

```
ML Pipeline ranks safe pools → Top 10 instance types
  └─ KarpenterService.sync_ml_rankings_to_nodepool()
     └─ Patches Karpenter NodePool v1 with ML-approved instance types
        └─ Karpenter provisions from safe list only
```

### 4.2 Key Methods

| Method | Purpose |
|--------|---------|
| `sync_ml_rankings_to_nodepool()` | Push ML-ranked types to NodePool |
| `switch_to_ondemand()` | Fallback when no safe spot pools (12h TTL auto-revert) |
| `revert_to_spot()` | Revert from OD fallback (manual or TTL-triggered) |
| `_final_capacity_check()` | Execution-layer DryRun with escalation logic |
| `_validate_drain()` | `kubectl drain --dry-run=client` pre-check |
| `_check_circuit_breaker()` | Block if >10 execution failures in 10 min (30-min disable) |

### 4.3 On-Demand Fallback

When no safe spot pools exist:
1. NodePool patched with `capacity-type: on-demand`
2. Redis key `spot:ondemand_fallback:{cluster_id}` set with 12h TTL
3. Labels: `fallback-mode: on-demand`
4. Auto-reverts to spot when TTL expires or ML finds safe pools

### 4.4 Execution Safety Layers

| Layer | Key Pattern | TTL | Behavior |
|-------|------------|-----|----------|
| Execution penalty | `spot:execution_fail:{pool}` | 1h | Skip pool after 1 failure, blacklist after 2 |
| Cluster circuit breaker | `spot:cluster_circuit_breaker:{cluster_id}` | 30min | Block all execution |
| Failure window | `spot:exec_fail_window:{cluster_id}` | 10min | Count to 10 triggers breaker |

### 4.5 Retry & Rollback

- **PATCH retries**: Up to 2 retries with delays [5s, 15s]
- **Rollback**: On final failure, restores previous NodePool state via `_restore_nodepool_state()`
- **Circuit breaker recording**: `_record_execution_failure()` increments failure window counter

---

## 5. Decision Engine v3

**Source**: `backend/services/decision_engine_service.py` (322 lines)

Unified facade integrating pool selection, blacklisting, and diversity enforcement.

### 5.1 Decision Flow

```
DecisionEngineService.get_best_pool(cluster_id, profile_id)
  │
  ├─ 1. Check per-profile cache (Redis, TTL 120s)
  ├─ 2. PoolRankingService.rank_pools() → scored list
  ├─ 3. BlacklistService.filter_blacklisted() → remove banned pools
  ├─ 4. DiversityEnforcer.apply_diversity() → enforce family/AZ spread
  ├─ 5. Record launch attempt in Redis
  └─ 6. Return best pool or None (triggers OD fallback)
```

### 5.2 Launch Failure Tracking

| Key | TTL | Purpose |
|-----|-----|---------|
| `spot:launch_attempt:{pool}:{cluster}` | 1h | Count attempts per pool per cluster |
| `spot:launch_fail:{pool}` | 24h | Global failure counter for pool |

---

## 6. Risk Engine

**Source**: `backend/core/risk_engine.py` (343 lines)

Deterministic spot risk computation producing a 0.0–1.0 composite risk score.

### 6.1 Risk Components

| Component | Weight | Source | Description |
|-----------|--------|--------|-------------|
| Bayesian Pool Pressure | 0.30 | Spot price history + interruption frequency | Beta-posterior estimator of interruption probability |
| AZ Instability | 0.25 | Cross-AZ price variance | Measures concentration risk within an AZ |
| Price Volatility | 0.25 | Rolling 24h price σ / mean | Coefficient of variation of spot pricing |
| Frequency Score | 0.20 | AWS interruption data | Historical interrupt rate for instance type |

### 6.2 Formula

```
risk = (0.30 × bayesian_pressure)
     + (0.25 × az_instability)
     + (0.25 × price_volatility)
     + (0.20 × frequency_score)
```

All inputs are clamped to [0.0, 1.0] before weighting. Final score is clamped to [0.0, 1.0].

---

## 7. EV Model (Expected Value)

**Source**: `backend/core/ev_model.py` (184 lines)

Calculates the Economic Expected Value of running on a specific spot pool vs on-demand.

### 7.1 Six-Term EV Formula

```
EV = E[savings] − E[interruption_cost] − E[migration_penalty]
     − E[capacity_failure_risk] − E[warmup_cost] + E[stability_bonus]
```

| Term | Description |
|------|-------------|
| `E[savings]` | `(od_price - spot_price) × hours_per_month` |
| `E[interruption_cost]` | `interrupt_prob × downtime_minutes × cost_per_minute` |
| `E[migration_penalty]` | `migration_count × penalty_multiplier × base_cost` |
| `E[capacity_failure_risk]` | `(1 - capacity_prob) × full_od_cost` |
| `E[warmup_cost]` | `warmup_minutes × od_price_per_minute` (new node boot time) |
| `E[stability_bonus]` | `stability_days × bonus_per_day` (reward for long-running pools) |

### 7.2 Decision Rules

| EV Result | Action |
|-----------|--------|
| EV > 0 AND risk < ceiling | Approve spot migration |
| EV > 0 AND risk ≥ ceiling | Defer (mark as "risky but profitable") |
| EV ≤ 0 | Block migration (stay on-demand) |

---

## 8. Execution Controller (13-Step Pipeline)

**Source**: `backend/services/execution_controller.py` (360 lines)

Safe node replacement pipeline used by the auto-rebalancer and manual actions.

### 8.1 Steps

```
Step  1: Validate cluster exists and is ACTIVE
Step  2: Check circuit breaker state (must be NORMAL or CONSERVATIVE)
Step  3: Verify guardrail constraints (spot ratio, AZ concentration, spend cap)
Step  4: Acquire distributed lock: lock:execution:{cluster_id}
Step  5: DryRun capacity check on target pool
Step  6: Cordon source node (mark unschedulable)
Step  7: Drain source node (evict pods, respect PDBs)
Step  8: Provision replacement via Karpenter NodePool patch
Step  9: Wait for replacement node to join cluster (health check loop)
Step 10: Verify workloads rescheduled on new node
Step 11: Terminate source EC2 instance
Step 12: Update DB records (instance lifecycle, costs, timestamps)
Step 13: Release locks, set cooldowns, emit events
```

### 8.2 Failure Handling

| Failure At | Recovery Action |
|-----------|-----------------|
| Steps 1–5 | Abort, no side effects |
| Step 6 (cordon) | Log + continue to drain |
| Step 7 (drain timeout) | Force-delete pods after configurable timeout (default 15 min) |
| Step 8 (provision) | Uncordon source, mark action failed |
| Step 9 (join timeout) | Terminate replacement, uncordon source |
| Steps 10–11 | Best-effort cleanup, log error |
| Step 12–13 | Idempotent, retry safe |

---

## 9. Guardrail Engine

**Source**: `backend/services/guardrail_engine.py` (351 lines)

Hard constraints that block unsafe actions before execution.

### 9.1 Four Guard Types

| Guard | Default Limit | Description |
|-------|--------------|-------------|
| **Spot Ratio Cap** | 80% | Max percentage of cluster nodes on spot |
| **AZ Concentration** | 60% per AZ | Max nodes in a single availability zone |
| **Family Concentration** | 40% per family | Max nodes using same instance family |
| **Monthly Spend Cap** | Configurable | Hard dollar ceiling on spot spend |

### 9.2 Health Score

```python
health_score = (
    0.40 × (1 - spot_ratio / spot_cap)
  + 0.30 × (1 - max_az_concentration / az_cap)
  + 0.20 × (1 - max_family_concentration / family_cap)
  + 0.10 × (1 - spend_ratio)
)
```

Returns 0.0 (critical) to 1.0 (healthy). Actions blocked when health_score < 0.2.

---

## 10. Circuit Breaker (Pillar 1 State Machine)

**Source**: `backend/services/circuit_breaker.py` (268 lines)

Three-state circuit breaker per cluster, stored in Redis.

### 10.1 State Machine

```
    ┌─────────────┐
    │   NORMAL    │ ← Stability window (configurable, default 30 min)
    │             │
    └──────┬──────┘
           │ Rollback detected
           ▼
    ┌─────────────┐
    │ CONSERVATIVE│ ← Restrict to safer pools only
    │             │
    └──────┬──────┘
           │ Multiple rollbacks within window
           ▼
    ┌─────────────┐
    │    HALT     │ ← Block ALL spot actions
    │             │
    └─────────────┘
           │ Manual reset OR stability window expires
           └─────────────→ NORMAL
```

### 10.2 Transition Triggers

| Trigger | Transition |
|---------|-----------|
| 1 rollback within window | NORMAL → CONSERVATIVE |
| 2+ rollbacks within window | CONSERVATIVE → HALT |
| Stability window expires (no rollbacks) | Any → NORMAL |
| Manual admin reset | Any → NORMAL |

### 10.3 Redis Keys

| Key | TTL | Purpose |
|-----|-----|---------|
| `spot:circuit_breaker:{cluster_id}` | Varies | Current state |
| `spot:cb_rollback_count:{cluster_id}` | Window duration | Rollback counter |
| `spot:cb_stability_window:{cluster_id}` | Window duration | Stability timer |

---

## 11. Blacklist Service

**Source**: `backend/services/blacklist_service.py` (440 lines)

Global pool blacklisting with exponential backoff and source differentiation.

### 11.1 Tiered TTLs

| Strike | TTL | Description |
|--------|-----|-------------|
| 1st | 1 hour | First failure |
| 2nd | 6 hours | Repeated failure |
| 3rd | 24 hours | Persistent failure |
| 4th+ | 48 hours (capped) | Chronic failure |

### 11.2 Source Differentiation

| Source | Weight | Description |
|--------|--------|-------------|
| `deterministic` | 1.0 | Actual EC2 capacity failure |
| `predictive` | 0.5 | ML-predicted instability |
| `execution` | 1.0 | Execution-layer DryRun failure |

### 11.3 Key Methods

| Method | Purpose |
|--------|---------|
| `blacklist_pool_tiered_safe()` | Blacklist with exponential backoff |
| `is_blacklisted()` | Check if pool is currently blacklisted |
| `get_pool_blacklist_info()` | Get blacklist metadata (strikes, source, TTL) |
| `clear_blacklist()` | Manual admin clear |

### 11.4 Redis Keys

| Key | TTL | Purpose |
|-----|-----|---------|
| `spot:blacklist:{pool_id}` | Tiered (1h–48h) | Active blacklist flag |
| `spot:blacklist_strikes:{pool_id}` | 7 days | Strike counter for exponential backoff |
| `spot:blacklist_meta:{pool_id}` | Same as blacklist | JSON metadata (source, reason, timestamp) |

---

## 12. Cooldown Controller

**Source**: `backend/services/cooldown_controller.py` (428 lines)

Anti-flapping cooldowns at three levels with DB write-through for persistence.

### 12.1 Cooldown Types

| Type | Key Pattern | Default TTL | Purpose |
|------|------------|-------------|---------|
| **Cluster** | `spot:cooldown:cluster:{cluster_id}` | 60s | After any cluster-level action |
| **Pool** | `spot:cooldown:pool:{pool_id}` | 300s | After pool-specific action |
| **Action** | `spot:cooldown:action:{type}:{cluster_id}` | Varies | Per action type (switch/resize/substitute) |

### 12.2 Action-Specific Cooldowns

| Action Type | Default TTL | Purpose |
|-------------|-------------|---------|
| `switch` | 600s (10 min) | After pool switch |
| `resize` | 7200s (2 hours) | After right-sizing |
| `substitute` | 300s (5 min) | After substitute activation |

### 12.3 Stabilization Lock

```python
CooldownController.acquire_stabilization_lock(cluster_id, duration_s=60)
```

- Set in Redis: `spot:stabilization:{cluster_id}` (TTL = duration_s)
- Written to DB: `cluster_cooldown_states.stabilization_until`
- On Redis cache miss, auto-rebalancer re-hydrates from DB table
- All systems check `is_stabilization_locked()` before acting

### 12.4 DB Persistence (Issue 13 Fix)

`ClusterCooldownState` table ensures stabilization lock survives Redis restarts:

| Column | Type | Purpose |
|--------|------|---------|
| `cluster_id` | String(36) PK | Cluster reference |
| `stabilization_until` | DateTime | When stabilization expires |
| `last_action_at` | DateTime | When last action was taken |

---

## 13. Recovery Monitor

**Source**: `backend/workers/tasks/recovery_monitor.py` (805 lines)

Four Celery tasks running every 5 minutes, aggregated by the `recovery_monitor` umbrella task.

### 13.1 Task 1: `sync_instance_states`

Syncs AWS EC2 instance states to DB:
- For each active cluster, calls `DescribeInstances` (via STS assumed-role)
- Marks DB instances as `terminated` if AWS says `terminated` or `shutting-down`
- Uses batch describe (200 IDs/call) with individual fallback on `InvalidInstanceID`
- **Cross-account safety**: Skips clusters where `assume_role` fails (never falls back to platform creds for wrong account)

### 13.2 Task 2: `scan_orphans`

Detects and terminates orphaned EC2 instances:
- Finds instances tagged `spot-optimizer:status=pending` that are older than `ORPHAN_INSTANCE_TIMEOUT_MIN`
- Checks for `node_joined:{iid}` Redis key before termination
- **Problem #18 double-check**: Also checks DB for `node_name` (agent heartbeat) and manual override key `spot:prevent_orphan_termination:{iid}`
- **Two-pass scanning**:
  - Pass 1: Platform-creds (same-account clusters only, P-M5 optimized)
  - Pass 2: Per-cluster assumed-role (cross-account customers)

### 13.3 Task 3: `detect_karpenter_stalls`

Detects Karpenter consolidation stalls:
- Finds `TERMINATE_NODE` actions with `termination_mode=karpenter` completed >15 min ago
- Checks if target EC2 instance is still running in AWS
- Force-terminates if stalled (records `karpenter_stall_detected` in metadata)
- P-C4 fix: Uses assumed-role credentials for cross-account clusters

### 13.4 Task 4: `recover_stuck_cordoned_nodes` (Z2 Fix)

Detects nodes cordoned by rebalancer whose action subsequently failed:
- Finds failed RebalancingActions where `step_2_cordon` exists in metadata
- Also catches in_progress/waiting_agent actions stuck >20 min past cordon
- Checks cluster agent is online (heartbeat <5 min)
- Dispatches `UNCORDON_NODE` AgentAction if no pending uncordon exists

### 13.5 Task 5: `compute_all_cluster_coverage`

Computes spot pool coverage per cluster:
- Coverage statuses: `COVERED` (≥3 pools), `AT_RISK` (1–2), `STRANDED` (0), `STATEFUL`, `UNCLASSIFIED`
- Cached in Redis: `cluster_coverage:{cluster_id}` (TTL 360s, Issue 3d fix)
- Warns on `STRANDED` nodes (no verified pools available)

---

## 14. Discovery Worker

**Source**: `backend/workers/tasks/discovery.py` (1040 lines)

Scans AWS accounts for EKS clusters and EC2 instances every 5 minutes.

### 14.1 Scan Flow

```
1. Query all ACTIVE/SCANNING accounts from DB
2. For each account:
   a. Assume IAM role via STS (platform credentials from SystemConfig)
   b. Scan EKS clusters across 14 AWS regions
   c. For each cluster:
      - Describe cluster metadata (endpoint, CA cert, version)
      - Shallow Scan: analyze spot vs OD pricing for savings estimate
      - Cost Explorer query (cached 24h)
      - Instance pricing fallback if Cost Explorer returns $0
      - Upsert cluster record (create or update)
   d. Scan EC2 instances across all regions
   e. Cleanup deleted clusters
3. Stale agent-node cleanup (instances not updated >10 min)
4. Update account sync status
```

### 14.2 Cluster Lifecycle (Discovery)

| Status | Condition |
|--------|-----------|
| `DISCOVERED` | Found in AWS, no agent |
| `ACTIVE` | Agent installed + heartbeat |
| `DEGRADED` | Agent installed but missing from AWS (preserved data) |
| `DISCONNECTED` | Agent timeout |

### 14.3 Key Features

- **Multi-region scanning**: 14 AWS regions per account
- **ARN-based deduplication**: Uses cluster ARN as primary key (globally unique), fallback to `(account_id, name)`
- **Dismissed cluster revival**: Auto-revives dismissed clusters when rediscovered in AWS
- **DEGRADED restoration**: Restores DEGRADED clusters when they reappear
- **RC3 guard**: 3-consecutive-observation requirement for SPOT→OD lifecycle downgrade (600s TTL)
- **Stale node cleanup**: Agent-reported nodes not updated >10 min marked as terminated
- **Discovery freshness key**: `spot:discovery_last_updated:{cluster_id}` (600s TTL) — rebalancer can skip stale data

---

## 15. Hibernation Service

**Source**: `backend/services/hibernation_service.py` (494 lines)

Schedule-based cluster hibernation with three strategies.

### 15.1 Strategies

| Strategy | Description | Savings | Wake Time | Risk |
|----------|-------------|---------|-----------|------|
| `NAMESPACE_SLEEP` | Scale all workload replicas to 0 | 80% | 2 min | Low |
| `NUCLEAR` | Terminate worker nodes | 70% | 5 min | Medium |
| `SNAPSHOT_RESTORE` | Stop entire cluster | 95% | 15 min | High |

### 15.2 Schedule Types

| Type | Slots | Description |
|------|-------|-------------|
| `WEEKLY` | 168 (7×24) | Hour-by-hour weekly schedule |
| `DAILY` | 24 | Daily recurring pattern |
| `MONTHLY` | 744 (31×24) | Full month schedule |

### 15.3 Key Features

- **Schedule matrix**: Binary string (`0`=awake, `1`=sleeping) per hour slot
- **Conflict detection**: Matrix overlap comparison across all schedule types (normalized to 744 monthly slots)
- **Pre-warm**: Configurable minutes before wake to pre-warm nodes
- **Cluster locking**: `hibernation_lock` UUID + `hibernation_lock_acquired_at` for concurrency control
- **Savings estimation**: `sleep_hours × hourly_cost × strategy_savings_pct`

---

## 16. Background Schedules

### 16.1 Celery Beat Schedule (Source: `backend/workers/app.py`)

42+ scheduled tasks. Key entries:

| Task | Interval | Purpose |
|------|----------|---------|
| `auto_rebalancer_loop` | 15s | Execute pending rebalancing actions |
| `termination_monitor` | 30s | Detect spot termination notices |
| `discovery_worker_loop` | 5 min | Scan AWS accounts |
| `pricing_collector_loop` | 5 min | Refresh spot/OD pricing |
| `recovery_monitor` | 5 min | Sync states, scan orphans, detect stalls |
| `sync_instance_states` | 5 min | AWS→DB instance state sync |
| `scan_orphans` | 5 min | Terminate orphaned pending instances |
| `detect_karpenter_stalls` | 5 min | Detect & fix Karpenter stalls |
| `compute_all_cluster_coverage` | 5 min | Coverage computation per cluster |
| `reconciliation_worker` | 5 min | Node alternative reconciliation |
| `hibernation_executor` | 1 min | Execute hibernation schedules |
| `rightsizing_worker` | 10 min | Generate right-sizing recommendations |
| `auto_scaler_loop` | 30s | ASCP auto-scaler (pending pod detection) |
| `volatility_collector` | 5 min | Collect spot price volatility data |
| `substitute_reconcile` | 5 min | Reconcile warm substitutes |
| `cleanup_stale_actions` | 5 min | Expire stuck rebalancing actions |
| `expire_stale_agent_actions` | 5 min | Expire old agent actions |
| `heartbeat_monitor` | 1 min | Detect disconnected agents |

### 16.2 APScheduler Jobs (Source: `backend/scheduler.py`)

| Job | Interval | Purpose |
|-----|----------|---------|
| `detect_cluster_activity` | 5 min | Check cluster activity and update status |
| `reconcile_stale_substitutes` | 10 min | Clean up expired warm substitutes |
| `detect_spot_volatility` | 5 min | Detect abnormal spot price movements |
| `schedule_proactive_migrations` | 15 min | Pre-emptive migrations for at-risk nodes |
| `cleanup_expired_locks` | 30 min | Remove stale distributed locks |
| `log_system_metrics` | 1 min | Emit system health metrics |

---

## 17. API Gateway & Routes

**Source**: `backend/core/api_gateway.py` (826 lines)

### 17.1 Route Groups

| Prefix | Router Source | Purpose |
|--------|-------------|---------|
| `/api/v1/auth` | `auth_router` | Login, register, JWT refresh |
| `/api/v1/accounts` | `accounts_router` | AWS account CRUD |
| `/api/v1/clusters` | `clusters_router` | Cluster management |
| `/api/v1/instances` | `instances_router` | Instance CRUD |
| `/api/v1/optimization` | `optimization_router` | Optimization jobs |
| `/api/v1/ascpai` | `ascpai_router` | Decision engine & ML pipeline |
| `/api/v1/agent` | `agent_router` | In-cluster agent communication |
| `/api/v1/metrics` | `metrics_router` | Metrics ingestion |
| `/api/v1/settings` | `settings_router` | Platform settings |
| `/api/v1/profile` | `profile_router` | User profile |
| `/api/v1/templates` | `templates_router` | Node templates |
| `/api/v1/cost` | `cost_router` | Cost analytics |
| `/api/v1/events` | `events_router` | Event log |
| `/api/v1/audit` | `audit_router` | Audit trail |
| `/api/v1/alerts` | `alerts_router` | Alert configuration |
| `/api/v1/hibernation` | `hibernation_router` | Hibernation schedules |
| `/api/v1/karpenter` | `karpenter_router` | Karpenter NodePool management |
| `/api/v1/rightsizing` | `rightsizing_router` | Right-sizing proposals |
| `/api/v1/reports` | `reports_router` | Report generation |
| `/api/v1/admin` | `admin_router` | Platform administration |
| `/api/v1/onboarding` | `onboarding_router` | Guided onboarding flow |
| `/api/v1/system` | `system_router` | System health |
| `/api/v1/notifications` | `notification_router` | User notifications |

### 17.2 WebSocket

| Endpoint | Purpose |
|----------|---------|
| `/ws/metrics` | Real-time cluster metrics streaming |

### 17.3 Special Endpoints

| Endpoint | Purpose |
|----------|---------|
| `GET /` | Service info (version, timestamp) |
| `GET /health` | Health check (DB + Redis connectivity) |
| `GET /api/v1/system/health` | Detailed system health |
| `GET /api/v1/debug/routes` | List all registered routes |

---

## 18. Data Models (Key Tables)

**Source**: `backend/models/cluster.py` (315 lines)

### 18.1 Cluster Model

| Column | Type | Purpose |
|--------|------|---------|
| `id` | String(36) PK | UUID |
| `cluster_uid` | String(8) UNIQUE | Short display ID (hex) |
| `name` | String | EKS cluster name |
| `account_id` | String FK | Parent AWS account |
| `arn` | String UNIQUE | AWS cluster ARN |
| `region` | String | AWS region |
| `status` | Enum | PENDING, DISCOVERED, ACTIVE, INACTIVE, ERROR, TERMINATED, DISCONNECTED, DEGRADED |
| `agent_installed` | String | 'Y' or 'N' |
| `karpenter_mode` | Enum | `dry_run` or `auto` |
| `optimization_mode` | String(20) | COST_FIRST, BALANCED, NO_DOWNTIME_FIRST |
| `auto_rebalance_enabled` | Boolean | Enable auto OD→spot migration |
| `rightsizing_enabled` | Boolean | Enable right-sizing |
| `is_hibernating` | Boolean | Currently hibernated |
| `is_dismissed` | Boolean | User-dismissed (prevents re-discovery) |
| `managed_node_group_deleted` | Boolean | Original MNG deleted after migration |

### 18.2 ClusterOptimizationSettings

Per-cluster tunable overrides (PK: `cluster_id`):

| Setting | Default | Description |
|---------|---------|-------------|
| `auto_rebalance_enabled` | false | Auto-rebalancing toggle |
| `auto_rightsizing_enabled` | false | Auto right-sizing toggle |
| `cooldown_override_minutes` | null | Custom cooldown duration |
| `manual_approval_required` | false | Require human approval |
| `target_spot_exposure_pct` | 100 | Max spot exposure |
| `maintain_standby` | false | Keep warm substitute nodes |
| `diversify_pools` | false | Enable pool diversification |
| `max_family_diversification_cap_pct` | 40 | Max family concentration |
| `instance_type_diversification_pct` | 100 | Instance type spread |
| `failure_cooldown_minutes` | 30 | Cooldown after failure |
| `min_node_count` | 1 | Hard floor for node count |
| `scale_down_threshold_pct` | 20 | Idle threshold for scale-down |
| `scale_down_stabilization_minutes` | 15 | Stabilization before scale-down |
| `enable_ascp_auto_scaler` | false | Built-in auto-scaler toggle |
| `check_interval_seconds` | 15 | Rebalance check frequency |
| `architecture_preference` | "both" | CPU arch filter (both/amd64/arm64) |
| `drain_timeout_minutes` | 15 | Pod drain timeout |
| `max_concurrent_rebalance_actions` | null (=1) | Parallel replacement cap |
| `rebalance_batch_percent` | null (=auto) | Max % nodes rebalanced per cycle |
| `karpenter_only_mode` | false | Skip ASG code paths |

### 18.3 OptimizationStrategy

Per-cluster optimization profile:

| Column | Default | Description |
|--------|---------|-------------|
| `strategy_type` | BALANCED | COST_FIRST, BALANCED, NO_DOWNTIME_FIRST, CUSTOM |
| `risk_ceiling_percent` | 25 | Max acceptable risk score |
| `min_savings_percent` | 15 | Min savings to justify migration |
| `volatility_tolerance_percent` | 20 | Max price volatility tolerance |
| `migration_penalty_multiplier` | 1.5 | Cost multiplier for migrations |
| `diversity_strictness_level` | Medium | Low/Medium/High |
| `risk_savings_tradeoff_pct` | 20 | Accept X% more expensive if safer |

---

## 19. Pillar 1 — Rebalancing State Machine

**Source**: `backend/workers/tasks/auto_rebalancer.py` lines 33–113

### 19.1 States

```
CREATED → POOL_SELECTED → SOURCE_CORDONED → SOURCE_DRAINED
    → REPLACEMENT_LAUNCHING → REPLACEMENT_READY
    → SOURCE_TERMINATING → COMPLETED
                                        ↘ FAILED
                                        ↘ DRAIN_TIMEOUT
```

### 19.2 Atomic Transitions (`_sm_transition`)

Uses **optimistic locking** via SQL:

```sql
UPDATE rebalancing_actions
   SET current_state = :to_state
 WHERE id = :action_id
   AND current_state = :from_state
```

- Returns `True` if exactly 1 row updated (transition won)
- Returns `False` if another worker already advanced past `from_state`
- **BUG-8 fix**: Up to 2 retries with 100ms/200ms backoff
- Re-reads current state before each retry to detect if another worker won

### 19.3 Force-Set State (`_sm_set_state`)

For initial `CREATED` and terminal states (`FAILED`/`COMPLETED`), bypasses optimistic check.

---

## 20. Pillar 6 — Schema Validation

**Source**: `backend/workers/tasks/auto_rebalancer.py` lines 250–306

`_validate_rebalancing_action_schema()` enforces data contracts **before** DB insert.

### 20.1 Validation Rules

| Rule | Constraint | Error |
|------|-----------|-------|
| Contract 1 | `source_pool` must contain `:` (format: `instance_type:az`) | ValueError |
| Contract 1 | `target_pool` must contain `:` (format: `instance_type:az`) | ValueError |
| Contract 2 | `source_od_price_hr` must be ≥ 0 when provided | ValueError |
| Contract 2 | `target_spot_price_hr` must be ≥ 0 when provided | ValueError |
| Contract 3 | `estimated_savings_hr` must ≈ `source_od - target_spot` (5% tolerance) | ValueError |

### 20.2 Pool Format

Valid pool format: `^[a-z][a-z0-9.]+:[a-z]{2}-[a-z]+-\d[a-z]$`

Examples:
- ✅ `m5.large:ap-south-1a`
- ✅ `c6g.xlarge:us-east-1b`
- ❌ `m5.large` (missing AZ)
- ❌ `M5.LARGE:ap-south-1a` (uppercase)

---

## 21. Cross-System Safety Gates

**Source**: `backend/workers/tasks/auto_rebalancer.py` lines 714–752

Before any rebalancing action executes, five safety gates are checked in order:

| Gate | Check | Defer Reason |
|------|-------|-------------|
| 1. Cluster Cooldown | `key_cluster_cooldown(cluster_id)` exists in Redis | Recent action needs time to settle |
| 2. Concurrency Lock | `key_rebalance_lock(cluster_id)` SET NX (TTL 2700s) | Another rebalance in progress |
| 3. Stabilization Lock | `CooldownController.is_stabilization_locked()` | Another system acted recently |
| 4. Substitute Mutex | `spot:substitute:state:{cluster_id}` = PREWARMING/RELEASING | SubstituteManager mid-flight |
| 5. Resize Cooldown | `spot:cooldown:action:resize:{cluster_id}` exists | Right-sizing in progress |

If any gate triggers, the action is set to `status='deferred'` with an explanatory error message.

### Additional Guards

| Guard | Source | Purpose |
|-------|--------|---------|
| **Double-launch** | `replacement_spot_instance_id` in metadata | Prevents re-launching already-launched replacement |
| **Distributed lock** | `lock:node_action:{cluster_id}` (TTL 1200s) | One system drains per cluster at a time |
| **Lock heartbeat** | Background thread, 60s interval | Renews per-cluster rebalance lock TTL |

---

## 22. Redis Key Reference

Comprehensive reference of all Redis keys used across the system.

### State & Locks

| Key Pattern | TTL | Owner |
|------------|-----|-------|
| `spot:circuit_breaker:{cluster_id}` | Varies | CircuitBreaker |
| `spot:cb_rollback_count:{cluster_id}` | Window | CircuitBreaker |
| `spot:stabilization:{cluster_id}` | 60s default | CooldownController |
| `spot:substitute:state:{cluster_id}` | None | SubstituteManager |
| `lock:node_action:{cluster_id}` | 1200s | AutoRebalancer |
| `lock:execution:{cluster_id}` | 600s | ExecutionController |

### Cooldowns

| Key Pattern | TTL | Owner |
|------------|-----|-------|
| `spot:cooldown:cluster:{cluster_id}` | 60s | CooldownController |
| `spot:cooldown:pool:{pool_id}` | 300s | CooldownController |
| `spot:cooldown:action:{type}:{cluster_id}` | Varies | CooldownController |

### Blacklisting

| Key Pattern | TTL | Owner |
|------------|-----|-------|
| `spot:blacklist:{pool_id}` | 1h–48h | BlacklistService |
| `spot:blacklist_strikes:{pool_id}` | 7 days | BlacklistService |
| `spot:blacklist_meta:{pool_id}` | Same as blacklist | BlacklistService |

### Caching

| Key Pattern | TTL | Owner |
|------------|-----|-------|
| `spot:pool_rank:{cluster_id}` | 300s | PoolRankingService |
| `spot:pool_score:{pool_id}` | 600s | PoolRankingService |
| `verified_pools:{cluster_id}` | 300s | PoolRankingService |
| `cluster_coverage:{cluster_id}` | 360s | RecoveryMonitor |
| `instance_type_arch:{type}` | 7 days | AutoRebalancer |

### Execution Safety

| Key Pattern | TTL | Owner |
|------------|-----|-------|
| `spot:execution_fail:{pool_id}` | 1h | KarpenterService |
| `spot:cluster_circuit_breaker:{cluster_id}` | 30min | KarpenterService |
| `spot:exec_fail_window:{cluster_id}` | 10min | KarpenterService |
| `spot:dryrun_failures_24h:{pool}` | 24h | PoolRankingService |
| `spot:dryrun_count:{region}` | 24h | PoolRankingService |

### Recovery & Monitoring

| Key Pattern | TTL | Owner |
|------------|-----|-------|
| `spot:ondemand_fallback:{cluster_id}` | 12h | KarpenterService |
| `spot:discovery_last_updated:{cluster_id}` | 600s | DiscoveryWorker |
| `node_joined:{instance_id}` | Varies | Agent |
| `spot:prevent_orphan_termination:{iid}` | Manual | Manual override |
| `aws_sync:empty_streak:{cluster_id}` | 600s | AutoRebalancer |
| `rc3:sync_od_streak:{instance_id}` | 600s | AutoRebalancer |

### Concurrency Locks

| Key Pattern | TTL | Owner |
|------------|-----|-------|
| `key_rebalance_lock:{cluster_id}` | 2700s (45min) | AutoRebalancer |
| `key_cluster_cooldown:{cluster_id}` | Varies | AutoRebalancer |

---

## Appendix: File Index

| File | Lines | Primary Responsibility |
|------|-------|----------------------|
| `backend/core/api_gateway.py` | 826 | FastAPI app, routes, middleware |
| `backend/core/risk_engine.py` | 343 | Bayesian risk scoring |
| `backend/core/ev_model.py` | 184 | Economic expected value |
| `backend/services/pool_ranking_service.py` | 2886 | 8-step ML pipeline (System A) |
| `backend/services/decision_engine_service.py` | 322 | Pool selection facade |
| `backend/services/execution_controller.py` | 360 | 13-step replacement pipeline |
| `backend/services/guardrail_engine.py` | 351 | Hard safety constraints |
| `backend/services/circuit_breaker.py` | 268 | 3-state circuit breaker |
| `backend/services/blacklist_service.py` | 440 | Pool blacklisting |
| `backend/services/cooldown_controller.py` | 428 | Anti-flapping cooldowns |
| `backend/services/karpenter_service.py` | 1016 | Karpenter NodePool management |
| `backend/services/hibernation_service.py` | 494 | Cluster hibernation |
| `backend/workers/tasks/auto_rebalancer.py` | 5948 | Node migration execution |
| `backend/workers/tasks/recovery_monitor.py` | 805 | State sync + orphan cleanup |
| `backend/workers/tasks/discovery.py` | 1040 | AWS account scanning |
| `backend/workers/app.py` | 324 | Celery config + beat schedule |
| `backend/scheduler.py` | 220 | APScheduler jobs |
| `backend/models/cluster.py` | 315 | Cluster + settings models |
