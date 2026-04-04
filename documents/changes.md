# Karpenter Simulation — Final Production-Grade Plan
> Based on: `SYSTEM_ARCHITECTURE_COMPLETE.md` + `KARPENTER_SIMULATION_DEEP_DIVE.md`  
> Scope: What-if consolidation advisor — "if we rebalanced right now, what would the optimal spot fleet look like?"  
> No synthetic assumptions — all data from real cluster state only

---

## Table of Contents

1. [Current State Audit — What Is Real vs Approximated](#1-current-state-audit)
2. [Reality Gaps — Specific Code References](#2-reality-gaps)
3. [Final Target Architecture](#3-final-target-architecture)
4. [Stage 1 — Consistent Snapshot Engine](#4-stage-1--consistent-snapshot-engine)
5. [Stage 2 — Virtual Cluster State Engine](#5-stage-2--virtual-cluster-state-engine)
6. [Stage 3 — Multi-Cycle Convergence Loop](#6-stage-3--multi-cycle-convergence-loop)
7. [Stage 4 — Scheduler-Driven Packing (Replace FFD)](#7-stage-4--scheduler-driven-packing-replace-ffd)
8. [Stage 5 — Real Karpenter Behavior Modeling](#8-stage-5--real-karpenter-behavior-modeling)
9. [Stage 6 — Constraint Replay Engine](#9-stage-6--constraint-replay-engine)
10. [Stage 7 — Per-Cluster Isolation](#10-stage-7--per-cluster-isolation)
11. [Stage 8 — Time-Based State Machine](#11-stage-8--time-based-state-machine)
12. [Stage 9 — Calibration & Accuracy Loop](#12-stage-9--calibration--accuracy-loop)
13. [Final Output Schema](#13-final-output-schema)
14. [Validation Criteria](#14-validation-criteria)
15. [What This Replaces vs What Stays](#15-what-this-replaces-vs-what-stays)

---

## 1. Current State Audit

### What Is Already Real (Keep As-Is)

| Component | File | What It Does Correctly |
|-----------|------|----------------------|
| Pod metrics query | `ascpai_routes.py` L1937 | Real pod CPU/memory from `pod_metrics` table (last 10 min) |
| DaemonSet separation | `ascpai_routes.py` L1950 | Correctly separates DS from user pods; prevents overestimation |
| Overhead accounting | Step 3 of simulation | DaemonSet + 100m kubelet CPU + 256MB RAM subtracted per node |
| ML composite scoring | `_ScoredPoolWrapper` | `ml_score = savings × (1 - risk_probability)` — correct |
| HA minimum constraint | Step 8 | Enforces `>= 2 nodes` — prevents single-spot SPOF |
| Spot outlier rejection | Step 4 | Rejects `discount < 5%` or `> 90%` or `price <= 0` |
| Architecture detection | Step 5 | ARM64/amd64 detection via family prefix + `\dg` pattern |
| Right-sizing integration | Step 6 | Substitutes right-sized pod requests when `use_rightsized=true` |
| Stateful node exclusion | Phase 3 per-node | `STATEFUL_PROTECTED` / `SYSTEM_PROTECTED` nodes excluded from spot packing |
| PDB-safe batch | `pdb_service.py` | PDB-aware batch percent enforced on real rebalance cycles |
| Pool ranking (4-pass) | `pool_ranking_service.py` | Pass 1→4 fallback cascade for pool selection |
| NodePool sync | `karpenter_service.py` | Real K8s PATCH to `karpenter.sh/v1/nodepools/default` |

### What Is Currently Approximated (Must Fix)

| Gap | Current Behavior | Problem |
|-----|-----------------|---------|
| Single-pass FFD | One sweep, place all pods, done | Real K8s schedules greedily, causes fragmentation; simulation is too optimal by 15–30% |
| No provisioning delay | Replacement assumed instantly available | Karpenter takes 30–90s; pending pods during this window not modeled |
| Static snapshot | `pod_metrics` ≠ `instances` timestamp | Temporal inconsistency → wrong pod-to-node mapping |
| No drain state | Pods "move" instantly | Real system: cordon → evict → pending → reschedule → stabilize |
| No Redis constraint replay | `launch_blocked`, `rebalanced` keys ignored in simulation | Simulation recommends pools the live system would block |
| Global pool ranking | `global_pool_rankings:{region}` shared across clusters | Cluster-specific AZ availability, blacklist, failure history not applied |
| No convergence detection | Single pass always terminates | Multi-node clusters need multiple cycles to reach stable state |
| No failure modeling | Provisioning never fails | In reality: `spot:launch_blocked` triggers fallback; retries cost time |
| No PDB-aware drain order | FFD ignores PDB constraints | Drain order in real system follows PDB-safe batch; simulation skips this |

---

## 2. Reality Gaps — Specific Code References

### Gap A: Temporal Inconsistency in Snapshot
```
pod_metrics: timestamp >= now - 10min      ← window-based, not point-in-time
instances:   state='running'               ← current DB state (may be 5min old)
Redis:       real-time                     ← live
```
These three are read at different moments inside a single API request. A node could be mid-drain in reality but appear RUNNING in `instances` while its pods show as PENDING in `pod_metrics`.

**Source:** `ascpai_routes.py` Phase 1 (L1388–1443) + Phase 4 Step 1 (L1937–1950)

### Gap B: FFD Is Too Optimal
Current:
```python
_user_pod_demands.sort(key=lambda p: (-p['cpu_millicores'], -p['memory_bytes']))
# Place each pod in first bin that fits → globally optimal packing
```
Real Kubernetes scheduler:
- Does not globally sort pods
- Schedules one pod at a time based on arrival order
- Each scheduling decision may increase fragmentation
- NodeAffinity, Taints, Tolerations can block "optimal" placement

**Source:** `ascpai_routes.py` Step 7 (L1937 bin-packing loop)

### Gap C: No Launch Block Enforcement in Simulation
The auto-rebalancer enforces:
```python
# auto_rebalancer.py L1500–1521
if redis.exists(f"spot:launch_blocked:{cid}:{type}:{az}"):
    skip_pool()
```
The simulation does not check this. It will recommend pools that the live system has already blacklisted for 30 minutes.

### Gap D: Per-Cluster Blacklist Not Applied
The simulation uses `market_view_cache:{region}` — global, shared across all clusters in the same region.
The live system additionally uses `blacklist:global:{pool_key}` (24h TTL) and `risky_pools:{region}` SET.
Neither is applied to the simulation's candidate pool list.

---

## 3. Final Target Architecture

### Replace This:
```
Input → FFD → Cost → Output
```

### With This:
```
Real Snapshot (frozen timestamp)
         │
         ▼
Virtual Cluster State Engine
  [Nodes: SPOT + OD | Pods: RUNNING/PENDING/EVICTING]
         │
         ▼
Multi-Cycle Simulation Loop (max 10 cycles)
  ┌──────────────────────────────────────┐
  │  1. Identify consolidation targets   │
  │     (SPOT nodes + OD nodes)          │
  │  2. Simulate drain                   │
  │     (pods → PENDING, respect PDB)    │
  │  3. Simulate Karpenter provision     │
  │     (NodePool + constraints + delay) │
  │  4. Simulate scheduler placement     │
  │     (greedy, not globally optimal)   │
  │  5. Update virtual state             │
  │  6. Check convergence                │
  └──────────────────────────────────────┘
         │
         ▼
Convergence Detector
  (no removals + no pending pods = stable)
         │
         ▼
Cost Engine (spot fleet)
         │
         ▼
Enhanced Output (cycles, failures, fragmentation, confidence)
```

---

## 4. Stage 1 — Consistent Snapshot Engine

### Goal
All simulation inputs must be frozen at the same logical timestamp to eliminate temporal inconsistency (Gap A).

### What to Build: `SimulationSnapshot`

```python
@dataclass
class SimulationSnapshot:
    snapshot_id: str                    # UUID for traceability
    frozen_at: datetime                 # Single reference timestamp

    # From instances table (state='running', at frozen_at)
    nodes: List[SimNode]

    # From pod_metrics (timestamp closest to frozen_at, per node)
    pods: List[SimPod]

    # Redis state (copy of relevant keys at snapshot time)
    redis_state: SimRedisState

    # From ClusterOptimizationSettings (DB read at frozen_at)
    cluster_settings: SimClusterSettings

    # From karpenter_service (K8s CRD read at frozen_at)
    nodepool_config: SimNodePoolConfig

    # Validity flag — reject if any source is stale
    is_valid: bool
    invalid_reason: Optional[str]
```

### SimNode (per node)
```python
@dataclass
class SimNode:
    instance_id: str
    instance_type: str
    lifecycle: str              # "spot" | "on-demand"
    az: str
    architecture: str           # "amd64" | "arm64"
    vcpu: int
    memory_gb: float
    price_hourly: float
    workload_class: str         # "stateless" | "stateful" | "system"
    status: str                 # "READY" | "CALIBRATING" | "UNKNOWN"
    is_standby: bool
```

### SimRedisState (keys to snapshot)
```python
@dataclass
class SimRedisState:
    launch_blocked: Set[str]         # spot:launch_blocked:{cid}:{type}:{az}
    blacklisted_pools: Set[str]      # blacklist:global:{pool_key}
    risky_pools: Set[str]            # risky_pools:{region} SET members
    node_classification: Dict[str, str]  # spot:node_classification:{cid}
    pdb_safe_percent: Optional[int]  # pdb:safe_percent:{cluster_id}
```

### Snapshot Validity Rules
```
REJECT snapshot if:
  - pod_metrics freshness > 15 min from frozen_at
  - instances count == 0
  - market_view_cache miss (return null simulation)
  - nodepool_config unreadable
```

---

## 5. Stage 2 — Virtual Cluster State Engine

### Goal
Replace static node/pod objects with a **stateful virtual cluster** that tracks transitions across simulation cycles.

### VirtualClusterState
```python
class VirtualClusterState:
    nodes: Dict[str, VirtualNode]
    pods: Dict[str, VirtualPod]
    cycle: int = 0
    
    def drain_node(self, node_id: str, pdb_batch: int) -> List[str]:
        """Mark node cordoned; move pods to PENDING; return pending pod IDs."""
    
    def provision_node(self, pool: SimPool, delay_ticks: int) -> str:
        """Add PROVISIONING node; returns virtual_node_id."""
    
    def node_becomes_ready(self, virtual_node_id: str):
        """Transition PROVISIONING → READY; trigger scheduler."""
    
    def schedule_pending_pods(self) -> List[str]:
        """Place pending pods on READY nodes; return unschedulable pod IDs."""
    
    def remove_node(self, node_id: str):
        """Remove node after drain complete; finalize termination."""
    
    def check_convergence(self) -> bool:
        """True if no node was removed this cycle AND pending_pods == 0."""
```

### VirtualNode Statuses
```
READY          → Currently running, schedulable
CORDONED       → Marked unschedulable, pods still running
DRAINING       → Eviction in progress (pods moving to PENDING)
PROVISIONING   → Karpenter launched, not yet READY (delay modeled)
TERMINATED     → Removed from virtual cluster
```

### VirtualPod Statuses
```
RUNNING   → Assigned to a READY node
PENDING   → Evicted from drain; waiting for scheduler
EVICTING  → Graceful eviction in progress (respects grace period)
FAILED    → Could not be scheduled (no fitting node)
```

---

## 6. Stage 3 — Multi-Cycle Convergence Loop

### Structure
```python
MAX_CYCLES = 10
PROVISIONING_DELAY_TICKS = 3   # ~90 simulated seconds per tick (~30s)

def run_simulation(snapshot: SimulationSnapshot) -> SimulationResult:
    state = VirtualClusterState.from_snapshot(snapshot)
    history = []

    for cycle in range(MAX_CYCLES):
        cycle_result = run_one_cycle(state, snapshot, cycle)
        history.append(cycle_result)

        if state.check_convergence():
            break

        # Advance provisioning timers
        state.tick_provisioning_nodes()

    return SimulationResult(
        cycles_run=len(history),
        converged=state.check_convergence(),
        final_state=state,
        history=history
    )
```

### Per-Cycle Steps

#### Step 1: Identify Consolidation Candidates
```python
def select_candidates(state, snapshot) -> List[VirtualNode]:
    candidates = []
    for node in state.ready_nodes():
        if node.is_standby: continue

        # STATEFUL nodes → always stay OD, never candidates
        # Their OD cost is tracked separately in the output, not consolidated
        if node.workload_class in ('stateful', 'system'):
            continue

        # STATELESS SPOT nodes: S2S rebalance (risky pool or diversification needed)
        if node.lifecycle == 'spot':
            if node.risk > settings.risk_ceiling or is_diversification_needed(node, state):
                candidates.append(node)

        # STATELESS OD nodes: primary migration targets — all eligible in what-if mode
        if node.lifecycle == 'on-demand':
            candidates.append(node)

    # Apply spot exposure cap
    candidates = apply_spot_exposure_cap(candidates, state, settings)
    # Apply PDB-safe batch sizing
    candidates = apply_pdb_batch(candidates, snapshot.redis_state.pdb_safe_percent, settings)
    return candidates
```

**`apply_spot_exposure_cap` logic:**
```python
def apply_spot_exposure_cap(candidates, state, settings) -> List[VirtualNode]:
    target = settings.target_spot_exposure_pct
    if target == 100:
        return candidates  # no cap, full migration mode

    current_spot = state.spot_node_count()
    total = state.total_running_node_count()
    current_spot_pct = (current_spot / total * 100) if total > 0 else 0

    if current_spot_pct >= target:
        return []  # already at or over target, skip all OD→Spot

    od_to_convert = max(1, int((target - current_spot_pct) / 100 * total))
    return candidates[:od_to_convert]
```

#### Step 2: Drain Simulation (Stateless Nodes Only)
```python
def simulate_drain(state, node, settings) -> DrainResult:
    pods_on_node = state.get_running_pods(node.id)

    # Stateful or system pods: node should never have reached this point,
    # but guard here as a safety check
    protected = [p for p in pods_on_node if p.is_stateful or p.has_local_pvc]
    if protected:
        return DrainResult(blocked=True, reason="stateful_pods_present")

    # Cordon first
    state.cordon_node(node.id)

    # Evict user pods (skip DaemonSets — they follow the node)
    evictable = [p for p in pods_on_node if not p.is_daemonset]
    for pod in evictable:
        state.set_pod_status(pod.id, 'PENDING')
        state.set_pod_node(pod.id, None)

    return DrainResult(blocked=False, evicted=len(evictable))
```

#### Step 3: Karpenter Provisioning Simulation
```python
def simulate_karpenter_provision(state, pending_pods, snapshot) -> ProvisionResult:
    # Group pending pods by resource profile (Karpenter batches)
    groups = batch_pending_pods(pending_pods)

    provisioned = []
    failures = []

    for group in groups:
        min_vcpu = max(p.cpu_millicores for p in group) / 1000
        min_mem  = max(p.memory_bytes for p in group) / (1024**3)

        # Select pool using EXACT 4-pass algorithm from pool_ranking_service.py
        pool = select_pool_for_simulation(
            min_vcpu=min_vcpu,
            min_mem=min_mem,
            snapshot=snapshot,     # applies launch_blocked, blacklist, risky_pools
            state=state,           # applies diversification
            settings=snapshot.cluster_settings
        )

        if pool is None:
            failures.append(ProvisionFailure(group=group, reason="no_eligible_pool"))
            continue

        # Add node in PROVISIONING state
        vnode_id = state.provision_node(pool, delay_ticks=PROVISIONING_DELAY_TICKS)
        provisioned.append(vnode_id)

    return ProvisionResult(provisioned=provisioned, failures=failures)
```

#### Step 4: Scheduler Simulation (Greedy, Not Global)
```python
def simulate_scheduler(state, snapshot) -> SchedulerResult:
    """Greedy scheduler — mirrors real K8s behavior, NOT globally optimal."""
    pending = state.get_pending_pods()
    unschedulable = []

    for pod in pending:  # NOT sorted — arrival order matters
        placed = False
        # Try existing READY nodes first (bin packing)
        for node in state.ready_nodes_sorted_by_remaining_cpu_desc():
            if node_fits_pod(node, pod) and node_allows_pod(node, pod, snapshot):
                state.place_pod(pod.id, node.id)
                placed = True
                break

        # Try newly READY nodes (just became ready this cycle)
        if not placed:
            for node in state.new_ready_nodes():
                if node_fits_pod(node, pod) and node_allows_pod(node, pod, snapshot):
                    state.place_pod(pod.id, node.id)
                    placed = True
                    break

        if not placed:
            unschedulable.append(pod.id)

    return SchedulerResult(
        placed=len(pending) - len(unschedulable),
        unschedulable=unschedulable
    )
```

`node_allows_pod` checks (derived from real constraints):
- Architecture match (amd64/arm64 from `architecture_preference`)
- Node not cordoned or draining
- Pool not in `launch_blocked` or `blacklist`
- Stateless pods only placed on stateless (spot) nodes; stateful pods only placed on stateful (OD) nodes

#### Step 5: Convergence Check
```python
def check_convergence(state, prev_node_count) -> bool:
    no_drain_this_cycle = (state.node_count == prev_node_count)
    no_pending_pods = (len(state.get_pending_pods()) == 0)
    no_provisioning_nodes = (len(state.provisioning_nodes()) == 0)
    return no_drain_this_cycle and no_pending_pods and no_provisioning_nodes
```

#### Step 6: Two-Pool Cost Calculation (runs once after convergence)
```python
def compute_two_pool_cost(final_state, snapshot) -> TwoPoolCost:
    """
    Compute costs separately for the stateless (spot) pool
    and the stateful (OD) pool — mirrors how the real system operates.
    """
    # STATELESS POOL — all nodes that host stateless workloads (should all be spot)
    stateless_nodes = [
        n for n in final_state.nodes.values()
        if n.workload_class == 'stateless' and n.status == 'READY'
    ]
    stateless_spot_hourly = sum(n.price_hourly for n in stateless_nodes if n.lifecycle == 'spot')
    stateless_od_hourly   = sum(n.price_hourly for n in stateless_nodes if n.lifecycle == 'on-demand')

    # STATEFUL POOL — nodes that host stateful workloads (always OD)
    stateful_nodes = [
        n for n in final_state.nodes.values()
        if n.workload_class in ('stateful', 'system') and n.status == 'READY'
    ]
    stateful_od_hourly = sum(n.price_hourly for n in stateful_nodes)

    return TwoPoolCost(
        # Stateless pool
        stateless_node_count   = len(stateless_nodes),
        stateless_spot_count   = sum(1 for n in stateless_nodes if n.lifecycle == 'spot'),
        stateless_hourly_cost  = stateless_spot_hourly + stateless_od_hourly,
        stateless_monthly_cost = (stateless_spot_hourly + stateless_od_hourly) * 730,

        # Stateful pool
        stateful_node_count    = len(stateful_nodes),
        stateful_hourly_cost   = stateful_od_hourly,
        stateful_monthly_cost  = stateful_od_hourly * 730,

        # Combined
        total_hourly_cost  = stateless_spot_hourly + stateless_od_hourly + stateful_od_hourly,
        total_monthly_cost = (stateless_spot_hourly + stateless_od_hourly + stateful_od_hourly) * 730,
    )
```

---

## 7. Stage 4 — Scheduler-Driven Packing (Replace FFD)

### Why FFD Must Be Replaced
Current FFD sorts ALL pods by size descending then globally optimizes placement. This produces 15–30% better packing than reality.

Real Kubernetes:
- Schedules pods one at a time in arrival order
- Each decision is local and greedy
- Leads to fragmentation over time
- Cannot retroactively repack

### Replacement: Greedy Scheduler with Fragmentation Model

#### Placement Priority (mirrors K8s + Karpenter)
```
Priority 1: Existing READY nodes with most remaining capacity
Priority 2: Newly provisioned READY nodes (this cycle)
Priority 3: Trigger new Karpenter provisioning request
```

#### Fragmentation Correction Factor
Post-placement, apply a fragmentation penalty to represent real-world waste:
```python
FRAGMENTATION_PCT = 0.08   # 8% default (derived from Accuracy Model section 13)

effective_utilization = actual_placed / theoretical_max
fragmentation_waste = 1 - effective_utilization
if fragmentation_waste > FRAGMENTATION_PCT:
    # Add 1 extra node of the most common type to model real fragmentation
    add_fragmentation_node(state)
```

This corrects the "too optimal" bias of pure bin-packing.

---

## 8. Stage 5 — Real Karpenter Behavior Modeling

### NodePool Constraint Application
The simulation must respect actual NodePool CRD constraints read from the cluster.

```python
@dataclass
class SimNodePoolConfig:
    # From karpenter.sh/v1/nodepools/default
    allowed_instance_types: List[str]   # ML-ranked types currently in NodePool
    allowed_azs: List[str]
    spot_allowed: bool
    architecture_requirements: List[str]  # amd64 / arm64
    
    # NodePool-level limits
    cpu_limit: Optional[int]
    memory_limit_gb: Optional[float]
```

Pool selection during simulation filters out any type NOT in `allowed_instance_types` unless it would be added by the simulation (which is what Phase 1 of the real rebalancer does via `add_allowed_instance_type()`).

### Provisioning Grouping
Karpenter batches pending pods before deciding instance type. The simulation mirrors this:
```python
def batch_pending_pods(pending_pods) -> List[List[VirtualPod]]:
    """Group pods by compatible resource profile + architecture."""
    # Group 1: amd64 pods
    # Group 2: arm64 pods
    # Within each: sub-group by min required instance size
    # This determines what instance Karpenter would provision
```

---

## 9. Stage 6 — Constraint Replay Engine

### All Pool & Cluster Constraints That Must Be Enforced

These are the constraints relevant to what-if recommendations — they reflect real capacity and safety realities, not operational execution gates.

#### Per-Pool Constraints (from Redis snapshot)
```python
def is_pool_eligible_for_simulation(pool, redis_state, cluster_id) -> Tuple[bool, str]:
    pool_key = f"{pool.instance_type}:{pool.az}"
    blocked_key = f"{cluster_id}:{pool.instance_type}:{pool.az}"

    # 1. Launch blocked (capacity failure)
    if blocked_key in redis_state.launch_blocked:
        return False, "launch_blocked"

    # 2. Global blacklist (interruption or terminated)
    if pool_key in redis_state.blacklisted_pools:
        return False, "globally_blacklisted"

    # 3. Risky pool set
    if pool_key in redis_state.risky_pools:
        return False, "risky_pool"

    return True, "eligible"
```

#### Cluster-Level Constraints
```python
def cluster_can_simulate(snapshot) -> Tuple[bool, str]:
    # Min node count floor — never recommend below this
    current_count = len(snapshot.nodes)
    if current_count <= snapshot.cluster_settings.min_node_count:
        return False, "at_min_node_count"

    return True, "ok"
```

#### Diversification Enforcement
Carry forward the same diversification logic from `ClusterOptimizationSettings`:
```python
def apply_diversification(pool, state, settings):
    if not settings.diversify_pools:
        return True  # no diversification constraint

    total_nodes = state.total_running_node_count()
    family = pool.instance_type.split('.')[0]
    family_count = state.count_nodes_by_family(family)
    family_cap = settings.max_family_diversification_cap_pct / 100
    az_count = state.count_nodes_by_az(pool.az)
    az_cap = 0.50  # hardcoded 50% AZ cap from pool_ranking_service

    if family_count / total_nodes >= family_cap:
        return False  # family cap exceeded
    if az_count / total_nodes >= az_cap:
        return False  # AZ cap exceeded
    return True
```

---

## 10. Stage 7 — Per-Cluster Isolation

### Problem
`global_pool_rankings:{region}` is a regional cache shared across all clusters in the same region. Two clusters in `ap-south-1` share the same ranked pool list regardless of:
- Their individual AZ composition
- Their individual blacklist history
- Their individual failure patterns

### Fix: Cluster-Scoped Pool View

```python
def build_cluster_pool_view(
    cluster_id: str,
    region: str,
    cluster_azs: List[str],
    redis_state: SimRedisState,
    market_view: List[dict]
) -> List[SimPool]:
    """
    Filters the regional market view to pools relevant and eligible
    for this specific cluster, applying cluster-specific constraints.
    """
    eligible = []
    for pool in market_view:
        # AZ filter: only pools in AZs this cluster uses
        if pool['az'] not in cluster_azs:
            continue

        # Architecture filter: from cluster_settings.architecture_preference
        if not arch_matches(pool, cluster_settings.architecture_preference):
            continue

        # Launch block check (cluster-specific)
        blocked_key = f"{cluster_id}:{pool['instance_type']}:{pool['az']}"
        if blocked_key in redis_state.launch_blocked:
            continue

        # Global blacklist
        pool_key = f"{pool['instance_type']}:{pool['az']}"
        if pool_key in redis_state.blacklisted_pools:
            continue

        eligible.append(SimPool.from_market_view(pool))

    # Sort using same ml_score formula
    eligible.sort(key=lambda p: (p.spot_price, -p.ml_score))
    return eligible
```

**Result:** Every cluster simulation operates on its own filtered, constraint-applied pool view — zero cross-cluster contamination.

---

## 11. Stage 8 — Time-Based State Machine

### Simulated Time Model
Each simulation "tick" represents ~30 real seconds (matching the Karpenter provisioning beat at `karpenter-nodepool-sync` 30s interval).

```python
TICK_SECONDS = 30
PROVISIONING_TICKS = 3   # 90s average Karpenter node join
STABILIZATION_TICKS = 3  # 90s post-join stabilization (matches 90s check in Phase 2)
DRAIN_TICKS_PER_NODE = 1 # 30s per node drain (fast path)
MAX_SIMULATION_TICKS = 30  # 15 minutes cap (matches `drain_timeout_minutes=15`)
```

### State Transition Timers

```python
@dataclass
class VirtualNode:
    status: str
    provisioning_ticks_remaining: int = 0
    stabilization_ticks_remaining: int = 0

    def tick(self):
        if self.status == 'PROVISIONING':
            self.provisioning_ticks_remaining -= 1
            if self.provisioning_ticks_remaining <= 0:
                self.status = 'STABILIZING'
                self.stabilization_ticks_remaining = STABILIZATION_TICKS

        elif self.status == 'STABILIZING':
            self.stabilization_ticks_remaining -= 1
            if self.stabilization_ticks_remaining <= 0:
                self.status = 'READY'   # Now schedulable
```

### Timeout Modeling
Mirror real auto-rebalancer timeouts to detect when simulation would stall:
```
WAITING_FOR_SPOT_NODE timeout: 28 min (56 ticks)
DRAIN timeout: 20 min (40 ticks)
PHASE 1 timeout: 45 min total (90 ticks)
```
If simulation reaches tick limit before convergence: `converged=false`, `timed_out=true`.

---

## 12. Stage 9 — Calibration & Accuracy Loop

### After Each Real Rebalance Completes
Store in `simulation_accuracy_log` table:
```python
{
    "cluster_id": "...",
    "simulation_run_at": "...",
    "rebalance_completed_at": "...",

    # Stateless pool
    "sim_stateless_node_count": 6,
    "actual_stateless_node_count": 7,
    "sim_stateless_monthly_cost": 182.40,
    "actual_stateless_monthly_cost": 196.10,

    # Stateful pool
    "sim_stateful_node_count": 2,
    "actual_stateful_node_count": 2,
    "sim_stateful_monthly_cost": 63.40,
    "actual_stateful_monthly_cost": 65.20,

    # Combined
    "sim_spot_pct": 75.0,
    "actual_spot_pct": 77.8,
    "simulated_cycles": 3,
    "stateless_node_count_error_pct": 14.3,
    "stateless_cost_error_pct": 7.0,
    "stateful_cost_error_pct": 2.8
}
```

### Calibration Signals Fed Back Into Simulation
```
stateless_node_count_error > 15% repeatedly → increase fragmentation_correction_factor
stateless_cost_error > 15% repeatedly       → check spot price staleness or pool ranking freshness
stateful_cost_error > 5% repeatedly         → check OD price worker freshness
spot_pct_error > 10% repeatedly             → check exposure cap enforcement or S2S detection
```

### Confidence Score Formula
```python
def compute_confidence(snapshot, state) -> float:
    score = 1.0

    # Penalize for stale pod metrics
    pod_data_age_min = (snapshot.frozen_at - snapshot.oldest_pod_metric_ts).seconds / 60
    if pod_data_age_min > 10:
        score -= 0.15  # stale data

    # Penalize for provisioning failures
    score -= 0.05 * state.total_provisioning_failures

    # Penalize for unschedulable pods
    if state.total_pods > 0:
        unschedulable_pct = state.unschedulable_pod_count / state.total_pods
        score -= 0.20 * unschedulable_pct

    # Penalize for slow convergence
    if state.cycles_to_converge > 6:
        score -= 0.10

    return max(0.0, min(1.0, round(score, 2)))
```

---

## 13. Final Output Schema

The enhanced simulation returns all existing fields PLUS new convergence and realism fields:

```python
karpenter_simulation = {
    # ── Existing fields (unchanged) ──────────────────────────────
    'mode': 'dry_run' | 'auto',
    'rightsized': bool,
    'consolidated_nodes': [ConsolidatedNode],
    'total_node_count': int,
    'total_hourly_cost': float,
    'total_monthly_cost': float,
    'current_node_count': int,
    'current_monthly_cost': float,
    'monthly_savings': float,
    'nodes_eliminated': int,
    'total_pods_packed': int,
    'total_pods_in_cluster': int,
    'user_pods': int,
    'daemonset_pods': int,
    'daemonset_overhead_cpu_m': int,
    'daemonset_overhead_mem_mb': int,
    'multi_arch': bool,
    'architectures_used': List[str],

    # ── NEW: Stateless pool (spot) ───────────────────────────────
    'stateless_node_count': int,            # simulated stateless node count
    'stateless_spot_count': int,            # how many are spot (should be all)
    'stateless_monthly_cost': float,        # total monthly cost for stateless pool
    'stateless_consolidated_nodes': [ConsolidatedNode],  # spot node types used
    'stateless_nodes_eliminated': int,      # stateless nodes removed vs current
    'stateless_monthly_savings': float,     # savings on stateless pool vs current OD price

    # ── NEW: Stateful pool (OD) ───────────────────────────────────
    'stateful_node_count': int,             # stateful node count (unchanged — always OD)
    'stateful_monthly_cost': float,         # total monthly cost for stateful pool
    'stateful_consolidated_nodes': [ConsolidatedNode],   # OD node types retained
    'stateful_monthly_savings': float,      # right-sizing savings if use_rightsized=true, else 0

    # ── NEW: Combined totals ──────────────────────────────────────
    'simulated_spot_node_count': int,       # all spot nodes across both pools
    'simulated_od_node_count': int,         # all OD nodes across both pools
    'simulated_spot_pct': float,            # spot % of total simulated fleet

    # ── NEW: Convergence data ─────────────────────────────────────
    'cycles_to_converge': int,
    'converged': bool,
    'timed_out': bool,
    'pending_pods_peak': int,               # max pending pods across all cycles
    'provisioning_failures': int,           # pools attempted but failed to provision
    'scheduler_fragmentation_pct': float,   # fragmentation waste vs theoretical optimal

    # ── NEW: Constraint visibility ────────────────────────────────
    'pools_skipped_launch_blocked': int,    # pools excluded due to launch block
    'pools_skipped_blacklisted': int,       # pools excluded due to global blacklist

    # ── NEW: Simulation quality ───────────────────────────────────
    'confidence_score': float,              # 0.0 – 1.0
    'snapshot_frozen_at': str,              # ISO timestamp of snapshot
    'pod_data_age_seconds': int,            # how old the pod metrics are
    'simulation_engine_version': str,       # "v2-convergence" (vs "v1-ffd")
}
```

### ConsolidatedNode (enhanced)
```python
{
    'instance_type': str,
    'az': str,
    'architecture': str,
    'vcpu': int,
    'memory_gb': float,
    'spot_price': float,
    'od_price': float,
    'lifecycle': str,         # "spot" (stateless pool) | "on-demand" (stateful pool)
    'workload_class': str,    # NEW: "stateless" | "stateful" | "system"
    'risk_probability': float,
    'ml_score': float,
    'count': int,
    'total_pods': int,
}
```

---

## 14. Validation Criteria

### Primary Accuracy Targets

| Metric | Acceptable Error | Action If Exceeded |
|--------|-----------------|-------------------|
| `stateless_node_count` vs actual post-rebalance | ≤ 10% | Increase fragmentation factor |
| `stateless_monthly_cost` vs actual | ≤ 10% | Check spot price staleness or pool ranking freshness |
| `stateful_monthly_cost` vs actual | ≤ 5% | Check OD price freshness (stateful nodes don't move, so this should be near exact) |
| `simulated_spot_pct` vs actual | ≤ 8% | Check exposure cap enforcement or S2S detection |
| `cycles_to_converge` correlation | Directionally correct | Check provisioning delay modeling |

### Regression Tests (Must Pass Before Deploying)

1. **Two-pool separation:** All nodes with `workload_class=stateful` must appear only in `stateful_consolidated_nodes` with `lifecycle="on-demand"`. No stateful node may appear in `stateless_consolidated_nodes`.
2. **All stateless → spot:** After convergence, `stateless_spot_count` must equal `stateless_node_count` (all stateless nodes should be on spot pools).
3. **Stateful cost unchanged:** `stateful_monthly_cost` must equal the current OD cost of stateful nodes — the stateful pool is never consolidated in what-if mode (unless `use_rightsized=true`).
4. **Launch block respected:** Pools in `spot:launch_blocked:{cid}:{type}:{az}` must appear in `pools_skipped_launch_blocked` and NOT appear in `stateless_consolidated_nodes`.
5. **Spot exposure cap:** When `target_spot_exposure_pct=70` and current spot is 65%, only enough stateless OD nodes to reach 70% of the total fleet should be migrated.
6. **HA minimum:** `stateless_node_count >= 2` always (spot SPOF protection applies to stateless pool).
7. **Convergence:** `converged=true` must mean `pending_pods_peak` at last cycle is 0.
8. **No negative savings:** Both `stateless_monthly_savings` and `stateful_monthly_savings` floored at 0.

---

## 15. What This Replaces vs What Stays

| Component | Action | Reason |
|-----------|--------|--------|
| `ascpai_routes.py` Phase 4 FFD loop | **Replace** with multi-cycle convergence loop | Core upgrade |
| `SimulationSnapshot` (new) | **Add** before Phase 4 | Temporal consistency |
| `VirtualClusterState` (new) | **Add** | State transition tracking |
| Pool candidate filtering | **Enhance** with Redis constraint replay | Gap D/E fix |
| Cost aggregation | **Enhance** with stateful-OD retained nodes | Stateful nodes correctly priced as OD |
| Output schema | **Extend** with new fields | Visibility |
| DaemonSet separation (Steps 2–3) | **Keep unchanged** | Already correct |
| HA minimum node constraint (Step 8) | **Keep unchanged** | Already correct |
| ML composite scoring | **Keep unchanged** | Already correct |
| Right-sizing integration (Step 6) | **Keep unchanged** | Already correct |
| Spot outlier rejection | **Keep unchanged** | Already correct |
| Architecture detection (Step 5) | **Keep unchanged** | Already correct |
| Accuracy model (7 fixes) | **Keep + extend** with convergence data | Already solid foundation |
| NodePool sync (karpenter_service.py) | **Keep unchanged** | This is real K8s patching, not simulation |
| Auto-rebalancer state machine | **Keep unchanged** | This is the real system; simulation mirrors it |

---

*Document based exclusively on real code from `SYSTEM_ARCHITECTURE_COMPLETE.md` and `KARPENTER_SIMULATION_DEEP_DIVE.md`.*  
*Primary source files: `ascpai_routes.py`, `auto_rebalancer.py`, `pool_ranking_service.py`, `karpenter_service.py`, `pdb_service.py`, `redis_keys.py`*