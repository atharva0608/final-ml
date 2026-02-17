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
from backend.api import (
    auth_router,
    template_router,
    audit_router,
    cluster_router,
    policy_router,
    hibernation_router,
    metrics_router,
    admin_router,
    lab_router,
    onboarding_router,
    organization_router,
    health_router,
    optimization_router,
    hygiene_router,
    team_router,
    user_router,
    governance_router,
    hygiene_policy_router,
)

# Dashboard Routes (Three Pricing Models)
from backend.api.dashboard_routes import router as dashboard_router

# Additional Analysis Routes
from backend.api.ri_routes import router as ri_router
from backend.api.s3_routes import router as s3_router
from backend.api.rds_routes import router as rds_router
from backend.api.transfer_routes import router as transfer_router

# AtharvaAi Pool Selection & Termination Monitoring
from backend.api.atharvaai_routes import router as atharvaai_router

# Tag Management Routes
from backend.api.tag_policy_routes import router as tag_policy_router
from backend.api.tag_management_routes import router as tag_management_router
from backend.api.tag_template_routes import router as tag_template_router

# Agent Communication Routes
from backend.routers.actions import router as actions_router
from backend.routers.metrics import router as agent_metrics_router
from backend.routers.agents import router as agents_router

__all__ = [
    "auth_router",
    "template_router",
    "audit_router",
    "cluster_router",
    "policy_router",
    "hibernation_router",
    "metrics_router",
    "admin_router",
    "lab_router",
    "onboarding_router",
    "organization_router",
    "health_router",
    "optimization_router",
    "hygiene_router",
    "team_router",
    "user_router",
]

from backend.api import account_routes
from backend.api import settings_routes

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


# Custom middleware to ensure CORS headers on all responses (including errors)
@app.middleware("http")
async def add_cors_headers(request: Request, call_next):
    """Ensure CORS headers are present on all responses, including errors"""
    response = await call_next(request)

    # Get origin from request
    origin = request.headers.get("origin")
    allowed_origins = get_cors_origins()

    # Check if origin is allowed
    if origin and (origin in allowed_origins or "*" in allowed_origins):
        response.headers["Access-Control-Allow-Origin"] = origin
        response.headers["Access-Control-Allow-Credentials"] = str(settings.CORS_ALLOW_CREDENTIALS).lower()
        response.headers["Access-Control-Allow-Methods"] = "GET, POST, PUT, PATCH, DELETE, OPTIONS"
        response.headers["Access-Control-Allow-Headers"] = "*"
        response.headers["Access-Control-Expose-Headers"] = "X-Total-Count, X-Page, X-Page-Size"

    return response


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
        error_message=exc.message,
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

# Audit routes
app.include_router(audit_router, prefix="/api/v1")

# Cluster routes
app.include_router(cluster_router, prefix="/api/v1")

# Policy routes
app.include_router(policy_router, prefix="/api/v1")

# Hibernation routes
app.include_router(hibernation_router, prefix="/api/v1")

# Metrics routes
app.include_router(metrics_router, prefix="/api/v1")

# Admin routes
app.include_router(admin_router, prefix="/api/v1")

# Lab routes
app.include_router(lab_router, prefix="/api/v1")

# Onboarding routes
# Onboarding routes
app.include_router(onboarding_router, prefix="/api/v1")

# Organization routes
app.include_router(organization_router, prefix="/api/v1")

# Account routes
app.include_router(account_routes.router, prefix="/api/v1")

# Health routes
app.include_router(health_router, prefix="/api/v1")

# Optimization routes
app.include_router(optimization_router, prefix="/api/v1")

# Hygiene routes
app.include_router(hygiene_router, prefix="/api/v1")
app.include_router(hygiene_policy_router, prefix="/api/v1")

# Dashboard routes (Three Pricing Models)
app.include_router(dashboard_router, prefix="/api/v1")


# Team routes
app.include_router(team_router, prefix="/api/v1")

# User routes
app.include_router(user_router, prefix="/api/v1")

# Settings routes
app.include_router(settings_routes.router, prefix="/api/v1")

# Role routes (RBAC)
# Role routes (RBAC)
from backend.api.role_routes import router as role_router
app.include_router(role_router, prefix="/api/v1")

# Permission routes (JIT Feature Access)
from backend.api.permission_routes import router as permission_router
app.include_router(permission_router, prefix="/api/v1")

# Approval routes (JIT)
from backend.api.approval_routes import router as approval_router
app.include_router(approval_router, prefix="/api/v1")

# Governance routes
app.include_router(governance_router, prefix="/api/v1")

# Analysis routes (RI, S3, RDS, Transfer)
app.include_router(ri_router, prefix="/api/v1")
app.include_router(s3_router, prefix="/api/v1")
app.include_router(rds_router, prefix="/api/v1")
app.include_router(transfer_router, prefix="/api/v1")

# AtharvaAi Pool Selection & Termination Monitoring routes
app.include_router(atharvaai_router, prefix="/api/v1")

# Pod Metrics & Right-Sizing routes
from backend.api.pod_metrics_routes import router as pod_metrics_router
app.include_router(pod_metrics_router, prefix="/api/v1")

# Tag Management routes
app.include_router(tag_policy_router, prefix="/api/v1")
app.include_router(tag_management_router, prefix="/api/v1")
app.include_router(tag_template_router, prefix="/api/v1")

# Agent Communication routes (used by Kubernetes agents)
app.include_router(agents_router)  # Prefix already defined in router
app.include_router(actions_router)  # Prefix already defined in router
app.include_router(agent_metrics_router)  # Prefix already defined in router

# Installer routes (public - no auth required)
from backend.api.installer_routes import router as installer_router
app.include_router(installer_router, prefix="/api")


# Agent routes (used by Kubernetes agent for registration/heartbeat)
from backend.api.agent_routes import router as agent_router
app.include_router(agent_router, prefix="/api/v1")

# Websocket endpoint for real-time agent communication
from fastapi import WebSocket, WebSocketDisconnect
from typing import Dict

# Store active connections: cluster_id -> WebSocket
active_connections: Dict[str, WebSocket] = {}

@app.websocket("/ws/cluster/{cluster_id}")
async def websocket_cluster_endpoint(websocket: WebSocket, cluster_id: str):
    """
    Websocket endpoint for cluster agents
    """
    await websocket.accept()
    active_connections[cluster_id] = websocket
    logger.info(f"Using Websocket connection for cluster {cluster_id}")
    try:
        while True:
            # Keep connection alive and process messages
            data = await websocket.receive_text()
            # In future: Handle incoming messages (e.g. immediate alerts)
            # For now just echo or ack
            await websocket.send_text(f"Ack: {len(data)} bytes")
    except WebSocketDisconnect:
        logger.info(f"Websocket disconnected for cluster {cluster_id}")
        if cluster_id in active_connections:
            del active_connections[cluster_id]
    except Exception as e:
        logger.error(f"Websocket error for {cluster_id}: {e}")
        if cluster_id in active_connections:
            del active_connections[cluster_id]


# Startup and shutdown events

@app.on_event("startup")
async def startup_event():
    """
    Application startup tasks
    """
    from backend.models.base import create_tables, seed_demo_data

    logger.info(
        "Application starting",
        service=settings.APP_NAME,
        version=settings.APP_VERSION,
        environment=settings.ENVIRONMENT,
        cors_origins=settings.CORS_ORIGINS,
        cors_allow_credentials=settings.CORS_ALLOW_CREDENTIALS
    )

    # Auto-create database tables
    try:
        logger.info("Creating database tables...")
        create_tables()
        logger.info("✅ Database tables created/verified")

        # Seed demo data
        seed_demo_data()

        # Seed roles and permissions
        try:
            from backend.services.role_service import RoleService
            from backend.models.base import SessionLocal

            db = SessionLocal()
            try:
                role_service = RoleService(db)
                perm_count = role_service.seed_permissions()
                role_count = role_service.seed_system_roles()
                logger.info(f"✅ Seeded {perm_count} permissions and {role_count} roles")
            finally:
                db.close()
        except Exception as seed_err:
            logger.warning(f"Role/permission seeding skipped or failed: {seed_err}")

    except Exception as e:
        logger.error(f"❌ Failed to initialize database: {e}")


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
