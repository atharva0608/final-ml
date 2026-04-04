 ---
  Technical Report: Karpenter Bin-Packing, Right-Sizing & Auto-Rebalancing Integration

  ---
  1. System Overview

  The platform implements a three-layer provisioning architecture where all three subsystems coordinate via Redis keys to ensure no two operations conflict:

  ┌────────────────────┐    ┌──────────────────────┐    ┌─────────────────────┐
  │  Pool Ranking (ML) │───▶│  Auto-Rebalancer     │───▶│  Karpenter Service  │
  │  rank_pools_for_*  │    │  execute_rebalancing  │    │  sync_ml_rankings   │
  └────────────────────┘    └──────────┬───────────┘    └─────────────────────┘
                                       │
                            ┌──────────▼───────────┐    ┌─────────────────────┐
                            │  Right-Sizing         │    │  ASCP Auto-Scaler   │
                            │  Bin-Pack + Propose   │    │  ASG +/-1 capacity  │
                            └──────────────────────┘    └─────────────────────┘

  ---
  2. How Karpenter Bin-Packing Works

  2.1 Bin-Packing Algorithm (auto_rebalancer.py)

  When auto_rightsizing_enabled = True, every rebalance action runs a bin-packing step before pool selection:

  Given: current node with cpu_pct (measured), mem_pct (measured)

  required_vcpu   = max(0.25, current_vcpu  × (cpu_pct  / 100) × 1.30)  ← 30% headroom
  required_memory = max(0.5,  current_mem   × (mem_pct  / 100) × 1.30)

  Find: cheapest instance_type with vcpu ≥ required_vcpu AND mem ≥ required_memory
  If found AND cheaper than current → set target_instance_type, bin_packed=True
  Else → fall back to same-size pool selection

  The 1.30 multiplier is a safety buffer above observed P95 usage — prevents the replacement from being undersized.

  2.2 NodePool Construction

  After bin-packing determines the target_instance_type, the Karpenter service builds a Kubernetes NodePool spec:

  sync_ml_rankings_to_nodepool(cluster_id, top_pools, nodepool_name="default")

  # Generated NodePool CRD:
  spec:
    template:
      spec:
        requirements:
          - key: karpenter.sh/capacity-type
            operator: In
            values: ["spot"]
          - key: node.kubernetes.io/instance-type
            operator: In
            values: [<ML-approved types from top_pools>]
          - key: topology.kubernetes.io/zone
            operator: In
            values: [<extracted AZs>]

  The allowed instance types are the output of PoolRankingService.rank_pools_for_node() filtered through the ML 4-pass selection (see §4 below). Karpenter then picks from this constrained list when it needs
  to provision a node — it handles the actual bin-packing of pods onto instances. ASCP controls which instance types are eligible; Karpenter controls which node gets which pods.

  2.3 Fallback to On-Demand

  switch_to_ondemand(cluster_id, ...) is called when no safe spot pools remain (all blacklisted or risk-exceeded):

  1. PATCHes the NodePool: capacity-type: spot → on-demand
  2. Writes spot:ondemand_fallback:{cluster_id} (Redis, TTL=43200s / 12 hours)
  3. After 12 hours TTL expires, revert_to_spot() restores spot mode

  _final_capacity_check(candidate_list, region) runs a DryRun before any NodePool patch:
  - Calls ec2.run_instances(DryRun=True) — actual capacity check, not just offering list
  - DryRunOperation response = capacity confirmed → proceed
  - InsufficientInstanceCapacity → increment spot:execution_fail:{pool_id} counter; if ≥ 2 failures → blacklist pool 6 hours

  2.4 Retry Logic

  ┌────────────────────────────────┬────────────────────────────────┐
  │           Parameter            │             Value              │
  ├────────────────────────────────┼────────────────────────────────┤
  │ MAX_PATCH_RETRIES              │ 2                              │
  ├────────────────────────────────┼────────────────────────────────┤
  │ Retry delays                   │ 5s, 15s                        │
  ├────────────────────────────────┼────────────────────────────────┤
  │ Circuit breaker threshold      │ 10 execution failures / 10 min │
  ├────────────────────────────────┼────────────────────────────────┤
  │ Circuit breaker disable window │ 30 minutes                     │
  └────────────────────────────────┴────────────────────────────────┘

  On any PATCH failure the service captures the current NodePool state and restores it (rollback to previous spec).

  ---
  3. How Right-Sizing Works with the Auto-Rebalancer

  Right-sizing and auto-rebalancing are designed to never run simultaneously on the same cluster. They use a Redis cooldown key as a mutual exclusion gate.

  3.1 Mutual Exclusion Gate

  auto_rebalancer.py — Gate 5 (line 1199):
    if redis.exists("spot:cooldown:action:resize:{cluster_id}"):
        → defer this rebalancing cycle
        → try next cluster

  right-sizing execution:
    after executing a resize: SET "spot:cooldown:action:resize:{cluster_id}" [TTL varies]
    → auto_rebalancer sees this key and skips the cluster

  3.2 Right-Sizing Proposal Generation

  Pool selection for right-sizing uses rank_pools_for_size(vcpu, memory_gb, region, limit):

  1. Create flexible size template:
     vcpu_min   = max(1, target_vcpu)
     vcpu_max   = target_vcpu + 1
     mem_min    = max(1, int(target_mem - 2))
     mem_max    = int(target_mem + 2)

  2. Call rank_pools() with template → sorted pool list

  3. Re-sort by size proximity:
     Primary key:   abs(pool_vcpu - target_vcpu)
     Secondary key: abs(pool_mem  - target_mem)

  4. Return top N pools (cheapest + best fit)

  3.3 Resize Guard Worker (resize_guard_worker.py)

  Runs every 5 minutes for 2 hours after any resize execution. Monitors 4 health signals:

  ┌───────────────────┬──────────────────────────┬─────────────────────────────────────────────┬───────────────────────────────────────────────────┐
  │       Check       │        Threshold         │                  Key Read                   │                 Action on Breach                  │
  ├───────────────────┼──────────────────────────┼─────────────────────────────────────────────┼───────────────────────────────────────────────────┤
  │ CPU stress        │ > 85%                    │ metrics:cpu_avg_10m:{cluster_id}            │ Mark proposal FAILED + set resize:rollback_needed │
  ├───────────────────┼──────────────────────────┼─────────────────────────────────────────────┼───────────────────────────────────────────────────┤
  │ Pod restart spike │ > 2× baseline            │ metrics:pod_restarts_10m:{cluster_id}       │ Mark proposal FAILED                              │
  ├───────────────────┼──────────────────────────┼─────────────────────────────────────────────┼───────────────────────────────────────────────────┤
  │ Memory pressure   │ > 5 events               │ metrics:memory_pressure_events:{cluster_id} │ Mark proposal FAILED                              │
  ├───────────────────┼──────────────────────────┼─────────────────────────────────────────────┼───────────────────────────────────────────────────┤
  │ Mode 3 synergy    │ Pool risk > risk_ceiling │ Pool ranking service call                   │ Mark proposal FAILED                              │
  └───────────────────┴──────────────────────────┴─────────────────────────────────────────────┴───────────────────────────────────────────────────┘

  Mode 3 Synergy Guard is the most important: if both auto_rebalance_enabled AND auto_rightsizing_enabled are on, the guard checks whether the proposed right-sized instance type would be on a pool the
  rebalancer would immediately try to leave (risk score exceeds cluster risk_ceiling). This prevents a resize from landing a node on a risky pool that the rebalancer then immediately tries to replace.

  3.4 Restart Baseline Calculation

  Every hour the worker computes a rolling 24-hour restart baseline (excluding the most recent 2 hours — the guard window itself):

  baseline = mean(hourly restart samples from hours 2–26 ago)
  stored: metrics:pod_restart_baseline:{cluster_id}  (TTL=1h)

  Spike detection: restart_rate > baseline × 2.0

  ---
  4. Auto-Rebalancer: Core Execution Flow

  4.1 Two-Phase Execution Model

  The rebalancer never drains a source node until a healthy replacement is confirmed running. This is the fundamental safety guarantee:

  PHASE 1: Provision Replacement
  ├── Create PATCH_KARPENTER_NODEPOOL AgentAction
  │   (payload: instance_types, azs, capacity_type=spot)
  ├── Agent picks up → kubectl patches NodePool CRD
  ├── Karpenter provisions new spot instance
  └── OR: Direct EC2 launch (if Karpenter not installed)

                 ↕ wait for spot node to join K8s

  PHASE 2: Drain Source (only after spot node is Ready)
  ├── Wait conditions:
  │   ├── Spot EC2 age ≥ 90s (stabilization buffer)
  │   ├── node_name populated (kubelet joined K8s)
  │   └── Instance.status = 'READY'
  ├── Create CORDON_NODE → DRAIN_NODE → TERMINATE_NODE
  │   (3 sequential AgentActions)
  └── On completion: action.status = 'completed'

  Timeout: 30 minutes (configurable per-cluster via spot_join_timeout_minutes) for Phase 2 gate. If the spot node doesn't join in time, the action fails and the orphan spot instance is terminated.

  4.2 The 8 Safety Gates

  Every rebalancing action must pass all 8 gates before execution:

  ┌──────────────────────────┬──────────────────────────────────────────┬──────────────────────────────┬──────────────────────────────────────────────────┐
  │           Gate           │                Redis Key                 │             TTL              │                     Purpose                      │
  ├──────────────────────────┼──────────────────────────────────────────┼──────────────────────────────┼──────────────────────────────────────────────────┤
  │ 1. Cluster cooldown      │ key_cluster_cooldown:{cluster_id}        │ 60–3600s                     │ Recent action or emergency hold                  │
  ├──────────────────────────┼──────────────────────────────────────────┼──────────────────────────────┼──────────────────────────────────────────────────┤
  │ 2. Concurrency lock      │ key_rebalance_lock:{cluster_id}          │ 2700s (45min)                │ One cycle at a time                              │
  ├──────────────────────────┼──────────────────────────────────────────┼──────────────────────────────┼──────────────────────────────────────────────────┤
  │ 3. Stabilization lock    │ ClusterCooldownState (DB) + Redis        │ 60s (STABILIZATION_LOCK_TTL) │ After any node change                            │
  ├──────────────────────────┼──────────────────────────────────────────┼──────────────────────────────┼──────────────────────────────────────────────────┤
  │ 4. Substitute state      │ spot:substitute:state:{cluster_id}       │ Varies                       │ Block if PREWARMING/RELEASING                    │
  ├──────────────────────────┼──────────────────────────────────────────┼──────────────────────────────┼──────────────────────────────────────────────────┤
  │ 5. Resize cooldown       │ spot:cooldown:action:resize:{cluster_id} │ Varies                       │ Resize in progress                               │
  ├──────────────────────────┼──────────────────────────────────────────┼──────────────────────────────┼──────────────────────────────────────────────────┤
  │ 6. Double-launch guard   │ replacement_spot_instance_id in metadata │ —                            │ Skip Phase 1 if already launched                 │
  ├──────────────────────────┼──────────────────────────────────────────┼──────────────────────────────┼──────────────────────────────────────────────────┤
  │ 7. Per-node lock         │ spot:node_active_action:{instance_id}    │ 600s                         │ Prevent overlapping drains                       │
  ├──────────────────────────┼──────────────────────────────────────────┼──────────────────────────────┼──────────────────────────────────────────────────┤
  │ 8. Concurrency semaphore │ rebalance:active_count:{cluster_id}      │ 300s                         │ Max concurrent actions (default 1, configurable) │
  └──────────────────────────┴──────────────────────────────────────────┴──────────────────────────────┴──────────────────────────────────────────────────┘

  Lock #2 has a heartbeat thread that renews it every 60 seconds to survive long drain operations. Released in the finally block on completion.

  4.3 ML Pool Selection: 4-Pass Algorithm

  Pass 1 (Primary): VALUE + SAFETY
    condition: spot_price < OD_price AND risk < risk_ceiling (default 25%)
    → Most common path; best savings with acceptable risk

  Pass 2 (Tradeoff): Accept slightly worse pool
    triggered: only if Pass 1 empty
    condition: spot_price ≤ cheapest_spot + tradeoff_pct × (OD - cheapest)
               AND risk < risk_ceiling
    → Up to X% more expensive if safer (default 20%)

  Pass 3 (Risk override): Current node already risky
    triggered: only if Pass 1+2 empty AND node_risk > risk_ceiling
    condition: pool_risk < node_risk
    → Any pool safer than current is a win

  Pass 4 (Final fallback): Anything cheaper than OD
    triggered: only if Pass 1+2+3 empty
    condition: spot_price < OD_price
    → Last resort, ignores risk ceiling

  4.4 Diversification Filters (Always Active)

  Applied after ML ranking, before selecting the final target pool:

  Build occupancy maps from running instances + in-flight actions (last 10 min):
    pool_counts[(instance_type, az)]
    az_counts[az]
    fam_counts[family]

  For each candidate pool (sorted by EV desc):
    ✗ Skip if pool_counts[pool] > 0         (pool uniqueness)
    ✗ Skip if az_counts[az] / total > 50%   (AZ cap)
    ✗ Skip if strict mode AND                (family cap, only if diversify_pools=ON)
        fam_counts[family] ≥ ceil(40% × total_nodes)

  → First pool passing all filters = selected target

  The in-flight 10-minute window prevents the rebalancer from selecting a pool that a concurrent action is already targeting (the new EC2 may not appear in the DB yet).

  4.5 Failure Backoff

  Backoff formula: min(300 × 2^(failure_count - 1), 3600) seconds

  failure_count=1 → 300s  (5 min)
  failure_count=2 → 600s  (10 min)
  failure_count=3 → 1200s (20 min)
  failure_count=4 → 2400s (40 min)
  failure_count=5 → 3600s (1 hour, max)

  Counter resets if no failure in 24 hours.
  Key: rebalance_failures:{instance_id}  (TTL=86400s)

  4.6 Stale Action Cleanup

  Per-step timeouts prevent actions from hanging indefinitely:

  ┌─────────────────────────┬─────────┐
  │          State          │ Timeout │
  ├─────────────────────────┼─────────┤
  │ in_progress             │ 45 min  │
  ├─────────────────────────┼─────────┤
  │ waiting_agent           │ 10 min  │
  ├─────────────────────────┼─────────┤
  │ waiting_for_spot_node   │ 28 min  │
  ├─────────────────────────┼─────────┤
  │ cordoning_node          │ 10 min  │
  ├─────────────────────────┼─────────┤
  │ draining_pods           │ 20 min  │
  ├─────────────────────────┼─────────┤
  │ verifying_pod_readiness │ 20 min  │
  ├─────────────────────────┼─────────┤
  │ terminating_source      │ 10 min  │
  └─────────────────────────┴─────────┘

  On expiry: the orphan spot EC2 is terminated, the per-node lock is cleared, and the action is marked failed.

  ---
  5. How Auto-Scaling Integrates

  5.1 Architecture

  The ASCP built-in auto-scaler (auto_scaler.py) is optional and off by default (enable_ascp_auto_scaler = False). When enabled, it runs on the same 15-second Celery beat but is designed to be subordinate to
   the auto-rebalancer:

  - If Karpenter is in AUTO mode → auto-scaler skips (conflict avoidance)
  - If rebalancer has active actions → auto-scaler defers scale-down
  - If in-flight OD nodes being converted → auto-scaler skips scale-up bump

  5.2 Scale-Up Logic (Pending Pod Detection)

  1. Find pending pods: PodMetric records where node_name is NULL/unknown
     and created in last 3 minutes and cpu_request > 0

  2. If pending_count > 0:
     new_target = current_target + max(1, (pending_count + 9) // 10)
     (1 extra node per 10 pending pods, rounded up)

  3. Guard: if od_count > 0 (nodes being converted by rebalancer)
     → skip scale-up bump (don't double-provision)

  4. Execute: autoscaling:update_auto_scaling_group(DesiredCapacity = min(cur_desired+1, max_size))
     Set cooldown: cluster:scaler:cooldown:{cluster_id}  (TTL=30s)

  5.3 Scale-Down Logic (Utilization-Based)

  1. Gates (all must pass):
     ✓ No active rebalancing actions in DB
     ✓ running_count > min_node_count
     ✓ in_flight_od_count == 0
     ✓ scale-down stabilization window elapsed (default 15 min)

  2. Measure: avg(cpu_util) + avg(mem_util) over last 15 min for all instances
     avg_util = (avg_cpu + avg_mem) / 2

  3. If avg_util < scale_down_threshold (default 20%):
     Find the idle SPOT node with lowest cpu_util
     Create AgentAction: CORDON_NODE (reason='ascp_autoscaler_scale_down')
     Decrement Redis target: max(min_nodes, target - 1)

  Scale-down happens by evicting the idlest spot node — the agent executes the cordon, triggering Kubernetes to reschedule pods elsewhere before termination.

  5.4 Redis Target Tracking

  The auto-scaler uses a Redis key as the source of truth for desired capacity (not the ASG directly):

  ┌──────────────────────────────────────┬─────────┬─────────────────────────────────┐
  │                 Key                  │   TTL   │             Meaning             │
  ├──────────────────────────────────────┼─────────┼─────────────────────────────────┤
  │ cluster:target:{cluster_id}          │ 7 days  │ Desired node count              │
  ├──────────────────────────────────────┼─────────┼─────────────────────────────────┤
  │ cluster:last_asg_name:{cluster_id}   │ 30 days │ Last ASG used (fallback lookup) │
  ├──────────────────────────────────────┼─────────┼─────────────────────────────────┤
  │ cluster:scaler:cooldown:{cluster_id} │ 30s     │ Rate-limit on scale-up bumps    │
  └──────────────────────────────────────┴─────────┴─────────────────────────────────┘

  The ASG DesiredCapacity is only changed to match the Redis target — the Redis key is the authoritative state, not the other way around.

  ---
  6. Cross-System Coordination Map

  Auto-Rebalancer  ←→  Karpenter Service
    • PATCH_NODEPOOL AgentAction (ML types → CRD)
    • spot:ondemand_fallback key detected → skip rebalancing
    • spot:karpenter:installed key → choose Karpenter vs direct EC2 path
    • Circuit breaker (10 fails/10min) → disable Karpenter execution 30min

  Auto-Rebalancer  ←→  Right-Sizing
    • spot:cooldown:action:resize key → rebalancer defers
    • Both use rank_pools_for_* from same ranking service
    • Resize guard synergy check: validates proposed type won't be rejected by rebalancer

  Auto-Rebalancer  ←→  Auto-Scaler
    • Active rebalancing actions in DB → scaler defers scale-down
    • in_flight OD nodes → scaler skips scale-up bump
    • cluster:last_asg_name → scaler uses rebalancer's last ASG

  Right-Sizing  ←→  Auto-Scaler
    • Independent (no direct coupling)
    • Both subordinate to rebalancer's concurrency gates

  ---
  7. Key Configuration Thresholds

  ┌────────────────────────────┬──────────┬─────────────────────────────┬───────────────────────────────────────────────────┐
  │         Parameter          │ Default  │          Location           │                      Effect                       │
  ├────────────────────────────┼──────────┼─────────────────────────────┼───────────────────────────────────────────────────┤
  │ Bin-pack safety buffer     │ 30%      │ auto_rebalancer             │ Over-provision target size by 30%                 │
  ├────────────────────────────┼──────────┼─────────────────────────────┼───────────────────────────────────────────────────┤
  │ Risk ceiling               │ 25%      │ OptimizationStrategy        │ Max interruption probability for Pass 1 pools     │
  ├────────────────────────────┼──────────┼─────────────────────────────┼───────────────────────────────────────────────────┤
  │ Risk-savings tradeoff      │ 20%      │ OptimizationStrategy        │ How much more to pay for a safer pool             │
  ├────────────────────────────┼──────────┼─────────────────────────────┼───────────────────────────────────────────────────┤
  │ Family diversification cap │ 40%      │ ClusterOptimizationSettings │ Max nodes from same instance family (strict mode) │
  ├────────────────────────────┼──────────┼─────────────────────────────┼───────────────────────────────────────────────────┤
  │ AZ cap                     │ 50%      │ auto_rebalancer             │ Max nodes in a single AZ                          │
  ├────────────────────────────┼──────────┼─────────────────────────────┼───────────────────────────────────────────────────┤
  │ Spot join timeout          │ 30 min   │ ClusterOptimizationSettings │ Wait for spot node to join K8s                    │
  ├────────────────────────────┼──────────┼─────────────────────────────┼───────────────────────────────────────────────────┤
  │ Spot stabilization wait    │ 90s      │ auto_rebalancer             │ EC2 age before draining source                    │
  ├────────────────────────────┼──────────┼─────────────────────────────┼───────────────────────────────────────────────────┤
  │ Drain timeout              │ 15 min   │ ClusterOptimizationSettings │ Pod graceful eviction window                      │
  ├────────────────────────────┼──────────┼─────────────────────────────┼───────────────────────────────────────────────────┤
  │ Concurrent actions         │ 1        │ ClusterOptimizationSettings │ Simultaneous rebalances per cluster               │
  ├────────────────────────────┼──────────┼─────────────────────────────┼───────────────────────────────────────────────────┤
  │ Resize guard window        │ 2 hours  │ resize_guard_worker         │ Health monitoring post-resize                     │
  ├────────────────────────────┼──────────┼─────────────────────────────┼───────────────────────────────────────────────────┤
  │ CPU rollback threshold     │ 85%      │ resize_guard_worker         │ Trigger rollback review                           │
  ├────────────────────────────┼──────────┼─────────────────────────────┼───────────────────────────────────────────────────┤
  │ Scale-down threshold       │ 20%      │ ClusterOptimizationSettings │ Avg(cpu+mem) below which to remove a node         │
  ├────────────────────────────┼──────────┼─────────────────────────────┼───────────────────────────────────────────────────┤
  │ Scale-down stab window     │ 15 min   │ ClusterOptimizationSettings │ How long util must be low before acting           │
  ├────────────────────────────┼──────────┼─────────────────────────────┼───────────────────────────────────────────────────┤
  │ Karpenter fallback TTL     │ 12 hours │ karpenter_service           │ Auto-revert from OD mode to spot                  │
  ├────────────────────────────┼──────────┼─────────────────────────────┼───────────────────────────────────────────────────┤
  │ Failure backoff max        │ 1 hour   │ auto_rebalancer             │ Exponential ceiling per node                      │
  └────────────────────────────┴──────────┴─────────────────────────────┴───────────────────────────────────────────────────┘

