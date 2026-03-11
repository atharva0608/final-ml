# Rebalancing & Right-Sizing — Complete Flow Reference

> Last updated: 2026-03-11
> Covers: auto-rebalancer, right-sizing evaluator, emergency handler, standby system

---

## Table of Contents

1. [Architecture Overview](#1-architecture-overview)
2. [Rebalancing — Without Karpenter (Direct EC2)](#2-rebalancing--without-karpenter-direct-ec2)
3. [Rebalancing — With Karpenter](#3-rebalancing--with-karpenter)
4. [Right-Sizing — Without Karpenter](#4-right-sizing--without-karpenter)
5. [Right-Sizing — With Karpenter](#5-right-sizing--with-karpenter)
6. [Emergency Handling — Spot Interruption](#6-emergency-handling--spot-interruption)
7. [Standby Node System](#7-standby-node-system)
8. [Spot-to-Spot (S2S) Rebalancing](#8-spot-to-spot-s2s-rebalancing)
9. [Failure & Rollback Scenarios](#9-failure--rollback-scenarios)
10. [Guard Rails & Safety Checks](#10-guard-rails--safety-checks)
11. [Diversification Logic](#11-diversification-logic)
12. [Key Redis Keys & Cooldowns](#12-key-redis-keys--cooldowns)

---

## 1. Architecture Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                    CONTROL PLANE (Celery)                        │
│                                                                  │
│  auto_rebalancer (15s)   emergency_rebalancer (on-demand)       │
│  rightsizing_eval (24h)  recovery_monitor (60s)                 │
│  termination_monitor (30s)  standby (on-demand)                 │
│                                                                  │
│              ┌────────────────────────────┐                     │
│              │    Decision Engine (DE)     │                     │
│              │  ML Pool Rankings (Redis)   │                     │
│              │  Spot Advisor + Price Data  │                     │
│              └────────────────────────────┘                     │
└──────────────────────────┬──────────────────────────────────────┘
                           │ AgentAction rows (DB)
                           ▼
┌─────────────────────────────────────────────────────────────────┐
│             IN-CLUSTER AGENT (per EKS cluster)                   │
│                                                                  │
│  agent/actuator.py — polls AgentActions every 5s               │
│  Executes: CORDON, DRAIN, TERMINATE, UNCORDON, LABEL_NODE       │
│            PATCH_KARPENTER_NODEPOOL, FORCE_DELETE_NODE          │
└─────────────────────────────────────────────────────────────────┘
```

**Two paths** based on whether Karpenter is installed in the cluster:

| Dimension | Without Karpenter | With Karpenter |
|-----------|-------------------|----------------|
| Who provisions new node | Backend calls EC2 `RunInstances` directly | Backend patches NodePool CRD; Karpenter provisions |
| Node group | ASG (standard-workers managed node group) | NodeClaim (unmanaged by ASG) |
| Spot pricing | Determined by ML Decision Engine | Determined by NodePool instance types (ML-ranked) |
| Cordon/Drain | In-cluster agent | In-cluster agent |
| Terminate old node | Backend calls ASG `terminate_instance_in_asg` | In-cluster agent calls `kubectl delete node` OR backend terminates EC2 |

---

## 2. Rebalancing — Without Karpenter (Direct EC2)

**Trigger**: `auto_rebalancer` Celery task, every 15 seconds.
**Goal**: Replace an on-demand node with a cheaper spot node of similar/smaller size.

### Phase 1 — Spot Provisioning (Backend)

```
auto_rebalancer wakes up
│
├─ Safety checks (skip if any fail):
│   ├─ Cluster status == ACTIVE
│   ├─ auto_rebalance_enabled == True
│   ├─ No strict 600s cooldown active (Redis key: cluster_cooldown:{cluster_id})
│   ├─ No rebalancing lock (Redis: rebalance_lock:{cluster_id})
│   ├─ At least 1 OD node exists
│   └─ Daily limit not exceeded (max_rebalances_per_24h, default 5)
│
├─ ML Pool Selection:
│   ├─ DecisionEngineService.get_top_pools(region, node_template)
│   ├─ Filter: dry-run capacity check (EC2 RunInstances DryRun=True, TTL=120s)
│   ├─ Filter: diversification caps (40% family, 50% AZ, +in-flight actions)
│   ├─ Filter: blacklisted pools (24h after interruption)
│   └─ Select top-3 candidates
│
├─ ASG Suspend:
│   └─ suspend_asg_processes(['Launch', 'Terminate', 'AZRebalance'])
│       Reason: prevents ASG from interfering while we swap nodes
│
├─ Direct EC2 Launch (run_instances):
│   ├─ ImageId: from source node's AMI
│   ├─ InstanceType: top ML-ranked type
│   ├─ NetworkInterfaces: [{SubnetId, Groups, AssociatePublicIpAddress: False}]
│   │   ← AssociatePublicIpAddress=False is REQUIRED for EKS nodes
│   ├─ InstanceMarketOptions: spot / one-time
│   ├─ IamInstanceProfile: from source node
│   ├─ UserData: from source node (contains EKS bootstrap script)
│   └─ Tags: spot-optimizer:status=pending, kubernetes.io/cluster/{name}=owned
│
├─ RebalancingAction created: status=waiting_agent
│   └─ action_metadata: {
│        step_1_spot_provisioning: <timestamp>,
│        provisioner_type: direct_ec2,
│        replacement_spot_instance_id: <new EC2 id>,
│        asg_name_used, asg_min_at_start, asg_desired_at_start
│      }
│
└─ 24h per-instance cooldown: Redis setex spot:rebalanced:instance:{instance_id}
```

### Phase 2 — Node Migration (Backend watches; Agent executes)

```
auto_rebalancer polls every 15s for action in waiting_agent
│
├─ Wait for new spot node to join K8s (max 1800s / 30 min):
│   ├─ Condition: running spot count > baseline AND age >= 90s (stabilization)
│   │   90s window lets kubelet register, pods schedule, EBS re-attach
│   └─ On join: record step_4_new_node_joined
│                queue LABEL_NODE (karpenter.sh/do-not-disrupt=true) for new node
│
├─ Create Phase 2 AgentActions (queued to DB, agent polls):
│   ├─ CORDON_NODE (old OD node)    ← prevents new pods scheduling on it
│   ├─ DRAIN_NODE (old OD node)     ← evicts pods, waits for graceful shutdown
│   │   payload: {grace_period: 60, ignore_daemonsets: true}
│   └─ (TERMINATE handled by backend after drain — see below)
│
├─ Backend monitors for drain completion (poll every 15s):
│   ├─ DRAIN_NODE AgentAction status == COMPLETED
│   ├─ Post-drain readiness: wait for new node to become fully Ready (max 120s)
│   │   Reason: gives EBS volumes time to re-attach on new node
│   └─ Terminate old node:
│       ├─ Try: asg.terminate_instance_in_auto_scaling_group(
│       │         InstanceId, ShouldDecrementDesiredCapacity=True)
│       ├─ If asg_desired <= asg_min: first set_min_size(0), then terminate
│       └─ Tag spot node: spot-optimizer:status=joined (removes pending tag)
│
├─ RebalancingAction.status = completed
│   └─ action_metadata adds: step_2_cordon, step_3_draining_pods,
│        step_5_old_node_terminated, step_6_optimization_complete
│
├─ Post-success:
│   ├─ Resume ASG processes
│   ├─ Remove karpenter.sh/do-not-disrupt from new spot node
│   ├─ Trigger savings recalculation
│   └─ Set 600s strict cooldown on cluster
│
└─ set_min_size restored if it was lowered
```

### State Machine

```
pending → in_progress → waiting_agent → completed
                                      ↘ failed (with rollback)
```

---

## 3. Rebalancing — With Karpenter

**Key difference**: Backend patches the Karpenter `NodePool` CRD with ML-ranked instance types. Karpenter provisions the spot node via its own controller loop.

```
auto_rebalancer wakes up
│
├─ Safety checks (same as non-Karpenter)
│
├─ ML Pool Selection → top-3 spot instance types
│
├─ Karpenter NodePool Patch (every 30 min, Redis cooldown):
│   └─ PATCH_KARPENTER_NODEPOOL AgentAction queued
│       payload: {instance_types: [...top ML types...]}
│       Agent executes: kubectl patch NodePool default --patch ...
│
├─ Phase 1 waits for Karpenter to provision:
│   ├─ spot count > baseline (Karpenter creates NodeClaim → EC2 → joins K8s)
│   ├─ Timeout: 1800s (30 min); if expired, proceed anyway (Karpenter may be slow)
│   └─ On join: karpenter.sh/do-not-disrupt=true annotated via LABEL_NODE
│
└─ Phase 2 (CORDON → DRAIN → TERMINATE):
    ├─ Same as non-Karpenter (agent executes CORDON + DRAIN)
    ├─ TERMINATE: kubectl delete node (Karpenter manages EC2 lifecycle)
    └─ Remove do-not-disrupt annotation after completion
```

**NodePool sync** (separate from rebalancing, runs every 30 min):
- `sync_karpenter_nodepools` Celery task
- Gets top ML pools → patches NodePool instanceTypes
- Karpenter's consolidation loop then evicts/reprovisions nodes as needed

---

## 4. Right-Sizing — Without Karpenter

**Trigger**: `rightsizing_evaluation_worker`, every 24 hours.
**Goal**: Identify nodes running at low utilization that could be bin-packed onto a smaller instance type.

```
rightsizing_evaluation_worker runs
│
├─ Safety checks:
│   ├─ auto_rightsizing_enabled == True
│   ├─ ≥24h stability window (no recent rebalancing actions)
│   └─ No pending/in-progress rightsizing proposals
│
├─ Bin-packing analysis per node:
│   ├─ Get CPU / memory utilization (7-day P95 from pod_metrics)
│   ├─ Required size: actual_usage × 1.25 safety headroom
│   ├─ INSTANCE_SPECS lookup: find smallest type that fits required + headroom
│   └─ Filter: must be ≥15% cheaper than current type
│
├─ Proposal created: OptimizationProposal (status=pending)
│   └─ If manual_approval_required: waits for human approval
│   └─ Auto-approve: if StatelessRules allow (low risk, single node, etc.)
│
├─ Execution (after approval):
│   ├─ CORDON old node (agent)
│   ├─ Direct EC2 launch of smaller type (same as rebalancing Phase 1)
│   ├─ Wait for new node to join
│   ├─ DRAIN old node (agent)
│   └─ Terminate old node (same as rebalancing Phase 2)
│
├─ Post-resize guard (resize_guard_worker, every 5 min, 2h window):
│   ├─ Monitor CPU stress (>80%), pod restarts (>baseline×3), memory pressure
│   └─ Auto-rollback: launch original size if guard triggers
│
└─ Stateful right-sizing (auto_stateful_rightsizing_enabled):
    ├─ 48h stability window (vs 24h for stateless)
    ├─ Max 1 stateful node per cluster per cycle
    ├─ StatefulRules.require_approval always True
    └─ No bin-packing — stateful nodes keep same instance family
```

---

## 5. Right-Sizing — With Karpenter

```
Karpenter handles consolidation natively via:
  WhenEmptyOrUnderutilized consolidation policy

Backend role:
├─ Calculate bin-packed target type (same analysis as above)
├─ Patch NodePool with: [target_type, ...fallback_types]
├─ Set consolidationPolicy: WhenEmptyOrUnderutilized
│   → Karpenter evicts pods from underutilized nodes and reprovisions
└─ Backend monitors for completion (node count changes)

If manual_approval_required:
└─ Same approval gate; once approved, patch NodePool
```

---

## 6. Emergency Handling — Spot Interruption

**Trigger sources**:
1. SQS EventBridge message (2-min warning from AWS)
2. Agent metadata polling (IMDSv2 `/spot/termination-time`)
3. `recovery_monitor` orphan detection

**Queue**: `emergency` (dedicated, isolated from batch workers)

```
emergency_rebalancer task dispatched
│
├─ Override cooldowns (clear cluster_cooldown + rebalance_lock)
│
├─ Report to Decision Engine: blacklist pool for 24h
│   Redis: blacklist:global:{instance_type}:{az}
│
├─ Check: maintain_standby enabled AND standby node available?
│
├─ YES — Standby Failover (fast path, <30s):
│   ├─ UNCORDON standby node (immediately schedulable)
│   ├─ CORDON interrupted node (no new pods)
│   ├─ DRAIN interrupted node:
│   │   force=True (bypass PDBs — required for 2-min window)
│   │   grace_period=90s (AWS kills at T+120s)
│   │   emergency=True (actuator uses 90s escalation timer)
│   ├─ Mark interrupted as terminating
│   ├─ Mark standby as active (standby=False)
│   └─ Launch new standby async (launch_standby_node.delay)
│
└─ NO — Normal Emergency Flow:
    ├─ Create RebalancingAction with action_type=emergency
    │   action_metadata: {emergency: True, bypass_double_gate: True}
    └─ auto_rebalancer picks it up next cycle with priority
        (bypasses daily limit check and double-gate)
```

**2-Minute Window Budget**:
```
T+0s:   AWS sends spot interruption warning via SQS
T+5s:   SQS consumer receives message, dispatches emergency_rebalancer
T+10s:  Standby uncordoned (if available) OR new spot launched
T+30s:  Drain starts, pods begin evicting
T+90s:  force-delete any remaining PDB-blocked pods
T+120s: AWS terminates instance (hard deadline)
```

---

## 7. Standby Node System

**Purpose**: Pre-warm a spot node so failover takes seconds instead of minutes.

```
launch_standby_node task
├─ Pool selection (ML-ranked, same cluster region)
├─ AZ pinning: match AZ of busiest node (avoids zonal PVC deadlock)
│   If PVC workloads detected + no pools in preferred AZ → abort
├─ Direct EC2 launch (same run_instances as rebalancer)
├─ Tag instance: spot-optimizer:standby=true
├─ Wait for K8s join (max 15 min)
└─ CORDON standby node:
    Reason: keeps it Ready but unschedulable (not wasting resources)
    Sets Instance.standby = True

Standby lifecycle:
  CORDONED (ready, no pods)
  → UNCORDONED on interruption (becomes active node)
  → New standby launched to replace it
```

**Zombie standby GC**: `reconcile_standby` in `substitute_manager.py` skips nodes with `is_warm_spare=True` flag — they are intentionally idle.

---

## 8. Spot-to-Spot (S2S) Rebalancing

**Purpose**: Replace an existing spot node in an over-represented pool (diversification violation or high-risk pool) with a better spot node.

```
S2S triggers:
├─ Family share > 40% (e.g., 5/8 nodes are t3.* = 62.5%)
└─ Pool risk score > 0.4 (high interruption probability)

S2S flow (same as OD→Spot rebalancing):
├─ Launch new spot node (different type/AZ)
├─ Wait for join
├─ CORDON + DRAIN old spot node
└─ Terminate old spot node (direct EC2 terminate, not ASG)
    Reason: spot nodes are NOT in the ASG (they were launched outside it)
```

---

## 9. Failure & Rollback Scenarios

### Rollback Helper: `_do_rollback_uncordon_and_terminate`

Called when CORDON or DRAIN fails. Performs full cleanup:
1. Terminate orphan spot node (using `replacement_spot_instance_id` from metadata, or timestamp fallback)
2. Queue `UNCORDON_NODE` AgentAction for the source OD node
3. Resume ASG if it was suspended
4. Mark action as `failed`

### Rollback Helper: `_do_rollback_terminate_orphan_spot`

Called when EC2 terminate fails post-drain. Only terminates orphan spot (K8s node already deleted by drain, so no uncordon needed).

### Failure Scenario Matrix

| Stage | What fails | Rollback action |
|-------|-----------|-----------------|
| Phase 1 — EC2 launch | `RunInstances` errors (capacity, quota) | Try next type in list; if all fail → set action failed, resume ASG |
| Phase 1 — Karpenter timeout | NodePool patched but no node joins in 30 min | Proceed with drain anyway (Karpenter may provision post-drain) |
| Phase 2 — CORDON fails | Agent action status=FAILED | Terminate orphan spot + UNCORDON OD node |
| Phase 2 — DRAIN fails | Agent action status=FAILED | Terminate orphan spot + UNCORDON OD node |
| Phase 2 — EC2 terminate fails | boto3 exception | Terminate orphan spot (OD node already drained) |
| Post-resize — CPU spike | >80% after resize | Resize-guard triggers rollback (original size relaunched) |
| Standby failover — all fail | Exception in standby path | Fall back to normal emergency flow |

### UNCORDON_NODE in Actuator

**Critical**: `UNCORDON_NODE` is handled in `execute_action_v2` by calling `cordon_node(node_name, uncordon=True)`.
Before 2026-03-11, this was missing from the v2 dispatcher — all rollback uncordon attempts silently failed, leaving nodes stuck cordoned.

---

## 10. Guard Rails & Safety Checks

### Double Gate (OD → Spot)

Every rebalancing action must pass **two independent checks**:

1. **Gate 1 — Policy check** (at action creation): `auto_rebalance_enabled`, daily limits, cooldowns
2. **Gate 2 — Execution check** (at execute time): cluster still healthy, node still running, cooldown still valid

Emergency actions with `bypass_double_gate=True` skip Gate 2.

### Cluster Stability Checks

```python
# In auto_rebalancer before proceeding:
if _total_nodes <= _od_count + 1:  # Would leave only 1 node
    continue  # Last-node guard — don't drain if no replacement yet

# Strictly one rebalancing per cluster per cycle:
_active = db.query(RebalancingAction).filter(status.in_(['pending', 'in_progress', 'waiting_agent'])).first()
if _active:
    break
```

### Per-Instance 24h Cooldown

After successfully rebalancing an instance, a 24h Redis key prevents re-targeting:
```
Redis: spot:rebalanced:instance:{instance_id}  TTL: 86400s
```

### Strict 600s Cluster Cooldown

After completing any rebalancing action, no new actions for 10 min:
```
Redis: cluster_cooldown:{cluster_id}  TTL: 600s
```

### ASG Min-Size Guard

If `asg_desired == asg_min` (last node in ASG), the terminate call would fail.
Fix: temporarily set `MinSize=0` before calling `terminate_instance_in_auto_scaling_group(ShouldDecrementDesiredCapacity=True)`.
After termination, `MinSize` is restored.

---

## 11. Diversification Logic

**When `diversify_pools=True`** (cluster setting):

```
Family cap:  (nodes_of_family + 1) / total_nodes <= 0.40  (40%)
AZ cap:      (nodes_in_az + 1) / total_nodes <= 0.50      (50%)

"total_nodes" = running instances in DB
             + in-flight actions (waiting_agent / in_progress)
             ← CRITICAL: in-flight included to prevent same pool during provisioning
             + 1 (the new incoming node)

If diversification filters everything:
  → Relax AZ cap (allow any AZ, but keep 40% family cap)
  → Last resort: use top-3 from ML rankings as-is
```

**In recommendations UI** (`/clusters/{id}/node-recommendations`):
- Each OD node gets a **different** recommended target type (`used_types` set)
- 40% family cap applied across recommended targets

---

## 12. Key Redis Keys & Cooldowns

| Key Pattern | TTL | Purpose |
|-------------|-----|---------|
| `cluster_cooldown:{cluster_id}` | 600s | Post-rebalance cooldown |
| `rebalance_lock:{cluster_id}` | 180s | Distributed lock during execution |
| `spot:rebalanced:instance:{instance_id}` | 86400s | Per-instance 24h cooldown |
| `blacklist:global:{type}:{az}` | 86400s | Pool blacklisted after interruption |
| `spot:karpenter:nodepool_updated:{cluster_id}` | 1800s | NodePool sync 30-min cooldown |
| `dry_run:{region}:{type}:{az}` | 120s | Capacity probe cache |
| `node_joined:{instance_id}` | set on join | Prevents orphan termination |
| `cluster_pools:{cluster_id}` | set | Pool membership set (Redis SADD) |
| `emergency:od_fallback:{cluster_id}` | set | Marks OD emergency fallback active |

---

## Common Scenarios

### Scenario A: Normal night-time rebalancing (no Karpenter)
1. 3 OD `t3.medium` nodes, `auto_rebalance_enabled=True`
2. ML ranks `c5.large:ap-south-1b` as top pool (40% savings, <5% interruption)
3. rebalancer creates action, suspends ASG, launches `c5.large` via RunInstances
4. New node joins in 4 min
5. Agent cordons + drains `ip-192-168-x-x` (OD t3.medium)
6. Backend terminates OD via ASG with decrement
7. Result: 2 OD t3.medium + 1 spot c5.large

### Scenario B: Spot interruption with standby
1. AWS sends 2-min warning for spot node `i-abc`
2. SQS consumer → emergency_rebalancer dispatched
3. Standby node `ip-192-168-standby` uncordoned immediately
4. `i-abc` cordoned + drained in 90s (force=True bypasses PDBs)
5. New standby launched in background
6. Total downtime for pods: 0s (pods schedule to uncordoned standby)

### Scenario C: Diversification violation
1. 5 nodes: 4× t3.medium + 1× t3.large = 100% `t3` family
2. Diversify cap 40% → t3 blocked
3. ML ranks `m5.large` next; `(0+1)/6 = 17%` → allowed
4. Rebalancer picks `m5.large` for next replacement
5. Cluster moves toward: 3× t3 + 1× m5 + 1× c5 (healthy diversity)

### Scenario D: Right-sizing (over-provisioned node)
1. Node `t3.large` (2 vCPU, 8 GB) at 15% CPU, 20% memory
2. Required: `2 × 0.15 × 1.25 = 0.375 vCPU`, `8 × 0.20 × 1.25 = 2 GB`
3. Bin-pack: `t3.micro` fits (2 vCPU, 1 GB) — NO (memory insufficient)
4. `t3.small` fits (2 vCPU, 2 GB) — YES, 40% cheaper
5. Proposal created, approved, executed
6. Result: `t3.small spot` replaces `t3.large OD`

### Scenario E: CORDON fails — rollback
1. Action in progress, spot node already launched (`i-spot-new`)
2. CORDON AgentAction returns FAILED (node disappeared / kubelet unresponsive)
3. Rebalancer detects CORDON_NODE failed (not DRAIN_NODE)
4. Calls `_do_rollback_uncordon_and_terminate`:
   - Terminates `i-spot-new` (orphan) via EC2 API
   - Queues UNCORDON_NODE for source OD (in case it was partially cordoned)
   - Resumes ASG
5. Action marked `failed`, 24h cooldown cleared for source node
6. Will retry on next cycle

---

## FAQ

**Q: Why does the spot node get launched in the same AZ as an existing spot node?**
A: Diversification caps per AZ (50%). Check if `diversify_pools=True` in cluster settings. Also verify `RebalancingAction` with `waiting_agent` status is included in in-flight count.

**Q: Why did the rebalancer launch a c5.large when the metadata says t3a.small?**
A: Pool selection at action creation time vs. at execution time can differ if ML rankings are refreshed between the two. The execute path uses the saved `target_instance_type` from the action — if it falls back to re-ranking, the cached pool may have changed.

**Q: Why is a node showing with a public IP?**
A: Subnets with `MapPublicIpOnLaunch=True` auto-assign public IPs when `RunInstances` uses top-level `SubnetId`. Fixed (2026-03-11): now uses `NetworkInterfaces` with `AssociatePublicIpAddress: False`.

**Q: Why are running nodes being marked terminated?**
A: `sync_instance_states` fell back to platform creds for cross-account clusters when assume_role failed. Platform creds can't describe customer's instances → empty DescribeInstances → "not returned = terminated" logic fired. Fixed (2026-03-11): skip cluster if assume_role fails; don't mark as terminated on empty response.

**Q: What happens if drain takes >2 minutes during spot interruption?**
A: `force=True` in emergency drain payload bypasses PodDisruptionBudgets. `grace_period=90` gives pods 90s; any remaining pods are force-deleted at T+90s by the actuator's PDB bypass path. AWS terminates the EC2 at T+120s regardless.
