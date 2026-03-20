# Remediation Task Plan — ASCP.ai Platform

> **Generated**: 2026-03-13 | **Updated**: 2026-03-13 | **Source**: `change-guide.md` + `main-2-updated.md` cross-referenced against live codebase  
> **Rule**: Every file path verified against actual project. No fake data. No hardcoded fallbacks.  
> **Structure**: 4 Parts, ordered by dependency (foundational → behavioral → safety → polish)  
> **Changes in this revision**: Task 2.2 corrected (RC3 resets on OD reads too; all 3 cluster grace periods); Task 2.9 added (ML circuit breaker Redis keys); Task 3.3 enhanced (full 6-step Karpenter install + `agent/config.py` CLUSTER_NAME); Task 3.7 enhanced (orphan cleanup via action metadata, per-mode failure paths).

---

## Part 1 — Agent & Termination Infrastructure (Foundation Layer)

> These changes are prerequisites for Parts 2–4. The agent's termination mode, component architecture, and communication primitives must be correct before higher-level logic can work.

---

### Task 1.1 — Replace `decrement_asg` Boolean with `termination_mode` Enum

**Priority**: 🔴 CRITICAL  
**Status**: `[ ]`

**Problem**: The old `decrement_asg=True` boolean is used in 7 locations. The doc requires a 3-mode enum: `"replacement"`, `"karpenter"`, `"scaledown"`.

**Files to modify**:

| # | File | Path | Size | What to change |
|---|---|---|---|---|
| 1 | `actuator.py` | `agent/actuator.py` | 75,528B | L1144: Replace `decrement_asg = payload.get("decrement_asg", True)` with `termination_mode = payload.get("termination_mode", "scaledown")`. L1174-1256: Branch logic by mode. |
| 2 | `auto_rebalancer.py` | `backend/workers/tasks/auto_rebalancer.py` | 209,405B | L655: Change `"decrement_asg": True` to `"termination_mode": "replacement"`. L1730: Same. L3576: Same. |
| 3 | `karpenter_routes.py` | `backend/api/karpenter_routes.py` | 102,932B | L1130: Change `"decrement_asg": True` to `"termination_mode": "karpenter"`. |
| 4 | `emergency_rebalancer.py` | `backend/workers/tasks/emergency_rebalancer.py` | 11,020B | All TERMINATE_NODE payloads: set `"termination_mode": "replacement"` (or `"karpenter"` when Karpenter installed). |
| 5 | `execution_controller.py` | `backend/services/execution_controller.py` | 15,305B | Verify termination payload construction uses `termination_mode`. |

**Implementation for `agent/actuator.py` `_terminate_node()`**:
```python
# MODE: "replacement" → detach-not-decrement
#   1. Redis NX lock: asg:suspend_lock:{asg_name} (30s TTL)
#   2. suspend_processes(['Launch'])
#   3. detach_instances(ShouldDecrementDesiredCapacity=False)
#   4. ec2.terminate_instances()
#   5. resume_processes(['Launch'])
#
# MODE: "karpenter" → direct EC2 terminate, zero ASG calls
#   1. ec2.terminate_instances() only
#
# MODE: "scaledown" → existing logic
#   1. terminate_instance_in_auto_scaling_group(ShouldDecrementDesiredCapacity=True)
```

**Deprecated code to remove**:
- `agent/actuator.py` L1144: `decrement_asg = payload.get("decrement_asg", True)` — DELETE
- `agent/actuator.py` L1174: `if decrement_asg:` — REPLACE with mode switch
- `agent/actuator.py` L1256: `# Direct EC2 terminate (used if decrement_asg=False` — UPDATE comment

**Inter-dependencies**:
- `backend/utils/aws/asg.py` (10,420B): Contains `detach_instances()` at L182 and L247 — used by `"replacement"` mode
- `backend/services/distributed_locks.py` (12,508B): Provides Redis NX lock for `asg:suspend_lock:{asg_name}`
- `backend/core/redis_client.py` (3,201B): Redis client for lock operations

**Validation**: After change, grep for `decrement_asg` — should return 0 results outside test files.

---

### Task 1.2 — `termination-mode` Label Safety Check + Post-Conflict Outcome

**Priority**: 🟠 HIGH  
**Status**: `[ ]`

**Files to modify**:

| # | File | Path | What to change |
|---|---|---|---|
| 1 | `actuator.py` | `agent/actuator.py` | In `_terminate_node()`: Read `spot-optimizer/termination-mode` label. If label says `"replacement"` and caller tries `"scaledown"` → block, mark action FAILED, uncordon node, no fallback. |

**Post-conflict outcome** (must be explicit):
1. Action status → `FAILED`
2. Node → uncordoned (if it was cordoned in CORDON phase)
3. No alternative termination mode attempted
4. Log conflict as `termination_mode_conflict` event

---

### Task 1.3 — Orchestrator Endpoint Authentication (Issue #2)

**Priority**: 🔴 CRITICAL  
**Status**: `[ ]`

**Files to modify**:

| # | File | Path | What to change |
|---|---|---|---|
| 1 | `agents.py` | `backend/routers/agents.py` | 6,822B — Add `Depends(validate_api_key)` to `/register`, `/deregister`, `/heartbeat`, orchestrator polling endpoints. |
| 2 | `dependencies.py` | `backend/core/dependencies.py` | 17,053B — `validate_api_key` already exists (L441 shows legacy X-API-Key). Verify it works for orchestrator. |
| 3 | `actuator.py` | `agent/actuator.py` | Verify `poll_actions()` and `report_action_result()` send `Authorization: Bearer {API_TOKEN}` header. |
| 4 | `agent_routes.py` | `backend/api/agent_routes.py` | 13,433B — If orchestrator endpoints are here instead of `routers/agents.py`, add auth here. |

**Deprecated to clean**:
- `backend/core/dependencies.py` L309: `DEPRECATED: Use get_agent_cluster_from_jwt for OIDC-based authentication` — the legacy `get_agent_cluster_from_api_key()` function should be marked for removal after migration.
- `backend/core/dependencies.py` L441: `X-API-Key: <api_key> (Legacy - deprecated)` — plan migration timeline.

---

### Task 1.4 — Emergency Action FIFO Ordering (Issue #7)

**Priority**: 🟠 HIGH  
**Status**: `[ ]`

**Files to modify**:

| # | File | Path | What to change |
|---|---|---|---|
| 1 | `agents.py` | `backend/routers/agents.py` | 6,822B — In orchestrator polling endpoint query, change ordering to `priority DESC, created_at ASC`. |
| 2 | `agent_action.py` | `backend/models/agent_action.py` | 4,031B — Verify `priority` field exists (integer, default 0, emergency = 10). |

---

### Task 1.5 — Agent Component Architecture Verification

**Priority**: 🟡 MEDIUM  
**Status**: `[ ]`

**Files to verify** (all must exist and match doc):

| # | Component | File | Path | Size | Role |
|---|---|---|---|---|---|
| 1 | SpotPoller | `poller.py` | `agent/poller.py` | 7,609B | IMDS termination detection (DaemonSet) |
| 2 | MetricsCollector | `collector.py` | `agent/collector.py` | 20,639B | Node-level metrics (DaemonSet) |
| 3 | PodMetricsCollector | `pod_metrics_collector.py` | `agent/pod_metrics_collector.py` | 12,876B | Pod CPU/memory, sends every 5min (DaemonSet) |
| 4 | HeartbeatSender | `heartbeat.py` | `agent/heartbeat.py` | 12,511B | Health check (DaemonSet) |
| 5 | ActionActuator | `actuator.py` | `agent/actuator.py` | 75,528B | Action execution (Deployment) |
| 6 | WebSocketClient | `websocket_client.py` | `agent/websocket_client.py` | 15,374B | Emergency push + polling (Deployment) |

**In `agent/main.py`** (17,673B):
- Verify DaemonSet entrypoint starts components 1-4
- Verify Deployment entrypoint starts components 5-6
- Verify health monitor has max restart count + exponential backoff (Issue #9): `max_restart_count=5`, backoff `2^n` capped at 60s

---

### Task 1.6 — WebSocket Push + HMAC Verification

**Priority**: 🟠 HIGH  
**Status**: `[ ]`

| # | File | Path | What to change |
|---|---|---|---|
| 1 | `websocket_client.py` | `agent/websocket_client.py` | 15,374B — Verify handles `emergency_command` message type. Verify HMAC-SHA256 verification of incoming payloads using `SECRET_KEY`. |
| 2 | `sse_manager.py` | `backend/core/sse_manager.py` | 1,986B — Verify sends `emergency_command` type for priority=10 actions. |
| 3 | `action_executor.py` | `backend/core/action_executor.py` | 18,916B — Verify HMAC-SHA256 signing of outbound action payloads. |
| 4 | `cluster_routes.py` | `backend/api/cluster_routes.py` | 35,883B — `POST /clusters/{id}/agent/disconnect` must force-close WebSocket connections (Issue #8). |

---

### Task 1.7 — WebSocket API Key Invalidation (Issue #8)

**Priority**: 🟠 HIGH  
**Status**: `[ ]`

| # | File | Path | What to change |
|---|---|---|---|
| 1 | `cluster_routes.py` | `backend/api/cluster_routes.py` | 35,883B — L531-565 disconnect endpoint: After rotating API key, call `close_connections_for_cluster(cluster_id)` on WebSocket manager. |
| 2 | `sse_manager.py` | `backend/core/sse_manager.py` | 1,986B — Add `close_connections_for_cluster()` method if missing. |
| 3 | `websocket_routes.py` | `backend/api/websocket_routes.py` | 2,442B — Verify WebSocket handler respects forced disconnection. |

---

### Task 1.8 — Thread Restart Loop Backoff (Issue #9)

**Priority**: 🟡 MEDIUM  
**Status**: `[ ]`

| # | File | Path | What to change |
|---|---|---|---|
| 1 | `main.py` | `agent/main.py` | 17,673B — L415-481 health monitor: Add `max_restart_count=5` per component. Add exponential backoff `delay = min(2^n, 60)` seconds. After max exceeded → log CRITICAL, mark component DEAD. |

**UI impact**: Cluster Details → Agent tab → show restart counts per component.

---

### Part 1 Checklist

- [ ] 1.1 — `termination_mode` enum replaces `decrement_asg` (7 locations)
- [ ] 1.2 — Label safety check + post-conflict outcome (FAILED + uncordon)
- [ ] 1.3 — Orchestrator endpoint auth (Issue #2)
- [ ] 1.4 — Emergency FIFO ordering (Issue #7)
- [ ] 1.5 — All 6 agent components verified
- [ ] 1.6 — WebSocket push + HMAC verification
- [ ] 1.7 — WebSocket forced disconnect (Issue #8)
- [ ] 1.8 — Thread restart backoff (Issue #9)

---
---

## Part 2 — Data Sources, Decision Engine & Action System

> Core optimization logic: pricing, discovery, pool rankings, the 15-step decision pipeline, and the 3-mode action system (Mode 1 Rebalance / Mode 2 Rightsizing / Mode 3 Synergy).

---

### Task 2.1 — Pricing Staleness & Emergency Refresh

**Priority**: 🟠 HIGH  
**Status**: `[ ]`

| # | File | Path | Size | What to change |
|---|---|---|---|---|
| 1 | `aws_pricing_service.py` | `backend/services/aws_pricing_service.py` | 19,818B | Detect partial refresh (some AZs succeed, others fail). Set `spot:pricing:partial_stale:{cluster_id}` Redis key. |
| 2 | `pricing_worker.py` | `backend/workers/tasks/pricing_worker.py` | 8,858B | Add emergency pricing refresh trigger on spot interruption. Add partial staleness detection. |
| 3 | `spot_advisor_scraper.py` | `backend/scrapers/spot_advisor_scraper.py` | 15,507B | Add versioning key `spot:advisor:version` — compare scraped data hash vs cached hash, skip write if identical (Issue #19). |
| 4 | `pricing_collector.py` | `backend/scrapers/pricing_collector.py` | 20,672B | Verify pricing data flow. |

**Hardcoded data to clean** (from codebase scan):
- `backend/services/pool_ranking_service.py` L1553: `# Hardcoded accurate on-demand hourly prices (ap-south-1)` — Replace with DB-backed pricing from `aws_pricing_service.py`
- `backend/services/pool_rotation_service.py` L526: `# Hardcoded for ap-south-1` — Must pull from pricing API
- `backend/services/dynamic_instance_helpers.py` L22: `# Hardcoded fallback tables` — Acceptable ONLY as boot fallback, but must log warning when used

---

### Task 2.2 — Discovery Worker Fixes (Issues #10, RC4, Grace Periods)

**Priority**: 🟠 HIGH  
**Status**: `[ ]`

| # | File | Path | Size | What to change |
|---|---|---|---|---|
| 1 | `discovery.py` | `backend/workers/tasks/discovery.py` | 39,682B | **RC3 guard reset** (Issue #10, L720-768): `rc3:od_streak:{instance_id}` counter — confirmed SPOT reading resets counter. **Also reset on confirmed OD read** (currently missing — counter can expire silently). **RC4 ghost cleanup** (L794-839): After EC2 scan, any DB instance with `state='running'` NOT seen in scan → mark `terminated`. Terminated instances older than 5 min → delete from DB. **Cluster cleanup grace periods** (L583-633): (1) Never delete clusters created <60 min ago; (2) Agent-installed clusters require 2h heartbeat absence before deletion; (3) Any cluster with heartbeat <10 min ago must be preserved. |
| 2 | `daily_stats_aggregator.py` | `backend/workers/tasks/daily_stats_aggregator.py` | 2,938B | Verify `daily_cluster_stats` table receives daily snapshot writes. |
| 3 | `daily_cluster_stats.py` | `backend/models/daily_cluster_stats.py` | 1,402B | Verify model schema matches doc (savings, spot_usage_pct, cost columns). |

**RC3 Correction Detail**: Current code (`discovery.py` L720-768) only resets `rc3:od_streak:{instance_id}` on confirmed SPOT reading. A clean OD read does NOT reset the counter — it can expire silently without triggering downgrade. Fix: reset counter explicitly on **both** confirmed SPOT and confirmed OD reads.

---

### Task 2.3 — Emergency Dedup (Issue #20) — CORRECTED

**Priority**: 🔴 CRITICAL  
**Status**: `[ ]`

| # | File | Path | Size | What to change |
|---|---|---|---|---|
| 1 | `termination_monitor.py` | `backend/workers/tasks/termination_monitor.py` | 11,662B | **PRIMARY FILE**: Add Redis key `emergency:dedup:{instance_id}` (TTL=**2min**) in `detect_termination_notice()`. Check before creating emergency action. |
| 2 | `sqs_consumer.py` | `backend/workers/tasks/sqs_consumer.py` | 11,046B | Route through same dedup path in `termination_monitor.py`. |
| 3 | `emergency_rebalancer.py` | `backend/workers/tasks/emergency_rebalancer.py` | 11,020B | NOT the dedup location (corrected from earlier). Receives already-deduped events. |

⚠️ **Key/TTL/File corrected**: Was `spot:emergency_dedup` / 5min / `emergency_rebalancer.py`. Now `emergency:dedup:{instance_id}` / 2min / `termination_monitor.py`.

---

### Task 2.4 — Decision Engine 15-Step Pipeline + Optimization Profiles

**Priority**: 🟠 HIGH  
**Status**: `[ ]`

| # | File | Path | Size | What to change |
|---|---|---|---|---|
| 1 | `decision_engine.py` | `backend/core/decision_engine.py` | 37,806B | Verify 15-step pipeline exists. Verify 3 optimization profiles: `COST_FIRST` (ceiling 0.55), `BALANCED` (0.35), `NO_DOWNTIME_FIRST` (0.15). |
| 2 | `ev_model.py` | `backend/core/ev_model.py` | 7,716B | Verify EV scoring formula: `EV = savings_pct × (1 - interruption_risk) × capacity_confidence`. |
| 3 | `risk_engine.py` | `backend/core/risk_engine.py` | 12,383B | Verify volatility guard (pool >2 interruptions/24h → penalty 1.5×) and three-layer risk ceiling: `effective_ceiling = base × volatility_factor × trust_phase_factor`. |
| 4 | `diversity_enforcer.py` | `backend/services/diversity_enforcer.py` | 9,766B | Verify Step 12 diversification: `max_family_diversification_cap_pct` setting enforced. |
| 5 | `pool_ranking_service.py` | `backend/services/pool_ranking_service.py` | 80,989B | Verify cache miss handling: If Redis `spot:pool_rankings:{cluster_id}` → MISS, Decision Engine should block and return `NO_ACTION` (Issue #6). |

**Deprecated to clean**:
- `backend/core/scoring.py` L15: `compute_expected_value: DEPRECATED for execution paths` — L53 emits warning. Verify no production code still calls it.
- `backend/core/scoring.py` L17: `compute_combined_expected_value: DEPRECATED` — L139 emits warning. Remove all callers.

---

### Task 2.5 — Three-Mode Action System (Mode 1 / Mode 2 / Mode 3)

**Priority**: 🔴 CRITICAL  
**Status**: `[ ]`

| # | File | Path | Size | What to change |
|---|---|---|---|---|
| 1 | `auto_rebalancer.py` | `backend/workers/tasks/auto_rebalancer.py` | 209,405B | **Mode 1**: Verify node eval order (descending hourly cost). Verify Gate 1 five conditions: `candidate_ev > current_ev` AND `savings >= min_savings_percent` AND `risk < risk_ceiling_percent` AND NOT on cooldown AND passes DryRun. Verify action expiry (15min). Verify `[:6]` instance cascade (Issue #18 — make configurable). |
| 2 | `rightsizing_service.py` | `backend/services/rightsizing_service.py` | 43,484B | **Mode 2**: Verify two-gate system (Gate 1: ML analysis, Gate 2: safety checks). Verify 5 settings: `rightsizing_target`, `rightsizing_history_window_days`, `rightsizing_frequency_hours`, `rightsizing_cooldown_hours`, `rightsizing_headroom_multiplier`. |
| 3 | `optimizer_coordinator.py` | `backend/services/optimizer_coordinator.py` | 27,537B | **Mode 3 synergy**: Lock `rightsizing_target` to `"spot"` when both toggles ON. Combined execution creates BOTH `PATCH_CONTAINER_RESOURCES` + `PATCH_KARPENTER_NODEPOOL`. **Downgrade path**: Gate 1 fails → fall back to Gate 2 only (resize pods, no NodePool patch). |
| 4 | `optimizer_coordinator_worker.py` | `backend/workers/tasks/optimizer_coordinator_worker.py` | 10,630B | Verify 4 tasks: `pool_optimization_worker` (30min), `rightsizing_evaluation_worker` (24h), `evaluate_proposal_task` (event), `execute_approved_proposal_task` (trigger). |
| 5 | `workload_inspector.py` | `backend/services/workload_inspector.py` | 14,396B | Verify classification: `STATELESS_ELIGIBLE` / `STATEFUL_PROTECTED`. Redis key: `spot:node_classification:{id}`. |
| 6 | `control_plane_loop.py` | `backend/workers/tasks/control_plane_loop.py` | 16,455B | Verify 8-step decision cycle exists. |

**Concurrency control** (3 layers in `auto_rebalancer.py`):
1. Global Redis lock: `spot:rebalancer:lock:{cluster_id}` (10min TTL)
2. Per-node: `spot:node:in_progress:{node_name}` (15min TTL)
3. Per-ASG: `asg:suspend_lock:{asg_name}` (30s TTL)

---

### Task 2.6 — VolumeAttachment Cleanup Post-Drain

**Priority**: 🟡 MEDIUM  
**Status**: `[ ]`

| # | File | Path | What to change |
|---|---|---|---|
| 1 | `actuator.py` | `agent/actuator.py` | After `drain_node()` completes, list `VolumeAttachment` objects for drained node → delete them to prevent EBS volume leak. |

---

### Task 2.7 — Savings Calculator: Filter + Aggregation

**Priority**: 🟡 MEDIUM  
**Status**: `[ ]`

| # | File | Path | Size | What to change |
|---|---|---|---|---|
| 1 | `savings_calculator.py` | `backend/workers/tasks/savings_calculator.py` | 6,988B | Verify filters by `spot-optimizer/launched-by=platform` label (Issue #3). Verify `daily_cluster_stats` write path. |
| 2 | `auto_rebalancer.py` | `backend/workers/tasks/auto_rebalancer.py` | 209,405B | Verify `Cluster.realized_savings_monthly` updated after every successful rebalance. |
| 3 | `cluster.py` | `backend/models/cluster.py` | 10,334B | Verify `realized_savings_monthly` field exists. |

---

### Task 2.8 — Resize Guard Enhanced (Synergy + Full 2h Monitoring)

**Priority**: 🟡 MEDIUM  
**Status**: `[ ]`

| # | File | Path | Size | What to change |
|---|---|---|---|---|
| 1 | `resize_guard_worker.py` | `backend/workers/tasks/resize_guard_worker.py` | 7,138B | Add pool risk signal monitoring for Mode 3 (synergy). Verify 2h post-execution: CPU >85%/10min → revert, pod restart >2× baseline → revert, memory >5 events/2h → revert. |
| 2 | `rightsizing_service.py` | `backend/services/rightsizing_service.py` | 43,484B | Revert mechanism: re-patch to original requests (stateless). Stateful → alert only. |

---

### Task 2.9 — ML Circuit Breaker Monitoring (Redis Keys)

**Priority**: 🟡 MEDIUM  
**Status**: `[ ]`

**Problem**: ML pipeline failures need circuit breaker tracking via Redis keys `atharvaai:ml_fail_count` (INCR, 10-min TTL) and `atharvaai:ml_degraded` (10-min TTL). Verify exact key names match between code and doc.

| # | File | Path | What to change |
|---|---|---|---|
| 1 | `pool_ranking_service.py` | `backend/services/pool_ranking_service.py` | 80,989B — Verify ML circuit breaker logic: `atharvaai:ml_fail_count` INCR (10-min TTL) + `atharvaai:ml_degraded` flag (10-min TTL). Confirm Redis key names match exactly. |
| 2 | `atharvaai_worker.py` | `backend/workers/tasks/atharvaai_worker.py` | Verify circuit breaker activations flow from ML worker → `pool_ranking_service.py`. |
| 3 | `redis_client.py` | `backend/core/redis_client.py` | 3,201B — Verify Redis client handles ML fail count operations. |

**UI impact**: Admin Dashboard → ML Status section → show circuit breaker state (Normal / Degraded).

---

### Part 2 Checklist

- [ ] 2.1 — Pricing staleness + emergency refresh + hardcoded price cleanup
- [ ] 2.2 — Discovery RC3 reset (SPOT + OD), RC4 ghost cleanup, all 3 cluster grace periods
- [ ] 2.3 — Emergency dedup (CORRECTED: `emergency:dedup`, 2min, `termination_monitor.py`)
- [ ] 2.4 — Decision engine 15-step + profiles + deprecated scoring cleanup
- [ ] 2.5 — Three-mode action system (all 6 files)
- [ ] 2.6 — VolumeAttachment cleanup
- [ ] 2.7 — Savings filter + aggregation
- [ ] 2.8 — Resize guard synergy + 2h monitoring
- [ ] 2.9 — ML circuit breaker Redis key verification (`atharvaai:ml_fail_count`, `atharvaai:ml_degraded`)

---
---

## Part 3 — Emergency System, Karpenter & Safety Gates

> Interruption handling, Karpenter integration, blacklist/cooldown/circuit breaker logic, and failure recovery. These depend on Part 1 (termination_mode) and Part 2 (decision engine).

---

### Task 3.1 — Emergency Standby-First Path + Karpenter EC2 Direct

**Priority**: 🔴 CRITICAL  
**Status**: `[ ]`

| # | File | Path | Size | What to change |
|---|---|---|---|---|
| 1 | `emergency_rebalancer.py` | `backend/workers/tasks/emergency_rebalancer.py` | 11,020B | Verify standby-first path (6 steps): UNCORDON standby → CORDON interrupted → DRAIN 90s/force → Terminate → Mark active → Launch new standby. **Karpenter path**: When Karpenter installed, use direct `ec2.terminate_instances()` with **zero ASG interaction**. |
| 2 | `standby.py` | `backend/workers/tasks/standby.py` | 6,118B | Verify async standby launch after emergency use. |
| 3 | `maintain_warm_spare_worker.py` | `backend/workers/tasks/maintain_warm_spare_worker.py` | 4,662B | Verify warm spare maintenance loop. |
| 4 | `cluster.py` | `backend/models/cluster.py` | 10,334B | Verify `maintain_standby` field in `cluster_optimization_settings`. |

---

### Task 3.2 — InstabilityPropagator Cross-Cluster Pressure

**Priority**: 🟠 HIGH  
**Status**: `[ ]`

| # | File | Path | Size | What to change |
|---|---|---|---|---|
| 1 | `instability_propagator.py` | `backend/services/instability_propagator.py` | 9,950B | Verify all 6 steps: INCR events (30min TTL) → SADD affected clusters (2h TTL) → Bayesian pressure → Store → AZ average → ESCALATE_ALL if ≥3 clusters. |
| 2 | `risk_engine.py` | `backend/core/risk_engine.py` | 12,383B | `calculate_bayesian_pool_pressure()` — verify exists and is called from propagator. |
| 3 | `termination_monitor.py` | `backend/workers/tasks/termination_monitor.py` | 11,662B | Propagation called synchronously within interruption handling. |

---

### Task 3.3 — Karpenter Three-Way Toggle + Install + Redis Keys

**Priority**: 🟠 HIGH  
**Status**: `[ ]`

| # | File | Path | Size | What to change |
|---|---|---|---|---|
| 1 | `karpenter_service.py` | `backend/services/karpenter_service.py` | 36,002B | Verify three-way toggle: `None` (Off) / `"dry_run"` (Insights) / `"auto"` (Auto-Optimize). Verify 5 Redis keys: `spot:karpenter:installed:{id}`, `spot:karpenter:nodepool_updated:{id}` (30min), `spot:karpenter:provision_requested:{id}` (15min), `spot:ondemand_fallback:{id}` (12h), `spot:execution_failures:{id}` (10min). |
| 2 | `karpenter_routes.py` | `backend/api/karpenter_routes.py` | 102,932B | Verify install flow (6 steps): (1) Create SQS queue `KarpenterInterruptionQueue-{cluster_name}`, (2) helm install v1.0.8, (3) IRSA annotation on ServiceAccount, (4) Register `KarpenterNodeRole` access entry, (5) Create default `EC2NodeClass` with `alias: al2023@latest` (dual-arch), (6) Create default `NodePool` with `karpenter.sh/v1`, `consolidationPolicy: WhenUnderutilized`, `consolidateAfter: 30s`. |
| 3 | `actuator.py` | `agent/actuator.py` | 75,528B | **NodePool patch** (Issue #1 CRITICAL): Verify JSON path `spec.template.spec.requirements` not `spec.requirements`. **Auto-creation** (Issue #11): On 404, fall back to `CLUSTER_NAME` env var (not ConfigMap inference) for NodePool auto-create. Verify `install_karpenter()` L782-868 (all 6 steps). Verify `uninstall_karpenter()` L1289-1326. |
| 4 | `config.py` | `agent/config.py` | Add `CLUSTER_NAME` env var (used as fallback when NodePool auto-create runs on 404). Without this, the agent falls back to unreliable ConfigMap/label inference. |

**NodePool Auto-Create Correction**: Current code infers cluster name from ConfigMap or node labels on 404. Change to use `CLUSTER_NAME` env var set during agent deployment — this is the reliable source of truth.

---

### Task 3.4 — Blacklist System (Cascade, Backoff, Tiered, Hygiene)

**Priority**: 🟠 HIGH  
**Status**: `[ ]`

| # | File | Path | Size | What to change |
|---|---|---|---|---|
| 1 | `blacklist_service.py` | `backend/services/blacklist_service.py` | 14,018B | **Issue #14**: Cascade >70% → suspend only predictive, keep deterministic. **Issue #16**: Backoff max 168h — add decay/recency. **Tiered** (5 tiers): DryRun 1-2×→6h, DryRun 3+→12h, ML>0.45→24h, Termination→24h, Exec DryRun→penalty only. **Hygiene**: `cleanup_redis_keys()` daily — orphaned `spot:*` keys get 24h safety TTL. |

---

### Task 3.5 — Cooldown System (10 Types)

**Priority**: 🟡 MEDIUM  
**Status**: `[ ]`

| # | File | Path | Size | What to change |
|---|---|---|---|---|
| 1 | `cooldown_controller.py` | `backend/services/cooldown_controller.py` | 11,665B | Verify all 10 cooldowns exist with correct TTLs: Cluster switch (60min), Pool reuse (120min), Resize per-controller (6h), ASG suspend lock (30s), Stateful per-cluster (48h), Stateful per-instance (48h), + 4 others. |

---

### Task 3.6 — Circuit Breaker (States, Exclusions, Transitions)

**Priority**: 🟠 HIGH  
**Status**: `[ ]`

| # | File | Path | Size | What to change |
|---|---|---|---|---|
| 1 | `circuit_breaker.py` | `backend/services/circuit_breaker.py` | 10,829B | Verify 3 states: NORMAL → CONSERVATIVE (≥2 rollbacks/1h, ×1.3) → HALT (≥3, blocks all except emergency). Recovery: HALT→CONSERVATIVE 30min, CONSERVATIVE→NORMAL 2h. Emergency (priority=10) and gate rejections DO NOT increment rollback counter. |
| 2 | `circuit_breaker_state.py` | `backend/models/circuit_breaker_state.py` | 2,319B | Verify model exists with state, transition timestamps. |

---

### Task 3.7 — Failure Handling: Mode-Split + Uncordon + Karpenter Failure

**Priority**: 🟠 HIGH  
**Status**: `[ ]`

| # | File | Path | What to change |
|---|---|---|---|
| 1 | `auto_rebalancer.py` | `backend/workers/tasks/auto_rebalancer.py` | **TERMINATE phase split by mode**: `"replacement"` → terminate orphan using `replacement_spot_instance_id` from action metadata, then uncordon original. `"scaledown"` → no orphan (ASG manages). `"karpenter"` → no ASG rollback path, log+alert only. **Orphan cleanup**: If DB record of replacement node is missing, use `replacement_spot_instance_id` from action metadata to terminate orphan directly via EC2 API. **Uncordon-after-rollback**: When Phase 2 CORDON or Phase 2 DRAIN fails → explicitly call `uncordon_node()` before terminating orphan spot instance. This must be explicit, not assumed. |
| 2 | `recovery_monitor.py` | `backend/workers/tasks/recovery_monitor.py` | 13,824B — Verify karpenter-mode lingering nodes: add timeout check — if Karpenter fails to terminate a node (consolidation stalls), fall back to direct `ec2.terminate_instances()`. Add periodic reconciliation task or resize guard hook for this detection. |

**Termination Mode Failure Paths** (must be implemented separately per mode):
- `"replacement"` → On DRAIN failure → `uncordon_node(original)` → terminate orphan spot via `replacement_spot_instance_id`
- `"scaledown"` → On failure → no orphan node, log only
- `"karpenter"` → On Karpenter consolidation stall → detect lingering node via timeout → fall back to `ec2.terminate_instances()` directly

---

### Task 3.8 — PDB Fail-Safe Direction (Issue #13) + Finalizer Removal (Issue #12)

**Priority**: 🟡 MEDIUM  
**Status**: `[ ]`

| # | File | Path | What to change |
|---|---|---|---|
| 1 | `actuator.py` | `agent/actuator.py` | L103-128 `check_pdb_violation()`: Verify fail-safe returns `False` (allow drain) on error, matching `kubectl drain`. |
| 2 | `actuator.py` | `agent/actuator.py` | L254-280 `force_delete_node()`: After deleting K8s node, list `Terminating` pods on that node and PATCH to remove finalizers (`metadata.finalizers = []`). |
| 3 | `agent_action.py` | `backend/models/agent_action.py` | 4,031B | Add `REMOVE_POD_FINALIZERS` to `AgentActionType` enum. |

---

### Task 3.9 — Node Labels + Drain Grace + Resolution Chain

**Priority**: 🟡 MEDIUM  
**Status**: `[ ]`

| # | File | Path | What to change |
|---|---|---|---|
| 1 | `auto_rebalancer.py` | `backend/workers/tasks/auto_rebalancer.py` | Apply labels at launch: `spot-optimizer/template-id`, `allowed-architectures`, `launched-by`, `termination-mode`. |
| 2 | `actuator.py` | `agent/actuator.py` | **Drain grace by caller**: Mode 1→60s/no-force, Mode 3→60s/no-force, Emergency→90s/force, IMDS→30s/force. **Node resolution chain**: (1) `payload.node_name` → (2) `_find_node_by_instance_id()` via `spec.providerID` → (3) `_find_node_name()` label match. |
| 3 | `asg.py` | `backend/utils/aws/asg.py` | 10,420B | Verify `detach_instances()` and `_detach_instance_from_asg()` exist for replacement mode. |
| 4 | `template_service.py` | `backend/services/template_service.py` | 2,991B | Template label source. |
| 5 | `node_template.py` | `backend/models/node_template.py` | 3,328B | Verify template model fields. |

---

### Part 3 Checklist

- [ ] 3.1 — Emergency standby-first + Karpenter EC2 direct path
- [ ] 3.2 — InstabilityPropagator (6 steps + SYSTEMIC threshold)
- [ ] 3.3 — Karpenter toggle + install + Redis keys + NodePool patch (Issue #1)
- [ ] 3.4 — Blacklist cascade/backoff/tiered/hygiene (Issues #14, #16)
- [ ] 3.5 — Cooldown system (10 types)
- [ ] 3.6 — Circuit breaker states + emergency exclusion
- [ ] 3.7 — Failure mode-split + uncordon + karpenter failure
- [ ] 3.8 — PDB fail-safe (Issue #13) + finalizer removal (Issue #12)
- [ ] 3.9 — Node labels + drain grace + resolution chain

---
---

## Part 4 — Compliance, Cleanup, UI & Infrastructure

> Audit, notifications, deprecated code removal, multi-tenancy verification, UI enhancements, and HA infrastructure. These are independent of Parts 1-3 and can be parallelized.

---

### Task 4.1 — Audit Log: Retention + Tamper Detection

**Priority**: 🟠 HIGH  
**Status**: `[ ]`

| # | File | Path | Size | What to change |
|---|---|---|---|---|
| 1 | `audit_service.py` | `backend/services/audit_service.py` | 5,733B | Add configurable retention policy. Verify SHA-256 checksum on insert: `hash(actor_id + event + resource + timestamp + diffs)`. Add periodic integrity verification Celery task (Issue #15). |
| 2 | `audit_log.py` | `backend/models/audit_log.py` | 2,613B | Verify `checksum` column exists. Verify model is immutable (no `update()` method). |
| 3 | `audit_routes.py` | `backend/api/audit_routes.py` | 4,004B | Add retention policy settings endpoint. |

---

### Task 4.2 — Decision Audit Persistence (Issue #4)

**Priority**: 🟠 HIGH  
**Status**: `[ ]`

| # | File | Path | Size | What to change |
|---|---|---|---|---|
| 1 | `observability_logger.py` | `backend/services/observability_logger.py` | 6,731B | Decision audit currently uses Redis with 24h expiry → persist to DB. Add `decision_audit` table or extend `audit_log`. |
| 2 | `decision_engine_service.py` | `backend/services/decision_engine_service.py` | 11,966B | Verify service writes to persistent storage. |
| 3 | `decision_routes.py` | `backend/api/decision_routes.py` | 5,654B | Verify endpoint returns historical data. |

---

### Task 4.3 — External Alerting (Issue #17)

**Priority**: 🟡 MEDIUM  
**Status**: `[ ]`

| # | File | Path | Size | What to change |
|---|---|---|---|---|
| 1 | `notification_service.py` | `backend/services/notification_service.py` | 26,883B | Add webhook-based notifications (Slack, PagerDuty, email). Currently only Prometheus metrics. |
| 2 | `alert_worker.py` | `backend/workers/tasks/alert_worker.py` | 9,776B | Wire webhook calls for events: Spot Interruption, Circuit Breaker State Change, Rebalance Failure. |
| 3 | `alert_config.py` | `backend/models/alert_config.py` | 7,232B | Verify model supports webhook URL config. |
| 4 | `alert_history.py` | `backend/models/alert_history.py` | 7,372B | Verify alert history tracking. |

---

### Task 4.4 — Multi-Tenancy Data Isolation Verification

**Priority**: 🟡 MEDIUM  
**Status**: `[ ]`

| # | File | Path | What to change |
|---|---|---|---|
| 1 | `cluster.py` | `backend/models/cluster.py` | Verify `organization_id → account_id → cluster_id` hierarchy. Each cluster has unique `API_KEY`. |
| 2 | `redis_client.py` | `backend/core/redis_client.py` | 3,201B — Verify all Redis keys include `cluster_id`. |
| 3 | `node_template.py` | `backend/models/node_template.py` | Templates scoped to organization, shared across clusters. |
| 4 | `redis_keys.py` | `backend/redis_keys.py` | 1,683B — Central Redis key definitions. Verify all keys are tenant-scoped. |

---

### Task 4.5 — HA & Scaling: Celery Emergency Queue

**Priority**: 🟡 MEDIUM  
**Status**: `[ ]`

| # | File | Path | What to change |
|---|---|---|---|
| 1 | `app.py` | `backend/workers/app.py` | 12,348B — Verify Celery app config routes `emergency_rebalancer` to dedicated `emergency` queue. |
| 2 | `docker-compose / K8s` | Project root or `charts/` | Verify separate `celery-emergency` worker container with higher concurrency. |
| 3 | `scheduler.py` | `backend/scheduler.py` | 7,532B — Verify Celery beat schedule includes all periodic tasks. |

---

### Task 4.6 — Upgrade Process: Agent Update Endpoint

**Priority**: 🟡 MEDIUM  
**Status**: `[ ]`

| # | File | Path | What to change |
|---|---|---|---|
| 1 | `cluster_routes.py` | `backend/api/cluster_routes.py` | 35,883B — Verify `POST /clusters/{id}/update-agent` exists (redeploys DaemonSet + Orchestrator). |
| 2 | `agent_injector.py` | `backend/services/agent_injector.py` | 108,658B — Agent install/update logic. |
| 3 | `installer_routes.py` | `backend/api/installer_routes.py` | 6,914B — L57 has hardcoded fallback — verify it only applies to missing manifest file, not to data. |

---

### Task 4.7 — Deprecated Code Cleanup

**Priority**: 🟡 MEDIUM  
**Status**: `[ ]`

All deprecated items found in codebase scan:

| # | File | Path | Line | Deprecated Item | Action |
|---|---|---|---|---|---|
| 1 | `scoring.py` | `backend/core/scoring.py` | L15 | `compute_expected_value()` | Remove all production callers. Function emits deprecation warning (L53). |
| 2 | `scoring.py` | `backend/core/scoring.py` | L17 | `compute_combined_expected_value()` | Remove all production callers. Function emits deprecation warning (L139). |
| 3 | `hygiene_routes.py` | `backend/api/hygiene_routes.py` | L260 | Categories endpoint (`GET /hygiene/categories`) | Already returns `{"deprecated": True}`. Plan removal or keep stub. |
| 4 | `auth_routes.py` | `backend/api/auth_routes.py` | L72, L166 | `org_role=None` parameter | Comment says "Deprecated - using unified role instead". Clean up. |
| 5 | `user.py` | `backend/models/user.py` | L67 | `org_role` column (commented out) | Remove dead code: `# org_role = Column(...)`. |
| 6 | `dependencies.py` | `backend/core/dependencies.py` | L309 | `get_agent_cluster_from_api_key()` | L309: "DEPRECATED: Use get_agent_cluster_from_jwt". Plan migration. |
| 7 | `dependencies.py` | `backend/core/dependencies.py` | L441 | `X-API-Key` header auth | L441: "Legacy - deprecated". Plan migration to Bearer JWT. |
| 8 | `agent_injector.py` | `backend/services/agent_injector.py` | L112 | `api_key` parameter | "legacy, will be deprecated". Plan migration. |

**Hardcoded data to address** (NOT in tests):

| # | File | Path | Line | Issue | Fix |
|---|---|---|---|---|---|
| 1 | `pool_ranking_service.py` | `backend/services/pool_ranking_service.py` | L1553 | Hardcoded OD prices for ap-south-1 | Use `aws_pricing_service.py` DB lookup with this as final fallback only + log warning |
| 2 | `pool_rotation_service.py` | `backend/services/pool_rotation_service.py` | L526 | `# Hardcoded for ap-south-1` | Pull from pricing API |
| 3 | `dynamic_instance_helpers.py` | `backend/services/dynamic_instance_helpers.py` | L22 | Hardcoded fallback tables | OK as boot fallback, add prominent log warning |
| 4 | `pool_ranking_service.py` | `backend/services/pool_ranking_service.py` | L158-159 | Hardcoded instance catalog | OK as boot fallback until worker populates DB |
| 5 | `tag_scoring_service.py` | `backend/services/tag_scoring_service.py` | L130 | `mock_resources = [` | Replace with real resource query |
| 6 | `karpenter_service.py` | `backend/services/karpenter_service.py` | L218 | `fallback_data = {` | Verify this is only used when real data unavailable |
| 7 | `base.py` | `backend/models/base.py` | L78 | `seed_demo_data()` | Ensure NOT called in production. Guard with `ENV != production`. |

---

### Task 4.8 — Instance Cascade Limit (Issue #18)

**Priority**: 🟡 MEDIUM  
**Status**: `[ ]`

| # | File | Path | What to change |
|---|---|---|---|
| 1 | `auto_rebalancer.py` | `backend/workers/tasks/auto_rebalancer.py` | L408-463: `[:6]` slice is hardcoded. Read from `cluster_optimization_settings.max_instance_type_attempts`. |
| 2 | `cluster.py` | `backend/models/cluster.py` | Add `max_instance_type_attempts` column to `cluster_optimization_settings` if not present (default 6). |

---

### Task 4.9 — Optimizer State Trust Phases

**Priority**: 🟡 MEDIUM  
**Status**: `[ ]`

| # | File | Path | Size | What to change |
|---|---|---|---|---|
| 1 | `optimizer_state.py` | `backend/models/optimizer_state.py` | 2,941B | Verify enum phases: `INITIAL_POOL_OPTIMIZATION`, `STABILIZATION`, `COOLDOWN`, etc. |
| 2 | `optimizer_coordinator_routes.py` | `backend/api/optimizer_coordinator_routes.py` | 16,486B | Verify API exposes current phase. |

---

### Part 4 Checklist

- [ ] 4.1 — Audit log retention + tamper detection
- [ ] 4.2 — Decision audit persistence (Issue #4)
- [ ] 4.3 — External alerting webhooks (Issue #17)
- [ ] 4.4 — Multi-tenancy data isolation verification
- [ ] 4.5 — Celery emergency queue HA
- [ ] 4.6 — Agent update endpoint verification
- [ ] 4.7 — Deprecated code cleanup (8 items + 7 hardcoded data)
- [ ] 4.8 — Instance cascade configurable (Issue #18)
- [ ] 4.9 — Optimizer state trust phases

---
---

## Master Summary

| Part | Tasks | Priority Breakdown | Key Files (most touched) |
|---|---|---|---|
| **Part 1 — Agent & Termination** | 8 tasks | 2 🔴, 3 🟠, 3 🟡 | `agent/actuator.py`, `backend/routers/agents.py`, `agent/main.py` |
| **Part 2 — Data & Decision** | 9 tasks | 2 🔴, 3 🟠, 4 🟡 | `auto_rebalancer.py`, `decision_engine.py`, `termination_monitor.py`, `pool_ranking_service.py` |
| **Part 3 — Emergency & Safety** | 9 tasks | 1 🔴, 5 🟠, 3 🟡 | `emergency_rebalancer.py`, `blacklist_service.py`, `circuit_breaker.py` |
| **Part 4 — Compliance & Cleanup** | 9 tasks | 0 🔴, 3 🟠, 6 🟡 | `audit_service.py`, `notification_service.py`, `scoring.py` |

**Total**: 35 tasks across **45+ files** | **5 CRITICAL** | **14 HIGH** | **16 MEDIUM**

### Execution Order
1. **Part 1 first** — foundation (termination_mode, auth) blocks everything else
2. **Part 2 next** — decision engine + action system builds on Part 1
3. **Part 3 after** — emergency + safety depends on Parts 1-2
4. **Part 4 parallel** — compliance/cleanup can run alongside Parts 2-3

### Open Issues Cross-Reference

| Issue # | Description | Part.Task |
|---|---|---|
| #1 | NodePool patch JSON path (CRITICAL) | 3.3 |
| #2 | Orchestrator endpoints unauthenticated (CRITICAL) | 1.3 |
| #3 | Savings counts pre-existing spot | 2.7 |
| #4 | Decision audit expires in 24h | 4.2 |
| #5 | Partial pricing refresh staleness | 2.1 |
| #6 | Pool rankings cache miss | 2.4 |
| #7 | Emergency FIFO ordering | 1.4 |
| #8 | WebSocket API key invalidation | 1.7 |
| #9 | Thread restart loop backoff | 1.8 |
| #10 | RC3 guard reset logic | 2.2 |
| #11 | NodePool auto-creation reliability | 3.3 |
| #12 | Force-delete pod finalizer removal | 3.8 |
| #13 | PDB fail-safe wrong direction | 3.8 |
| #14 | Blacklist cascade protection | 3.4 |
| #15 | Audit log retention | 4.1 |
| #16 | Blacklist backoff max cap | 3.4 |
| #17 | External alerting missing | 4.3 |
| #18 | Instance type cascade hardcoded | 4.8 |
| #19 | Spot advisor versioning key | 2.1 |
| #20 | SQS + IMDS deduplication | 2.3 |