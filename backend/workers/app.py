from celery import Celery
from celery.schedules import crontab
import os
from backend.core.config import settings

app = Celery(
    "spot_optimizer",
    broker=os.getenv("CELERY_BROKER_URL", "redis://redis:6379/1"),
    backend=os.getenv("CELERY_RESULT_BACKEND", "redis://redis:6379/2"),
    include=[
        "backend.workers.tasks.discovery",
        "backend.workers.tasks.optimization",
        "backend.workers.tasks.hibernation_worker",
        "backend.workers.tasks.report_worker",
        "backend.workers.tasks.event_processor",
        "backend.scrapers.pricing_collector",
    ],
)

app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    worker_prefetch_multiplier=1,
    # Celery Beat Schedule for periodic tasks
    beat_schedule={
        # Discovery worker - scan AWS accounts every 5 minutes
        "discovery-scan-all-accounts": {
            "task": "workers.discovery.scan_all_accounts",
            "schedule": 300.0,  # 5 minutes
        },
        # Pricing collector - update spot prices every 10 minutes
        "pricing-collect-spot-prices": {
            "task": "scrapers.pricing.collect_spot_prices",
            "schedule": 600.0,  # 10 minutes
        },
        # Optimization worker - analyze clusters every 15 minutes
        "optimization-analyze-clusters": {
            "task": "workers.optimization.analyze_all_clusters",
            "schedule": 900.0,  # 15 minutes
        },
        # On-Demand pricing - daily at 1:00 AM UTC
        "pricing-collect-ondemand-prices": {
            "task": "scrapers.pricing.collect_ondemand_prices",
            "schedule": crontab(hour=1, minute=0),
        },
    },
)

if __name__ == "__main__":
    app.start()

