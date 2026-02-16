from celery import Celery
import os

app = Celery(
    "worker",
    broker=os.environ.get("REDIS_URL", "redis://localhost:6379/0"),
    backend=os.environ.get("REDIS_URL", "redis://localhost:6379/0"),
    include=[
        'backend.workers.tasks.discovery',
        'backend.workers.tasks.pricing_task',
        'backend.workers.tasks.agent_tasks',
        'backend.workers.tasks.health',
        'backend.workers.tasks.cost_calculator',
        'backend.workers.tasks.cost_explorer',
        'backend.workers.tasks.savings_calculator',
        'backend.workers.tasks.approval_cleanup',
        'backend.workers.tasks.resource_pricing_worker',
        'backend.workers.tasks.hibernation_worker'
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
        'task': 'workers.hibernation.check_schedules',
        'schedule': 60.0,  # 1 minute
    },
}
