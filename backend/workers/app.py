from celery import Celery
import os

celery_app = Celery(
    "worker",
    broker=os.environ.get("REDIS_URL", "redis://localhost:6379/0"),
    backend=os.environ.get("REDIS_URL", "redis://localhost:6379/0")
)

celery_app.conf.beat_schedule = {
    'discovery-task': {
        'task': 'backend.workers.tasks.discovery.run_discovery',
        'schedule': 300.0,
    },
}
