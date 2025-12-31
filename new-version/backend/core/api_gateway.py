"""
FastAPI Application Gateway

Main application configuration with middleware, error handlers, and route registration
"""
from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
import time
from backend.core.config import settings, get_cors_origins
from backend.core.exceptions import SpotOptimizerException
from backend.core.logger import StructuredLogger, log_request
from backend.api import auth_router

logger = StructuredLogger(__name__)

# Create FastAPI application
app = FastAPI(
    title=settings.APP_NAME,
    description="Spot Optimizer Platform - AWS Spot Instance Management for Kubernetes",
    version=settings.APP_VERSION,
    docs_url="/docs" if not settings.is_production() else None,
    redoc_url="/redoc" if not settings.is_production() else None,
    openapi_url="/openapi.json" if not settings.is_production() else None,
)


# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=get_cors_origins(),
    allow_credentials=settings.CORS_ALLOW_CREDENTIALS,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["*"],
    expose_headers=["X-Total-Count", "X-Page", "X-Page-Size"],
)


# Request logging middleware
@app.middleware("http")
async def log_requests(request: Request, call_next):
    """Log all HTTP requests with timing"""
    start_time = time.time()

    # Process request
    response = await call_next(request)

    # Calculate duration
    duration_ms = (time.time() - start_time) * 1000

    # Extract user ID if available
    user_id = None
    if hasattr(request.state, "user_context"):
        user_id = request.state.user_context.user_id

    # Log request
    log_request(
        method=request.method,
        path=request.url.path,
        status_code=response.status_code,
        duration_ms=duration_ms,
        user_id=user_id
    )

    # Add timing header
    response.headers["X-Process-Time"] = f"{duration_ms:.2f}ms"

    return response


# Exception handlers

@app.exception_handler(SpotOptimizerException)
async def spot_optimizer_exception_handler(
    request: Request,
    exc: SpotOptimizerException
) -> JSONResponse:
    """
    Handle custom application exceptions

    Args:
        request: FastAPI request
        exc: Custom exception

    Returns:
        JSON error response
    """
    logger.error(
        "Application exception",
        exception=exc.__class__.__name__,
        message=exc.message,
        status_code=exc.status_code,
        details=exc.details,
        path=request.url.path
    )

    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": exc.__class__.__name__,
            "message": exc.message,
            "details": exc.details
        }
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(
    request: Request,
    exc: RequestValidationError
) -> JSONResponse:
    """
    Handle Pydantic validation errors

    Args:
        request: FastAPI request
        exc: Validation error

    Returns:
        JSON error response
    """
    logger.warning(
        "Validation error",
        errors=exc.errors(),
        path=request.url.path
    )

    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={
            "error": "ValidationError",
            "message": "Request validation failed",
            "details": exc.errors()
        }
    )


@app.exception_handler(Exception)
async def general_exception_handler(
    request: Request,
    exc: Exception
) -> JSONResponse:
    """
    Handle unexpected exceptions

    Args:
        request: FastAPI request
        exc: Exception

    Returns:
        JSON error response
    """
    logger.exception(
        "Unhandled exception",
        exception=exc.__class__.__name__,
        path=request.url.path
    )

    # In production, don't expose internal error details
    if settings.is_production():
        message = "An internal error occurred"
    else:
        message = str(exc)

    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "error": "InternalServerError",
            "message": message
        }
    )


# Health check endpoints

@app.get(
    "/health",
    tags=["Health"],
    summary="Basic health check",
    description="Check if the application is running"
)
async def health_check() -> dict:
    """
    Basic health check

    Returns:
        Health status
    """
    return {
        "status": "healthy",
        "service": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "environment": settings.ENVIRONMENT
    }


@app.get(
    "/health/detailed",
    tags=["Health"],
    summary="Detailed health check",
    description="Check application and dependencies health"
)
async def detailed_health_check() -> dict:
    """
    Detailed health check including database and Redis

    Returns:
        Detailed health status
    """
    from backend.models.base import engine
    from sqlalchemy import text

    health_status = {
        "status": "healthy",
        "service": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "environment": settings.ENVIRONMENT,
        "checks": {}
    }

    # Check database
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        health_status["checks"]["database"] = "healthy"
    except Exception as e:
        health_status["checks"]["database"] = f"unhealthy: {str(e)}"
        health_status["status"] = "degraded"

    # Check Redis (if configured)
    try:
        import redis
        r = redis.from_url(settings.REDIS_URL)
        r.ping()
        health_status["checks"]["redis"] = "healthy"
    except Exception as e:
        health_status["checks"]["redis"] = f"unhealthy: {str(e)}"
        health_status["status"] = "degraded"

    return health_status


# Root endpoint

@app.get(
    "/",
    tags=["Root"],
    summary="API root",
    description="Get API information"
)
async def root() -> dict:
    """
    API root endpoint

    Returns:
        API information
    """
    return {
        "service": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "description": "Spot Optimizer Platform - AWS Spot Instance Management for Kubernetes",
        "docs_url": "/docs" if not settings.is_production() else "Documentation disabled in production",
        "health_check": "/health"
    }


# Register routers

# Authentication routes
app.include_router(auth_router, prefix="/api/v1")

# Template routes
app.include_router(template_router, prefix="/api/v1")

# Additional routers will be added here as they are implemented
# app.include_router(cluster_router, prefix="/api/v1")
# app.include_router(policy_router, prefix="/api/v1")
# app.include_router(hibernation_router, prefix="/api/v1")
# app.include_router(audit_router, prefix="/api/v1")
# app.include_router(admin_router, prefix="/api/v1")
# app.include_router(lab_router, prefix="/api/v1")


# Startup and shutdown events

@app.on_event("startup")
async def startup_event():
    """
    Application startup tasks
    """
    logger.info(
        "Application starting",
        service=settings.APP_NAME,
        version=settings.APP_VERSION,
        environment=settings.ENVIRONMENT
    )


@app.on_event("shutdown")
async def shutdown_event():
    """
    Application shutdown tasks
    """
    logger.info(
        "Application shutting down",
        service=settings.APP_NAME
    )


# Export app
__all__ = ["app"]
