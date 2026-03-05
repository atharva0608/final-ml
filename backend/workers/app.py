from celery import Celery
import os

app = Celery(
    "worker",
    broker=os.environ.get("REDIS_URL", "redis://localhost:6379/0"),
    backend=os.environ.get("REDIS_URL", "redis://localhost:6379/0"),
    include=[
        'backend.workers.tasks.discovery',
        'backend.workers.tasks.pricing_task',
        'backend.workers.tasks.pricing_worker',  # NEW: Phase 1 enterprise pricing
        'backend.workers.tasks.instance_catalog_worker',  # NEW: Phase 1 instance catalog
        'backend.workers.tasks.agent_tasks',
        'backend.workers.tasks.health',
        'backend.workers.tasks.cost_calculator',
        'backend.workers.tasks.cost_explorer',
        'backend.workers.tasks.savings_calculator',
        'backend.workers.tasks.approval_cleanup',
        'backend.workers.tasks.resource_pricing_worker',
        'backend.workers.tasks.hibernation_worker',
        'backend.workers.tasks.atharvaai_worker',
        'backend.workers.tasks.termination_monitor',
        'backend.workers.tasks.auto_rebalancer',
        'backend.workers.tasks.pod_metrics_cleanup',
        'backend.workers.tasks.optimizer_coordinator_worker',  # NEW: Unified optimizer coordination
        'backend.workers.tasks.resize_guard_worker',  # NEW: Post-resize guard (Enhancement 4 & 9)
        'backend.workers.tasks.pool_rotation_worker',  # NEW: Pool auto-rotation & fresh cache
        'backend.workers.tasks.control_plane_loop',  # NEW: 8-step control plane
        'backend.workers.tasks.maintain_warm_spare_worker',  # NEW: 24x7 warm spare maintenance
    ]
)

app.conf.beat_schedule = {
    # Existing discovery task
    'discovery-every-5-mins': {
        'task': 'workers.discovery.scan_all_accounts',
        'schedule': 300.0,
    },
    # Pricing task
    'pricing-every-hour': {
        'task': 'backend.workers.tasks.pricing.fetch_aws_pricing',
        'schedule': 3600.0,
    },
    # NEW: Zombie Node Cleanup (2 mins)
    'zombie-cleanup-every-2-mins': {
        'task': 'backend.workers.tasks.health.cleanup_zombie_nodes',
        'schedule': 120.0,
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
    # Savings Calculator (12 hours) - Calculates real potential and realized savings
    'savings-calculator-every-12-hours': {
        'task': 'workers.savings.calculate_real_savings',
        'schedule': 43200.0,
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
    # Spot Price Collection (Every 10 minutes) - Collects historical spot prices for ML features
    # FIXED: Now uses real AWS pricing scraper instead of mock data
    'spot-price-collection-every-10-mins': {
        'task': 'backend.workers.tasks.pricing.fetch_aws_pricing',
        'schedule': 600.0,  # 10 minutes
    },
    # Termination Monitor (Every 30 seconds) - Monitors spot termination notices and updates blacklist
    'termination-monitor-every-30-secs': {
        'task': 'workers.termination_monitor',
        'schedule': 30.0,  # 30 seconds
    },
    # Auto-Rebalancer (Every 15 seconds) - Executes auto-rebalancing actions for flagged pools
    'auto-rebalancer-every-15-secs': {
        'task': 'workers.auto_rebalancer',
        'schedule': 15.0,  # 15 seconds
    },
    # Karpenter NodePool Sync (Every 30 seconds) - Syncs ML rankings to Karpenter NodePools
    'karpenter-nodepool-sync-every-30-secs': {
        'task': 'workers.atharvaai.sync_karpenter_nodepools',
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
    # PHASE 1 REMEDIATION: Instance Catalog Refresh (Nightly at 3 AM UTC) - Live AWS instance specifications
    'instance-catalog-refresh-nightly': {
        'task': 'workers.instance_catalog.refresh_catalog',
        'schedule': 86400.0,  # 24 hours
    },
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
}
