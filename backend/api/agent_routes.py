"""
Agent Routes - API endpoints for Kubernetes agent communication

These endpoints handle:
- Agent registration (when agent starts up)
- Agent deregistration (when agent shuts down gracefully)
- Heartbeat updates (periodic health checks)
"""

from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Header
from pydantic import BaseModel
from typing import List, Optional
from sqlalchemy.orm import Session

from backend.models.base import get_db
from backend.models.cluster import Cluster, ClusterStatus

router = APIRouter(prefix="/agents", tags=["agents"])


# --- Request/Response Schemas ---

class AgentRegisterRequest(BaseModel):
    cluster_id: str
    agent_id: str
    timestamp: str
    capabilities: List[str] = []
    version: str = "1.0.0"


class AgentDeregisterRequest(BaseModel):
    cluster_id: str
    agent_id: str
    timestamp: str


class AgentHeartbeatRequest(BaseModel):
    cluster_id: str
    agent_id: str
    timestamp: str
    metrics: Optional[dict] = None
    health: Optional[dict] = None


class AgentResponse(BaseModel):
    success: bool
    message: str
    agent_id: Optional[str] = None


# --- Helper function to validate API key ---

def validate_api_key(
    authorization: str = Header(...),
    db: Session = Depends(get_db)
) -> Cluster:
    """
    Validate the agent's API key and return the associated cluster.
    """
    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Invalid authorization header")
    
    api_key = authorization.replace("Bearer ", "")
    
    cluster = db.query(Cluster).filter(Cluster.api_key == api_key).first()
    if not cluster:
        raise HTTPException(status_code=401, detail="Invalid API key")
    
    return cluster


# --- Endpoints ---

@router.post("/register", response_model=AgentResponse)
async def register_agent(
    request: AgentRegisterRequest,
    db: Session = Depends(get_db),
    cluster: Cluster = Depends(validate_api_key)
):
    """
    Register an agent with the backend.
    
    This is called when the agent first starts up. It updates the cluster
    status to ACTIVE and records the agent registration.
    """
    # Verify cluster_id matches
    if request.cluster_id != cluster.id:
        raise HTTPException(
            status_code=403, 
            detail="Cluster ID mismatch"
        )
    
    # Update cluster status
    cluster.status = ClusterStatus.ACTIVE
    cluster.agent_installed = "Y"
    cluster.last_heartbeat = datetime.utcnow()
    
    db.commit()
    
    return AgentResponse(
        success=True,
        message="Agent registered successfully",
        agent_id=request.agent_id
    )


@router.post("/deregister", response_model=AgentResponse)
async def deregister_agent(
    request: AgentDeregisterRequest,
    db: Session = Depends(get_db),
    cluster: Cluster = Depends(validate_api_key)
):
    """
    Deregister an agent from the backend.
    
    This is called when the agent shuts down gracefully.
    """
    # Verify cluster_id matches
    if request.cluster_id != cluster.id:
        raise HTTPException(
            status_code=403, 
            detail="Cluster ID mismatch"
        )
    
    # Update cluster status to inactive
    cluster.status = ClusterStatus.INACTIVE
    cluster.agent_installed = "N"
    
    db.commit()
    
    return AgentResponse(
        success=True,
        message="Agent deregistered successfully",
        agent_id=request.agent_id
    )


@router.post("/heartbeat", response_model=AgentResponse)
async def agent_heartbeat(
    request: AgentHeartbeatRequest,
    db: Session = Depends(get_db),
    cluster: Cluster = Depends(validate_api_key)
):
    """
    Receive heartbeat from agent.
    
    Updates the last_heartbeat timestamp to track agent health.
    """
    # Verify cluster_id matches
    if request.cluster_id != cluster.id:
        raise HTTPException(
            status_code=403, 
            detail="Cluster ID mismatch"
        )
    
    # Update heartbeat timestamp
    cluster.last_heartbeat = datetime.utcnow()
    
    # Ensure status is ACTIVE if receiving heartbeats
    if cluster.status != ClusterStatus.ACTIVE:
        cluster.status = ClusterStatus.ACTIVE
        cluster.agent_installed = "Y"
    
    db.commit()
    
    return AgentResponse(
        success=True,
        message="Heartbeat received",
        agent_id=request.agent_id
    )
