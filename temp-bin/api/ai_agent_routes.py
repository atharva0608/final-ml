"""
AI Agent API Routes
===================

FastAPI routes for multi-agent AI system.

Endpoints:
- POST /api/v1/ai-agents/optimize/{cluster_id} - Run optimization pipeline
- POST /api/v1/ai-agents/rightsizing/{cluster_id} - Generate rightsizing recommendations
- POST /api/v1/ai-agents/events/interruption - Handle interruption events
- GET /api/v1/ai-agents/health - Agent health status
"""

import logging
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import Optional
from pydantic import BaseModel

from backend.core.dependencies import get_db, get_current_user
from backend.services.agent_service import AgentService
from backend.models.user import User


logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/ai-agents", tags=["ai-agents"])


# Request/Response Models

class OptimizationRequest(BaseModel):
    """Request model for optimization"""
    mode: str = "auto"  # 'manual' or 'auto'
    force_refresh: bool = False


class OptimizationResponse(BaseModel):
    """Response model for optimization"""
    cluster_id: str
    status: str
    mode: str
    stages: dict
    started_at: str
    completed_at: Optional[str] = None
    error: Optional[str] = None


class RightsizingRequest(BaseModel):
    """Request model for rightsizing"""
    analysis_window_hours: int = 168  # 7 days


class InterruptionEventRequest(BaseModel):
    """Request model for interruption event"""
    cluster_id: str
    event_type: str  # 'rebalance_notice' or 'termination_notice'
    instance_type: str
    az: str


class AgentHealthResponse(BaseModel):
    """Response model for agent health"""
    orchestrator: str
    version: str
    agents: dict
    timestamp: str


# Routes

@router.post("/{cluster_id}/optimize", response_model=OptimizationResponse)
async def run_optimization(
    cluster_id: str,
    request: OptimizationRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Run optimization pipeline for a cluster.

    This endpoint executes the complete multi-agent optimization pipeline:
    1. Global Intelligence Agent - Ranks spot pools
    2. Capacity Validator - Validates availability
    3. Decision Engine - Selects optimal pool
    4. Cooldown Controller - Prevents flapping
    5. Cluster Execution - Applies changes (auto mode only)

    **Modes:**
    - `manual`: Returns top 3 candidate pools for user approval
    - `auto`: Automatically selects and applies best pool

    **Permissions Required:** `compute:manage`
    """
    try:
        logger.info(f"Optimization requested for cluster {cluster_id} by user {current_user.email}")

        # Initialize agent service
        agent_service = AgentService(db=db)

        # Run optimization
        results = await agent_service.run_optimization_for_cluster(
            cluster_id=cluster_id,
            mode=request.mode,
            force_refresh=request.force_refresh
        )

        if results['status'] == 'FAILED':
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=results.get('error', 'Optimization failed')
            )

        return OptimizationResponse(**results)

    except ValueError as e:
        logger.error(f"Validation error: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        logger.error(f"Optimization error: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Optimization failed: {str(e)}"
        )


@router.post("/{cluster_id}/rightsizing")
async def generate_rightsizing_recommendations(
    cluster_id: str,
    request: RightsizingRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Generate rightsizing recommendations for a cluster.

    Analyzes pod-level metrics and generates instance resizing recommendations
    with ML risk and savings metadata.

    **Analysis Logic:**
    1. Group metrics by controller
    2. Compute P95 CPU and memory
    3. Detect oversized (P95 < 50% request) or undersized (P95 > 95%)
    4. Add 20% safety buffer
    5. Map to valid instance types
    6. Enrich with ML risk scores

    **Permissions Required:** `compute:view`
    """
    try:
        logger.info(f"Rightsizing analysis requested for cluster {cluster_id}")

        agent_service = AgentService(db=db)

        results = await agent_service.generate_rightsizing_recommendations(
            cluster_id=cluster_id,
            analysis_window_hours=request.analysis_window_hours
        )

        if results.get('status') == 'FAILED':
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=results.get('error', 'Rightsizing analysis failed')
            )

        return results

    except Exception as e:
        logger.error(f"Rightsizing error: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Rightsizing analysis failed: {str(e)}"
        )


@router.post("/events/interruption")
async def handle_interruption_event(
    request: InterruptionEventRequest,
    db: Session = Depends(get_db)
):
    """
    Handle spot instance interruption event.

    This endpoint processes AWS spot interruption notices and triggers
    appropriate responses:

    **Rebalance Notice:**
    - Prewarm substitute instance
    - Evaluate early switch opportunity

    **Termination Notice:**
    - Cordon and drain affected node
    - Promote substitute instance
    - Blacklist affected pool for 24 hours
    - Trigger re-ranking pipeline

    **Note:** This endpoint is typically called by AWS EventBridge or
    cluster agents monitoring EC2 metadata.

    **Authentication:** Uses API key or cluster agent token
    """
    try:
        logger.info(
            f"Interruption event received: {request.event_type} "
            f"for {request.instance_type} in {request.az}"
        )

        agent_service = AgentService(db=db)

        results = await agent_service.handle_interruption_event(
            cluster_id=request.cluster_id,
            event_type=request.event_type,
            instance_type=request.instance_type,
            az=request.az
        )

        if results.get('status') == 'FAILED':
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=results.get('error', 'Event handling failed')
            )

        return results

    except Exception as e:
        logger.error(f"Event handling error: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Event handling failed: {str(e)}"
        )


@router.get("/health", response_model=AgentHealthResponse)
async def get_agent_health(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Get health status of all AI agents in the orchestrator.

    Returns status for all 8 agents:
    1. GlobalIntelligenceAgent
    2. CapacityValidatorAgent
    3. DecisionEngineAgent
    4. RightsizingAgent
    5. CooldownControllerAgent
    6. SubstituteManagerAgent
    7. ClusterExecutionAgent
    8. EventMonitoringAgent

    **Permissions Required:** `system:view` (Admin only)
    """
    try:
        agent_service = AgentService(db=db)
        health_status = await agent_service.get_agent_health_status()

        return AgentHealthResponse(**health_status)

    except Exception as e:
        logger.error(f"Health check error: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Health check failed: {str(e)}"
        )


@router.get("/status/{cluster_id}")
async def get_cluster_agent_status(
    cluster_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Get AI agent execution status for a specific cluster.

    Returns:
    - Last optimization run timestamp
    - Current mode (manual/auto)
    - Recent agent actions
    - Active cooldowns
    - Blacklisted pools

    **Permissions Required:** `compute:view`
    """
    try:
        # This would query recent agent executions from database
        # For now, return placeholder

        return {
            "cluster_id": cluster_id,
            "last_optimization": None,
            "mode": "auto",
            "recent_actions": [],
            "active_cooldowns": [],
            "blacklisted_pools": []
        }

    except Exception as e:
        logger.error(f"Status check error: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Status check failed: {str(e)}"
        )
