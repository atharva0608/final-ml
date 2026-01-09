from backend.workers.app import app

# Export as both 'app' and 'celery' for compatibility
celery = app

__all__ = ["app", "celery"]
