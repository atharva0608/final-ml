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
from api.websocket_routes import router as websocket_router
from database.connection import init_db
from jobs.scheduler import start_scheduler, stop_scheduler

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
    except Exception as e:
        print(f"⚠️  Database initialization failed: {e}")
        print("   Continuing without database (using in-memory storage)")

    # Start background scheduler
    try:
        start_scheduler()
    except Exception as e:
        print(f"⚠️  Scheduler startup failed: {e}")

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
