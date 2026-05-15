# Execution Map — Files That Take Real Actions on AWS / K8s

> **What counts as "real action"**: any code path that writes to the Kubernetes API server,
> calls an AWS API (EC2, EKS, STS, ASG), or queues an `AgentAction` DB record that the
> in-cluster DaemonSet agent will execute.

---

## 1. The Execution Model — How Actions Actually Reach the Cluster

All real K8s mutations go through a two-step pattern:

```
Backend Service / Celery Task
       │
       ▼  writes DB row
  AgentAction table  (PostgreSQL)
       │
       ▼  agent polls every N sec via GET /clusters/{id}/actions/pending
  In-Cluster DaemonSet Agent
       │
       ▼  calls real K8s API
  Kubernetes API Server → EC2 / EKS
```

`KarpenterService` is the one exception — it patches K8s CRDs (NodePool) **directly** 
from the backend using a SigV4-signed K8s API client, without going through the agent.

---

## 2. The Agent Action Queue

### `backend/models/agent_action.py`
**The queue.** Defines `AgentActionType` enum — every action type that can run on a real cluster:

| Action Type | What it does |
|---|---|
| `EVICT_POD` | K8s Pod eviction (graceful restart/reschedule) |
| `DRAIN_NODE` | K8s node drain (cordon + evict all pods) |
| `CORDON_NODE` | Mark node unschedulable |
| `UNCORDON_NODE` | Re-enable scheduling on a node |
| `TERMINATE_NODE` | Terminate the underlying EC2 instance |
| `FORCE_DELETE_NODE` | Force-delete ghost/stuck K8s Node object |
| `REMOVE_POD_FINALIZERS` | Strip finalizers from Terminating pods |
| `UPDATE_DEPLOYMENT` | `kubectl scale` — change replica count |
| `PATCH_CONTAINER_RESOURCES` | Right-size CPU/memory requests+limits |
| `PATCH_AFFINITY` | Apply nodeAffinity to Deployment/StatefulSet pod template |
| `ANNOTATE_WORKLOAD` | Add tier-override annotation to workload |
| `INSTALL_KARPENTER` | Run `helm install karpenter` inside cluster |
| `UNINSTALL_KARPENTER` | Run `helm uninstall karpenter` inside cluster |
| `INSTALL_KEDA` | Run `helm install keda` inside cluster |
| `UNINSTALL_KEDA` | Run `helm uninstall keda` inside cluster |
| `LABEL_NODE` | Patch K8s node labels |

**Trigger**: any backend service or Celery task creates a row with `status=PENDING`.  
The in-cluster agent polls, picks it up → `PICKED_UP` → executes → `COMPLETED/FAILED`.

---

## 3. Files That Write AgentActions (Backend → Cluster Queue)

### `backend/services/placement_controller_service.py`
**Auto pod eviction / spot rebalancing.**

- `_dispatch_eviction()` — writes `EVICT_POD` AgentAction.
- **Trigger**: called by `PlacementController.run()` when a pod on on-demand should move
  to spot. Runs on the **Celery task `placement_controller_task`** (see §5).

### `backend/services/placement_rollout_service.py`
**Stateful pod rolling migration (scale-up-then-evict strategy).**

- `_scale_workload()` — writes `UPDATE_DEPLOYMENT` AgentAction.
- `_evict_pod()` — writes `EVICT_POD` AgentAction.
- **Trigger**: called by placement controller for stateful workloads (StatefulSet, Platinum/Gold tier).

### `backend/services/execution_controller.py`
**Node drain + terminate flow (swap old OD node for new spot).**

- `_drain_node()` — writes `DRAIN_NODE` AgentAction, then polls until COMPLETED.
- `_rollback_drain()` — writes `UNCORDON_NODE` AgentAction on failure.
- `_terminate_node()` — writes `TERMINATE_NODE` AgentAction.
- **Trigger**: called by `auto_rebalancer` during Phase 3 (drain old node) and Phase 5
  (terminate EC2 after drain).

### `backend/services/keda_service.py`
**KEDA autoscaler install/uninstall.**

- Writes `INSTALL_KEDA` / `UNINSTALL_KEDA` AgentActions.
- **Trigger**: UI button on KEDA management page, or the `keda_installer` Celery task.

### `backend/services/anchored_node_service.py`
**Anchor node labeling.**

- Writes `LABEL_NODE` AgentAction.
- **Trigger**: UI toggle for anchoring a node; also called by optimizer.

### `backend/workers/tasks/recovery_monitor.py`
**Emergency recovery after spot interruption.**

- Writes `UNCORDON_NODE`, `EVICT_POD`, `DRAIN_NODE` AgentActions.
- **Trigger**: Celery beat task, runs on detection of a terminated/interrupted node.

### `backend/workers/tasks/emergency_rebalancer.py`
**Forced emergency eviction when pending pod count spikes.**

- Writes `EVICT_POD` AgentActions with `priority=10` (preempts normal queue).
- **Trigger**: Celery beat task, triggered by SQS spot-interruption notice or agent heartbeat alert.

### `backend/workers/tasks/placement_controller_task.py`
**Celery entry point for the placement controller.**

- Calls `PlacementControllerService.run()` → which calls `_dispatch_eviction()`.
- **Trigger**: Celery beat (see §6 schedule).

### `backend/workers/tasks/auto_scaler.py`
**Horizontal auto-scaling.**

- Writes `UPDATE_DEPLOYMENT` AgentAction to scale replica count.
- **Trigger**: Celery beat task, runs resource utilization checks.

### `backend/workers/tasks/standby.py`
**Warm standby node management.**

- Writes `UNCORDON_NODE` AgentAction to activate a standby node during emergency.
- **Trigger**: Celery beat, monitors for emergency conditions.

### `backend/workers/tasks/keda_installer.py`
**KEDA install automation.**

- Writes `INSTALL_KEDA` / `UNINSTALL_KEDA` AgentActions.
- **Trigger**: Celery task, called on KEDA enable/disable API calls.

### `backend/api/optimize_routes.py`
**UI manual trigger: AZ rebalance.**

- `POST /optimize/workloads/{workload_id}/rebalance-az` — calls placement controller
  directly to dispatch evictions.
- **Trigger**: UI button "Rebalance AZ" on the Workloads page.

### `backend/api/karpenter_routes.py`
**Multiple UI-triggered real actions** (see §4).

---

## 4. Files That Call AWS APIs Directly (No Agent)

### `backend/services/karpenter_service.py`
**The heaviest direct-AWS file.** Uses `boto3` + K8s API client to:

| Method | AWS / K8s operation | When called |
|---|---|---|
| `sync_ml_rankings_to_nodepool()` | K8s PATCH `karpenter.sh/v1/nodepools` | Auto-rebalancer after ML ranking, or manual sync |
| `switch_to_ondemand()` | K8s PATCH NodePool → capacity-type=on-demand | When no safe spot pools exist (auto) |
| `revert_to_spot()` | K8s PATCH NodePool → capacity-type=spot | After 12h OD fallback TTL expires (auto) |
| `_update_nodepool()` | K8s PATCH/CREATE NodePool | Every ML sync cycle |
| `_get_k8s_client()` | AWS STS `GetCallerIdentity` (SigV4 presigned) | Auth for every K8s call |
| `_get_ec2_client()` | `boto3.client('ec2')` | Capacity checks |
| `patch_consolidation_policy()` | K8s PATCH NodePool disruption spec | UI toggle |
| Karpenter install routes | `helm install` via `INSTALL_KARPENTER` AgentAction | UI Deploy button |

**Trigger sources**:
- Auto-rebalancer Celery task (ML ranking cycle).
- API routes: `POST /karpenter/deploy`, `POST /karpenter/toggle/{cluster_id}`,
  `POST /karpenter/apply-recommendation/{id}`, `PATCH /karpenter/mode/{cluster_id}`.
- 12-hour TTL auto-revert (background scheduler).

### `backend/workers/tasks/auto_rebalancer.py`
**The largest execution file (~10K lines).** Orchestrates the full node-swap cycle:

```
Phase 1  — Launch replacement spot EC2 via Karpenter (NodePool triggers spot provisioning)
Phase 2  — Wait for new node to register in K8s + reach Ready
Phase 3  — Cordon + drain old on-demand node  (dispatches DRAIN_NODE AgentAction)
Phase 4  — Verify pods rescheduled on spot
Phase 5  — Terminate old EC2 instance  (dispatches TERMINATE_NODE AgentAction)
Rollback — UNCORDON_NODE + TERMINATE orphan spot if any phase fails
```

Also calls:
- `boto3` EC2 `DescribeInstances`, `DescribeInstanceTypes`, `DescribeImages`
- `karpenter_service.sync_ml_rankings_to_nodepool()` (after each ranking update)
- K8s API directly for node labeling during Phase 1

**Trigger**: Celery beat every ~60–90s via `execute_rebalancing()` task.

### `backend/services/tag_management_service.py`
**Real AWS tag read/write** via STS AssumeRole + boto3:

- `get_resource_tags()` — reads EC2/EBS/S3/RDS tags.
- `apply_tags()` — writes tags to AWS resources.
- **Trigger**: UI tag compliance page actions, or tag policy enforcement job.

### `backend/workers/tasks/discovery.py`
**Cluster + node discovery.** Calls AWS EKS `DescribeCluster`, EC2 `DescribeInstances`,
K8s API `list_node` etc. to populate the DB.

- **Trigger**: Celery beat (periodic), or UI "Rescan Cluster" button.

### `backend/api/karpenter_routes.py`
Direct AWS via KarpenterService for:

| Endpoint | Real action |
|---|---|
| `POST /karpenter/deploy` | K8s NodePool CREATE via karpenter_service |
| `POST /karpenter/apply-recommendation/{id}` | K8s NodePool PATCH |
| `POST /karpenter/apply-recommendations/batch` | K8s NodePool PATCH (bulk) |
| `PATCH /karpenter/mode/{cluster_id}` | Toggle auto vs dry_run, may PATCH NodePool |
| `POST /nodegroup/{cluster_id}/enable-spot` | AWS ASG `UpdateNodegroupConfig` (for non-Karpenter) |
| `POST /nodegroup/{cluster_id}/revert-to-ondemand` | AWS ASG `UpdateNodegroupConfig` |
| `POST /clusters/{cluster_id}/install` | Queues `INSTALL_KARPENTER` AgentAction |
| `DELETE /clusters/{cluster_id}/install` | Queues `UNINSTALL_KARPENTER` AgentAction |
| `POST /native-spot/enable/{cluster_id}` | AWS ASG update (no Karpenter) |
| `POST /native-spot/revert/{cluster_id}` | AWS ASG revert |

### `backend/workers/tasks/resize_guard_worker.py`
**Right-sizing execution.** Dispatches `PATCH_CONTAINER_RESOURCES` AgentAction to
update pod CPU/memory requests+limits via K8s patch.

- **Trigger**: Celery beat after rightsizing proposal is approved (auto or manual).

### `backend/workers/tasks/reconciliation_worker.py`
**NodePool class reconciler.** Patches Karpenter NodePool requirements (instance families,
AZs) to stay aligned with ML rankings.

- **Trigger**: Scheduler every 10 min (throttled internally to 30 min / 6 h).

---

## 5. Trigger Summary — When Does Each Fire?

### Fully Automatic (no human action required)

| What fires | File | Cadence |
|---|---|---|
| Spot node swap (full drain+provision cycle) | `auto_rebalancer.py` | Celery beat ~60–90s |
| Pod evictions (OD → spot) | `placement_controller_task.py` | Celery beat ~60s |
| Emergency evictions (spot interruption) | `emergency_rebalancer.py` | Celery beat + SQS event |
| Stuck node recovery (uncordon/evict) | `recovery_monitor.py` | Celery beat ~5 min |
| ML rankings → NodePool sync | `auto_rebalancer.py` + `karpenter_service.py` | Each rebalance cycle |
| NodePool class reconciliation | `reconciliation_worker.py` | Every 10 min |
| Rightsizing patch (after auto-approve) | `resize_guard_worker.py` | Celery beat |
| WIE classification update | `scheduler.py` → WIE | Every 2 min (fast) / 10 min (slow) |
| Placement cycle (PPE + DE) | `placement_advisor_task.py` | Every 10 min |
| OD fallback auto-revert (12h TTL) | `karpenter_service.revert_to_spot()` | Redis TTL expiry |
| Standby node activation | `standby.py` | Celery beat, on emergency signal |
| KEDA scale trigger | `auto_scaler.py` | Celery beat |

### UI Button / Manual API Trigger

| UI button / action | API route | Service called | Real action |
|---|---|---|---|
| Karpenter → Deploy | `POST /karpenter/deploy` | `KarpenterService` | K8s NodePool CREATE |
| Karpenter → Pause/Resume | `POST /karpenter/toggle/{id}` | `KarpenterService` | NodePool patch, mode flag |
| Apply Recommendation | `POST /karpenter/apply-recommendation/{id}` | `KarpenterService` | K8s NodePool PATCH |
| Bulk Apply Recommendations | `POST /karpenter/apply-recommendations/batch` | `KarpenterService` | K8s NodePool PATCH (N) |
| Mode switch (dry_run ↔ auto) | `PATCH /karpenter/mode/{id}` | `KarpenterService` | NodePool + Redis flag |
| Install Karpenter | `POST /karpenter/clusters/{id}/install` | AgentAction queue | `helm install` in-cluster |
| Uninstall Karpenter | `DELETE /karpenter/clusters/{id}/install` | AgentAction queue | `helm uninstall` in-cluster |
| Enable Spot (ASG) | `POST /nodegroup/{id}/enable-spot` | KarpenterService | AWS ASG update |
| Revert to OD (ASG) | `POST /nodegroup/{id}/revert-to-ondemand` | KarpenterService | AWS ASG update |
| Workload → Rebalance AZ | `POST /optimize/workloads/{id}/rebalance-az` | PlacementController | EVICT_POD AgentAction |
| Install KEDA | `POST /karpenter/keda/install` | `keda_service` | INSTALL_KEDA AgentAction |
| Workload Placement → Apply | _(not yet wired; PPE+DE produces manifest)_ | DistributionEngine | pending EE |
| Deploy Substitute | `POST /karpenter/v3/substitute/{id}/deploy` | SubstituteManager | EC2 launch + K8s |
| Rightsizing → Approve | `POST /karpenter/rightsize/approve` | resize_guard_worker | PATCH_CONTAINER_RESOURCES |
| Tag → Apply | tag routes | `tag_management_service` | AWS tag write (boto3) |

---

## 6. Background Scheduler (`scheduler.py`) — Job Registry

All jobs start 60s after server boot, then repeat:

| # | Job | Interval | Downstream execution |
|---|---|---|---|
| 1 | Refresh active cluster count | 5 min | DB read only |
| 2 | Reconcile stuck substitutes | 5 min | may write AgentActions |
| 3 | Scan clusters (WIE slow loop) | 10 min | Redis + DB writes |
| 4 | Check cost drift | 30 min | DB/Redis read |
| 5 | Detect volatility regimes | 1 hour | DB writes |
| 6 | Blacklist + Redis cleanup | Daily 2AM | DB/Redis delete |
| 7 | WIE fast loop | 2 min | Redis writes |
| 8 | Karpenter metrics collection | 2 min | Redis writes |
| 9 | Placement advisor cycle (PPE) | 10 min | Celery async task |
| 10 | NodePool class reconciliation | 10 min | K8s NodePool PATCH |

> Note: Auto-rebalancer (`execute_rebalancing`) and placement controller
> (`placement_controller_task`) run as **Celery beat tasks**, not APScheduler jobs.
> They are defined in the Celery worker configuration, not in `scheduler.py`.

---

## 7. Safety Gates (Why Real Actions Don't Fire Uncontrolled)

Before any real K8s/AWS action executes, these guards must all pass:

1. **Shadow mode** (`spot:shadow_mode:{cluster_id}` Redis key) — if set, metrics only, no evictions.
2. **Cluster cooldown** (`spot:cluster:cooldown:{cluster_id}`) — post-rebalance quiet period.
3. **Karpenter pause key** (`spot:karpenter_pause:{cluster_id}`) — set when Karpenter is actively consolidating.
4. **Distributed rebalance lock** (`spot:rebalance_lock:{cluster_id}`) — one rebalance cycle at a time per cluster.
5. **PDB check** (in PPE `PlanValidator`) — blocks pod eviction if PDB `minAvailable` would be violated.
6. **Circuit breaker** (`spot:exec_fail_window:{cluster_id}`) — blocks `KarpenterService` if >10 failures in 10 min.
7. **dry_run / Insights mode** — Karpenter NodePool never patched; only recommendations written to DB.
8. **`MAX_MOVES_PER_CYCLE = 2`** — hard cap in PPE; at most 2 pods move per engine cycle.
