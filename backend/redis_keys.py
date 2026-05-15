"""
REDIS KEY REGISTRY — Spot Optimizer Platform
=============================================

EXISTING KEYS (pre-hardening):
spot:cooldown:cluster:{id}          TTL: 60min    CooldownController
spot:cooldown:pool:{pool_id}        TTL: 120min   CooldownController
spot:cooldown:resize:{id}           TTL: 360min   CooldownController
spot:cooldown:pool_switch:{id}      TTL: 30min    CooldownController
spot:cooldown:substitute:{id}       TTL: 120min   CooldownController
spot:node_classification:{id}       TTL: 10min    WorkloadInspector
spot:cluster_mode:{id}              TTL: 300s     DecisionEngine
spot:global_rankings:{region}       TTL: 65min    GlobalPoolCacheService
spot:volatility_regime:{region}     TTL: 2h       EventMonitor
spot:substitute:state:{id}          TTL: Variable SubstituteManager
spot:dryrun_count:{region}          TTL: 1h       PoolRankingService
spot:dryrun_failures_24h:{pool}     TTL: 24h      PoolRankingService
hibernation:lock:{sched}:{cluster}  TTL: 180s     HibernationWorker
ascpai:ml_fail_count             TTL: 10min    PoolRankingService
ascpai:ml_degraded               TTL: 10min    PoolRankingService

NEW KEYS (added by hardening):
spot:cluster_state:{cluster_id}     TTL: NONE     risk_engine.py
spot:rankings_version:{region}      TTL: NONE     multiple invalidators
spot:stabilization_lock:{cluster_id} TTL: 15min   cooldown_controller.py
spot:execution_plan:{cluster_id}    TTL: 1h       control_plane_loop.py
spot:org_spend_state:{org_id}       TTL: 1h       billing_service.py
spot:rejection_counter:{id}:{reason} TTL: 24h     decision_engine.py
spot:config:org_velocity_threshold  TTL: NONE     config (manually set)

KEDA + SMART WORKLOAD ENGINE KEYS (K1 / W1 / W2 / W3 / W5):

K1 — KEDA Detection
spot:keda_detection:{cluster_id}            TTL: 300s   keda_service.detect_installation()
                                            Read by:    keda_routes.py, integrations_routes.py
spot:keda_paused_state:{ns}/{name}          TTL: 600s   keda_service.pause_scaled_object()
                                            Read by:    keda_service.restore_scaled_object()
spot:keda_installing:{cluster_id}           TTL: 300s   keda_service.install_keda()  [K2]
                                            Read by:    keda_service.detect_installation()

W1/W2 — Workload Tier Classification
spot:workload_tier:{cluster_id}:{ns}/{ctrl} TTL: 540s   workload_inspector.build_workload_profile()
                                            Read by:    auto_rebalancer.py, eviction_safety.py,
                                                        optimizer_coordinator_worker.py
spot:workload_profile:{cluster_id}:{ns}/{ctrl} TTL:540s workload_inspector (EXISTING, extended with tier fields)

W3 — Anchored Node Scheduling  [future]
spot:anchored_nodes:{cluster_id}            TTL: 300s   anchored_node_service.py
                                            Read by:    auto_rebalancer.py, control_plane_loop.py
spot:anchored_fill:{cluster_id}             TTL: 120s   anchored_node_service.py
                                            Read by:    control_plane_loop.py, cluster_routes.py

Karpenter NodePool type tracking (W3.0c-e)
karpenter:nodepool_baseline:{cluster_id}:{nodepool} TTL: 86400s (24h)  karpenter_service.add_allowed_instance_type()
spot:injected_type:{cluster_id}:{nodepool}:{type}   TTL: 7200s  (2h)   karpenter_service.add_allowed_instance_type()
                                            Read by:    reconcile_nodepool_types Celery task

W5 — KEDA Queue Gate  [future]
spot:queue_baseline:{ns}/{ctrl}             TTL: 3600s  eviction_safety.queue_allows_migration()
spot:migration_ready:{cluster_id}:{ns}/{ctrl} TTL:300s  eviction_safety.queue_allows_migration()
                                            Read by:    auto_rebalancer.py

W7 — HPA/KEDA Freeze  [future]
spot:autoscaler_freeze:{ns}/{ctrl}          TTL: 180s   eviction_safety.freeze_autoscaler()
                                            Read by:    eviction_safety.restore_autoscaler(),
                                                        reconciliation cleanup task
"""


# ── Key builder helpers ───────────────────────────────────────────────────────
# Use these instead of hand-constructing key strings to avoid typos.

def keda_detection_key(cluster_id: str) -> str:
    return f"spot:keda_detection:{cluster_id}"

def keda_paused_state_key(namespace: str, name: str) -> str:
    return f"spot:keda_paused_state:{namespace}/{name}"

def keda_installing_key(cluster_id: str) -> str:
    return f"spot:keda_installing:{cluster_id}"

def workload_tier_key(cluster_id: str, namespace: str, controller_name: str) -> str:
    return f"spot:workload_tier:{cluster_id}:{namespace}/{controller_name}"

def workload_profile_key(cluster_id: str, namespace: str, controller_name: str) -> str:
    return f"spot:workload_profile:{cluster_id}:{namespace}/{controller_name}"

def nodepool_baseline_key(cluster_id: str, nodepool_name: str) -> str:
    return f"karpenter:nodepool_baseline:{cluster_id}:{nodepool_name}"

def injected_type_key(cluster_id: str, nodepool_name: str, instance_type: str) -> str:
    return f"spot:injected_type:{cluster_id}:{nodepool_name}:{instance_type}"

def anchored_nodes_key(cluster_id: str) -> str:
    return f"spot:anchored_nodes:{cluster_id}"

def anchored_fill_key(cluster_id: str) -> str:
    return f"spot:anchored_fill:{cluster_id}"

def queue_baseline_key(namespace: str, controller_name: str) -> str:
    return f"spot:queue_baseline:{namespace}/{controller_name}"

def migration_ready_key(cluster_id: str, namespace: str, controller_name: str) -> str:
    return f"spot:migration_ready:{cluster_id}:{namespace}/{controller_name}"

def autoscaler_freeze_key(namespace: str, controller_name: str) -> str:
    return f"spot:autoscaler_freeze:{namespace}/{controller_name}"

# ── Phase 2 Placement Advisor Keys ───────────────────────────────────────────

def placement_policy_key(cluster_id: str, workload_id: str) -> str:
    return f"spot:placement:policy:{cluster_id}:{workload_id}"

def placement_cluster_state_key(cluster_id: str) -> str:
    return f"spot:placement:cluster_state:{cluster_id}"

def placement_spot_availability_key(region: str) -> str:
    return f"spot:placement:spot_availability:{region}"

def placement_spot_availability_az_key(region: str, az: str) -> str:
    return f"spot:placement:spot_availability_az:{region}:{az}"

def placement_scheduling_success_key(instance_type: str, window: str) -> str:
    # window should be '15m' or '120m'
    return f"spot:placement:scheduling_success:{instance_type}:{window}"

def placement_provision_p90_key(nodepool_class: str) -> str:
    return f"spot:placement:provision_p90:{nodepool_class}"

def placement_metrics_key(cluster_id: str) -> str:
    return f"spot:placement:metrics:{cluster_id}"

def placement_cycle_lock_key(cluster_id: str) -> str:
    return f"spot:placement:cycle_lock:{cluster_id}"

def placement_stability_key(cluster_id: str, workload_id: str) -> str:
    return f"spot:placement:stability:{cluster_id}:{workload_id}"

def agent_data_pod_metrics_key(cluster_id: str) -> str:
    return f"spot:placement:agent_data:{cluster_id}:pod_metrics"

def agent_data_cluster_spot_summary_key(cluster_id: str) -> str:
    return f"spot:placement:agent_data:{cluster_id}:cluster_spot_summary"

def agent_data_hpa_pdb_key(cluster_id: str) -> str:
    return f"spot:placement:agent_data:{cluster_id}:hpa_pdb"

def subnet_ips_key(cluster_id: str, az: str) -> str:
    return f"spot:placement:subnet_ips:{cluster_id}:{az}"


# ---------------------------------------------------------------------------
# P-03 — Unified Redis TTL Registry
# All expire() / setex() calls MUST reference this dict.
# Do NOT change values here without explicit sign-off — changing TTLs affects
# cooldown windows, cache freshness, and cleanup schedules.
# ---------------------------------------------------------------------------

REDIS_TTL: dict = {
    "workload_state":           300,
    "workload_log":             3600,
    "pc_metrics":               3600,
    "pc_workload_metrics":      3600,
    "placement_summary":        60,
    "cooldown":                 600,
    "rollout_blocked":          14400,
    "keda_last_scale":          120,
    "consolidation_candidates": 600,
    "instance_price":           3600,
    "cluster_mutex":            60,
    "workload_lock":            30,
    "rebalance_active_count":   300,
    "ondemand_fallback":        43200,
}
