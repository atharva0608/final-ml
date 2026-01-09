from celery import Celery
import os

app = Celery(
    "worker",
    broker=os.environ.get("REDIS_URL", "redis://localhost:6379/0"),
    backend=os.environ.get("REDIS_URL", "redis://localhost:6379/0"),
    include=['backend.workers.tasks.discovery', 'backend.workers.tasks.pricing_task']
)

app.conf.beat_schedule = {
    # Existing discovery task
    'discovery-every-5-mins': {
        'task': 'workers.discovery.scan_all_accounts', # Matches discovery.py name
        'schedule': 300.0, # 5 minutes
    },
    # NEW: Pricing task
    'pricing-every-hour': {
        'task': 'backend.workers.tasks.pricing.fetch_aws_pricing', # Matches pricing_task.py name
        'schedule': 3600.0, # 1 hour
    },
}
