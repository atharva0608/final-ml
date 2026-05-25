# Spot Optimizer — Full System Logic Guide

> **For:** Akhilesh  
> **Written by:** Atharva  
> **What this covers:** Kubernetes Rebalancing, Auto Right-Sizing, and Execution Engines — every step explained simply but technically.

---

## Table of Contents

1. [Big Picture — What Does This System Do?](#big-picture)
2. [System Architecture Overview](#architecture)
3. [Part 1 — Kubernetes Rebalancing](#part-1-kubernetes-rebalancing)
   - [What is Rebalancing?](#what-is-rebalancing)
   - [How Rebalancing is Triggered](#how-rebalancing-is-triggered)
   - [The Karpenter NodePool Update Flow](#karpenter-nodepool-flow)
   - [Rebalance Action States](#rebalance-action-states)
   - [Safety Gates Before Any Rebalance](#safety-gates)
   - [Cooldown System](#cooldown-system)
   - [Distributed Lock — One Drain at a Time](#distributed-lock)
4. [Part 2 — Auto Right-Sizing](#part-2-auto-right-sizing)
   - [What is Right-Sizing?](#what-is-right-sizing)
   - [Step-by-Step: How Right-Sizing Works](#right-sizing-steps)
   - [Statistical Analysis (P95/P99)](#statistical-analysis)
   - [Safety Buffers and Phase Awareness](#safety-buffers)
   - [JVM Detection](#jvm-detection)
   - [Confidence Scoring](#confidence-scoring)
   - [Cost Estimation Logic](#cost-estimation)
   - [Workload Tier Filtering](#workload-tier-filtering)
5. [Part 3 — Execution Engines](#part-3-execution-engines)
   - [Two Execution Engines Explained](#two-engines)
   - [Decision Engine (The Brain — 15 Steps)](#decision-engine)
   - [Execution Engine (The Muscle — 6 Steps)](#execution-engine)
   - [Why the Agent Exists (Private Subnet Problem)](#agent-problem)
   - [Agent Command Lifecycle](#agent-command-lifecycle)
   - [Failure Modes and Recovery](#failure-modes)
6. [Background Scheduler — The Heartbeat](#scheduler)
7. [Data Flow: End-to-End Walk-Through](#end-to-end)
8. [Redis Key Reference](#redis-keys)
9. [Common Error Scenarios and What They Mean](#error-scenarios)

---

## Big Picture — What Does This System Do? {#big-picture}

This system is a **Spot Instance Optimizer** for AWS EKS (Kubernetes) clusters.

**The problem it solves:**  
AWS Spot instances are very cheap (60-80% cheaper than On-Demand) but they can be interrupted anytime by AWS. You need to:
1. Pick the **safest + cheapest** spot instances using ML.
2. **Move workloads** from expensive/risky instances to cheaper/safer ones.
3. **Right-size** your pods (containers) so they don't request too much or too little CPU/RAM.
4. Do all of this **automatically, without downtime**.

**The core loop:**
```
Collect metrics → ML ranks best pools → Decision Engine approves →
Execution Engine runs → Kubernetes changes applied → Verify
```

---

## System Architecture Overview {#architecture}

```
┌─────────────────────────────────────────────────────────┐
│                    BACKEND SERVER                        │
│                                                          │
│  ┌─────────────┐  ┌──────────────┐  ┌───────────────┐  │
│  │  FastAPI     │  │ Celery Beat  │  │ Celery Worker │  │
│  │  (API layer) │  │ (scheduler)  │  │ (task runner) │  │
│  └─────────────┘  └──────────────┘  └───────────────┘  │
│           │               │                  │           │
│  ┌────────▼───────────────▼──────────────────▼────────┐ │
│  │            PostgreSQL (source of truth)             │ │
│  └────────────────────────┬────────────────────────────┘ │
│                           │                              │
│  ┌────────────────────────▼────────────────────────────┐ │
│  │       Redis (fast cache, locks, pub/sub)            │ │
│  └──────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────┘
                            │
                    WebSocket / HTTP
                            │
┌─────────────────────────────────────────────────────────┐
│              AWS EKS CLUSTER (Private VPC)               │
│                                                          │
│  ┌─────────────────┐    ┌──────────────────────────┐   │
│  │  Agent DaemonSet │    │  Karpenter Controller    │   │
│  │  (pod per node)  │    │  (node provisioner)      │   │
│  └─────────────────┘    └──────────────────────────┘   │
│          │                          │                    │
│  ┌───────▼──────────────────────────▼──────────────────┐ │
│  │           Kubernetes Nodes (EC2 Instances)           │ │
│  └──────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────┘
```

**Key components:**
- **Backend** — FastAPI server + Celery workers running on a separate server (NOT inside Kubernetes)
- **PostgreSQL** — stores all persistent data (clusters, actions, metrics, manifests)
- **Redis** — stores fast-access data (locks, rankings, cooldowns, WIE cache)
- **Agent** — runs INSIDE the Kubernetes cluster as a DaemonSet pod, executes actual K8s operations
- **Karpenter** — AWS-native node autoscaler that provisions EC2 instances

---

## Part 1 — Kubernetes Rebalancing {#part-1-kubernetes-rebalancing}

### What is Rebalancing? {#what-is-rebalancing}

Rebalancing means **moving your workloads from one type of EC2 instance (node) to another**, without any downtime.

**Example scenario:**
- You are running pods on `m5.large` spot instances in `ap-south-1a`
- ML model finds that `c5.large` in `ap-south-1b` is cheaper AND safer (lower interruption risk)
- Rebalancing moves your pods from the `m5.large` node to a `c5.large` node

**Why this needs to be done carefully:**
- If you just kill the old node, pods have nowhere to go → your app goes down
- You need to **pre-warm a replacement node** before draining the old one
- PodDisruptionBudgets (PDBs) limit how many pods can be down at once
- Some pods are stateful (databases) — they should never be moved

---

### How Rebalancing is Triggered {#how-rebalancing-is-triggered}

**Trigger 1: Scheduled Auto-Rebalancer (every 15 minutes)**
```
Celery Beat → auto_rebalancer_task → Decision Engine → Execution Engine
```

**Trigger 2: Spot Interruption Notice (ITN)**
- AWS sends a 2-minute warning before killing a spot instance
- System receives this via EventBridge → emergency mode → bypasses cooldowns
- Must act within 120 seconds

**Trigger 3: Manual API call**
- User clicks "Rebalance" in the UI
- Goes through same Decision Engine + Execution Engine flow

**The auto-rebalancer task checks each cluster:**
1. Is the cluster active?
2. Is there already a rebalance in progress? (check distributed lock)
3. Run Decision Engine → get recommendation
4. If approved → run Execution Engine

---

### The Karpenter NodePool Update Flow {#karpenter-nodepool-flow}

**What is a NodePool?**  
A Karpenter NodePool is a YAML object in Kubernetes that says: "When you need new nodes, use THESE instance types in THESE availability zones."

**How we update it:**

```
Step 1: ML model scores all spot pools
        → Output: top 10 safest/cheapest instance types

Step 2: KarpenterService.sync_ml_rankings_to_nodepool()
        → Calls Kubernetes API: PATCH /apis/karpenter.sh/v1/nodepools/default
        → Sets: instance_types: [c5.large, m5.large, ...], capacity_type: spot, azs: [ap-south-1b]

Step 3: Karpenter controller sees the updated NodePool
        → When new pods need scheduling → provisions from the approved list only

Step 4: On-demand fallback (if no safe spot pools exist)
        → switch_to_ondemand() is called
        → Sets capacity_type: on-demand
        → Redis key: spot:ondemand_fallback:{cluster_id} with 12-hour TTL
        → After 12 hours → revert_to_spot() is called automatically
```

**The NodePool YAML that gets applied looks like this:**
```yaml
apiVersion: karpenter.sh/v1
kind: NodePool
metadata:
  name: default
  labels:
    managed-by: spot-optimizer
spec:
  template:
    spec:
      requirements:
        - key: karpenter.sh/capacity-type
          operator: In
          values: ["spot"]
        - key: node.kubernetes.io/instance-type
          operator: In
          values: ["c5.large", "m5.large", "c5.xlarge"]  # ← ML approved list
        - key: topology.kubernetes.io/zone
          operator: In
          values: ["ap-south-1b", "ap-south-1a"]
  disruption:
    consolidationPolicy: WhenEmpty
    consolidateAfter: Never
```

**Rollback logic:**
- Before patching, `_get_nodepool_state()` saves the current NodePool spec
- If the patch fails → `_restore_nodepool_state()` restores the old spec
- Max 2 retry attempts with delays of [5s, 15s]

---

### Rebalance Action States {#rebalance-action-states}

Each rebalance action goes through these states in the `rebalance_actions` database table:

```
PENDING → APPROVED → waiting_agent → CORDON_COMPLETE → DRAIN_COMPLETE → PATCH_COMPLETE → COMPLETED
                                                                                ↓
                                                                              FAILED (any step)
```

**State meanings:**
- `PENDING` — created, waiting for Decision Engine approval
- `APPROVED` — Decision Engine said go ahead
- `waiting_agent` — commands sent to agent, waiting for it to execute
- `CORDON_COMPLETE` — old node is now marked unschedulable (no new pods can land)
- `DRAIN_COMPLETE` — all pods evicted from old node
- `PATCH_COMPLETE` — Karpenter NodePool updated to target pool
- `COMPLETED` — full cycle done
- `FAILED` — something went wrong (see logs for which step failed)

> ⚠️ **Common issue:** If a rebalance action gets stuck in `waiting_agent`, it means the agent is disconnected or crashed. After 30 minutes, the backend can retry.

---

### Safety Gates Before Any Rebalance {#safety-gates}

Before any rebalance starts, `check_safety_gates()` verifies:

```python
# Gate 1: Is there already a rebalance in progress for this cluster?
lock_key = f"lock:node_action:{cluster_id}"
lock_acquired = redis.set(lock_key, "1", nx=True, ex=180)  # nx=True means "only set if not exists"
# If lock already exists → SKIP (another rebalance is running)

# Gate 2: Is the substitute node ready?
# The warm spare must be in READY state before draining the source node
# If substitute is PREWARMING or IDLE → DEFER

# Gate 3: Is the target instance in cooldown?
# Each instance has a 24-hour cooldown after being rebalanced
# Prevents re-targeting the same instance repeatedly

# Gate 4: Is the cluster in stabilization lock?
# After any cluster-wide event → 30-minute cooldown before next action
```

All 4 gates must pass. If any fails → action is deferred, logged, and retried next cycle.

---

### Cooldown System {#cooldown-system}

Cooldowns prevent too many changes too quickly. They are stored in Redis with TTLs (time-to-live).

| Cooldown Type | Redis Key | Duration | Purpose |
|---|---|---|---|
| Cluster cooldown | `spot:cooldown:cluster:{cluster_id}` | 30 minutes | Prevent two rebalances too close together |
| Pool cooldown | `spot:cooldown:pool:{instance_type}:{az}` | 30 minutes | Don't reuse a pool that was just used |
| Instance cooldown | `spot:cooldown:instance:{instance_id}` | 24 hours | Don't re-target the same EC2 instance |
| Emergency bypass | (ITN flag) | — | If spot interruption notice → skip all cooldowns |

**How it works in code:**
```python
# CooldownController.can_switch(cluster_id)
can_switch = not redis.exists(f"spot:cooldown:cluster:{cluster_id}")
remaining = redis.ttl(f"spot:cooldown:cluster:{cluster_id}")
# Returns (True, 0) if ok to proceed
# Returns (False, 1247) if 1247 seconds remaining in cooldown
```

---

### Distributed Lock — One Drain at a Time {#distributed-lock}

**Why we need this:**  
If two Celery workers both try to drain nodes on the same cluster simultaneously, pods might have nowhere to go → downtime.

**How it works:**
```python
lock_key = f"lock:node_action:{cluster_id}"
lock_acquired = redis.set(lock_key, "1", nx=True, ex=180)
# nx=True: "only set if key does NOT exist" → atomic compare-and-set
# ex=180:  key auto-expires in 180 seconds (safety net if backend crashes)

if not lock_acquired:
    return {"queued": False, "deferred_reason": "Lock held by concurrent operation"}

try:
    # ... do the rebalance work ...
    pass
finally:
    redis.delete(lock_key)  # ALWAYS release the lock
```

**The 180-second TTL is a safety net:** if the backend crashes mid-execution, the lock auto-expires so future cycles aren't stuck forever.

---

## Part 2 — Auto Right-Sizing {#part-2-auto-right-sizing}

### What is Right-Sizing? {#what-is-right-sizing}

When you deploy a container (pod) in Kubernetes, you set resource "requests":
```yaml
resources:
  requests:
    cpu: "500m"      # 500 millicores = 0.5 CPU core
    memory: "512Mi"  # 512 megabytes RAM
```

**The problem:** Developers almost always set these values **too high** (to be safe), wasting money.

**Right-sizing analyzes real usage** and recommends:
- "Your pod actually uses 150m CPU on average. Set it to 200m (with safety buffer)."
- "You're wasting 300Mi of RAM per pod × 20 replicas = 6000Mi per month."

**File:** [`backend/services/rightsizing_service.py`](file:///Users/atharvapudale/Desktop/backend-ecc/Atharva%20Repo/github/final-ml/backend/services/rightsizing_service.py)

---

### Step-by-Step: How Right-Sizing Works {#right-sizing-steps}

```
Step 0: Check metric freshness
        ↓ Latest metric must be < 5 minutes old. Otherwise skip.

Step 1: Check cluster cooldown
        ↓ Same cooldown check as rebalancing (CooldownController)

Step 2: Check node classification
        ↓ Only analyze STATELESS_ELIGIBLE nodes
        ↓ Skip if nodes are STATEFUL (databases, etc.)

Step 3: Get all controllers (Deployments, StatefulSets, etc.)
        ↓ Query pod_metrics table: SELECT DISTINCT namespace, controller_kind, controller_name

Step 4: For EACH controller → analyze metrics
        ↓ Fetch all pod metrics from last 7 days (168 hours)
        ↓ Minimum 100 data points required

Step 5: Calculate statistics
        ↓ CPU: avg, P50, P95, P99 in millicores
        ↓ Memory: avg, P50, P95, P99 in bytes

Step 6: Calculate recommended size
        ↓ recommended_cpu = P95 × (1 + safety_buffer%)
        ↓ Also check: recommended_cpu must be ≥ P99 × 1.3

Step 7: Detect JVM workloads
        ↓ Uses name signals: 'java', 'spring', 'jvm', etc.
        ↓ JVM needs higher CPU floor: P99 × 1.6

Step 8: Check WIE confidence gate
        ↓ Skip DRAFT workloads (not enough observation data)

Step 9: Estimate cost savings
        ↓ current_cost = current_request × replica_count × $rate/hour × 730h
        ↓ recommended_cost = recommended_size × replica_count × $rate/hour × 730h
        ↓ savings = current_cost - recommended_cost

Step 10: Assign recommendation action
         ↓ REDUCE: if avg_usage < 50% of current request (oversized)
         ↓ INCREASE: if P99 > 95% of current request (undersized, risk of throttling)
         ↓ OBSERVE: if burst_ratio is too high (risky to reduce)
         ↓ NO_CHANGE: everything looks fine

Step 11: Return recommendation object
```

---

### Statistical Analysis (P95/P99) {#statistical-analysis}

We collect CPU and memory usage every ~5 minutes from each pod.

**What P95 means:**  
"95% of the time, this pod uses LESS than this amount of CPU."

**Example with 100 data points (CPU in millicores):**
```
[10, 12, 15, 20, 25, ... 150, 180, 200, 350, 500]
 ↑ (sorted from lowest to highest)

P50 (median) = 80m   ← typical usage
P95 = 200m           ← 95% of the time below this
P99 = 400m           ← 99% of the time below this (covers spikes)
max = 500m           ← worst ever spike
```

**Why P95 not max?**  
The max value might be a one-time spike (e.g., startup, one bad request). Sizing for max wastes money. P95 + safety buffer covers normal operations + reasonable spikes.

**Code:**
```python
def _percentile(self, sorted_values, percentile):
    index = int((percentile / 100) * (len(sorted_values) - 1))
    return sorted_values[index]
```

---

### Safety Buffers and Phase Awareness {#safety-buffers}

**Default safety buffer: 20%**  
`recommended_cpu = P95 × 1.20`

**Phase-aware buffer (trust system):**
- Phase 0 (new cluster, not yet trusted): **30% buffer** (very conservative)
- Phase 1 (partially trusted): **25% buffer**
- Phase 2 (fully trusted): **20% buffer** (default)

**Volatile market buffer:**  
If AWS is having a volatile period (many interruptions), buffer increases to **35% minimum**.
```python
is_volatile = redis.get(f"spot:volatility_regime:{region}")
if is_volatile:
    safety_buffer = max(safety_buffer, 35)
```

**P99 floor check:**  
Even after applying the buffer, the recommendation must be higher than `P99 × 1.3`. This prevents recommending a size that can't handle bursts.
```python
p99_cpu_floor = int(cpu_stats['p99'] * 1.3)
recommended_cpu = max(recommended_cpu, p99_cpu_floor)
```

---

### JVM Detection {#jvm-detection}

Java apps (Spring Boot, Tomcat, Quarkus) behave differently from other workloads:
- They need large memory upfront (heap allocation)
- They have bursty CPU patterns at startup

**How JVM is detected:**
```python
# Method 1: Name-based detection
jvm_signals = ['java', 'spring', 'jvm', 'tomcat', 'quarkus', 'micronaut', 'openjdk']
is_jvm = any(signal in controller_name.lower() for signal in jvm_signals)

# Method 2: Memory:CPU ratio (JVM apps are memory-heavy)
mem_mb = current_memory_request_bytes / (1024 * 1024)
cpu_cores = current_cpu_request / 1000.0
if mem_mb / cpu_cores > 4:   # if memory is >4x the CPU cores
    is_jvm = True

# Method 3: Memory growth pattern (JVM heap grows over time)
mem_growth = memory_stats['p99'] / memory_stats['avg']
if mem_growth > 1.8:   # P99 is 80% higher than average
    is_jvm = True
```

**If JVM detected → higher CPU floor:**
```python
jvm_cpu_floor = int(cpu_stats['p99'] * 1.6)  # 60% above P99
recommended_cpu = max(recommended_cpu, jvm_cpu_floor)
```

**Burst detection → OBSERVE mode:**
```python
burst_ratio = cpu_stats['p99'] / cpu_stats['avg']
# JVM threshold: 3.0x  (JVM has naturally higher bursts)
# Normal threshold: 5.0x
if burst_ratio > threshold and recommendation_action == "REDUCE":
    recommendation_action = "OBSERVE"  # too risky to reduce
    savings_monthly = 0.0
```

---

### Confidence Scoring {#confidence-scoring}

Recommendations need enough data to be reliable.

```python
expected_points = window_hours * 12  # 12 data points per hour (every 5 min)
coverage_ratio = data_points / expected_points

if data_points >= min_data_points * 5 and coverage_ratio >= 0.5:
    confidence = "HIGH"
elif data_points >= min_data_points and coverage_ratio >= 0.2:
    confidence = "MEDIUM"
else:
    confidence = "LOW"  # → SKIP: don't generate recommendation
```

**For a 7-day (168h) window:**
- Expected: `168 × 12 = 2016` data points
- HIGH confidence: `≥500 points AND ≥50% coverage`
- MEDIUM: `≥100 points AND ≥20% coverage`
- LOW: skip entirely (not enough data to be reliable)

**WIE confidence gate:**
```python
# Workload Intelligence Engine marks workloads as DRAFT until observed enough
wie_key = f"spot:wie:classification:{cluster_id}:{namespace}/{controller_name}"
wie = json.loads(redis.get(wie_key))
if wie.get("confidence_state") == "DRAFT":
    continue  # skip — not enough WIE observation data
```

---

### Cost Estimation Logic {#cost-estimation}

Cost is estimated based on CPU:memory ratio to pick the right instance family:

```python
ratio = cpu_cores / memory_gb

if ratio >= 0.4:      # High CPU → compute-optimized
    family = "c5"     # $0.042/core/hr, $0.005/GB/hr
elif ratio >= 0.2:    # Balanced → general purpose
    family = "m5"     # $0.048/core/hr, $0.006/GB/hr
else:                 # High memory → memory-optimized
    family = "r5"     # $0.063/core/hr, $0.008/GB/hr

cpu_cost_per_hour = cpu_cores × cpu_rate
mem_cost_per_hour = memory_gb × mem_rate
total_per_hour = (cpu_cost + mem_cost) × replica_count

monthly_cost = total_per_hour × 730  # 730 hours per month
```

Redis pricing cache is checked first (updated by a separate pricing worker). Falls back to hardcoded rates if Redis miss.

---

### Workload Tier Filtering {#workload-tier-filtering}

Before creating proposals, workloads are filtered by tier:

| Tier | Type | Right-Sizing Allowed? |
|---|---|---|
| TIER_0 | DaemonSets, system workloads | **NEVER** — cannot migrate |
| TIER_1 | Stateful databases (ANCHORED_MANUAL) | Only if `auto_stateful_rightsizing_enabled=True` |
| TIER_2 | Stateful-aware workloads | Yes, with extra safety |
| TIER_3 | Normal stateless workloads | Yes |
| TIER_4 | Permissive (default) | Yes |

```python
tier_raw = redis.get(f"spot:workload_tier:{cluster_id}:{namespace}/{controller_name}")
tier = json.loads(tier_raw).get("tier", 4)  # default TIER_4 if key missing

if tier == 0:
    continue  # NEVER rightsize DaemonSets
if tier == 1 and not include_stateful:
    continue  # skip stateful unless setting enabled
```

---

## Part 3 — Execution Engines {#part-3-execution-engines}

### Two Execution Engines Explained {#two-engines}

There are **two different execution engines** in this codebase — don't confuse them:

| | Decision Engine | Execution Engine |
|---|---|---|
| **Role** | The BRAIN — decides WHAT to do | The MUSCLE — does the actual work |
| **File (ML model)** | `ml_model/decision_engine/pipeline.py` | `ml_model/execution_engine/pipeline.py` |
| **File (backend)** | `backend/services/decision_engine_service.py` | `backend/services/execution_engine.py` |
| **Input** | Current cluster state + candidate pools | Approved recommendation from Decision Engine |
| **Output** | "Approved: switch to c5.large in ap-south-1b" | K8s operations (cordon, drain, patch NodePool) |
| **When it runs** | Before any cluster change | After Decision Engine approves |

---

### Decision Engine (The Brain — 15 Steps) {#decision-engine}

**File:** [`ml_model/decision_engine/pipeline.py`](file:///Users/atharvapudale/Desktop/backend-ecc/Atharva%20Repo/github/final-ml/ml_model/decision_engine/pipeline.py)

The Decision Engine runs 15 validation steps. Any step can **BLOCK** the action (return `approved: False`). Only if ALL steps pass → action is approved.

**Step 1 — Cluster Cooldown Check**
```
Is the cluster in a post-action cooldown period? (30 minutes)
→ If yes → BLOCK: "Cluster cooldown active (1247s remaining)"
→ Emergency mode (ITN) → BYPASS this check
```

**Step 1b — Pricing Freshness Check**
```
Is our AWS pricing data fresh? (must be < 15 minutes old)
→ If stale → BLOCK: "Pricing data stale (18 min old, max 15 min)"
→ Redis key: pricing:last_updated:{region}
→ Fail-open: if key missing, proceed anyway
```

**Step 2 — Pool Cooldown Check (per candidate)**
```
For each candidate pool: was this pool recently used? (30-minute cooldown)
→ Remove cooled-down pools from candidate list
→ If ALL candidates are cooled → BLOCK
```

**Step 2b — Node Classification Fetch**
```
Get WorkloadInspector's cached classification from Redis
→ If no classification found → BLOCK: "WorkloadInspector scan required"
→ Classification maps each node to: STATELESS_ELIGIBLE, STATEFUL_PROTECTED, etc.
```

**Step 2c — Filter Stateless-Eligible Nodes**
```
Only nodes classified as STATELESS_ELIGIBLE can be drained
→ If none found → BLOCK: "No STATELESS_ELIGIBLE nodes found"
```

**Step 3 — Model Version Validation (soft)**
```
Check if candidates were scored by the current ML model (regressor_6.onnx)
→ If wrong version → LOG WARNING but don't block
```

**Step 4 — Load Optimization Mode**
```
What mode is this cluster in?
→ COST_FIRST: risk_ceiling=25%, delta_threshold=3%
→ BALANCED: risk_ceiling=20%, delta_threshold=5%   ← default
→ NO_DOWNTIME_FIRST: risk_ceiling=10%, delta_threshold=8%
→ Reads from Redis: spot:cluster_mode:{cluster_id}
```

**Step 5 — Load Global Rankings**
```
Get ML-scored global pool rankings from Redis
→ Redis key: spot:global_rankings:{region}
→ If missing → BLOCK: "Intelligence Layer required"
→ Rankings are updated by a separate Intelligence Layer worker
```

**Step 6 — Three-Layer Risk Ceiling Filter**
```
Layer 1: Optimization mode ceiling (25%/20%/10%)
Layer 2: If volatile market → subtract 5% from ceiling
Layer 3: If cluster is in early trust phase → apply stricter ceiling

effective_ceiling = min(mode_ceiling, trust_ceiling) - volatility_adjustment

→ Remove all candidates where risk_probability > effective_ceiling
→ If ALL candidates exceed ceiling → BLOCK
```

**Step 7 — Capacity Freshness Staleness Penalty**
```
If capacity data is old (>80 minutes) → reduce predicted_savings by 5%
→ Stale data means we're less sure the pool is actually available
```

**Step 9 — Re-Score with Full Economic EV Model**
```
EV = Expected Value = probability-weighted economic outcome

EV formula:
  ev = savings × (1 - risk) × (1 - volatility_penalty) × (1 - capacity_failure_rate)

→ capacity_failure_rate: from DryRun results stored in Redis
→ Remove all candidates with EV ≤ 0 (costs more than saves)
```

**Step 10 — Score Current Pool**
```
What is the EV of staying on the current pool?
current_ev = current_savings × (1 - current_risk)
→ Needed to compare: is moving worth it?
```

**Step 11 — Template + Karpenter Filters**
```
Apply user-defined node template constraints:
→ Instance family whitelist (e.g., only c5, m5 families)
→ Blacklisted pools (manually excluded)
→ Architecture filter (amd64 vs arm64)
→ Karpenter NodePool requirements
```

**Step 12 — Diversity Constraints**
```
Don't over-concentrate workloads:
→ max_family_ratio = 40%: no more than 40% of nodes from same instance family
→ max_az_ratio = 50%: no more than 50% of nodes in same AZ
→ If candidate would violate limits → skip it
→ If ALL candidates violate → BLOCK
```

**Step 13 — Delta Threshold Check**
```
Is the improvement worth the migration disruption?
delta = best_candidate_ev - current_pool_ev

→ COST_FIRST threshold: 3% improvement required
→ BALANCED threshold: 5% improvement required
→ NO_DOWNTIME_FIRST threshold: 8% improvement required

If delta < threshold → BLOCK: "Delta 0.02 below threshold 0.05"
```

**Step 14 — APPROVE**
```
All 13 checks passed!
→ Return approved=True with recommendation dict:
  {
    "approved": True,
    "recommendation": {
      "pool": {instance_type: "c5.large", az: "ap-south-1b"},
      "ev_improvement": 0.087,
      "optimization_mode": "BALANCED"
    },
    "delta": 0.087,
    "duration_ms": 142
  }
```

---

### Execution Engine (The Muscle — 6 Steps) {#execution-engine}

**File:** [`ml_model/execution_engine/pipeline.py`](file:///Users/atharvapudale/Desktop/backend-ecc/Atharva%20Repo/github/final-ml/ml_model/execution_engine/pipeline.py)

Once the Decision Engine approves, the Execution Engine runs these 6 steps:

---

**Step 1 — Action Queue (Backend: Celery)**

Creates 3 `AgentAction` records in PostgreSQL:

```python
actions = [
    AgentAction(action_type="CORDON_NODE",              # Step 3: mark node unschedulable
                payload={"instance_id": "i-0abc123", "node_name": "ip-10-0-1-50.ec2.internal"}),
    AgentAction(action_type="DRAIN_NODE",               # Step 4: evict all pods
                payload={"instance_id": "i-0abc123", "grace_period": 30}),
    AgentAction(action_type="PATCH_KARPENTER_NODEPOOL", # Step 5: update NodePool to target
                payload={"instance_types": ["c5.large"], "azs": ["ap-south-1b"]}),
]
db.add_all(actions)
db.commit()
```

Also sets 24-hour instance cooldown in Redis so this instance won't be targeted again today.

---

**Step 2 — Command Dispatcher (Backend: FastAPI)**

Sends the queued actions to the agent:

```
Primary path: WebSocket push (real-time, <1 second)
Fallback path: Agent polls GET /api/v1/agents/actions/pending every 10 seconds
```

The agent is authenticated with an API key stored in the Kubernetes cluster as a Secret.

---

**Step 3 — K8s Actuator: CORDON (Agent: in-cluster DaemonSet)**

```
Agent receives: CORDON_NODE command for instance i-0abc123

Step 3a: Resolve K8s node name
  → Scan all nodes: kubectl get nodes -o json
  → Find node where spec.providerID contains "i-0abc123"
  → node_name = "ip-10-0-1-50.ec2.internal"

Step 3b: Patch the node
  → PATCH /api/v1/nodes/ip-10-0-1-50.ec2.internal
  → Body: {"spec": {"unschedulable": true}}
  → Effect: No new pods can be scheduled on this node

Step 3c: Report result to backend
  → POST /api/v1/agents/actions/{action_id}/result
  → Backend updates AgentAction status to COMPLETED
  → Backend publishes SSE event to UI
```

---

**Step 4 — K8s Actuator: DRAIN (Agent: in-cluster DaemonSet)**

```
Agent receives: DRAIN_NODE command

Step 4a: List all pods on the node
  → GET /api/v1/pods?fieldSelector=spec.nodeName=ip-10-0-1-50.ec2.internal
  → Filter out: DaemonSet pods (kube-proxy, fluent-bit, etc.)
  → Filter out: Mirror pods (static pods)
  → Remaining: all application pods that need to move

Step 4b: PDB check
  → For each pod: check if evicting it would violate PodDisruptionBudget
  → PDB says: "at least N replicas must be running at all times"
  → If eviction would violate PDB → wait until PDB allows it

Step 4c: Evict each pod (parallel)
  → POST /api/v1/namespaces/{ns}/pods/{pod_name}/eviction
  → Kubernetes sends SIGTERM to pod → graceful shutdown (up to 30 seconds)
  → Pod terminates → Kubernetes reschedules it on a different node

Step 4d: Wait for all evictions to complete (~30-35 seconds total)

Step 4e: Report DRAIN result → Backend updates DB
```

**What happens to the evicted pods?**  
They are rescheduled on the **warm spare (substitute) node** which was pre-provisioned and waiting.

---

**Step 5 — Substitute Manager: Warm Spare Becomes Active (Backend + Redis)**

```
Concurrent with Step 3/4 (runs in parallel):

BEFORE drain:
  → Substitute node is in READY state (pre-provisioned, sitting idle, 24×7)
  → It's already running and joined the cluster

DURING drain:
  → Evicted pods see the substitute node as available
  → Kubernetes scheduler places them on the warm spare immediately
  → Warm spare: READY → ACTIVE (absorbs all drained pods)
  → TTL: 6 hours (after which a new warm spare is prewarmed)

AFTER drain:
  → SubstituteManager starts prewarming the NEXT warm spare
  → Maintains continuous availability: always one warm spare ready
```

**Why this gives zero downtime:**  
The warm spare is already running before drain starts. Pods land on it immediately after eviction. There is no provisioning delay.

---

**Step 6 — Result Reporter (Agent → Backend)**

```
Agent POSTs to: POST /api/v1/agents/actions/{action_id}/result

Backend does:
1. Update AgentAction DB record: status = COMPLETED
2. Update RebalancingAction DB record: new status
3. Publish SSE event to UI (real-time update in browser)
4. If terminate_after_drain=True:
   → Call AWS EC2 TerminateInstances API on the old instance
   → Why: forces pods into PENDING state on the new Karpenter pool
   → Karpenter sees PENDING pods → provisions c5.large spot node
   → Pods move from warm spare to the new spot node (their permanent home)
   → Warm spare can be released (ACTIVE → RELEASING → IDLE)
```

---

### Why the Agent Exists (Private Subnet Problem) {#agent-problem}

```
The Problem:
  EKS control plane endpoint is in a PRIVATE subnet inside AWS VPC.
  Our backend server is outside that VPC.
  The backend CANNOT directly call the Kubernetes API!

The Solution: Agent as a bridge
  ┌─────────────────┐    commands via WS/HTTP    ┌──────────────────┐
  │ Backend Server  │ ─────────────────────────► │  Agent DaemonSet │
  │ (outside VPC)   │ ◄───────────────────────── │  (inside cluster)│
  │                 │    results via HTTP          │  has in-cluster  │
  └─────────────────┘                             │  kubeconfig      │
                                                  └──────────────────┘
```

The agent runs as a Kubernetes DaemonSet (one pod on every node). It has a ServiceAccount with in-cluster credentials that allow it to call the Kubernetes API from inside.

**Backend writes commands to PostgreSQL → Agent reads them → Executes K8s operations → Reports back.**

---

### Agent Command Lifecycle {#agent-command-lifecycle}

```
Backend creates AgentAction in DB:
  status = PENDING

Agent receives command (WebSocket push or HTTP poll):
  status = PICKED_UP

Agent starts executing:
  status = IN_PROGRESS

Agent completes/fails:
  status = COMPLETED or FAILED

Backend processes result:
  Updates RebalancingAction status
  Sends next command (CORDON → DRAIN → PATCH, in order)
```

**If agent disconnects mid-execution:**
- Actions remain in `PICKED_UP` state
- After 30 minutes → backend detects timeout → can retry
- WebSocket reconnect triggers re-push of pending actions

---

### Failure Modes and Recovery {#failure-modes}

**CORDON fails:**
```
→ DRAIN is NOT sent (pointless without cordon)
→ Distributed lock released
→ RebalancingAction marked FAILED
→ Next auto-rebalancer cycle will try again (after cooldown)
```

**DRAIN fails (PDB blocking, unmanaged pods):**
```
→ PATCH_NODEPOOL is NOT sent (node still has pods)
→ Un-cordon the node: PATCH /api/v1/nodes/{name} → spec.unschedulable=false
→ Distributed lock released
→ Increment circuit breaker failure counter
```

**PATCH_NODEPOOL fails:**
```
→ Log error, release lock
→ Karpenter won't be directed to target pool
→ BUT node is already drained → pods are on warm spare (zero downtime preserved)
→ Next cycle will retry the NodePool patch
```

**Circuit Breaker (Karpenter):**
```
If >10 execution failures in 10 minutes for a cluster:
  → Circuit breaker trips
  → All spot operations disabled for 30 minutes
  → Redis key: spot:cluster_circuit_breaker:{cluster_id} with 1800s TTL
  → After 30 min → auto-resets → normal operation resumes
```

**Execution capacity failure for a specific pool:**
```
1st failure: Redis key spot:execution_fail:{pool_id} = 1, TTL=1h
2nd failure: fail_count = 2 → escalate to 6-hour blacklist
Blacklist: spot:blacklist:{pool_id} in Redis with 6h TTL
After 6h: pool is eligible again
```

---

## Background Scheduler — The Heartbeat {#scheduler}

**File:** [`backend/scheduler.py`](file:///Users/atharvapudale/Desktop/backend-ecc/Atharva%20Repo/github/final-ml/backend/scheduler.py)

The APScheduler runs in the FastAPI background. It fires these jobs:

| Job | Interval | What It Does |
|---|---|---|
| `job_refresh_active_count` | Every 5 min | Refresh cluster count for DryRun budgets |
| `job_reconcile_substitutes` | Every 5 min | Fix stuck warm spare nodes |
| `job_scan_clusters` | Every 10 min | WorkloadInspector classification + WIE slow loop |
| `job_check_cost_drift` | Every 30 min | Alert if costs deviate from expected |
| `job_detect_volatility` | Every 1 hour | Check if region is in volatile spot market |
| `job_cleanup_blacklist` | Daily at 2 AM | Clean expired blacklists and Redis keys |
| `job_wie_fast_loop` | Every 2 min | Update pod state cache (restarts, ready counts) |
| `job_karpenter_metrics_collection` | Every 2 min | Collect Karpenter provision success rates |
| `job_run_placement_cycle` | Every 10 min | Run placement advisor for each cluster |
| `job_reconcile_nodepool_classes` | Every 10 min | Reconcile Karpenter NodePool class templates |

**First run is delayed by 60 seconds** to allow the FastAPI server to start serving HTTP before consuming thread pool resources.

**WIE Fast Loop (every 2 min):**
```
Updates pod state in Redis:
→ Which pod is on which node?
→ Pod phase (Running/Pending/Failed)
→ Restart count
→ Ready replica count
→ AZ placement

Redis key: spot:wie:pod_state:{cluster_id}:{pod_name}
TTL: auto-expires so stale data doesn't accumulate
```

---

## Data Flow: End-to-End Walk-Through {#end-to-end}

Here is what happens from start to finish when the system decides to rebalance a node:

```
t=-10min  WIE fast loop runs → updates all pod states in Redis
t=-10min  Karpenter metrics collected → stored in Redis

t=0       Celery Beat fires auto_rebalancer_task
t=0       Task fetches cluster list from PostgreSQL

t=0+100ms Decision Engine runs 15-step pipeline:
           → Cooldown check: pass
           → Pricing fresh: pass (8 min old)
           → Pool cooldowns: 3 of 5 candidates pass
           → Node classification: STATELESS_ELIGIBLE found
           → Risk ceiling: 2 candidates pass (risk < 20%)
           → EV scoring: best candidate EV = 0.72
           → Current pool EV = 0.63
           → Delta = 0.09 > threshold 0.05 ✓
           → APPROVED: switch to c5.large in ap-south-1b

t=0+150ms Execution Engine (backend side):
           → Safety gates: all pass
           → Acquire distributed lock: success
           → Create 3 AgentActions in PostgreSQL
           → Set 24h instance cooldown in Redis
           → Return: queued=True, actions=[uuid1, uuid2, uuid3]

t=1s      WebSocket push to agent: CORDON_NODE {instance_id: i-0abc}

t=1s      Agent executes CORDON:
           → Resolves node name from instance ID
           → PATCH node → unschedulable=True
           → Reports result

t=2s      Backend: marks CORDON COMPLETED, sends DRAIN_NODE command

t=3s      Agent executes DRAIN:
           → Lists 8 pods on node
           → Checks PDB for each: all safe to evict
           → Evicts all 8 pods in parallel (30s grace period)

t=35s     All pods evicted:
           → Pods land on warm spare immediately (zero downtime)
           → Warm spare: READY → ACTIVE

t=36s     Agent receives PATCH_KARPENTER_NODEPOOL
t=36s     Agent patches NodePool: c5.large, ap-south-1b, spot
t=37s     Agent reports success

t=37s     Backend:
           → Updates all 3 AgentActions → COMPLETED
           → Updates RebalancingAction → COMPLETED
           → Publishes SSE to UI
           → Calls EC2 TerminateInstances (old instance)

t=38s     Old EC2 instance terminated
           → Pods become PENDING (warm spare is temp)
           → Karpenter sees PENDING pods

t=90s     Karpenter provisions c5.large spot node in ap-south-1b
t=90s     New node joins cluster → pods move to it (permanent home)
t=90s     Warm spare: ACTIVE → RELEASING → IDLE

t=92s     SubstituteManager starts prewarming next warm spare
           → IDLE → PREWARMING → READY (for next rebalance)

t=6h      Warm spare auto-released (6h TTL)
           → New warm spare already ready (started at t=92s)
```

---

## Redis Key Reference {#redis-keys}

| Redis Key | Purpose | TTL |
|---|---|---|
| `spot:cooldown:cluster:{cluster_id}` | Cluster-level cooldown | 30 min |
| `spot:cooldown:pool:{type}:{az}` | Pool-level cooldown | 30 min |
| `spot:cooldown:instance:{instance_id}` | Instance 24h cooldown | 24 hours |
| `lock:node_action:{cluster_id}` | Distributed drain lock | 180 seconds |
| `spot:global_rankings:{region}` | ML-scored pool rankings | Updated every cycle |
| `spot:cluster_mode:{cluster_id}` | COST_FIRST/BALANCED/NO_DOWNTIME_FIRST | Persistent |
| `spot:volatility_regime:{region}` | "true" if volatile | Updated hourly |
| `spot:execution_fail:{pool_id}` | Execution failure counter | 1 hour |
| `spot:cluster_circuit_breaker:{cluster_id}` | Circuit breaker flag | 30 min |
| `spot:ondemand_fallback:{cluster_id}` | On-demand fallback active flag | 12 hours |
| `spot:wie:pod_state:{cluster_id}:{pod_name}` | WIE pod state cache | 2 min (fast loop TTL) |
| `spot:wie:node_state:{cluster_id}:{node_name}` | WIE node state cache | Updated by slow loop |
| `spot:wie:classification:{cluster_id}:{ns}/{name}` | Workload tier + confidence | Updated by WIE |
| `spot:blacklist:{pool_id}` | Blacklisted pool | 6 hours |
| `pricing:last_updated:{region}` | When pricing was last refreshed | Updated by pricing worker |
| `spot:ee:manifest:{cluster_id}` | Execution manifest (for EE2) | 120 seconds (Redis cache) |
| `spot:ee:action:{cluster_id}:{exec_id}:{pod}` | ActionTracker write-ahead log | 1 hour |
| `spot:exec_fail_window:{cluster_id}` | Execution failure window counter | 10 min |
| `spot:rejection_counters:{cluster_id}` | Decision Engine rejection stats | 24 hours |

---

## Common Error Scenarios and What They Mean {#error-scenarios}

**Error: "Skipping NodePool sync — active rebalance action #94 (status=waiting_agent)"**
```
Cause: A rebalance action is stuck in waiting_agent (agent not responding)
Fix: Check agent connectivity:
  → Is the agent pod running? kubectl get pods -A | grep spot-agent
  → Check WebSocket connection logs
  → Manually resolve: UPDATE rebalance_actions SET status='failed' WHERE id=94;
```

**Error: "Failed to collect Karpenter metrics: unsupported operand type(s) for +: 'NoneType' and 'str'"**
```
Cause: cluster.ca_data is None in database (cluster wasn't properly discovered)
Fix: Re-run cluster discovery to populate CA cert, or manually set:
  UPDATE clusters SET ca_data='<base64-encoded-cert>' WHERE id='...';
```

**Error: "User not authorized to perform sts:AssumeRole"**
```
Cause: IAM user ml-project lacks cross-account role assumption permission
Fix: Add AssumeRole permission to the IAM user, or update trust policy on SpotOptimizerRole
```

**Error: "All candidate pools in cooldown"**
```
Cause: All viable pools were recently used → 30-min cooldown active
Fix: Wait 30 minutes, or check if ITN emergency bypass should be triggered
Info: redis.keys("spot:cooldown:pool:*") — shows all active pool cooldowns
```

**Error: "Delta 0.02 below threshold 0.05"**
```
Cause: Best candidate EV is only 2% better than current — not worth the disruption
Fix: Not an error — this is intentional. Either the cluster is well-optimized,
     or change optimization_mode to COST_FIRST (threshold drops to 3%)
```

**Error: "Circuit breaker TRIPPED: cluster=..., failures=10"**
```
Cause: 10+ execution failures in 10 minutes — something is seriously wrong
Fix: Investigate the failures in the log. Check:
  → AWS spot capacity in the region
  → Karpenter NodePool status
  → Agent connectivity
  → Circuit auto-resets after 30 minutes
```

**Error: "WIE confidence=DRAFT — skipping recommendation"**
```
Cause: Workload has been observed for <24h — not enough data for reliable right-sizing
Fix: Wait 24+ hours for WIE to build enough observation history
Info: DRAFT → CONFIRMED after sufficient observation time + stability
```

---

*End of akhilesh.md*

> **Note:** This document reflects the codebase as of May 2026. Check `memory.md` for recent changes and `duplicate-logic.md` for areas that need cleanup.
