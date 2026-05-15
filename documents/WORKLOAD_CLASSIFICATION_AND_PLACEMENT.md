# Workload Classification & Pod Placement Guide

> **Current cluster snapshot** · 27 Total Pods · 14 Spot-friendly (52%) · 13 Non spot-friendly · 13 Stateful · Node classification: 2 Mixed → review

---

## Table of Contents

1. [How Workloads Are Classified — The Three Layers](#1-how-workloads-are-classified--the-three-layers)
2. [Layer 1 — WorkloadInspector (Node-level)](#2-layer-1--workloadinspector-node-level)
3. [Layer 2 — SmartWorkloadClassifier (Controller / Tier-level)](#3-layer-2--smartworkloadclassifier-controller--tier-level)
4. [Layer 3 — Per-Pod `is_stateful` Determination (API / UI)](#4-layer-3--per-pod-is_stateful-determination-api--ui)
5. [What Makes a Pod Spot-Friendly vs Not](#5-what-makes-a-pod-spot-friendly-vs-not)
6. [Ideal Pod Placement Architecture](#6-ideal-pod-placement-architecture)
7. [How Karpenter Enforces the Placement](#7-how-karpenter-enforces-the-placement)
8. [The Rebalancing Pipeline — How Pods Are Moved](#8-the-rebalancing-pipeline--how-pods-are-moved)
9. [Critical Pod Protection — How Stateful Pods Are Never Moved](#9-critical-pod-protection--how-stateful-pods-are-never-moved)
10. [The "2 Mixed → Review" Problem](#10-the-2-mixed--review-problem)
11. [Current Cluster State Analysis & Recommended Actions](#11-current-cluster-state-analysis--recommended-actions)

---

## 1. How Workloads Are Classified — The Three Layers

```
K8s API
   │
   ▼
┌──────────────────────────────────┐
│  Layer 1: WorkloadInspector      │  ← Node-level scan every 9 min
│  Output: STATELESS_ELIGIBLE /    │     Cached: spot:node_classification:{cluster_id}
│          STATEFUL_PROTECTED /    │
│          DRAIN_UNSAFE /          │
│          SYSTEM_PROTECTED        │
└──────────────┬───────────────────┘
               │
               ▼
┌──────────────────────────────────┐
│  Layer 2: WorkloadClassifier     │  ← Per-controller scan every 9 min
│  Output: TIER 0 – TIER 4        │     Cached: spot:workload_tier:{cluster_id}:{ns}/{ctrl}
│          + migration policy      │
└──────────────┬───────────────────┘
               │
               ▼
┌──────────────────────────────────┐
│  Layer 3: is_stateful per pod    │  ← Real-time per-pod decision
│  (cluster_service.py)            │     Combines: Redis + pod spec signals
│  Output: is_stateful=true/false  │     Used by: the fleet UI display
└──────────────────────────────────┘
```

Each layer feeds into the next. The Decision Engine and Rebalancer only act on nodes classified **STATELESS_ELIGIBLE** by Layer 1. Layer 2 determines which pods on those nodes can actually be rescheduled to spot. Layer 3 feeds the UI numbers you see.

---

## 2. Layer 1 — WorkloadInspector (Node-level)

**File**: `backend/services/workload_inspector.py`
**Schedule**: Celery beat every 9 minutes
**Redis key**: `spot:node_classification:{cluster_id}` (TTL = 540 s)

### Node Classification Logic (evaluated in priority order)

```
For each node in the cluster:
  │
  ├─ 1. Is control-plane / system node? ──────────────► SYSTEM_PROTECTED
  │      (label: node-role.kubernetes.io/control-plane
  │       OR node-role.kubernetes.io/master)
  │
  ├─ 2. Any pod on this node has owner kind == StatefulSet? ─► STATEFUL_PROTECTED
  │
  ├─ 3. Any pod mounts a PVC (EBS CSI volume)? ──────────► STATEFUL_PROTECTED
  │
  ├─ 4. Any pod mounts a hostPath volume? ───────────────► STATEFUL_PROTECTED
  │
  ├─ 5. Any PDB with maxUnavailable = 0 covers a pod here?─► DRAIN_UNSAFE
  │
  └─ 6. None of the above ────────────────────────────────► STATELESS_ELIGIBLE
```

### What each status means

| Status | Meaning | Rebalancer action |
|---|---|---|
| `STATELESS_ELIGIBLE` | All pods are ephemeral, no sticky storage | **Candidate for spot migration** |
| `STATEFUL_PROTECTED` | Has StatefulSet, PVC, or hostPath | **Never touched by rebalancer** |
| `DRAIN_UNSAFE` | PDB blocks safe eviction | **Never drained** |
| `SYSTEM_PROTECTED` | Control plane or kube-system node | **Never touched** |

> **Key insight**: A `STATELESS_ELIGIBLE` node does NOT mean every pod on it can go to spot. It means the node itself is safe to drain. Whether individual pods go to spot is decided by Layer 2.

---

## 3. Layer 2 — SmartWorkloadClassifier (Controller / Tier-level)

**File**: `backend/services/workload_classifier.py`
**Schedule**: Runs alongside WorkloadInspector every 9 minutes
**Redis key**: `spot:workload_tier:{cluster_id}:{ns}/{controller_name}` (TTL = 540 s)

### The 8-Step Detection Pipeline

For each Deployment / StatefulSet / DaemonSet / CronJob / ReplicaSet in the cluster, the classifier runs all 8 checks in priority order and stops at the first match:

```
Step 1  ──  Is it a DaemonSet? ──────────────────────────────────────► TIER_0 NEVER_MIGRATE
            OR is it in a system namespace?
            (kube-system, kube-public, kube-node-lease, karpenter,
             spot-optimizer, cert-manager, monitoring, istio-system, linkerd)

Step 2  ──  Is it a StatefulSet? ────────────────────────────────────► TIER_1 ANCHORED_MANUAL
            OR does any pod have an active PVC?
            OR does the image match a database pattern?
            (postgres, mysql, mariadb, oracle, mssql, mongodb, redis,
             cassandra, elasticsearch, couchdb, influxdb, prometheus,
             neo4j, etcd, zookeeper, rabbitmq, kafka, nats, activemq)

Step 3  ──  Is it an Operator-managed DB? ───────────────────────────► TIER_1 ANCHORED_MANUAL
            (owner kind in: PostgresCluster, MysqlCluster, RedisCluster,
             KafkaCluster, ElasticsearchCluster, MongoDBCommunity,
             PerconaXtraDBCluster, ...)
            OR has a label marking it as operator-managed?

Step 4  ──  Is it a KEDA queue consumer? ────────────────────────────► TIER_2 SPOT_WITH_CAUTION
            (Deployment managed by KEDA ScaledObject, exposed to message queue)

Step 5  ──  Is it a batch / worker process? ─────────────────────────► TIER_3 KEDA_GATED
            (image contains: celery, sidekiq, resque, dramatiq, bull,
             bullmq, faktory, machinery — OR controller name contains worker/batch)

Step 6  ──  Readiness delay heuristic (W1.5d) ───────────────────────► May promote to TIER_1
            initialDelaySeconds > 60 s → suggests slow-starting stateful service

Step 7  ──  Confidence scoring (W1.5c) ──────────────────────────────► Validates placement
            Weighted scoring of: PVC count, image match, replicas, PDB,
            hostNetwork, readiness delay, mesh sidecar presence

Step 8  ──  Fallback ────────────────────────────────────────────────► TIER_4 SPOT_ELIGIBLE
```

### Tier Definitions & Migration Policies

| Tier | Name | Migration Policy | Examples |
|---|---|---|---|
| **TIER_0** | `NEVER_MIGRATE` | `block` | DaemonSets, kube-system pods, CNI agents |
| **TIER_1** | `ANCHORED_MANUAL` | `anchored_only` | PostgreSQL, Redis, Kafka, StatefulSets, Operator CRDs |
| **TIER_2** | `SPOT_WITH_CAUTION` | `spot_with_keda_gate` | KEDA queue consumers (RabbitMQ consumers, Kafka consumers) |
| **TIER_3** | `KEDA_GATED` | `spot_with_keda_gate` | Celery workers, Sidekiq workers, batch jobs |
| **TIER_4** | `SPOT_ELIGIBLE` | `spot_eligible` | Stateless web servers, REST APIs, frontend services |

> **Spot-friendly** = TIER_2, TIER_3, TIER_4 (can be scheduled on spot nodes)
> **Not spot-friendly** = TIER_0, TIER_1 (must stay on on-demand nodes)

---

## 4. Layer 3 — Per-Pod `is_stateful` Determination (API / UI)

**File**: `backend/services/cluster_service.py` (pod classification block)
**Runs**: On every API request to the fleet view endpoint

For every pod in the cluster, we determine `is_stateful` using **5 combined factors**:

### Factor 1 — PVC / StatefulSet owner (pod spec)
```python
has_pvc = any volume that is "persistentVolumeClaim" in pod.spec.volumes
is_stateful_owner = pod.owner_kind == "StatefulSet"

if has_pvc or is_stateful_owner:
    is_stateful = True
```

### Factor 2 — Node classification from Redis (Layer 1)
```python
node_status = _node_classification.get(pod.node_name)  # from Redis

if node_status in (STATEFUL_PROTECTED, DRAIN_UNSAFE):
    is_stateful = True
```
This catches pods on nodes that have hostPath volumes or PDB issues — cases where the pod itself looks stateless but the node is locked.

### Factor 3 — System namespace
```python
SYSTEM_NS = {"kube-system", "kube-public", "kube-node-lease", "karpenter",
             "spot-optimizer", "cert-manager", "monitoring", "istio-system", "linkerd"}

if pod.namespace in SYSTEM_NS:
    is_stateful = True  # non-migratable infrastructure pod
```

### Factor 4 — DaemonSet owner
```python
if pod.owner_kind == "DaemonSet":
    is_stateful = True  # tied to specific node, cannot migrate
```
DaemonSet pods are not counted as spot-migratable even if the image is stateless.

### Factor 5 — Workload Tier from Redis (Layer 2)
```python
tier_key = f"spot:workload_tier:{cluster_id}:{pod.namespace}/{pod.controller_name}"
tier_data = redis.get(tier_key)

if tier_data and tier_data["tier"] <= 1:  # TIER_0 or TIER_1
    is_stateful = True
```

### Final determination
```python
is_spot_friendly = NOT is_stateful
```

The UI counts:
- `spot_friendly_pods` = count of pods where `is_stateful = False`
- `non_spot_friendly_pods` = count of pods where `is_stateful = True`
- `stateful_pods` = same as `non_spot_friendly_pods`

---

## 5. What Makes a Pod Spot-Friendly vs Not

### Spot-Friendly (can be placed on spot nodes)

A pod is **spot-friendly** when ALL of the following are true:

- No PVC volumes in pod spec
- Owner is NOT a StatefulSet
- Node it runs on is classified STATELESS_ELIGIBLE (not STATEFUL_PROTECTED or DRAIN_UNSAFE)
- Namespace is NOT a system namespace
- Owner is NOT a DaemonSet
- Workload tier (from Layer 2) is TIER_2, TIER_3, or TIER_4

**Typical examples**: React/Express frontends, REST API servers, Celery workers, Sidekiq workers, KEDA consumers.

### Not Spot-Friendly (must stay on on-demand)

A pod is **NOT spot-friendly** when ANY of the following is true:

| Trigger | Reason |
|---|---|
| Has PVC volumes | Attached EBS volume — spot termination corrupts writes |
| Owner is StatefulSet | Ordered identity, sticky storage, special upgrade semantics |
| Image is a database (postgres/mysql/redis/etc.) | Data integrity risk on spot interruption |
| Node has hostPath | Volume is physically on that node's disk |
| PDB `maxUnavailable=0` | Cannot be evicted without violating PDB |
| DaemonSet owner | Binds to node, cannot float to a different node |
| System namespace | Infrastructure — must always be available |
| Operator-managed DB CRD | Postgres/Redis/Kafka operators own the lifecycle |

---

## 6. Ideal Pod Placement Architecture

```
┌──────────────────────────────┐     ┌──────────────────────────────┐
│   ON-DEMAND NODE(S)          │     │   SPOT NODE(S)               │
│   NodePool: stateful-od      │     │   NodePool: stateless-spot    │
│   Instance type: m5.xlarge   │     │   Instance type: m5.large     │
│   label: workload=stateful   │     │   label: workload=stateless   │
│                              │     │                              │
│  ● PostgreSQL pod (PVC)      │     │  ● API server (Deployment)   │
│  ● Redis pod (StatefulSet)   │     │  ● Celery worker             │
│  ● Kafka pod (Operator CRD)  │     │  ● Frontend service          │
│  ● cert-manager (sys ns)     │     │  ● KEDA consumer             │
│  ● kube-dns (kube-system)    │     │  ● Batch job                 │
│  ● Prometheus (PVC)          │     │                              │
│                              │     │  All stateless, no PVC,      │
│  All stateful / anchored     │     │  tolerates spot interruption  │
└──────────────────────────────┘     └──────────────────────────────┘
         ▲                                        ▲
         │ nodeSelector/affinity                  │ toleration
         │ workload=stateful                      │ workload=stateless
         │                                        │ node.kubernetes.io/capacity-type=spot
```

### Required Kubernetes Configuration

#### For stateful workloads — pin to on-demand nodes

Add to StatefulSet / Deployment spec:
```yaml
spec:
  template:
    spec:
      nodeSelector:
        workload: stateful
      tolerations:
        - key: "workload"
          operator: "Equal"
          value: "stateful"
          effect: "NoSchedule"
```

#### For stateless workloads — allow spot nodes

Add to Deployment spec:
```yaml
spec:
  template:
    spec:
      nodeSelector:
        workload: stateless
      tolerations:
        - key: "node.kubernetes.io/capacity-type"
          operator: "Equal"
          value: "spot"
          effect: "NoSchedule"
```

Without these tolerations + nodeSelectors, Kubernetes scheduler will freely mix pods across nodes, which is the root cause of the "Mixed" node classification.

---

## 7. How Karpenter Enforces the Placement

The system provisions two Karpenter NodePools:

### `stateless-spot` NodePool
```yaml
apiVersion: karpenter.sh/v1beta1
kind: NodePool
metadata:
  name: stateless-spot
spec:
  template:
    metadata:
      labels:
        workload: stateless
    spec:
      requirements:
        - key: karpenter.sh/capacity-type
          operator: In
          values: ["spot"]
        - key: kubernetes.io/arch
          operator: In
          values: ["amd64"]
      taints:
        - key: workload
          value: stateless
          effect: NoSchedule
  limits:
    cpu: "100"
    memory: "400Gi"
```
**Result**: Only pods that tolerate `workload=stateless` land here. Karpenter provisions spot instances. If spot is unavailable, it falls back to on-demand within the same pool.

### `stateful-od` NodePool
```yaml
apiVersion: karpenter.sh/v1beta1
kind: NodePool
metadata:
  name: stateful-od
spec:
  template:
    metadata:
      labels:
        workload: stateful
    spec:
      requirements:
        - key: karpenter.sh/capacity-type
          operator: In
          values: ["on-demand"]
      taints:
        - key: workload
          value: stateful
          effect: NoSchedule
```
**Result**: Only pods that tolerate `workload=stateful` land here. Always on-demand. Stateful pods are never interrupted.

### Anchor Node (Critical Pod Protection)

The first on-demand node in the cluster is designated the **anchor node**. It is never drained.

- All TIER_1 (ANCHORED_MANUAL) pods prefer the anchor node via pod affinity
- The anchor node is explicitly excluded from the rebalancer's candidate list
- Even if 100% of other nodes migrate to spot, the anchor node stays on-demand

---

## 8. The Rebalancing Pipeline — How Pods Are Moved

**File**: `backend/workers/tasks/auto_rebalancer.py`
**Trigger**: Celery beat every 15 seconds
**State machine**: `CREATED → POOL_SELECTED → SOURCE_CORDONED → SOURCE_DRAINED → REPLACEMENT_LAUNCHING → REPLACEMENT_READY → SOURCE_TERMINATING → COMPLETED`

### Phase 0 — Candidate Selection (which nodes to migrate)

```python
# Only STATELESS_ELIGIBLE nodes are candidates
stateless_nodes = [
    node for node, status in node_classification.items()
    if status == "STATELESS_ELIGIBLE"
]

# Filter further: only nodes that are on on-demand instances
# AND are not the anchor node
od_candidates = [
    node for node in stateless_nodes
    if node.instance_lifecycle == "on-demand"
    and node.name != anchor_node_name
]
```

Nodes classified `STATEFUL_PROTECTED`, `DRAIN_UNSAFE`, or `SYSTEM_PROTECTED` are **never in the candidate pool**. The rebalancer literally cannot see them.

### Phase 1 — Pool Selection (Decision Engine)

For each candidate OD node, the Decision Engine:

1. Reads current spot availability from AWS EC2 API
2. Scores each spot instance pool: `score = availability_score × savings_score × diversification_score`
3. Picks the pool with the highest score
4. Patches the Karpenter NodePool to add the chosen spot instance type

### Phase 2 — Replacement Provisioning

```
Rebalancer patches Karpenter NodePool (adds instance type)
    │
    ▼
Karpenter detects pending pods (or proactive scale-up trigger)
    │
    ▼
Karpenter provisions new SPOT node from selected pool
    │
    ▼
New spot node joins cluster, labeled workload=stateless
    │
    ▼
State transitions: REPLACEMENT_LAUNCHING → REPLACEMENT_READY
```

### Phase 3 — Drain & Move Pods

```python
# Cordon the on-demand node (prevent new pods)
kubectl cordon <od-node>

# Graceful drain: evict pods one by one
kubectl drain <od-node> --grace-period=300 --delete-emptydir-data

# Kubernetes scheduler places evicted pods on new spot node
# (because spot node tolerates workload=stateless)
```

During drain:
- PDB violations are respected — if a pod can't be evicted without violating `minAvailable`, drain waits
- DaemonSet pods are automatically skipped (drain ignores them by default)
- StatefulSet pods are skipped because their nodes are never candidates (STATEFUL_PROTECTED)
- `terminationGracePeriodSeconds` is fully respected

### Phase 4 — Terminate OD Node

Once all moveable pods are off the OD node:
```python
# Terminate the on-demand EC2 instance via AWS API
boto3 EC2 client → terminate_instances(InstanceIds=[od_instance_id])
```

Cost savings realized immediately — on-demand billing stops.

### S2S (Spot-to-Spot) Rebalancing

After all OD nodes are migrated, the rebalancer enters S2S mode:

- **Reason**: Spot pools can become unbalanced over time (all pods on one AZ/pool → single point of failure)
- **Check**: If > 60% of spot capacity is in a single pool → trigger diversification rebalance
- **Action**: Migrate pods from over-represented pool to under-represented pools
- **Goal**: Spread pods across AZs and instance families to reduce correlated interruption risk

### Emergency Rebalancing (90-second path)

When an AWS spot interruption notice arrives (via EC2 instance metadata):

```
Spot interruption notice → 2-minute warning
    │
    ▼
termination_monitor.py detects notice (polls every 5s)
    │
    ▼
Creates EMERGENCY rebalancing_action in DB (priority=high)
    │
    ▼
auto_rebalancer.py picks it up next 15s tick
    │
    ▼
Immediate cordon + accelerated drain (grace-period=60s)
    │
    ▼
Pods land on remaining healthy spot nodes or pending OD fallback
```

---

## 9. Critical Pod Protection — How Stateful Pods Are Never Moved

Protection is enforced at **4 independent layers**. All 4 must be bypassed for a stateful pod to accidentally move. This makes it essentially impossible.

### Protection Layer A — Rebalancer candidate filter (strongest)

```python
# auto_rebalancer.py — candidate selection
for node_name, status in classification.items():
    if status != "STATELESS_ELIGIBLE":
        continue  # ← STATEFUL_PROTECTED, DRAIN_UNSAFE, SYSTEM_PROTECTED → skip
    candidates.append(node_name)
```

If a node is `STATEFUL_PROTECTED`, it is invisible to the rebalancer. No rebalancing action can ever be created for it.

### Protection Layer B — WorkloadClassifier migration policy (pre-flight check)

Before creating a rebalancing action, the Decision Engine checks the workload tier:

```python
if workload_tier <= 1:  # TIER_0 or TIER_1
    migration_policy = "block"  # or "anchored_only"
    # → skip this pod/controller entirely
```

Even if a `TIER_1` pod somehow ended up on a `STATELESS_ELIGIBLE` node, the pre-flight check blocks migration.

### Protection Layer C — Kubernetes PDB enforcement (during drain)

```yaml
# Example PDB protecting a StatefulSet
apiVersion: policy/v1
kind: PodDisruptionBudget
spec:
  minAvailable: 1  # or maxUnavailable: 0
  selector:
    matchLabels:
      app: postgres
```

When `kubectl drain` tries to evict a pod protected by a PDB with `maxUnavailable=0`, the eviction API returns `429 Too Many Requests`. The drain waits and retries. After a timeout, the drain is aborted and the action moves to `SM_DRAIN_TIMEOUT`.

### Protection Layer D — WorkloadInspector DRAIN_UNSAFE classification

Even before Layer C fires, WorkloadInspector reads all PDBs and marks nodes with blocking PDBs as `DRAIN_UNSAFE`. These nodes never enter the candidate pool (Layer A already excludes them).

### Summary: 4-layer defense matrix

```
                    │ L-A: Rebalancer │ L-B: Tier check │ L-C: PDB eviction │ L-D: DRAIN_UNSAFE
────────────────────┼─────────────────┼─────────────────┼───────────────────┼──────────────────
DaemonSet pods      │ Node may qualify │ BLOCK (TIER_0)  │ drain auto-skips  │ (not applicable) 
StatefulSet pods    │ Node=STAT.PROT. │ BLOCK (TIER_1)  │ PDB may fire      │ PDB→DRAIN_UNSAFE 
Database pods (PVC) │ Node=STAT.PROT. │ BLOCK (TIER_1)  │ PDB may fire      │ PDB→DRAIN_UNSAFE 
System ns pods      │ Node=SYS.PROT.  │ BLOCK (TIER_0)  │ kube eviction off │ (not applicable) 
Operator CRDs       │ Node=STAT.PROT. │ ANCHORED (T1)   │ PDB may fire      │ PDB→DRAIN_UNSAFE 
```

---

## 10. The "2 Mixed → Review" Problem

### What "Mixed" means

A **Mixed** node contains **both** stateful and stateless pods co-located on the same node.

```
Mixed Node (on-demand)
├── PostgreSQL pod       ← TIER_1, must stay on OD
├── API server pod       ← TIER_4, should move to spot
└── Celery worker pod    ← TIER_3, should move to spot
```

**Problem**: WorkloadInspector scans the node and finds a StatefulSet/PVC → classifies it `STATEFUL_PROTECTED`. This locks the entire node. The stateless pods (API, Celery) are stuck on on-demand because they share a node with PostgreSQL.

### Why it happens

The root cause is missing node affinity / pod anti-affinity rules on stateless workloads. Without explicit scheduling constraints, the Kubernetes default scheduler packs pods onto available nodes, mixing stateful and stateless freely.

### How to resolve "2 Mixed → review"

#### Step 1 — Label your on-demand and spot node groups

The Karpenter NodePools should taint the nodes:
```bash
# On-demand stateful node taint (already in stateful-od NodePool)
node.kubernetes.io/capacity-type=on-demand
workload=stateful:NoSchedule

# Spot node taint (already in stateless-spot NodePool)
node.kubernetes.io/capacity-type=spot
workload=stateless:NoSchedule
```

#### Step 2 — Add pod affinity to stateless workloads

For every Deployment that should run on spot:
```yaml
spec:
  template:
    spec:
      # Tolerate spot nodes
      tolerations:
        - key: "node.kubernetes.io/capacity-type"
          operator: Equal
          value: "spot"
          effect: NoSchedule
        - key: "workload"
          operator: Equal
          value: "stateless"
          effect: NoSchedule
      # Prefer spot nodes (soft), require stateless label (hard)
      affinity:
        nodeAffinity:
          requiredDuringSchedulingIgnoredDuringExecution:
            nodeSelectorTerms:
              - matchExpressions:
                  - key: workload
                    operator: In
                    values: ["stateless"]
          preferredDuringSchedulingIgnoredDuringExecution:
            - weight: 100
              preference:
                matchExpressions:
                  - key: node.kubernetes.io/capacity-type
                    operator: In
                    values: ["spot"]
```

#### Step 3 — Add pod anti-affinity to stateful workloads (optional, defense-in-depth)

```yaml
# On StatefulSet / DB Deployment
spec:
  template:
    spec:
      tolerations:
        - key: "workload"
          operator: Equal
          value: "stateful"
          effect: NoSchedule
      affinity:
        nodeAffinity:
          requiredDuringSchedulingIgnoredDuringExecution:
            nodeSelectorTerms:
              - matchExpressions:
                  - key: workload
                    operator: In
                    values: ["stateful"]
        podAntiAffinity:
          preferredDuringSchedulingIgnoredDuringExecution:
            - weight: 100
              podAffinityTerm:
                labelSelector:
                  matchExpressions:
                    - key: tier
                      operator: NotIn
                      values: ["stateful"]
                topologyKey: kubernetes.io/hostname
```

#### Step 4 — Trigger a pod eviction from the Mixed node

Once affinity rules are added, evict the stateless pods from the mixed node so they reschedule on the correct spot node:
```bash
# Find stateless pods on the mixed node
kubectl get pods --field-selector spec.nodeName=<mixed-node> -A

# Delete (evict) the stateless pods — they'll reschedule on spot node
kubectl delete pod <api-server-pod> -n <namespace>
kubectl delete pod <celery-worker-pod> -n <namespace>
```

Kubernetes will reschedule them on the spot node (because they now have the correct tolerations). Once the mixed node only has the StatefulSet/DB pod, WorkloadInspector reclassifies it as `STATEFUL_PROTECTED` on the next scan (within 9 minutes), and it is no longer "Mixed".

---

## 11. Current Cluster State Analysis & Recommended Actions

### Current Numbers Explained

| Metric | Value | Meaning |
|---|---|---|
| Total Pods | 27 | All running pods in the cluster |
| Spot-friendly | 14 (52%) | 14 pods classified as safe for spot nodes |
| Non spot-friendly | 13 (48%) | 13 pods that must stay on on-demand |
| Stateful pods | 13 | Same 13 non-spot pods: StatefulSet / PVC / DB / system |
| Mixed nodes | 2 | 2 nodes have both stateful and stateless pods co-located |

### What the 13 stateful pods likely include

Based on the tier detection rules:
- **kube-system pods** (coredns × 2, kube-proxy, aws-node): 4–6 pods → TIER_0, Factor 3 (system ns)
- **spot-optimizer pods** (spot-agent DaemonSet, spot-orchestrator): 1–2 pods → TIER_0, Factor 4 (DaemonSet / system ns)
- **Your application's stateful workloads** (node with PVC/StatefulSet): remaining pods

### What the 14 spot-friendly pods likely include

- REST API / web server deployments (multiple replicas)
- Worker processes (Celery / async workers)
- Other stateless microservices
- Frontend serving pods

### Recommended Actions (priority order)

#### Action 1 — Fix "2 Mixed" nodes IMMEDIATELY

The 2 Mixed nodes are the most impactful issue. They lock on-demand VMs from being rebalanced to spot.

1. Identify the mixed nodes:
   - In the UI, click "Mixed → review" to see which nodes are mixed
   - Or: `kubectl describe nodes | grep -A10 "Allocated resources"`
2. Add tolerations + affinity to all stateless Deployments (see Step 2 above)
3. Evict stateless pods from mixed nodes (they reschedule on spot automatically)
4. Wait 9 minutes for WorkloadInspector to re-classify the nodes

**Expected result**: Mixed → 0, spot-friendly % increases, and the rebalancer can now drain the on-demand node.

#### Action 2 — Verify spot node exists and is available

The rebalancer can only migrate to spot if a `stateless-spot` NodePool node exists:
```bash
kubectl get nodes -l workload=stateless
kubectl get nodeclaim -n karpenter
```

If no spot nodes exist, trigger the rebalancer manually or create a test pod with spot tolerations to force Karpenter to provision one.

#### Action 3 — Confirm Karpenter NodePools are correctly tainted

```bash
kubectl get nodepool stateless-spot -o yaml | grep -A5 taints
kubectl get nodepool stateful-od -o yaml | grep -A5 taints
```

If taints are missing, Karpenter will provision nodes that accept any pod — defeating the separation.

#### Action 4 — Monitor rebalancing actions

```bash
# Check active rebalancing actions (if DB access is available)
# Or monitor via backend logs
kubectl logs -n spot-optimizer deployment/spot-orchestrator | grep rebalancer
```

#### Action 5 — Review spot coverage target

After fixing the Mixed nodes, the expected optimal state is:

```
Total 27 pods
  ├── On-demand (stateful-od NodePool): ~13 stateful pods  → 48%
  └── Spot (stateless-spot NodePool):  ~14 spot pods       → 52%

Potential savings: (2 Mixed OD nodes → 1–2 spot nodes) × (OD price - spot price)
Typical spot discount: 60–80% vs on-demand
```

---

## Appendix A — Classification Flow Diagram (Full End-to-End)

```
Pod enters cluster (Scheduler phase)
        │
        ▼
WorkloadInspector scan (every 9 min)
  └─► Classifies the NODE it lands on:
      STATELESS_ELIGIBLE / STATEFUL_PROTECTED / DRAIN_UNSAFE / SYSTEM_PROTECTED
        │
        ▼
WorkloadClassifier scan (every 9 min)
  └─► Classifies the CONTROLLER (Deployment/SS/DS):
      TIER_0 / TIER_1 / TIER_2 / TIER_3 / TIER_4
        │
        ▼
cluster_service.py per-request (API call)
  └─► Combines both + pod spec for UI is_stateful:
      5 factors → True / False
        │
        ├─► False → spot_friendly_pods++ (counts toward 14)
        └─► True  → stateful_pods++ (counts toward 13)
        │
        ▼
Decision Engine (auto_rebalancer.py every 15s)
  └─► Finds STATELESS_ELIGIBLE nodes on OD instances
  └─► Confirms per-pod tier allows migration
  └─► Scores spot pools and selects best
        │
        ▼
Karpenter (NodePool patching)
  └─► Provisions spot replacement node
        │
        ▼
Drain OD node
  └─► Pods evicted → reschedule on spot node
  └─► PDB / DaemonSet / Anchor node protected throughout
        │
        ▼
Terminate OD EC2 instance → Cost savings

```

---

## Appendix B — Redis Cache Keys Reference

| Key | Populated by | TTL | Content |
|---|---|---|---|
| `spot:node_classification:{cluster_id}` | WorkloadInspector | 540 s | `{"node-1": "STATELESS_ELIGIBLE", ...}` |
| `spot:workload_tier:{cluster_id}:{ns}/{ctrl}` | WorkloadClassifier | 540 s | `{"tier": 4, "policy": "spot_eligible", "confidence": 0.9}` |
| `spot:anchor_node:{cluster_id}` | Decision Engine | 3600 s | `"ip-10-0-1-5.ap-south-1.compute.internal"` |

---

*Last updated: reflects current state of `cluster_service.py` (5-factor is_stateful), `workload_inspector.py` (4-level node classification), `workload_classifier.py` (TIER 0-4 engine), and `auto_rebalancer.py` (state-machine rebalancer).*
