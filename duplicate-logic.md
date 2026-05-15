# DUPLICATE & LEGACY LOGIC AUDIT
**Scope**: `backend/` Python source only. No .md or README files used as evidence.
**Mode**: Code-traced execution paths, import graph, and runtime usage analysis.
**Every claim below includes a file:line code reference.**

---

## Executive Summary

| Category | Count | Highest Risk |
|---|---|---|
| Parallel execution systems (planning-only vs real) | 3 phantom / 2 real | ControlPlaneLoop never dispatches AgentAction |
| Duplicate classification pipelines | 3 overlapping systems | WI vs WIE conflict on same workload |
| Legacy provisioning path | 1 (SpotASGService) | Partially active — API only |
| Confirmed dead code | 4 modules/classes | ExecutionController, ActionExecutor, BinPacker plans, agents/orchestrator |
| Beat schedule tasks with no confirmed registration | 5+ | `workers.discovery`, `workers.cost.*`, `workers.approval.*` |
| Broken data dependencies (read-only keys) | 3 Redis keys | `spot:workload:state`, `spot:keda:last_scale_event`, `spot:cluster:pending_pods` |
| Duplicate state stores | 3 concepts, 2+ stores each | Workload tier in DB + 2x Redis keys |

---

## §1. Actual Execution Flow (Verified from Code)

### 1.1 Flows That Actually Reach AgentAction (VERIFIED)

```
FLOW A — Auto-Rebalancer (Node Migration)
  beat(15s) → workers.auto_rebalancer (auto_rebalancer.py:2629)
           → execute_rebalancing()
           → eviction_safety.py checks
           → RebalancingAction (DB) + AgentAction (CORDON_NODE / DRAIN_NODE / EVICT_POD) created
           → Agent polls GET /agents/actions/pending (agent_routes.py:229)
           → Agent executes K8s call
           → Agent reports POST /agents/actions/{id}/result (agent_routes.py:330)
  SOURCE: auto_rebalancer.py:2629, agent_routes.py:229

FLOW B — PlacementController (Pod Eviction)
  beat(5min) → dispatch_placement_controller_cycles (placement_controller_task.py:48)
            → run_placement_controller_task (placement_controller_task.py:120)
            → PlacementController.run_cycle() (placement_controller_service.py:170)
            → _dispatch_eviction() → AgentAction(EVICT_POD) created (placement_controller_service.py:706)
  GUARD: FEATURE_PLACEMENT_CONTROLLER_ENABLED=False by default (core/config.py:108)
  SOURCE: placement_controller_task.py:120, placement_controller_service.py:706

FLOW C — Emergency Handler (Spot Interruption)
  SQS/IMDS → poll_interruption_queues (sqs_consumer.py:29)
           → emergency_rebalancer (emergency_rebalancer.py:35)
           → emergency_handler.py:69 → ExecutionController.execute_replacement()
           → ALL 4 STEPS ARE STUBS → never reaches AgentAction
           → Falls through to OD fallback
  SOURCE: emergency_handler.py:67-75, execution_controller.py:341,351,361,376

FLOW D — Placement Advisor Rollout
  beat(5min) → run_placement_cycle_task (placement_advisor_task.py:21)
            → execute_rollout_task (placement_advisor_task.py:105)
            → PlacementRolloutService._evict_pod() (placement_rollout_service.py:392)
            → AgentAction(EVICT_POD) created
  GUARD: FEATURE_PLACEMENT_ADVISOR_ENABLED=False by default (core/config.py:102)
  SOURCE: placement_advisor_task.py:21, placement_rollout_service.py:392

FLOW E — AnchoredNodeService (Stateful Pod Migration)
  api_trigger → AnchoredNodeService.migrate_pod_to_anchored_node() (anchored_node_service.py:192)
             → AgentAction(PATCH_AFFINITY) + AgentAction(EVICT_POD) created
  SOURCE: anchored_node_service.py:193-196
```

### 1.2 Planning-Only Loops — NEVER Dispatch AgentAction (CONFIRMED DEAD OUTPUT)

```
LOOP A — ControlPlaneLoop (8-step decision cycle)
  beat(5min) → run_all_clusters_decision_cycle (control_plane_loop.py:55)
            → ControlPlaneController.run_cycle() (control_plane_loop.py:100)
            → Step 8: _step8_build_execution_plan() returns dict with plan_hash
            → plan written to Redis spot:execution_plan_hash:{cluster_id} (control_plane_loop.py:487)
            → plan RETURNED to Celery task → logged → DISCARDED
            → ActionExecutor.execute_action_plan() is NEVER called from here
  PROOF: control_plane_loop.py:164-186 — return dict, no dispatch call
  RISK: Entire 8-step cycle (pool ranking, EV model, diversification) produces zero output

LOOP B — optimization.py optimize_cluster()
  beat → trigger_manual_optimization (optimization.py:22) → optimize_cluster (optimization.py:58)
       → spot_optimizer.detect_opportunities() + bin_packer.analyze_fragmentation()
       → action_plan dict built (optimization.py:101)
       → action_plan LOGGED and returned → no AgentAction dispatch
  PROOF: optimization.py:94-130 — no AgentAction import or creation
  SOURCE: optimization.py:58, modules/bin_packer.py:193

LOOP C — health.py check_reversion_opportunities()
  beat(1h) → check_reversion_opportunities (health.py)
           → optimizer.handle_fallback_reversion(cluster.id)
           → "In a real system, we'd execute these plans via Actuator" (health.py:45)
           → plans logged only
  PROOF: health.py:45-47 — comment explicitly says plans are not executed
```

---

## §2. Duplicate Logic (Confirmed)

### 2.1 THREE Workload Classification Pipelines (HIGH RISK)

#### Pipeline 1 — WorkloadClassifier (tier 0-4 dict)
- **File**: `services/workload_classifier.py:253`
- **Function**: `classify_workload(profile: dict) → dict` with keys `tier`, `tier_name`, `spot_eligible`
- **Output schema**: Integer tier 0–4 + string tier_name
- **Called from**:
  - `services/workload_inspector.py:906` — node-level scan
  - `services/workload_identification_engine.py:2306` — as "classifier bridge C4" (cross-import: `from backend.classification.workload_classifier import classify_workload`)

#### Pipeline 2 — WorkloadInspector (node-level Redis)
- **File**: `services/workload_inspector.py:37`
- **Class**: `WorkloadInspector`
- **Output schema**: `NodeStatus` enum (STATELESS_ELIGIBLE, STATEFUL_PROTECTED, STATEFUL_ELIGIBLE, SYSTEM_PROTECTED, UNKNOWN) — **5 different categories than Pipeline 1**
- **Storage**: Redis `spot:workload_tier:{cluster_id}:{ns}/{ctrl}` TTL 540s + `spot:workload_profile:{cluster_id}:{ns}/{ctrl}` TTL 540s
- **Called from**:
  - `services/optimizer_coordinator.py:73` — pool optimization
  - `services/substitute_manager.py:226` — warm spare
  - `services/rightsizing_service.py:130` — rightsizing
  - `workers/tasks/control_plane_loop.py:223` — Step 4 node filtering
  - `workers/tasks/auto_rebalancer.py` — eviction safety

#### Pipeline 3 — WorkloadIdentificationEngine (workload-level DB+Redis)
- **File**: `services/workload_identification_engine.py:2235`
- **Class**: `WorkloadIdentificationEngine`
- **Function**: `classify_workload(workload: WorkloadInput) → WorkloadClassification` with 50+ fields
- **Output schema**: Criticality tiers Platinum/Gold/Silver/Bronze/Spot — **incompatible with Pipeline 2 NodeStatus schema**
- **Storage**: `workload_classifications` DB table + Redis classification cache
- **Called from**:
  - `scheduler.py:82,173` — APScheduler slow/fast loops
  - `api/workload_classification_routes.py:37` — API routes
  - `services/placement_advisor_service.py` — reads from DB

**Conflict confirmed**:
- `auto_rebalancer.py` uses WI (Pipeline 2) to classify workloads for eviction safety
- `placement_controller_service.py` uses WIE (Pipeline 3) via `disruption_safe` field in `PlacementPolicy`
- Same workload can be classified differently by both systems simultaneously
- WI's `STATELESS_ELIGIBLE` ≠ WIE's `spot_friendly=True` — no mapping layer exists

### 2.2 TWO Parallel Execution Orchestrators (HIGH RISK)

| Orchestrator | File | Schedules | Actually Executes? |
|---|---|---|---|
| `ControlPlaneController` | `workers/tasks/control_plane_loop.py:75` | Every 5 min | **NO** — returns plan, no dispatch |
| `PlacementController` | `services/placement_controller_service.py:112` | Every 5 min | YES — writes AgentAction |
| `auto_rebalancer` | `workers/tasks/auto_rebalancer.py:2630` | Every 15 s | YES — writes AgentAction |
| `ExecutionController` | `services/execution_controller.py:75` | On-demand (emergency) | **NO** — 4 stub steps |
| `ActionExecutor` | `core/action_executor.py:52` | Never triggered | **NO** — never called from active path |

Both `ControlPlaneController` and `PlacementController` run on a 5-minute beat. Both enumerate clusters. Both perform redundant guard checks (hibernation, node eligibility). They are completely independent with no coordination.

**ControlPlaneController result path**: `control_plane_loop.py:178-186` — result dict returned to Celery, never consumed.
**PlacementController result path**: `placement_controller_service.py:706-767` — AgentAction written to DB, agent picks it up.

### 2.3 TWO Spot Provisioning Systems (MEDIUM RISK)

| System | File | Trigger | Mechanism |
|---|---|---|---|
| Karpenter | `services/karpenter_service.py` | Node shortage → Karpenter NodePool | K8s CRD-based (NodeClaim) |
| SpotASGService | `services/spot_asg_service.py:98` | Manual API call | AWS ASG MixedInstancesPolicy |

`SpotASGService` is called from:
- `api/karpenter_routes.py:2203` — `/enable-spot-asg` endpoint
- `api/karpenter_routes.py:2271` — `/revert-asg-to-on-demand` endpoint
- `api/karpenter_routes.py:2335` — `/nodegroup-spot-status`

These are non-Karpenter fallback routes (comment at `karpenter_routes.py:2138-2142` confirms: "legacy EKS versions, SCP-restricted environments"). Both systems can simultaneously be active on different nodegroups of the same cluster. No mutual exclusion check exists.

### 2.4 TWO Emergency Execution Paths (MEDIUM RISK)

| Path | File | Uses AgentAction? | Status |
|---|---|---|---|
| `ExecutionController` | `services/execution_controller.py:75` | NO — stubs | Dead in practice |
| `emergency_rebalancer` | `workers/tasks/emergency_rebalancer.py` | YES — via AR | Active |

Both are triggered from the same SQS interruption event chain (`sqs_consumer.py:29` → `emergency_rebalancer.py`). `emergency_handler.py:70` calls `ExecutionController` which always fails, then falls through to OD. The `emergency_rebalancer` task handles the actual spot migration separately. Result: two handlers fire for the same interruption event.

---

## §3. Legacy Components

### 3.1 ExecutionController — Legacy Replacement Architecture

- **File**: `services/execution_controller.py:75`
- **Status**: `PARTIALLY_USED` — instantiated, called, always fails
- **Evidence**: All 4 internal steps return `(False, "stub")`:
  - `_launch_spot_instance()` — `execution_controller.py:341`
  - `_wait_substitute_ready()` — `execution_controller.py:351`
  - `_migrate_workloads()` — `execution_controller.py:361`
  - `_terminate_source()` — `execution_controller.py:376`
- **Replaced by**: `auto_rebalancer.py` multi-phase EC2 launch + drain pipeline
- **Removal recommendation**: Safe to remove `ExecutionController` class; update `emergency_handler.py:70-75` to skip directly to OD fallback

### 3.2 ActionExecutor — Never Invoked from Active Pipeline

- **File**: `core/action_executor.py:52`
- **Status**: `UNUSED` — defined, tested, never called from production paths
- **Active callers**: `tests/test_integration_hardening.py:46` only (test mock)
- **Internal stubs**: `core/action_executor.py:339` — "TODO: Implement Kubernetes drain logic"; `core/action_executor.py:481` — "TODO: Implement actual consolidation logic"
- **Replaced by**: Agent-side K8s operations via AgentAction
- **Removal recommendation**: Safe to remove; remove from `test_integration_hardening.py` mock too

### 3.3 agents/ Orchestrator Layer — Never Invoked

- **Files**: `agents/orchestrator.py`, `agents/decision_engine_agent.py`, `agents/global_intelligence_agent.py`, `agents/rightsizing_agent.py`, `agents/cluster_execution_agent.py`, `agents/event_monitoring_agent.py`, `agents/substitute_manager_agent.py`
- **Status**: `UNUSED` — entire `agents/` package defined, never imported from any route, task, or service
- **Evidence**: `grep_search` for `AgentOrchestrator|agents.orchestrator` returns 0 results in non-agent files
- **The `agents/__init__.py:7-47`** exports all agents — but no external module imports from `backend.agents`
- **Replaced by**: Celery task workers (auto_rebalancer, placement_controller, etc.)
- **Removal recommendation**: Entire `backend/agents/` directory is safe to remove

### 3.4 SubstituteManager — Legacy Warm-Spare System (Partially Active)

- **File**: `services/substitute_manager.py:196`
- **Status**: `PARTIALLY_USED` — actively called by `scheduler.py:103`, `maintain_warm_spare_worker.py:73`, `event_monitor.py:488`
- **Redundancy**: `event_monitor.py:181-183` note: "SubstituteManager may not exist yet — gracefully handle" — indicates this is optional
- **Replaced by**: Karpenter NodePool provisioning for Karpenter clusters
- **Scope**: Only relevant for non-Karpenter clusters (same scope as SpotASGService)
- **Removal recommendation**: Do NOT remove — needed for non-Karpenter clusters; mark as "non-Karpenter only" path

### 3.5 BinPackingModule — Plans Never Executed

- **File**: `modules/bin_packer.py`
- **Status**: `PARTIALLY_USED` — called from `workers/tasks/optimization.py:97`; output logged but not dispatched
- **Evidence**: `optimization.py:101-130` — `action_plan` dict built, returned; no AgentAction created; `modules/__init__.py:17` exports it
- **Replacement**: No direct replacement; `auto_rebalancer.py` handles real node migration
- **Removal recommendation**: `UNKNOWN` — may be intended for future batch consolidation UI

### 3.6 APScheduler (scheduler.py) — Runs Parallel to Celery

- **File**: `scheduler.py`
- **Status**: `PARTIALLY_USED` — runs WIE slow/fast loops, SubstituteManager reconciliation
- **Redundancy**: WIE also callable via `workload_classification_routes.py`. Celery beat also runs `recovery_monitor`, `health_monitor` which duplicate some scheduler logic
- **Risk**: APScheduler and Celery both run independently; if both are started, WIE runs in both (double-classification)
- **Evidence**: `scheduler.py:79-88` (WIE slow loop), `scheduler.py:170-178` (WIE fast loop)

---

## §4. Dead Code

### 4.1 Confirmed Dead: `workers.discovery.scan_all_accounts`

- **File**: `workers/tasks/discovery.py:180`
- **Beat schedule**: `workers/app.py:52-55` — fires every 5 min
- **Include list**: `backend.workers.tasks.discovery` **NOT in `workers/app.py` include list**
- **Only caller**: `api/cluster_routes.py:87` — direct `.delay()` call from FastAPI; not a Celery worker module
- **Risk**: Beat schedule fires task message every 5 min; if no worker loads `discovery.py`, messages accumulate in queue unprocessed
- **Safe to fix**: Add `backend.workers.tasks.discovery` to include list, or move to app import

### 4.2 Confirmed Dead Output: `ControlPlaneLoop` execution plan

- **File**: `workers/tasks/control_plane_loop.py:164-186`
- **Proof**: `run_cycle()` returns dict; no caller reads `execution_plan.actions` to dispatch anything
- **`spot:execution_plan_hash:{cluster_id}`** written to Redis (TTL 300s) — never verified by any consumer outside tests
- **`tests/test_integration_hardening.py:69`** — tests call `control_plane.execute_step()` which doesn't exist on `ControlPlaneController` — test is testing a non-existent method
- **Safe to remove**: Not the class — but the beat schedule entry is wasted CPU every 5 min per cluster

### 4.3 Confirmed Dead: `core/action_executor.py` K8s execution

- **File**: `core/action_executor.py:338-339`
- **Proof**: `# TODO: Implement Kubernetes drain logic` in `_execute_spot_migration()` — has been a stub since inception
- **Never called from**: Any active Celery task or FastAPI route
- **Safe to remove**: Yes — `ActionExecutor` class and `get_action_executor()` factory

### 4.4 Confirmed Dead: `agents/` Python orchestrator

- **Files**: All 8 files under `backend/agents/`
- **Proof**: No import of `backend.agents.*` found in any `services/`, `workers/`, or `api/` file
- **`agents/config.py:149`** — `DecisionEngineAgent` configured but never instantiated in production
- **Safe to remove**: Yes — entire directory

### 4.5 Registered Tasks Not in beat_schedule

The following tasks are defined with `@app.task` / `@shared_task` but NOT listed in `workers/app.py` beat schedule (trigger-only, no periodic schedule):

| Task Name | File | Trigger Path |
|---|---|---|
| `inject_agent` | `workers/tasks/agent_tasks.py:12` | API-triggered only |
| `generate_weekly_report` | `workers/tasks/report_worker.py:48` | API-triggered only |
| `generate_monthly_report` | `workers/tasks/report_worker.py:555` | API-triggered only |
| `export_savings_to_csv` | `workers/tasks/report_worker.py:637` | API-triggered only |
| `trigger_manual_optimization` | `workers/tasks/optimization.py:22` | API-triggered only |
| `launch_standby_node` | `workers/tasks/standby.py:18` | API-triggered only |
| `cleanup_managed_node_group` | `workers/tasks/cleanup_tasks.py:18` | API-triggered only |
| `execute_hibernation` | `workers/tasks/hibernation_worker.py:158` | Triggered by scheduler |
| `execute_wake` | `workers/tasks/hibernation_worker.py:244` | Triggered by scheduler |
| `execute_prewarm` | `workers/tasks/hibernation_worker.py:338` | Triggered by scheduler |
| `evaluate_proposal_task` | `workers/tasks/optimizer_coordinator_worker.py:184` | API/event-triggered |
| `execute_approved_proposal_task` | `workers/tasks/optimizer_coordinator_worker.py:225` | API-triggered |

These are **intentionally not scheduled** (trigger-only). Not dead code — but worth documenting.

---

## §5. Broken / Unused Data Dependencies

### 5.1 Complete Dead Redis Key Map (Never Written)

| Key | Expected Writer | Actual Writers | Impact |
|---|---|---|---|
| `spot:workload:state:{cluster_id}:{workload_id}` | Agent heartbeat (per-workload) | **NONE** | PDB floor never applied; rollout wait always times out |
| `spot:keda:last_scale_event:{cluster_id}` | KEDA webhook / placement_webhook | **NONE** | KEDA scaling guard always False |
| `spot:cluster:pending_pods:{cluster_id}` | Agent heartbeat | **NONE** | Pending pods guard always 0 |

Agent heartbeat (`agent_routes.py:202-206`) writes THREE cluster-level keys:
```
spot:placement:agent_data:{cluster_id}:pod_metrics        (TTL 120s)
spot:placement:agent_data:{cluster_id}:cluster_spot_summary (TTL 120s)
spot:placement:agent_data:{cluster_id}:hpa_pdb            (TTL 300s)
```
None of these feed the per-workload `spot:workload:state` keys — there is **no translation layer**.

### 5.2 Features Relying on Missing Data

| Feature | Data Dependency | Data Available? | Consequence |
|---|---|---|---|
| PC KEDA scaling guard | `spot:keda:last_scale_event` | NO | Guard dead — PC evicts during KEDA scale-up |
| PC pending pods guard | `spot:cluster:pending_pods` | NO | Guard dead — always returns 0 |
| Advisor PDB-aware baseline | `spot:workload:state.pdb_min_available` | NO | PDB floor omitted — over-spots Gold tier |
| Rollout completion check | `spot:workload:state.current_spot_pods` | NO | Rollout task always "stuck" — cancels early |
| Stale migration recovery | `spot:workload:state.original_replicas` | NO | Recovery always skips — `if not state_raw: continue` |
| `evictions_skipped_scaling_guard` metric | `spot:keda:last_scale_event` | NO | Metric permanently 0 — misleading |

### 5.3 Write-Only Redis Keys (Written, Never Read)

| Key | Written By | Readers Found |
|---|---|---|
| `spot:execution_plan_hash:{cluster_id}` | `control_plane_loop.py:487` | `execution_controller.py:verify_plan_hash()` — never called from active code |
| `spot:execution_plan:{cluster_id}` | `control_plane_loop.py` (via redis_keys.py:26) | No reader found |
| `spot:cluster_state:{cluster_id}` | `core/risk_engine.py` | Partially read — `control_plane_loop.py:124` reads circuit breaker, not this key |

---

## §6. State Duplication (Redis / DB)

### 6.1 Workload Classification — 3 Parallel Stores

| Store | Key/Table | Schema | Writer | Reader |
|---|---|---|---|---|
| DB | `workload_classifications` table | `WorkloadClassificationRecord` (50+ fields, Platinum/Gold/Silver/Bronze/Spot) | WIE (`workload_identification_engine.py`) | PlacementAdvisor, API routes |
| Redis (WI profile) | `spot:workload_profile:{cluster_id}:{ns}/{ctrl}` TTL 540s | profile dict with `workload_tier` int 0-4 | `workload_inspector.py:1126` | `auto_rebalancer.py`, `optimizer_coordinator.py` |
| Redis (WI tier) | `spot:workload_tier:{cluster_id}:{ns}/{ctrl}` TTL 540s | tier string ("SPOT_ELIGIBLE" etc.) | `workload_inspector.py` | `auto_rebalancer.py`, `eviction_safety.py` |

**Conflict**: `auto_rebalancer.py` reads from Redis WI tier; `placement_controller_service.py` reads from the WIE DB path via `PlacementPolicy.disruption_safe`. If WI says STATELESS_ELIGIBLE but WIE says `disruption_safe=False`, the two engines behave differently on the same workload.

### 6.2 Pod / Node State — 2 Parallel Sources

| Store | Key/Table | TTL | Writer |
|---|---|---|---|
| DB | `pod_metrics` table | Permanent | Agent heartbeat batch upsert |
| Redis | `spot:placement:agent_data:{cluster_id}:pod_metrics` | 120s | `agent_routes.py:202` |

`PlacementController._get_od_pods()` (`placement_controller_service.py:619-660`) reads from Redis agent data. `PlacementAdvisorService` reads from DB `workload_classifications`. They may see stale/different pod counts between them.

### 6.3 Spot Availability — 2 Parallel Caches

| Store | Key | TTL | Writer |
|---|---|---|---|
| Redis (global rankings) | `global_pool_rankings:{region}` | 65min | `cache_builder.py` |
| Redis (placement availability) | `spot:placement:spot_availability:{region}` | Unknown | `placement_advisor_service.py` |
| Redis (dry-run verified) | `spot:dryrun_count:{region}` | 1h | `dry_run_refresher.py` |

`ControlPlaneLoop._step6_evaluate_pools()` reads from `global_pool_rankings:{region}` (no prefix). `PlacementAdvisor` reads from `spot:placement:spot_availability:{region}`. Different freshness guarantees; no synchronization.

---

## §7. Risk Analysis

| Risk | Severity | Components | Impact |
|---|---|---|---|
| PC evicts pods during KEDA scale-up (guard dead) | **CRITICAL** | `placement_controller_service.py:512`, `spot:keda:last_scale_event` | Pod thrash / OOM |
| AR + PC simultaneous action on same workload | **CRITICAL** | `auto_rebalancer.py`, `placement_controller_service.py` | PDB violation, 0 replicas |
| Last-replica eviction (no minimum-survivor check) | **CRITICAL** | `placement_controller_service.py:309` | Zero pods on workload |
| ControlPlaneLoop CPU waste (plan never executed) | **HIGH** | `control_plane_loop.py:100-186` | Every 5 min × all clusters = wasted compute |
| WI vs WIE classification conflict | **HIGH** | `workload_inspector.py`, `workload_identification_engine.py` | AR and PC disagree on same workload's safety |
| `spot:workload:state` never written | **HIGH** | `placement_advisor_service.py:982` | PDB floor ignored; rollout always times out |
| `agents/` orchestrator defined but unused | **LOW** | `backend/agents/` | Dead code footprint; misleading |
| ExecutionController always fails | **MEDIUM** | `services/execution_controller.py` | Emergency spot replacement never succeeds |
| Beat schedule task `workers.discovery` possibly unrouted | **MEDIUM** | `workers/app.py:53`, `workers/tasks/discovery.py:180` | Queue message buildup |

---

## §8. Recommended Removals (Safe)

| Component | File | Reason | Confidence |
|---|---|---|---|
| `agents/` directory | `backend/agents/*.py` (8 files) | Zero callers outside the directory | **SAFE** |
| `ActionExecutor` class | `core/action_executor.py:52` | Never called from production paths; all internals are stubs | **SAFE** |
| `ExecutionController` | `services/execution_controller.py:75` | All steps stub — `emergency_handler.py` can skip directly to OD fallback | **SAFE** |
| `ControlPlaneLoop` beat schedule entry | `workers/app.py:197-200` | Produces plan that is never consumed; 5-min waste per cluster | **SAFE** (keep class for reference, remove beat entry) |
| `spot:execution_plan_hash` Redis write | `control_plane_loop.py:481-491` | No verified reader outside stale test | **SAFE** |
| `BinPackingModule` from optimization pipeline | `workers/tasks/optimization.py:97-130` | Output never dispatched; `ActionExecutor` which was meant to consume it is also dead | **SAFE to remove from optimization.py; keep module if future use planned** |

---

## §9. Recommended Migrations (Required Before Use)

| Component | Current Gap | Required Fix |
|---|---|---|
| `spot:workload:state` writer | No writer exists anywhere | Agent heartbeat must write per-workload state keys from `hpa_pdb_data`; `agent_routes.py:202` |
| `spot:keda:last_scale_event` writer | No writer exists | `placement_webhook_routes.py` must write key when KEDA-related pod detected |
| `spot:cluster:pending_pods` writer | No writer exists | Agent heartbeat must write pending pod count from cluster summary |
| `ExecutionController` stubs | 4 unimplemented methods | Wire to real AgentAction dispatch (same pattern as `placement_controller_service.py:706`) |
| WI ↔ WIE schema unification | NodeStatus vs Platinum/Gold/Silver tiers | Add mapping layer or migrate AR to read WIE output |
| `ControlPlaneLoop` → actual dispatch | Execution plan built but discarded | Either connect to `ActionExecutor` (fix stubs first) or remove beat schedule entry |

---

## §10. Final Classification Table

| Component | Classification | Status | Notes |
|---|---|---|---|
| `auto_rebalancer.py` | **CANONICAL** | Active | Primary node migration execution engine |
| `placement_controller_service.py` | **CANONICAL** | Active (flag-gated) | Pod eviction engine |
| `placement_advisor_service.py` | **CANONICAL** | Active (flag-gated) | Policy generation |
| `workload_identification_engine.py` | **CANONICAL** | Active | Full classification pipeline |
| `agent_routes.py` | **CANONICAL** | Active | AgentAction lifecycle |
| `emergency_rebalancer.py` | **CANONICAL** | Active | Emergency spot interruption handler |
| `karpenter_service.py` | **CANONICAL** | Active | Primary provisioning system |
| `workload_inspector.py` | **CANONICAL** | Active | Node-level classification cache |
| `workload_classifier.py` | **CANONICAL (sub-component)** | Active | Called by WI and WIE |
| `control_plane_loop.py` | **DUPLICATE** | Active (wasted) | Shadows AR; produces no output |
| `execution_controller.py` | **LEGACY** | Stub/Dead | All steps unimplemented |
| `core/action_executor.py` | **LEGACY** | Dead | Never called from production |
| `agents/orchestrator.py` + all agents | **DEAD** | Unused | No external callers |
| `modules/bin_packer.py` | **LEGACY** | Plan-only | Output never dispatched |
| `workers/tasks/optimization.py` | **LEGACY** | Plan-only | optimize_cluster output discarded |
| `spot_asg_service.py` | **LEGACY** | Partially active | Non-Karpenter fallback only |
| `substitute_manager.py` | **LEGACY** | Partially active | Non-Karpenter fallback only |
| `services/event_monitor.py` | **LEGACY** | Partially active | SubstituteManager-dependent path optional |
| `scheduler.py` | **LEGACY** | Partially active | APScheduler parallel to Celery; risk of double-run |
