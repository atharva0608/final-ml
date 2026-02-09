"""
Agent Registration Router

Handles agent registration, heartbeats, and deregistration.
"""

from fastapi import APIRouter, Depends, HTTPException, status, Header
from sqlalchemy.orm import Session
from typing import Dict, Any, Optional
from datetime import datetime
import logging

from ..models.base import get_db
from ..models.cluster import Cluster

router = APIRouter(prefix="/api/v1/agents", tags=["agents"])
logger = logging.getLogger(__name__)


@router.post("/register")
async def register_agent(
    payload: Dict[str, Any],
    authorization: Optional[str] = Header(None),
    db: Session = Depends(get_db)
):
    """
    Register an agent with the backend.

    Called by agents when they start up to announce their presence.
    Updates cluster heartbeat timestamp.
    """
    try:
        cluster_id = payload.get("cluster_id")
        agent_id = payload.get("agent_id")
        capabilities = payload.get("capabilities", [])
        version = payload.get("version")

        if not cluster_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="cluster_id is required"
            )

        # Verify cluster exists
        cluster = db.query(Cluster).filter(Cluster.id == cluster_id).first()
        if not cluster:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Cluster {cluster_id} not found"
            )

        # Update cluster heartbeat
        cluster.last_heartbeat = datetime.utcnow()
        cluster.agent_installed = "Y"

        db.commit()

        logger.info(f"Agent registered: cluster={cluster_id}, agent={agent_id}, version={version}")

        return {
            "success": True,
            "message": "Agent registered successfully",
            "cluster_id": cluster_id,
            "agent_id": agent_id,
            "timestamp": datetime.utcnow().isoformat()
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error registering agent: {e}")
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to register agent: {str(e)}"
        )


@router.post("/deregister")
async def deregister_agent(
    payload: Dict[str, Any],
    authorization: Optional[str] = Header(None),
    db: Session = Depends(get_db)
):
    """
    Deregister an agent from the backend.

    Called by agents when they shut down gracefully.
    """
    try:
        cluster_id = payload.get("cluster_id")
        agent_id = payload.get("agent_id")

        if not cluster_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="cluster_id is required"
            )

        # Verify cluster exists
        cluster = db.query(Cluster).filter(Cluster.id == cluster_id).first()
        if not cluster:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Cluster {cluster_id} not found"
            )

        logger.info(f"Agent deregistered: cluster={cluster_id}, agent={agent_id}")

        return {
            "success": True,
            "message": "Agent deregistered successfully",
            "cluster_id": cluster_id,
            "timestamp": datetime.utcnow().isoformat()
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deregistering agent: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to deregister agent: {str(e)}"
        )


@router.post("/heartbeat")
async def agent_heartbeat(
    payload: Dict[str, Any],
    authorization: Optional[str] = Header(None),
    db: Session = Depends(get_db)
):
    """
    Receive heartbeat from an agent.

    Agents send periodic heartbeats to indicate they're still alive.
    """
    try:
        cluster_id = payload.get("cluster_id")
        agent_id = payload.get("agent_id")
        health = payload.get("health", {})

        if not cluster_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="cluster_id is required"
            )

        # Update cluster heartbeat
        cluster = db.query(Cluster).filter(Cluster.id == cluster_id).first()
        if cluster:
            cluster.last_heartbeat = datetime.utcnow()
            db.commit()

        return {
            "success": True,
            "timestamp": datetime.utcnow().isoformat()
        }

    except Exception as e:
        logger.error(f"Error processing heartbeat: {e}")
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to process heartbeat: {str(e)}"
        )
