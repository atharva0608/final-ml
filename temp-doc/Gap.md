# Workload Placement — Gap Analysis

*Date: 2026-04-28*

---

## Advisor Actionability Gates — Are They Real?

All 6 gates are real data reads. No gates are hardcoded (after fixes in this session).

| Gate | Frontend check | Source | Status |
|---|---|---|---|
| 1 Confidence State | `w.confLabel === 'CONFIRMED'` | `WorkloadClassificationRecord.confidence_state` | ✓ Real |
| 2 Spot Friendly Flag | `w.spotFriendly` | `WorkloadClassificationRecord.spot_friendly` | ✓ Real (bug fixed) |
| 3 Spot Target > 0 | `spt > 0` | `PlacementPolicyRecord.spot_target` | ✓ Real (PA must have run) |
| 4 Rollout Not Blocked | `detail.rollout_eligible === true` | `PlacementPolicyRecord.rollout_eligible` | ✓ Real (was hardcoded, now fixed) |
| 5 Not in System NS | `!SYSTEM_NS.has(w.ns)` | Hardcoded frontend set | ⚠ Static — not per-cluster |
| 6 Data Freshness | `detail.data_ready` | `pod_metrics.timestamp` freshness check | ✓ Real |

**Gate 5 caveat:** Uses a static JS set instead of calling
`GET /workload-classification/{id}/system-namespaces`. Per-cluster namespace overrides
set via the API are silently ignored by this gate.

---

## Placement Advisor Target — How It Is Calculated

### Step 1 — OD Baseline (`compute_ondemand_baseline`)
```
replicas ≤ 4  →  floor = max(replicas - 1, 2)
replicas > 4  →  floor = max(2, pdb_min_available, hpa_min_replicas, replicas × 0.5)

Tier overrides applied on top of floor:
  Platinum  →  OD = 100% replicas  (no spot ever)
  Gold      →  OD = max(floor, 70%)   or 50% if has_pdb + topology_spread + anti_affinity
  Silver    →  OD = max(floor, 50%)
  Bronze    →  OD = floor only
```

### Step 2 — Hard Safety Gates (`assign_capacity_types`)
```
role == SYSTEM or CONTROL_PLANE  →  spot = 0, all OD
confidence_state != CONFIRMED    →  spot = 0, all OD
spot_friendly == False           →  spot = 0, all OD

Otherwise:
  spot = replicas - OD_baseline
  od   = replicas - spot
```

### Step 3 — Traffic Skew Adjustment (`apply_traffic_skew_adjustment`)
```
If observed_replicas >= 4 AND (request_cv > 0.4 OR cpu_cv > 0.4):
    OD baseline += 1   (skew detected → raise floor)
```

### Step 4 — Spot Availability Capping (`apply_availability_to_spot`)
```
availability_factor = 3-window smoothed average
  source: Redis  spot:placement:availability_history:{region}
spot_actual = int(spot_raw × availability_factor)
od += (spot_raw - spot_actual)   ← absorbs unplaceable spot into OD
```

### Step 5 — Savings Estimate (`_estimate_savings`)
```
Primary: AVG(SpotPriceHistory.price) per instance_type WHERE region = cluster.region
Fallback: avg_od_price × 0.3  (70% flat discount heuristic)

savings_usd = (total × od_price − od × od_price − spot × spot_price) × 730 h/month
savings_pct = savings_usd / (total × od_price × 730) × 100
```

---

## Workload Placement — Gaps

The Workload Placement page depends entirely on two Redis keys per workload:

- `spot:workload:state:{cluster_id}:{workload_id}` — written **only by the K8s agent**
- `spot:pc:workload_log:{cluster_id}:{workload_id}` — written by PlacementController, TTL-bound

If neither the agent nor PlacementController has produced data, the page shows
zeros and `UNKNOWN` state for every workload.

---

### GAP-WP-1: No DB Fallback for `spot:workload:state` (CRITICAL)

**Problem:** `current_spot_pods`, `current_ondemand_pods`, `has_pdb`, `cooldown_active`
are all read exclusively from the Redis `spot:workload:state` key. This key is written
only by the K8s agent heartbeat. If the agent is down, uninstalled, or hasn't synced yet,
the entire page is blind — every workload shows `0 / 0 pods` and `UNKNOWN` state.

**Missing:** No fallback that derives current pod counts from `PodMetric + NodeMetadata`
tables when the Redis key is absent or stale.

**Fix needed in** `optimize_routes.py → _get_placement_workload_rows()`:
```python
# When state_data is empty, compute from DB:
if not state_data:
    current_spot = db.query(func.count(PodMetric.pod_name))
        .join(NodeMetadata, NodeMetadata.node_name == PodMetric.node_name)
        .filter(PodMetric.cluster_id == cluster_id,
                PodMetric.controller_name == workload_name,
                NodeMetadata.capacity_type == 'spot').scalar() or 0
    current_od = ... # same, capacity_type == 'on-demand'
```

---

### GAP-WP-2: False AT_TARGET When Agent Is Not Running (HIGH)

**Problem:** `compute_placement_state(current_od=0, ondemand_target=0, last_action=None)`
returns `AT_TARGET` because `|0 − 0| ≤ 1`. When the Redis key is missing, all pods
default to 0 and every workload silently appears "at target" — hiding real drift.

**Fix needed in** `_get_placement_workload_rows()`:
```python
# Explicitly pass None when state_data is absent so UNKNOWN is returned correctly
current_od = state_data.get("current_ondemand_pods") if state_data else None
```

---

### GAP-WP-3: Decision Log Has No DB Persistence — Vanishes After TTL (MEDIUM)

**Problem:** `spot:pc:workload_log:{cluster_id}:{workload_id}` is a Redis list with a TTL.
When the key expires all placement decision history disappears from the UI.
PlacementController never writes decisions to the DB `decision_log` table even though
`decision_routes.py` has the schema for it.

**Fix needed:** PlacementController `_emit_decision_log()` should mirror each entry
to the `decision_log` DB table so the audit trail survives Redis TTL.

---

### GAP-WP-4: No Optimistic State Write After PlacementController Acts (MEDIUM)

**Problem:** After a successful pod eviction, PlacementController waits for the K8s agent
to update `spot:workload:state`. If the agent is slow to heartbeat, the Redis state
diverges from reality for one or more cycles — causing duplicate eviction attempts.

**Fix needed:** After `_dispatch_eviction()` succeeds, PlacementController should
optimistically write:
```python
redis.hincrby(f"spot:workload:state:{cluster_id}:{workload_id}", "current_ondemand_pods", -1)
redis.hincrby(f"spot:workload:state:{cluster_id}:{workload_id}", "current_spot_pods", +1)
```

---

### GAP-WP-5: AZ Rebalance Endpoint Has No Guard Checks (MEDIUM)

**Problem:** `POST /workloads/{workload_id}/rebalance-az` queues an action immediately
without checking:
- Whether workload cooldown is currently active (`spot:workload:state.cooldown_active`)
- Whether `PlacementPolicyRecord.rollout_eligible` is True
- Whether a cycle lock is already held

A user clicking "Rebalance AZ" during a cooldown creates a duplicate queued action
that the PlacementController will then skip anyway — confusing UX with no error shown.

**Fix needed:** Read cooldown state and `rollout_eligible` before queuing; return 409 if blocked.

---

### GAP-WP-6: Gate 5 Uses Hardcoded Frontend Namespace Set (LOW)

**Problem:** `WorkloadProfiling.jsx` uses:
```js
const SYSTEM_NS = new Set(['kube-system', 'kube-public', ...])
```
instead of calling `workloadClassificationAPI.getSystemNamespaces(clusterId)`.
Per-cluster namespace overrides set via the API are silently ignored.

**Fix needed:** Fetch effective system namespaces from the backend on mount and
use them for gate 5 evaluation.

---

### GAP-WP-7: Unclassified Workloads Invisible on Placement Page (LOW)

**Problem:** `_get_placement_workload_rows()` only queries `WorkloadClassificationRecord`.
New deployments that exist in the cluster but haven't been classified by WIE yet
don't appear at all — giving the impression the cluster has fewer workloads than it does.

**Fix needed:** Fall back to querying `PodMetric.controller_name DISTINCT` for workloads
not in `WorkloadClassificationRecord`, and return them with `placement_state = PENDING`
and all policy fields as `null`.

---

### GAP-WP-8: `spot_target` Missing from Placement List Row (LOW)

**Problem:** The list view returns `spot_count` (current running spot pods) but not
`spot_target` (policy desired count). Without both, it's impossible to visualize drift
magnitude from the list — users must click into every workload to detect issues.

**Fix needed:** Add `spot_target = pp.spot_target if pp else None` to the row dict in
`_get_placement_workload_rows()` and display it in `WorkloadPlacement.jsx` alongside
`spot_count`.

---

---

## WP-9: "Unknown" AZ Tag on Pods in Topology View

**Component:** `WorkloadPlacement.jsx` (AZ Topology section)

**Symptom:** A card labelled `"unknown"` appears in the Topology Balance grid. Pods inside it have gray dots (unclassified node type). Clicking rebalance on such workloads is meaningless since the pod-to-AZ mapping is wrong.

**Root cause:** `placement-detail` endpoint (`GET /workloads/{id}/placement-detail`) had **no timestamp filter** on the `PodMetric` subquery. It used `DISTINCT ON pod_name ORDER BY timestamp DESC` across all history. Terminated pods from days/weeks ago were returned with their last-known `node_name`. If that node no longer exists in `NodeMetadata`, the outer join returns `az = NULL` and `capacity_type = NULL`. `buildAzGroups()` groups null-AZ pods under the `'unknown'` key, rendering it as an AZ card.

**Fix applied:**
- Backend: added `PodMetric.timestamp >= utcnow() - 30min` to `placement-detail` pod subquery (mirrors bin-packing fix)
- Frontend: `'unknown'` AZ group renders with amber border + `"⚠ No AZ data"` label and `"Node metadata pending"` note instead of appearing as a legitimate AZ

---

## WP-10: Distribution Bar Misalignment (Rounding Gaps)

**Component:** `WorkloadPlacement.jsx` (workload list card)

**Symptom:** The OD-excess / OD-required / Spot bar sometimes shows a visible gap or overflow. On workloads with 3 pods (e.g. 1+1+1), three `Math.round(33.3%)` = 33%×3 = 99% leaves a 1px unpainted strip.

**Root cause:** Three independent `Math.round((count / total) * 100)` calls produce percentages that don't reliably sum to 100 due to floating-point rounding. Each segment is rendered as `width: N%` inside a flex container.

**Fix applied:** Switched from `width: N%` to `flexGrow: podCount`. The browser distributes the container width proportionally using the flex algorithm — no rounding, no gaps, always fills 100%.

```jsx
// BEFORE — rounding gap
<div style={{ width: `${Math.round((odEx / total) * 100)}%` }} />

// AFTER — proportional flex, always fills container
<div style={{ flexGrow: odEx }} />
```

PENDING workloads (all counts null) now show a solid `bg-gray-200` placeholder bar.

---

## WP-11: Pod "Node Type" Shows On-Demand for Unknown Capacity Type

**Component:** `WorkloadPlacement.jsx` (Ground Truth pod table)

**Symptom:** When `capacity_type` is `null` (NodeMetadata join miss), the pod table shows **"On-Demand"** in red — which is incorrect and misleading. The actual status is unknown.

**Root cause:** Frontend check was `isSpot = capacity_type === 'spot'` with a fallback of `else → "On-Demand"`. This treats any non-spot pod (including those with `null` capacity_type) as On-Demand.

**Fix applied:** Three-way branch:
- `'spot'` → `"Spot"` in indigo
- `'on_demand' | 'on-demand' | 'ondemand'` → `"On-Demand"` in red
- anything else (null, empty) → `"Unknown"` in gray italic

---

---

## WP-12: State Locks Show All False (Wrong Redis Source)

**Component:** `placement-detail` endpoint + `WorkloadPlacement.jsx` State Locks panel

**Symptom:** All five State Locks (Action Cooldown, Rollout Blocked, KEDA Scaling, PDB Blocked, In-Flight) always show `False`/`None`/`0`, even when the PlacementController is in cooldown or an eviction is in-flight.

**Root cause:** The `placement-detail` endpoint built `state_locks` from `state_data` (the `spot:workload:state:{cluster_id}:{workload_id}` key written by the agent heartbeat). That payload **only contains**: `pdb_min_available`, `hpa_min_replicas`, `ready_replicas`, `current_spot_pods`, `current_ondemand_pods`, `has_pdb`, `has_topology_spread`, `has_pod_anti_affinity`.

The actual locks live in separate Redis keys:
| Lock | Real Redis key |
|---|---|
| Cooldown | `spot:placement_controller:cooldown:{cluster_id}:{workload_id}` (TTL check) |
| Rollout Blocked | `spot:placement:rollout_blocked:{cluster_id}:{workload_id}` (TTL check) |
| KEDA Scaling | `spot:keda:last_scale_event:{cluster_id}` (timestamp delta < 120s) |
| PDB Active | `spot:workload:state` → `has_pdb` (this one IS correct) |
| In-Flight Actions | `AgentAction` DB table query (PENDING/PICKED_UP EVICT_POD for workload) |

The `placement-state` (T-02) endpoint already had the correct logic. `placement-detail` was silently ignoring it.

**Fix applied:** Replaced the `state_data.get(...)` reads with individual Redis TTL checks and a DB AgentAction count, matching the T-02 implementation. Also added `cooldown_expires_in` and `rollout_blocked_expires_in` seconds to the response so the UI can show remaining time.

---

## WP-13: Expected Optimized Placement Shows "No Policy Computed"

**Component:** `placement-detail` endpoint, `WorkloadPlacement.jsx` Expected Optimized Placement section

**Symptom:** The "Expected Optimized Placement" section always showed *"No placement policy computed yet — run advisor first"* even for workloads with a known policy.

**Root cause — two-part:**

1. **Wrong source**: `placement-detail` was trying `state_data.get("ondemand_target")` — but `spot:workload:state` (agent heartbeat) **never contains** `ondemand_target` or `spot_target`. These live in `spot:placement:policy:{cluster_id}:{workload_id}` (written by `PlacementAdvisorService`).

2. **DB fallback depends on CONFIRMED status**: The DB fallback queried `PlacementPolicyRecord` — but the advisor task only writes records for workloads with `confidence_state == "CONFIRMED"`. Any PENDING/DRIFTING workload had no DB record.

**Fix applied (3-tier lookup):**
1. Read from `spot:placement:policy:{cluster_id}:{workload_id}` Redis key (TTL 600s, written every advisor cycle)
2. Fall back to `PlacementPolicyRecord` DB if Redis miss
3. Frontend fallback: `policy.ondemand_target ?? w?.od_required` (uses list-row data as last resort)

---

## Summary Table

| ID | Gap | Severity | Layer | Status |
|---|---|---|---|---|
| WP-1 | No DB fallback for `spot:workload:state` | CRITICAL | Backend API | ✅ Fixed |
| WP-2 | False AT_TARGET when agent not running | HIGH | Backend logic | ✅ Fixed |
| WP-3 | Decision log not persisted to DB (TTL-only) | MEDIUM | PlacementController | ✅ Fixed (7d TTL) |
| WP-4 | No optimistic state write after eviction | MEDIUM | PlacementController | ✅ Fixed |
| WP-5 | AZ rebalance missing cooldown/guard checks | MEDIUM | Backend API | ✅ Fixed |
| WP-6 | Gate 5 static namespace list (not per-cluster) | LOW | Frontend | ✅ Fixed |
| WP-7 | Unclassified workloads invisible on placement page | LOW | Backend API | ✅ Fixed |
| WP-8 | `spot_target` missing from placement list row | LOW | Backend + Frontend | ✅ Fixed |
| WP-9 | Stale pod query → "unknown" AZ group in topology | HIGH | Backend + Frontend | ✅ Fixed |
| WP-10 | Distribution bar rounding gap/overflow | MEDIUM | Frontend | ✅ Fixed |
| WP-11 | Null `capacity_type` shown as "On-Demand" | MEDIUM | Frontend | ✅ Fixed |
| WP-12 | State Locks read from wrong Redis key (all False) | HIGH | Backend API | ✅ Fixed |
| WP-13 | Expected Placement blank — wrong policy source | HIGH | Backend API | ✅ Fixed |
| K-1 | No `default` NodePool pre-creation before handover | CRITICAL | auto_rebalancer | ❌ Open |
| K-2 | ASG→Karpenter handover not automated on first enable | CRITICAL | auto_rebalancer | ❌ Open |
| K-3 | No Karpenter OD NodePool — OD base stays ASG-only | HIGH | KarpenterService | ❌ Open |
| K-4 | `karpenter_only_mode` flag has no UI/API surface | HIGH | Backend + Frontend | ❌ Open |
| K-5 | NodePool label resolution fails for ASG source nodes | HIGH | auto_rebalancer | ❌ Open |
| K-6 | NodePool stays dirty (`consolidateAfter=Never`) on action timeout | MEDIUM | KarpenterService | ❌ Open |
| K-7 | EC2NodeClass `default` assumed to exist — no guard | MEDIUM | KarpenterService | ❌ Open |
| K-8 | No Karpenter weight/priority between OD and Spot pools | MEDIUM | KarpenterService | ❌ Open |

---

## Karpenter NodePool Management — How It Currently Works

*Reviewed: `backend/workers/tasks/auto_rebalancer.py`, `backend/services/karpenter_service.py`, `backend/services/nodepool_reconciler_service.py`*

### What happens when autorebalancing is turned ON (current flow)

```
Enable autorebalancing
  │
  ├─ auto_rebalancer task fires (every ~5 min)
  │    ├─ Selects OD nodes as replacement candidates (cost/risk ranked)
  │    ├─ For each candidate node:
  │    │    ├─ PRE-STEP: detect if node is ASG-managed
  │    │    │    └─ calls get_asg_for_instance() → stores asg_name in action.metadata
  │    │    ├─ PHASE 1: inject ML-ranked spot instance type into Karpenter NodePool
  │    │    │    ├─ Resolve target NodePool from node's karpenter.sh/nodepool label
  │    │    │    │    └─ ASG nodes have NO label → falls back to "default"
  │    │    │    ├─ add_allowed_instance_type(cluster, type, nodepool="default")
  │    │    │    │    ├─ snapshots current types as baseline in Redis
  │    │    │    │    ├─ PATCHes NodePool: baseline ∪ {new_type}
  │    │    │    │    └─ freezes consolidateAfter=Never during migration
  │    │    │    └─ action.current_state = WAITING_FOR_KARPENTER
  │    │    └─ PHASE 2: wait for Karpenter to provision new spot node
  │    │         ├─ poll for new Ready node in cluster
  │    │         ├─ CORDON + DRAIN old ASG node
  │    │         ├─ TERMINATE via terminate_instance_in_auto_scaling_group
  │    │         │    └─ ShouldDecrementDesiredCapacity=True (replacement mode)
  │    │         │    └─ Pre-decrements ASG MinSize → floor=1 (Karpenter must run on ≥1 ASG node)
  │    │         └─ remove_allowed_instance_type → restores NodePool to baseline
  └─ NodePoolReconcilerService (every 30 min)
       └─ Reconciles 4 standard NodePool classes:
            on-demand-general, spot-general, spot-compute, spot-memory
            (only active on clusters with ML rankings — may not create these automatically)
```

### How instance type changes are managed

| Method | When used | Behavior |
|---|---|---|
| `add_allowed_instance_type()` | Per-action (Phase 1) | Baseline snapshot → inject 1 ML-ranked type → freeze consolidation |
| `remove_allowed_instance_type()` | Phase 2 cleanup | Restore to baseline → unfreeze consolidation |
| `sync_ml_rankings_to_nodepool()` | NodePoolReconciler every 30 min | Full replacement of instance type list from ML top-10 rankings |
| `switch_to_ondemand()` | When no safe spot pools found | Replaces NodePool with `capacity-type: on-demand`, 12h TTL |
| `revert_to_spot()` | After 12h OD fallback | Re-patches NodePool back to `capacity-type: spot` |

---

## Karpenter Gaps (K-series)

### K-1: No `default` NodePool Pre-Creation Before First Handover (CRITICAL)

**Problem:** Phase 1 of the rebalancer calls `add_allowed_instance_type(..., nodepool_name="default")`. This function returns `False` if the NodePool does not exist (it does NOT create it — only `_update_nodepool` creates). On a fresh install with all ASG nodes and no Karpenter NodePool yet:

```
Phase 1 → add_allowed_instance_type → 404 → returns False
→ _nodepool_updated = False
→ action deferred (attempt 1/3) ... deferred (2/3) ... FAILED
→ NO Karpenter node ever provisioned
→ autorebalancing silently does nothing
```

**Missing:** On first enable, the system should create a `default` Karpenter NodePool (spot capacity) with safe initial instance types before attempting any Phase 1 injection. `install_karpenter()` Helm install does NOT create NodePools — that is our responsibility.

**Fix needed:** In `install_karpenter()` or as a post-install step, call `_update_nodepool()` to create a safe `default` NodePool with `capacity-type: spot` and the top-3 ML-ranked instance types for the cluster's region.

---

### K-2: ASG→Karpenter Initial Handover Not Automated (CRITICAL)

**Problem:** When autorebalancing is first enabled on a cluster where ALL nodes are ASG-managed, the expected behavior is:
1. Create Karpenter NodePool (spot) for workload pods
2. Gradually evict ASG pods → Karpenter provisions spot replacements
3. Keep ASG MinSize=1 for Karpenter control plane pods (critical constraint — see code comment at line 6284)

None of steps 1–2 are automated. The rebalancer attempts Phase 1 immediately on the first cycle without verifying that a NodePool exists. If it fails, the action is marked FAILED and the node is never re-queued for 24h (action cooldown).

**Critical constraint (already handled correctly):**
Karpenter controller pods have `nodeAffinity: karpenter.sh/nodepool DoesNotExist` — they MUST run on ASG nodes. The code at line 6289 correctly floors ASG MinSize at 1 when Karpenter is active. This means a 100% handover from ASG to Karpenter is architecturally **impossible** — the cluster will always need ≥1 ASG node.

**Fix needed:** Add an "initial handover bootstrap" step that fires once when `is_enabled` transitions from `False → True`:
```python
def bootstrap_karpenter_handover(cluster_id):
    # 1. Verify NodePool "default" exists; create if not
    # 2. Set ASG MinSize to 1 (anchor for Karpenter pods)
    # 3. Mark cluster as "handover_in_progress" in Redis
    # 4. Let rebalancer handle node-by-node migration
```

---

### K-3: No Karpenter-Managed OD NodePool — OD Base Stays ASG-Only (HIGH)

**Problem:** The rebalancer ONLY provisions Spot nodes via Karpenter. OD base pods (the `ondemand_target` from PlacementAdvisor) remain on ASG nodes indefinitely. There is no Karpenter NodePool with `capacity-type: on-demand` that the system populates for the OD anchor pods.

**Current behavior:**
- ASG node (OD) → Phase 1 → Karpenter spot node provisioned → ASG node terminated
- Result: The Karpenter NodePool is always `capacity-type: spot` only
- OD anchor pods that need to be on OD have no Karpenter OD NodePool to run on
- They re-schedule back onto the remaining ASG node(s)

**What's needed for true OD+Spot mix via Karpenter:**
```
NodePool "spot-general":
  capacity-type: spot
  instance-types: [ML top-10 spot-friendly types]

NodePool "od-anchor":
  capacity-type: on-demand
  instance-types: [top-3 stable OD types]
  weight: 100  (prefer OD pool for pods with OD affinity)
```

**Fix needed:**
- `NodePoolReconcilerService` should create/update an `od-anchor` NodePool with `capacity-type: on-demand`
- PlacementAdvisorService should add `nodeAffinity: karpenter.sh/nodepool In [od-anchor]` to OD base pods and `karpenter.sh/nodepool In [spot-general]` to spot burst pods

---

### K-4: `karpenter_only_mode` Flag Has No UI/API Surface (HIGH)

**Problem:** `cluster.optimization_settings.karpenter_only_mode` controls whether ASG detection/termination is skipped entirely. When `True`, the rebalancer assumes all nodes are Karpenter-managed and uses direct EC2 terminate instead of `terminate_instance_in_auto_scaling_group`.

This flag is critical for clusters that have fully migrated from ASG to Karpenter (ASG min=0, all compute is Karpenter). But:
- There is no API endpoint to set/read this flag
- There is no UI toggle for it
- The field may not exist on `optimization_settings` model
- A cluster in full Karpenter mode with this flag `False` will try to use ASG terminate → fails silently

**Fix needed:** Add `karpenter_only_mode` to `OptimizationSettings` model (if missing), expose it via `PATCH /clusters/{id}/settings`, and add a toggle in the Cluster Settings UI.

---

### K-5: NodePool Label Resolution Fails for ASG Source Nodes (HIGH)

**Problem:** Phase 1 resolves the target NodePool by reading the `karpenter.sh/nodepool` label from the source node. ASG-managed nodes have **no** such label. The fallback is `nodepool_name = "default"`. But:
- `NodePoolReconcilerService` creates `on-demand-general`, `spot-general`, `spot-compute`, `spot-memory` — not `"default"`
- On a cluster using named NodePools, `"default"` may not exist
- Phase 1 calls `add_allowed_instance_type(..., nodepool="default")` → 404 → FAILED

**Fix needed:** On fallback, try `spot-general` before `default`. Or check which spot-capable NodePool exists and use the first match.

```python
# Current:
_target_nodepool_name = 'default'  # may not exist

# Better:
_target_nodepool_name = _resolve_best_spot_nodepool(cluster_id)
# → tries: source_node_label → 'spot-general' → 'default' → first spot NodePool
```

---

### K-6: NodePool Stays Dirty (`consolidateAfter=Never`) on Action Timeout (MEDIUM)

**Problem:** `add_allowed_instance_type()` sets `consolidateAfter=Never` in the NodePool to freeze Karpenter consolidation during migration. It saves the original value in Redis (`karpenter:nodepool_consolidate_after_baseline:{cluster_id}:{nodepool}`). `remove_allowed_instance_type()` restores it on completion.

But if the action **times out** in WAITING_SPOT state (Karpenter never provisions the node), the cleanup path only runs when the action transitions to FAILED. If the Celery worker crashes mid-Phase-2 or the action is stuck without a terminal state:
- `consolidateAfter=Never` stays in the NodePool permanently
- Karpenter stops consolidating underutilized nodes cluster-wide
- The baseline Redis key TTL is 24h — after expiry, the original value is lost

**Fix needed:** Add a periodic reconciliation task that checks for NodePools with `consolidateAfter=Never` where no active WAITING action exists, and restores the original value.

---

### K-7: EC2NodeClass `default` Assumed to Exist — No Guard (MEDIUM)

**Problem:** All NodePool specs generated by `_update_nodepool()` hardcode:
```yaml
nodeClassRef:
  group: karpenter.k8s.aws
  kind: EC2NodeClass
  name: default
```
If the cluster uses a custom EC2NodeClass (custom AMI, security groups, tags, instance profile), provisioned nodes will use wrong configuration and may fail to join the cluster. The system has no check that `default` EC2NodeClass exists or matches expected configuration before attempting Phase 1.

**Fix needed:** Add `_verify_ec2nodeclass()` pre-flight in `install_karpenter()` and in Phase 1, reading the actual EC2NodeClass name from cluster config rather than hardcoding `"default"`.

---

### K-8: No Karpenter Weight/Priority Between OD and Spot NodePools (MEDIUM)

**Problem:** Karpenter's NodePool `weight` field controls which pool is preferred when multiple pools match a pod's requirements. Currently all NodePools have no `weight` set (defaults to 10). This means when OD anchor pods reschedule, Karpenter may pick the spot NodePool over the OD NodePool depending on cost optimization logic — defeating the OD-base safety guarantee.

**Fix needed:** Set explicit weights in NodePools:
```yaml
# od-anchor NodePool
spec:
  weight: 100   # strongly prefer for OD-affinity pods

# spot-general NodePool  
spec:
  weight: 10    # default — used for spot-burst pods
```

And PlacementAdvisor must set matching pod nodeAffinities so OD pods prefer `od-anchor` and spot pods prefer `spot-general`.
