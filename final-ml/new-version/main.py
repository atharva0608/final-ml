"""
Main Application Entry Point

Run the FastAPI application with Uvicorn
"""
import uvicorn
from backend.core.config import settings
from backend.core.logger import StructuredLogger

logger = StructuredLogger(__name__)


def main():
    """
    Start the Uvicorn server
    """
    logger.info(
        "Starting Spot Optimizer Platform",
        environment=settings.ENVIRONMENT,
        version=settings.APP_VERSION
    )

    # Uvicorn configuration
    uvicorn_config = {
        "app": "backend.core.api_gateway:app",
        "host": "0.0.0.0",
        "port": 8000,
        "reload": settings.is_development(),
        "log_level": settings.LOG_LEVEL.lower(),
        "workers": 1 if settings.is_development() else settings.WORKER_THREADS,
        "proxy_headers": True,
        "forwarded_allow_ips": "*",
    }

    # Run server
    uvicorn.run(**uvicorn_config)


if __name__ == "__main__":
    main()
