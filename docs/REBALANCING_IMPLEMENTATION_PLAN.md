# Toggle-Based Orchestration & Blast Radius Prevention

## Problem

The auto-rebalancer has critical execution gaps identified in the deep audit:
1. **EC2 terminate fails silently** → action marked COMPLETED but instance still running on AWS
2. **No provision-and-wait** → old node is drained/terminated BEFORE confirming a spot replacement exists
3. **No `optimization_target`** → no UI control for Spot vs On-Demand billing preference
4. **Karpenter consolidation conflict** → native Karpenter consolidation races with ML rebalancer when both are active
5. **Node allocatable not checked** → replacement type selected from ML rankings without verifying it meets the current node's real CPU/memory baseline

## Proposed Changes

> [!IMPORTANT]
> This plan modifies `auto_rebalancer.py` (the execution core), `cluster.py` (data model), `karpenter_routes.py` (API), and the frontend settings UI. Changes are scoped to fix the execution pipeline — no new ML models or training changes.

---

### Backend Data Model

#### [MODIFY] [cluster.py](file:///Users/atharvapudale/Desktop/backend-ecc/Atharva%20Repo/github/final-ml/backend/models/cluster.py)

Add `optimization_target` column to `ClusterOptimizationSettings`:

```python
# New column: "spot" or "on_demand" — controls billing model for right-sizing
optimization_target = Column(String(20), default="spot")  # "spot" | "on_demand"
```

**Logic**: When both `auto_rebalance_enabled` AND `auto_rightsizing_enabled` are True (synergy mode), this field is **force-locked to `"spot"`** by the API. When only rightsizing is ON, user can choose.

---

### Backend Execution: Safe 1-by-1 Rolling Swap

#### [MODIFY] [auto_rebalancer.py](file:///Users/atharvapudale/Desktop/backend-ecc/Atharva%20Repo/github/final-ml/backend/workers/tasks/auto_rebalancer.py)

**Change 1 — Fix EC2 terminate → fail action if terminate fails** (L987)

Currently:
```python
_wa.status = 'failed' if _failed > 0 else 'completed'  # Ignores EC2 terminate result
```

Change to:
```python
if _failed > 0:
    _wa.status = 'failed'
elif not _terminated and _wa_instance_id:
    _wa.status = 'failed'
    _wa.error_message = "Agent K8s actions succeeded but EC2 terminate failed — instance still running"
else:
    _wa.status = 'completed'
```

**Change 2 — Provision-and-wait: confirm spot node is Ready BEFORE draining** (L379-506)

The current flow is: `PATCH_NODEPOOL → CORDON → DRAIN → TERMINATE` — all 4 queued immediately.

New flow:
```
Phase 1: PATCH_NODEPOOL → Wait for spot node to be Ready (poll K8s)
Phase 2: Only after Ready → CORDON → DRAIN old node
Phase 3: TERMINATE old EC2
```

Implementation: Split into 2 execution phases in `execute_rebalancing_action()`:
- Phase 1 creates only 1 AgentAction: `PATCH_KARPENTER_NODEPOOL`
- Action resolution (L742-1028) checks for new spot node → once confirmed Ready, creates CORDON + DRAIN + TERMINATE AgentActions
- If no spot appears within 30 min timeout → mark action failed, do NOT proceed to drain

**Change 3 — Read node allocatable CPU/memory before selecting replacement** (L1376)

Currently uses `instance.cpu_util` / `instance.memory_util` (utilization %). 

Change: Query the actual Kubernetes node `allocatable` CPU/memory from the agent's telemetry cache in Redis (`spot:node_telemetry:{cluster_id}`). If the replacement instance type has less CPU or RAM than the current node's allocatable, reject it and pick the next ML-ranked pool.

```python
# Before accepting target_instance_type:
_cur_allocatable = _get_node_allocatable(cluster.id, instance.instance_id)
_tgt_specs = _INSTANCE_VCPU_MEM.get(target_instance_type, (2, 8))
if _tgt_specs[0] < _cur_allocatable['cpu'] or _tgt_specs[1] < _cur_allocatable['memory_gb']:
    # Skip this candidate, try next ML-ranked pool
    continue
```

**Change 4 — Enforce 10-min cooldown after termination** (L1248-1279)

Currently 20-min cooldown but ONLY checks for spot node appearance. Change to a strict 10-min minimum cooldown regardless:

```python
_COOLDOWN = 600  # 10 minutes strict minimum
if elapsed < _COOLDOWN:
    continue  # No exceptions — always wait 10 min
```

**Change 5 — Toggle-aware orchestration path** (L1366-1438)

| Toggle State | `optimization_target` | Behavior |
|---|---|---|
| ML Rebalancing only | N/A (target is always spot) | Same-size OD→Spot. Bypass Karpenter consolidation. Verify allocatable baseline. |
| Rightsizing only | User chooses: `spot` or `on_demand` | Right-size to cheaper/smaller instance. Respect target billing model. |
| Both ON (Synergy) | **Force-locked to `spot`** | Bin-pack + ML-rank → cheapest safest spot pool |

**Change 6 — Fix non-Karpenter last-node guard** (L1658-1663)

Currently, the non-Karpenter path just logs a warning and skips if only 1 node remains. 

Change: In the non-Karpenter case (`else` block of the last-node check), call `_launch_spot_instance_direct()` to provision a spot replacement first. Then `continue` the loop (skipping drain). This ensures that even single-node clusters can eventually rebalance once the spot node joins and total_nodes becomes 2.

---

### Backend API

#### [MODIFY] [karpenter_routes.py](file:///Users/atharvapudale/Desktop/backend-ecc/Atharva%20Repo/github/final-ml/backend/api/karpenter_routes.py)

**Change 1** — Accept `optimization_target` in PATCH `/karpenter/config/{cluster_id}`:

```python
optimization_target = updates.get("optimization_target")  # "spot" | "on_demand"
if optimization_target is not None:
    # Synergy mode lock: both toggles ON → force to "spot"
    if opt.auto_rebalance_enabled and opt.auto_rightsizing_enabled:
        optimization_target = "spot"
    opt.optimization_target = optimization_target
```

**Change 2** — Return `optimization_target` in GET `/karpenter/config/{cluster_id}`:

```python
cfg["optimization_target"] = opt.optimization_target if opt else "spot"
cfg["optimization_target_locked"] = bool(opt and opt.auto_rebalance_enabled and opt.auto_rightsizing_enabled)
```

**Change 3** — When `auto_rebalancing_enabled` is set to True, disable Karpenter native consolidation by patching NodePool `disruption.consolidationPolicy: WhenEmpty` (instead of `WhenEmptyOrUnderutilized`) to prevent Karpenter from making its own replacement decisions that conflict with ML:

```python
if auto_rebalancing:
    # Queue an AgentAction to patch NodePool consolidation policy
    # to "WhenEmpty" — prevents Karpenter from independently consolidating
```

---

### Frontend

#### [MODIFY] [ClusterDetails.jsx](file:///Users/atharvapudale/Desktop/backend-ecc/Atharva%20Repo/github/final-ml/frontend/src/components/clusters/ClusterDetails.jsx)

Add "Optimization Target" dropdown in cluster settings with options:
- `Spot` (default)
- `On-Demand`

When both auto-rebalancing AND auto-rightsizing toggles are ON, the dropdown shows "Spot" and is disabled (locked) with a tooltip: "Locked to Spot when both ML Rebalancing and Right-Sizing are active".

#### [MODIFY] [RightSizingDashboard.jsx](file:///Users/atharvapudale/Desktop/backend-ecc/Atharva%20Repo/github/final-ml/frontend/src/components/right-sizing/RightSizingDashboard.jsx)

Add the same optimization target dropdown in the right-sizing settings section. Respects the same locking rule.

---

### Database Migration

#### [NEW] [migration](file:///Users/atharvapudale/Desktop/backend-ecc/Atharva%20Repo/github/final-ml/backend/migrations/versions/20260305_add_optimization_target.py)

```python
# Add optimization_target column to cluster_optimization_settings
op.add_column('cluster_optimization_settings',
    sa.Column('optimization_target', sa.String(20), server_default='spot', nullable=False)
)
```

---

## What Will NOT Change

- ML models (ONNX scoring unchanged)
- Pool ranking pipeline (8-step pipeline unchanged)
- Discovery worker (14-region scan unchanged)
- ClusterCleanupService (teardown already automated for IAM, SQS, EventBridge, OIDC, Redis, K8s)
- Agent injection flow (already automated)

## Verification Plan

### Automated Tests

Existing test file: [test_integration_hardening.py](file:///Users/atharvapudale/Desktop/backend-ecc/Atharva%20Repo/github/final-ml/backend/tests/test_integration_hardening.py) — has 8 tests. These use mocked services and won't validate the actual execution changes.

New verification approach:

**1. Manual code-path verification** — trace the auto_rebalancer with logging to confirm:
- Phase 1/2 split works (PATCH_NODEPOOL first, wait, then CORDON/DRAIN/TERMINATE)
- EC2 terminate failure → action status = `failed`
- Synergy mode forces `optimization_target = "spot"`
- Allocatable check rejects undersized replacement

**2. API test** — curl the PATCH `/karpenter/config/{cluster_id}` endpoint after changes:
```bash
# Test synergy lock
curl -X PATCH http://localhost:8000/api/v1/karpenter/config/TEST_CLUSTER \
  -H "Content-Type: application/json" \
  -d '{"auto_rebalancing_enabled": true, "auto_rightsizing_enabled": true, "optimization_target": "on_demand"}'
# Expected: optimization_target should be returned as "spot" (force-locked)
```

**3. Frontend verification** — use browser to navigate to Cluster Details → Settings:
- Confirm "Optimization Target" dropdown appears
- Toggle both switches ON → dropdown should lock to Spot and become disabled
- Toggle only rightsizing ON → dropdown should be editable (Spot/On-Demand)

> [!IMPORTANT]
> I recommend having you test the complete flow on a real cluster after deployment. The auto_rebalancer runs every 15s, so you can observe the 2-phase execution by watching the `rebalancing_actions` table and Celery worker logs. Would you like me to add a specific test cluster workflow?
