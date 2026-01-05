from celery import Celery
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
)

if __name__ == "__main__":
    app.start()
