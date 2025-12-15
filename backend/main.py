"""
Spot Optimizer Platform - FastAPI Backend

Main application entry point with health check and evaluation endpoints
"""

from fastapi import FastAPI, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime

from config import settings
from api.sandbox import router as sandbox_router

# Create FastAPI app
app = FastAPI(
    title='Spot Optimizer Platform',
    description='Intelligent AWS Spot Instance optimization with ML prediction and reactive safety',
    version='3.0.0',
    docs_url='/docs',
    redoc_url='/redoc'
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
app.include_router(
    sandbox_router,
    prefix='/api/v1/sandbox',
    tags=['Sandbox']
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
    2. Runs the 6-layer decision pipeline
    3. Returns the final decision with reasoning

    **Note**: This is a placeholder. Real implementation would use:
    - decision_engine_v2.DecisionContext
    - dependencies.get_decision_pipeline()
    """
    # TODO: Implement real pipeline execution
    # For now, return mock response

    return EvaluateResponse(
        decision='STAY',
        reason='Instance is safe (crash probability < 0.85)',
        crash_probability=0.28,
        aws_signal='NONE',
        execution_time_ms=150.2,
        candidates_evaluated=1,
        selected_candidate=None
    )


if __name__ == '__main__':
    import uvicorn
    uvicorn.run(app, host='0.0.0.0', port=settings.api_port)
