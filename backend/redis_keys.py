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
"""
