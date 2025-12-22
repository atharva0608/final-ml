"""
Spot Optimizer Platform - Production Lab Mode Backend

Agentless, production-grade AWS Spot Instance optimizer with:
- Cross-account STS AssumeRole security
- Real ML inference on live data
- PostgreSQL + Redis data pipeline
- WebSocket real-time logs
- Multi-tenant authorization
- Lab Mode for single-instance optimization
"""

from fastapi import FastAPI, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime
from contextlib import asynccontextmanager

from config import settings
from api.lab import router as lab_router
from api.auth import router as auth_router
from api.admin import router as admin_router
from api.websocket_routes import router as websocket_router
# V3.1 Production Features
from api import waste_routes, governance_routes, approval_routes, onboarding_routes, ai_routes, metrics_routes, pipeline_routes, storage_routes, client_routes
from database.connection import init_db, seed_test_users
from jobs.scheduler import start_scheduler, stop_scheduler
from utils.system_logger import SystemLogger, Component
from database.connection import get_db


# Lifespan context manager for startup/shutdown
@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Application lifespan manager

    Handles startup and shutdown events.
    """
    # Startup
    print("\n" + "="*80)
    print("🚀 STARTING SPOT OPTIMIZER PLATFORM")
    print("="*80)

    # Initialize database
    try:
        init_db()
        print("✓ Database tables created")
    except Exception as e:
        print(f"⚠️  Database initialization failed: {e}")
        print("   Continuing without database (using in-memory storage)")

    # Seed test users (admin/admin, client/client)
    try:
        seed_test_users()
    except Exception as e:
        print(f"⚠️  Test user seeding failed: {e}")

    # Run real health checks for all components
    try:
        print("✓ Running health checks for all components...")
        from utils.health_checks import run_all_health_checks

        db_gen = get_db()
        db = next(db_gen, None)
        if db:
            results = run_all_health_checks(db)

            for component_name, (status, details) in results.items():
                try:
                    logger = SystemLogger(component_name, db=db)

                    # Log based on health check result
                    if status == "healthy":
                        logger.success(
                            f"Component initialized successfully",
                            details=details
                        )
                        print(f"  ✅ {component_name}: healthy")
                    elif status == "degraded":
                        logger.warning(
                            f"Component partially functional",
                            details=details
                        )
                        print(f"  ⚠️  {component_name}: degraded - {details.get('message', 'unknown')}")
                    else:  # unhealthy
                        logger.error(
                            f"Component health check failed",
                            details=details
                        )
                        print(f"  ❌ {component_name}: unhealthy - {details.get('message', 'unknown')}")

                except Exception as e:
                    print(f"  ❌ Failed to check {component_name}: {e}")

            db.close()
            print("✓ Health checks completed")
    except Exception as e:
        print(f"⚠️  Health check failed: {e}")


    # Start background scheduler
    try:
        start_scheduler()
    except Exception as e:
        print(f"⚠️  Scheduler startup failed: {e}")

    # Start health monitor (Phase 3)
    try:
        from workers.health_monitor import start_health_monitor_background
        health_monitor = start_health_monitor_background()
        print("✓ Health monitor started (checking every 30s)")
    except Exception as e:
        print(f"⚠️  Health monitor startup failed: {e}")

    print("="*80)
    print(f"✓ Server running on http://{settings.api_host}:{settings.api_port}")
    print(f"✓ API docs available at http://{settings.api_host}:{settings.api_port}/docs")
    print(f"✓ Environment: {settings.environment}")
    print("="*80 + "\n")

    yield

    # Shutdown
    print("\n" + "="*80)
    print("🛑 SHUTTING DOWN")
    print("="*80)
    stop_scheduler()
    print("="*80 + "\n")


# Create FastAPI app
app = FastAPI(
    title='Spot Optimizer Platform',
    description='Intelligent AWS Spot Instance optimization with ML prediction and reactive safety',
    version='3.0.0',
    docs_url='/docs',
    redoc_url='/redoc',
    lifespan=lifespan
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=['*'],  # Update in production
    allow_credentials=True,
    allow_methods=['*'],
    allow_headers=['*']
)


# Request/Response Models
class EvaluateRequest(BaseModel):
    """Request model for /evaluate endpoint"""
    instance_type: str = Field(..., description='EC2 instance type (e.g., c5.large)')
    availability_zone: str = Field(..., description='Availability zone (e.g., ap-south-1a)')
    instance_id: Optional[str] = Field(None, description='Instance ID (optional)')


class EvaluateResponse(BaseModel):
    """Response model for /evaluate endpoint"""
    decision: str = Field(..., description='STAY, SWITCH, DRAIN, or EVACUATE')
    reason: str = Field(..., description='Human-readable reason')
    crash_probability: Optional[float] = Field(None, description='ML prediction (0.0-1.0)')
    aws_signal: str = Field(..., description='NONE, REBALANCE, or TERMINATION')
    execution_time_ms: float = Field(..., description='Pipeline execution time')
    candidates_evaluated: int = Field(..., description='Number of candidates evaluated')
    selected_candidate: Optional[dict] = Field(None, description='Selected candidate details')


# Include routers
# Authentication
app.include_router(
    auth_router,
    prefix='/api/v1/auth',
    tags=['Authentication']
)

# Lab Mode (Production ML Optimizer)
app.include_router(
    lab_router,
    prefix='/api/v1/lab',
    tags=['Lab Mode']
)

# WebSocket (Real-time logs)
app.include_router(
    websocket_router,
    prefix='/api/v1',
    tags=['WebSocket']
)

# Admin (System Monitoring)
app.include_router(
    admin_router,
    prefix='/api/v1/admin',
    tags=['Admin']
)

# V3.1 Production Features - Waste Management
app.include_router(
    waste_routes.router,
    prefix='/api/v1/waste',
    tags=['Waste Management']
)

# V3.1 Production Features - Governance
app.include_router(
    governance_routes.router,
    prefix='/api/v1/governance',
    tags=['Governance']
)

# V3.1 Production Features - Approvals
app.include_router(
    approval_routes.router,
    prefix='/api/v1/approvals',
    tags=['Approvals']
)

# V3.1 Production Features - Client Onboarding
app.include_router(
    onboarding_routes.router,
    prefix='/api/v1/onboarding',
    tags=['Onboarding']
)

# V3.1 Production Features - AI Model Governance
app.include_router(
    ai_routes.router,
    prefix='/api/v1/ai',
    tags=['AI Governance']
)

# V3.1 Production Features - Metrics
app.include_router(
    metrics_routes.router,
    prefix='/api/v1/metrics',
    tags=['Metrics']
)

# V3.1 Production Features - Pipeline
app.include_router(
    pipeline_routes.router,
    prefix='/api/v1/pipeline',
    tags=['Pipeline']
)

# V3.1 Production Features - Storage Cleanup
app.include_router(
    storage_routes.router,
    prefix='/api/v1/storage',
    tags=['Storage']
)

# V3.1 Production Features - Client Dashboard
app.include_router(
    client_routes.router,
    prefix='/api/v1/client',
    tags=['Client Dashboard']
)


@app.get('/health')
async def health_check():
    """Health check endpoint"""
    return {
        'status': 'healthy',
        'environment': settings.environment,
        'timestamp': datetime.now().isoformat(),
        'version': '3.0.0'
    }


@app.post('/api/v1/evaluate', response_model=EvaluateResponse)
async def evaluate_instance(request: EvaluateRequest):
    """
    Evaluate a spot instance and recommend action

    This endpoint:
    1. Creates a DecisionContext from the request
    2. Runs the decision pipeline (CLUSTER_FULL or SINGLE_LINEAR based on config)
    3. Returns the final decision with reasoning

    The pipeline router (workers.optimizer_task) automatically selects:
    - SINGLE_LINEAR: Lab Mode (simplified pipeline for experimentation)
    - CLUSTER_FULL: Production Mode (full 6-layer pipeline)
    """
    from workers.optimizer_task import run_optimization_cycle

    # Use instance_id if provided, otherwise generate a test ID
    instance_id = request.instance_id or f"test-{request.instance_type}-{request.availability_zone}"

    # Run optimization cycle (automatically routes to correct pipeline)
    summary = run_optimization_cycle(instance_id)

    # Convert to response format
    return EvaluateResponse(
        decision=summary['decision'],
        reason=summary['reason'],
        crash_probability=summary['selected_candidate']['crash_probability'] if summary['selected_candidate'] else None,
        aws_signal=summary['aws_signal'],
        execution_time_ms=summary['execution_time_ms'],
        candidates_evaluated=3,  # TODO: Get from summary
        selected_candidate=summary['selected_candidate']
    )


if __name__ == '__main__':
    import uvicorn
    uvicorn.run(app, host='0.0.0.0', port=settings.api_port)
