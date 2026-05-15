from celery import Celery
from celery.schedules import crontab
import os

app = Celery(
    "worker",
    broker=os.environ.get("REDIS_URL", "redis://localhost:6379/0"),
    backend=os.environ.get("REDIS_URL", "redis://localhost:6379/0"),
    include=[
        'backend.workers.tasks.discovery',
        'backend.workers.tasks.pricing_worker',  # Phase 1 enterprise pricing (replaces legacy pricing_task)
        'backend.workers.tasks.instance_catalog_worker',  # NEW: Phase 1 instance catalog
        'backend.workers.tasks.agent_tasks',
        'backend.workers.tasks.health',
        'backend.workers.tasks.cost_calculator',
        'backend.workers.tasks.cost_explorer',
        'backend.workers.tasks.savings_calculator',
        'backend.workers.tasks.approval_cleanup',
        'backend.workers.tasks.resource_pricing_worker',
        'backend.workers.tasks.hibernation_worker',
        'backend.workers.tasks.ascpai_worker',
        'backend.workers.tasks.termination_monitor',
        'backend.workers.tasks.auto_rebalancer',
        'backend.workers.tasks.pod_metrics_cleanup',
        'backend.workers.tasks.optimizer_coordinator_worker',  # NEW: Unified optimizer coordination
        'backend.workers.tasks.resize_guard_worker',  # NEW: Post-resize guard (Enhancement 4 & 9)
        'backend.workers.tasks.pool_rotation_worker',  # NEW: Pool auto-rotation & fresh cache
        'backend.workers.tasks.control_plane_loop',  # NEW: 8-step control plane
        'backend.workers.tasks.maintain_warm_spare_worker',  # NEW: 24x7 warm spare maintenance
        'backend.workers.tasks.sqs_consumer',               # NEW: SQS spot interrupt consumer
        'backend.workers.tasks.cache_warmer',                # DE: Pre-warm pool rankings
        'backend.workers.tasks.dry_run_refresher',           # DE: Refresh dry-run cache
        'backend.workers.tasks.standby',                     # EE: Launch standby node
        'backend.workers.tasks.emergency_rebalancer',        # EE: Standby-aware emergency
        'backend.workers.tasks.recovery_monitor',            # EE: Detect orphaned instances
        'backend.workers.tasks.daily_stats_aggregator',      # Multi-Cluster: Rollup stats
        'backend.workers.tasks.auto_scaler',                  # ASCP: built-in optional auto-scaler
        'backend.workers.tasks.reconciliation_worker',        # Issue #34: EC2 vs DB reconciliation
        'backend.workers.tasks.health_monitor',              # Pillar 5: health scores + drift detection
        'backend.workers.tasks.cache_builder',               # Global pool rankings cache builder
        'backend.workers.tasks.global_ema_tasks',            # Global EMA: persist + decay
        'backend.workers.tasks.cleanup_tasks',               # Migration: managed node group cleanup
        'backend.workers.tasks.adaptive_itn_tasks',          # Adaptive ITN: hourly decay + Postgres flush
        'backend.workers.tasks.keda_installer',              # K2: KEDA install/uninstall lifecycle monitor
        'backend.workers.tasks.placement_advisor_task',      # Placement Advisor: core execution cycle
        'backend.workers.tasks.placement_controller_task',     # Placement Controller: pod-level eviction + shadow mode
        'backend.workers.tasks.workload_cv_task',               # T-07: 14-day CPU CV computation
        'backend.workers.tasks.hpa_recommendation_task',          # T-16: HPA recommended replicas
        'backend.workers.tasks.consolidation_analysis_task',       # T-18: Consolidation candidates
        'backend.workers.tasks.validate_actions_task',              # Real-time EVICT_POD convergence validator
    ]
)

app.conf.beat_schedule = {
    # Real-time EVICT_POD convergence validator — every 15 seconds
    'validate-eviction-actions-every-15s': {
        'task': 'validate_eviction_actions',  # registered name in validate_actions_task.py
        'schedule': 15.0,
    },
    # T-07: Workload CPU CV computation — every 10 minutes
    'workload-cv-every-10-mins': {
        'task': 'backend.workers.tasks.workload_cv_task.compute_workload_cv',
        'schedule': 600.0,
    },
    # T-16: HPA recommended replicas computation — every 30 minutes
    'hpa-recommendation-every-30-mins': {
        'task': 'backend.workers.tasks.hpa_recommendation_task.compute_hpa_recommendations',
        'schedule': 1800.0,
    },
    # T-18: Consolidation candidate analysis — every 10 minutes
    'consolidation-analysis-every-10-mins': {
        'task': 'backend.workers.tasks.consolidation_analysis_task.run_consolidation_analysis',
        'schedule': 600.0,
    },
    # Existing discovery task
    'discovery-every-5-mins': {
        'task': 'workers.discovery.scan_all_accounts',
        'schedule': 300.0,
    },
    # NOTE: legacy fetch_aws_pricing removed — replaced by pricing_worker.py tasks below
    # NEW: Zombie Node Cleanup (2 mins)
    'zombie-cleanup-every-2-mins': {
        'task': 'backend.workers.tasks.health.cleanup_zombie_nodes',
        'schedule': 120.0,
    },
    # Z1 fix: Zombie OD Instance Cleanup (hourly) — terminates OD instances with no K8s node after 10 min
    'zombie-od-cleanup-hourly': {
        'task': 'backend.workers.tasks.health.cleanup_zombie_od_instances',
        'schedule': 3600.0,
    },
    # Z5 fix: Cluster Pools Sync (30 min) — rebuilds cluster_pools Redis sets from DB state
    'sync-cluster-pools-every-30-mins': {
        'task': 'backend.workers.tasks.health.sync_cluster_pools',
        'schedule': 1800.0,
    },
    # Agent Stale Detection (1 min) — resets agent_installed when heartbeat >5 min old
    'reset-stale-agents-every-minute': {
        'task': 'backend.workers.tasks.health.reset_stale_agents',
        'schedule': 60.0,
    },
    # NEW: Reversion Check (1 hour)
    'reversion-check-every-hour': {
        'task': 'backend.workers.tasks.health.check_reversion_opportunities',
        'schedule': 3600.0,
    },
    # Cost Calculator (15 mins) - Updates cluster costs from instance prices
    'cost-calculator-every-15-mins': {
        'task': 'workers.cost.calculate_cluster_costs',
        'schedule': 900.0,
    },
    # Savings Calculator (30 min) - Calculates real potential and realized savings
    'savings-calculator-every-30-mins': {
        'task': 'workers.savings.calculate_real_savings',
        'schedule': 1800.0,
    },
    # Approval Cleanup (5 mins) - Marks expired approvals as EXPIRED
    'approval-cleanup-every-5-mins': {
        'task': 'workers.approval.cleanup_expired',
        'schedule': 300.0,
    },
    # Cost Explorer Sync (Daily at 8 AM UTC) - Fetches accurate AWS costs from Cost Explorer API
    'cost-explorer-sync-daily': {
        'task': 'workers.cost.sync_cost_explorer',
        'schedule': 86400.0,  # 24 hours
    },
    # Cost Explorer Cleanup (Weekly) - Deletes cost data older than 90 days
    'cost-explorer-cleanup-weekly': {
        'task': 'workers.cost.cleanup_old_cost_data',
        'schedule': 604800.0,  # 7 days
    },
    # Resource Pricing Refresh (Daily) - Updates individual resource costs in Redis cache
    'resource-pricing-refresh-daily': {
        'task': 'workers.pricing.refresh_all_resource_prices',
        'schedule': 86400.0,  # 24 hours
    },
    # Multi-Cluster Daily Aggregation (Daily) - Rolls up cluster stats
    'multi-cluster-daily-stats': {
        'task': 'backend.workers.tasks.daily_stats_aggregator.aggregate_daily_stats',
        'schedule': 86400.0,  # 24 hours
    },
    # Hibernation Scheduler (Every 1 minute) - Checks schedules and triggers sleep/wake actions
    'hibernation-scheduler-every-1-min': {
        'task': 'execute_hibernation_scheduler',
        'schedule': 60.0,  # 1 minute
    },
    # UNIFIED OPTIMIZER: Pool Optimization (Every 30 minutes) - Coordinator-aware Spot ML
    # Per problems.md: Frequent pool optimization is safe (only changes pool, not size)
    'unified-pool-optimization-every-30-mins': {
        'task': 'workers.optimizer.pool_optimization',
        'schedule': 1800.0,  # 30 minutes (was 30 seconds - FIXED!)
    },
    # UNIFIED OPTIMIZER: Rightsizing Evaluation (Every 24 hours) - Proposes size changes
    # Per problems.md: Requires ≥24h stability window, only proposes (does not execute)
    'unified-rightsizing-evaluation-daily': {
        'task': 'workers.optimizer.rightsizing_evaluation',
        'schedule': 86400.0,  # 24 hours
    },
    # POST-RESIZE GUARD: Monitors clusters for 2h after resize (Enhancement 4 & 9)
    # Checks CPU stress, pod restarts, memory pressure → triggers rollback if needed
    'resize-guard-every-5-mins': {
        'task': 'workers.optimizer.resize_guard',
        'schedule': 300.0,  # 5 minutes
    },
    # POD RESTART BASELINE: Updates baseline restart rate every hour (Enhancement 9)
    # Used by resize guard to detect anomalous restart spikes
    'update-restart-baseline-hourly': {
        'task': 'workers.optimizer.update_pod_restart_baseline',
        'schedule': 3600.0,  # 1 hour
    },
    # Spot prices covered by pricing_worker.py:
    #   regional-pricing-refresh-every-10-mins  (refresh_regional_pricing)
    #   spot-price-ingest-every-10-mins         (ingest_spot_prices)
    # Termination Monitor (Every 30 seconds) - Monitors spot termination notices and updates blacklist
    'termination-monitor-every-30-secs': {
        'task': 'workers.termination_monitor',
        'schedule': 30.0,  # 30 seconds
    },
    # Auto-Rebalancer (Every 60 seconds) - Executes auto-rebalancing actions for flagged pools
    # Increased from 15s: task is CPU-heavy (spawns cache_builder inline), 15s caused 180%+ CPU
    'auto-rebalancer-every-60-secs': {
        'task': 'workers.auto_rebalancer',
        'schedule': 60.0,  # 60 seconds (was 15s)
    },
    # Fix 16: Rebalancer Reconciliation (Every 5 minutes) - Detects and resolves stuck actions
    'rebalancer-reconciliation-every-5-min': {
        'task': 'workers.rebalancer_reconciliation',
        'schedule': 300.0,  # 5 minutes
    },
    # ASCP Auto-Scaler (Every 30 seconds) - Optional built-in scaler (off by default per cluster)
    'ascp-auto-scaler-every-30-secs': {
        'task': 'workers.auto_scaler.run',
        'schedule': 30.0,
    },
    # Karpenter NodePool Sync (Every 30 seconds) - Syncs ML rankings to Karpenter NodePools
    'karpenter-nodepool-sync-every-30-secs': {
        'task': 'workers.ascpai.sync_karpenter_nodepools',
        'schedule': 30.0,  # 30 seconds
    },
    # Pod Metrics Cleanup (Daily at 2 AM UTC) - Deletes metrics older than 7 days
    'pod-metrics-cleanup-daily': {
        'task': 'workers.pod_metrics.cleanup_old_metrics',
        'schedule': 86400.0,  # 24 hours
    },
    # PHASE 1 REMEDIATION: Regional Pricing Refresh (Every 10 minutes) - Enterprise pricing freshness guarantee
    'regional-pricing-refresh-every-10-mins': {
        'task': 'workers.pricing.refresh_regional_pricing',
        'schedule': 600.0,  # 10 minutes (15-min freshness threshold)
    },
    # Instance catalog refresh is registered below via crontab(3 AM) as 'instance-catalog-refresh-daily-3am'
    # (GAP-14 fix: removed duplicate 86400s interval entry to prevent double-fire)
    # POOL AUTO-ROTATION: Check rotation status for all clusters (Every 5 minutes) - Maintains fresh pool availability
    'pool-rotation-check-every-5-mins': {
        'task': 'pool_rotation.check_all_clusters',
        'schedule': 300.0,  # 5 minutes
    },
    # POOL AUTO-ROTATION: Refresh fresh pool caches (Every 15 minutes) - Proactive cache warming
    'pool-cache-refresh-every-15-mins': {
        'task': 'pool_rotation.refresh_all_caches',
        'schedule': 900.0,  # 15 minutes
    },
    # PLACEMENT CONTROLLER: Per-cluster pod-level spot eviction + stateful rollout (every 5 minutes)
    # Only executes when FEATURE_PLACEMENT_CONTROLLER_ENABLED=True in settings
    'placement-controller-every-5-mins': {
        'task': 'dispatch_placement_controller_cycles',
        'schedule': 300.0,  # 5 minutes
    },
    # PLACEMENT CONTROLLER RECOVERY: Stale migration + pending completion revalidation (hourly)
    'placement-controller-recovery-hourly': {
        'task': 'dispatch_placement_controller_recovery',
        'schedule': 3600.0,  # 1 hour
    },
    # CONTROL PLANE: Full 8-step decision cycle (every 5 minutes)
    'control-plane-all-clusters-every-5-mins': {
        'task': 'workers.control_plane.run_all_clusters_decision_cycle',
        'schedule': 300.0,  # 5 minutes
    },
    # WARM SPARE: Maintain 24x7 persistent substitute node (every 5 minutes)
    # Ensures ≥1 spot spare is always READY for zero-downtime node migrations
    'warm-spare-maintain-every-5-mins': {
        'task': 'warm_spare.maintain_all_clusters',
        'schedule': 300.0,  # 5 minutes
    },
    # SQS INTERRUPT CONSUMER: Poll spot interruption queues (every 30 seconds)
    # Triggers emergency rebalancing before the 2-minute spot interruption window closes
    'sqs-interrupt-consumer-every-30-secs': {
        'task': 'workers.sqs_consumer.poll_interruption_queues',
        'schedule': 30.0,  # 30 seconds
    },
    # DE: Cache Warmer (hourly) - Pre-compute rankings for common profiles
    'de-cache-warmer-hourly': {
        'task': 'cache_warmer',
        'schedule': 3600.0,  # 1 hour
    },
    # DE: Dry-Run Refresher (5 min) - Refresh capacity status for top pools
    'de-dryrun-refresher-every-5-mins': {
        'task': 'dry_run_refresher',
        'schedule': 300.0,  # 5 minutes
    },
    # DE: Verified Pool Set maintenance (5 min) - Maintain per-cluster capacity-confirmed pool sets
    'de-verified-pools-every-5-mins': {
        'task': 'maintain_all_verified_pool_sets',
        'schedule': 300.0,  # 5 minutes
    },
    # EE: Recovery Monitor (60 sec) - Detect orphaned instances and trigger recovery
    'ee-recovery-monitor-every-60-secs': {
        'task': 'recovery_monitor',
        'schedule': 60.0,  # 60 seconds
    },
    # EE: Cluster coverage computation (5 min) - Compute per-cluster spot pool coverage
    'ee-cluster-coverage-every-5-mins': {
        'task': 'backend.workers.tasks.recovery_monitor.compute_all_cluster_coverage',
        'schedule': 300.0,  # 5 minutes
    },
    # Orphan instance scan (every 5 minutes)
    'recovery-monitor-scan-every-5-mins': {
        'task': 'backend.workers.tasks.recovery_monitor.scan_orphans',
        'schedule': 300.0,
    },
    # Global pool cache rebuild (every hour) — ap-south-1
    'global-pool-cache-rebuild-ap-south-1': {
        'task': 'build_global_pool_cache',
        'schedule': 3600.0,
        'args': ['ap-south-1'],
    },
    # Global pool cache rebuild — us-east-1
    'global-pool-cache-rebuild-us-east-1': {
        'task': 'build_global_pool_cache',
        'schedule': 3600.0,
        'args': ['us-east-1'],
    },
    # Global pool cache rebuild — ap-southeast-1
    'global-pool-cache-rebuild-ap-southeast-1': {
        'task': 'build_global_pool_cache',
        'schedule': 3600.0,
        'args': ['ap-southeast-1'],
    },
    # Global EMA decay — daily at 2 AM (30-day half-life decay of all pool interruption rates)
    'global-ema-decay-daily': {
        'task': 'global_ema.decay',
        'schedule': crontab(minute=0, hour=2),
    },
    # Adaptive ITN ledger decay — hourly: increment node-hours, decay raw scores, flush to Postgres
    'adaptive-itn-decay-hourly': {
        'task': 'adaptive_itn.decay_scores',
        'schedule': 3600.0,  # 1 hour
    },
    # C6: Accumulate global node-hours (runs 5 min before decay so accumulator is ready)
    'adaptive-itn-accumulate-node-hours': {
        'task': 'adaptive_itn.accumulate_node_hours',
        'schedule': crontab(minute=55),  # :55 of every hour
    },
    # Spot advisor scrape — every 12h (Bug 3: was daily/4h; 12h keeps data under 6h stale gate)
    # Re-writes all Redis keys each run to refresh 12h TTLs.
    'spot-advisor-scrape-12h': {
        'task': 'scrapers.spot_advisor.scrape',
        'schedule': 43200.0,  # 12 hours
    },
    # Instance catalog refresh — us-east-1 (daily at 3:00 AM UTC)
    'instance-catalog-refresh-daily-3am': {
        'task': 'workers.instance_catalog.refresh_catalog',
        'schedule': crontab(minute=0, hour=3),
        'args': ['us-east-1'],
    },
    # Instance catalog refresh — ap-south-1 (daily at 3:05 AM UTC)
    # Required: bin-pack + pool ranking falls back to 30-type hardcoded dict
    # without a live catalog for the cluster's actual region.
    'instance-catalog-refresh-ap-south-1': {
        'task': 'workers.instance_catalog.refresh_catalog',
        'schedule': crontab(minute=5, hour=3),
        'args': ['ap-south-1'],
    },
    # Instance catalog refresh — us-west-2 (daily at 3:10 AM UTC)
    'instance-catalog-refresh-us-west-2': {
        'task': 'workers.instance_catalog.refresh_catalog',
        'schedule': crontab(minute=10, hour=3),
        'args': ['us-west-2'],
    },
    # Instance catalog refresh — ap-southeast-1 (daily at 3:15 AM UTC)
    'instance-catalog-refresh-ap-southeast-1-catalog': {
        'task': 'workers.instance_catalog.refresh_catalog',
        'schedule': crontab(minute=15, hour=3),
        'args': ['ap-southeast-1'],
    },
    # On-demand price refresh (every 12 hours)
    'ondemand-price-refresh-12h': {
        'task': 'workers.pricing.refresh_ondemand',
        'schedule': 43200.0,
    },
    # Spot price ingest (every 10 minutes)
    'spot-price-ingest-every-10-mins': {
        'task': 'workers.pricing.ingest_spot_prices',
        'schedule': 600.0,
    },
    # Circuit breaker audit (every 10 minutes)
    'circuit-breaker-audit-every-10-mins': {
        'task': 'circuit_breaker.audit_log',
        'schedule': 600.0,
    },
    # Pillar 5: Cluster Health Monitor (every 5 minutes) — per-cluster health scores + drift alerts
    'health-monitor-every-5-mins': {
        'task': 'health_monitor',
        'schedule': 300.0,  # 5 minutes
    },
    # Pillar 5: Drift Detector (every 15 minutes) — stuck actions, stale data, savings gap checks
    'drift-detector-every-15-mins': {
        'task': 'drift_detector',
        'schedule': 900.0,  # 15 minutes
    },
    # Issue #34: Reconciliation Worker (every 5 minutes) — EC2 vs DB instance state reconciliation
    'reconciliation-worker-every-5-mins': {
        'task': 'workers.reconciliation_worker',
        'schedule': 300.0,
    },
    # Issue #23: Ghost Nodes Table Cleanup (nightly at 3:30 AM UTC) — purge terminated rows >30 days
    'cleanup-terminated-instances-nightly': {
        'task': 'workers.cleanup_terminated_instances',
        'schedule': crontab(minute=30, hour=3),
    },
    # §10: Migration Event Cleanup (nightly at 3:45 AM UTC) — purge migration_event rows >30 days
    'cleanup-migration-events-nightly': {
        'task': 'workers.cleanup_old_migration_events',
        'schedule': crontab(minute=45, hour=3),
    },
    # W3.0e: NodePool type reconciliation (every 6 hours) — remove orphaned injected instance types
    'reconcile-nodepool-types-every-6h': {
        'task': 'workers.karpenter.reconcile_nodepool_types',
        'schedule': crontab(minute=0, hour='*/6'),
    },
    # Placement Controller: dispatcher enumerates all clusters and dispatches per-cluster tasks (every 5 minutes)
    # Shadow mode: SET spot:placement_controller:shadow_mode:{cluster_id} 1  → metrics only
    # Live mode:   DEL spot:placement_controller:shadow_mode:{cluster_id}    → evictions enabled
    'placement-controller-dispatch-every-5-mins': {
        'task': 'dispatch_placement_controller_cycles',  # registered name in placement_controller_task.py
        'schedule': 300.0,  # 5 minutes
    },
    # Placement Controller: stale migration recovery dispatcher (hourly) — §9 Risk 1
    'placement-controller-recovery-dispatch-hourly': {
        'task': 'dispatch_placement_controller_recovery',  # registered name in placement_controller_task.py
        'schedule': 3600.0,  # 1 hour
    },
    # K2.5: KEDA install/uninstall lifecycle monitor (every 30 seconds)
    'keda-install-monitor-every-30-secs': {
        'task': 'workers.keda.monitor_install_actions',
        'schedule': 30.0,
    },
    # W7.8: Stale autoscaler freeze cleanup (every 5 minutes)
    'stale-autoscaler-freeze-cleanup-every-5-mins': {
        'task': 'workers.keda.cleanup_stale_autoscaler_freezes',
        'schedule': 300.0,
    },
}

app.conf.task_routes = {
    # ── Agent installation queue (user-triggered, must not wait in backlog) ───
    'workers.agent.inject_agent': {'queue': 'agent'},
    'backend.workers.tasks.agent_tasks.inject_agent_task': {'queue': 'agent'},

    # ── High-priority emergency queue ─────────────────────────────────────────
    # Emergency tasks MUST run within milliseconds of dispatch.
    # They must NEVER share a queue with heavy batch jobs (pricing ingest,
    # ML feature generation, cluster syncs) which can block the worker for
    # minutes and waste the 2-minute AWS spot interruption window.
    # Start the emergency worker with:
    #   celery -A backend.workers.app worker -Q emergency -c 4 --prefetch-multiplier=1
    'emergency_rebalancer': {'queue': 'emergency'},
    'backend.workers.tasks.emergency_rebalancer.emergency_rebalancer': {'queue': 'emergency'},
    'workers.sqs_consumer.poll_interruption_queues': {'queue': 'emergency'},
    'backend.workers.tasks.sqs_consumer.*': {'queue': 'emergency'},

    # ── Standard queues ────────────────────────────────────────────────────────
    'workers.pricing.*': {'queue': 'pricing'},
    'scrapers.*': {'queue': 'pricing'},
    'backend.workers.tasks.recovery_monitor.*': {'queue': 'monitoring'},
    'circuit_breaker.*': {'queue': 'monitoring'},
}
