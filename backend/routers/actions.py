"""
Action Management Router

Handles action queuing and execution for agent clusters.
Actions can be evictions, node operations, or deployment updates.
"""

from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from typing import List, Optional, Dict, Any
from datetime import datetime
import logging

from ..models.base import get_db
from ..models.cluster import Cluster
from ..models.user import User
from ..models.agent_action import AgentAction, AgentActionStatus, AgentActionType
from ..core.dependencies import get_current_user

router = APIRouter(prefix="/api/v1/actions", tags=["actions"])
logger = logging.getLogger(__name__)


@router.get("/poll")
async def poll_actions(
    cluster_id: str = Query(..., description="Cluster ID to poll actions for"),
    db: Session = Depends(get_db)
):
    """
    Poll for pending actions for a specific cluster.

    Used by agents to check for pending actions to execute.
    Returns actions in PENDING status for the specified cluster.
    """
    try:
        # Find pending actions for this cluster
        actions = db.query(AgentAction).filter(
            AgentAction.cluster_id == cluster_id,
            AgentAction.status == AgentActionStatus.PENDING
        ).order_by(AgentAction.created_at).limit(10).all()

        # Mark actions as PICKED_UP
        for action in actions:
            action.status = AgentActionStatus.PICKED_UP
            action.picked_up_at = datetime.utcnow()

        db.commit()

        # Format response for agent
        action_list = []
        for action in actions:
            action_list.append({
                "id": str(action.id),
                "type": action.action_type.value,
                "parameters": action.payload or {},
                "signature": "",  # TODO: Implement HMAC signature
                "created_at": action.created_at.isoformat() if action.created_at else None
            })

        logger.info(f"Cluster {cluster_id} polled {len(action_list)} actions")

        return {
            "cluster_id": cluster_id,
            "actions": action_list,
            "timestamp": datetime.utcnow().isoformat()
        }

    except Exception as e:
        logger.error(f"Error polling actions for cluster {cluster_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to poll actions: {str(e)}"
        )


@router.post("/{action_id}/result")
async def update_action_result(
    action_id: str,
    result: Dict[str, Any],
    db: Session = Depends(get_db)
):
    """
    Update the result of an action execution.

    Called by agents after executing an action to report success/failure.
    """
    try:
        # Find the action
        action = db.query(AgentAction).filter(AgentAction.id == action_id).first()

        if not action:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Action {action_id} not found"
            )

        # Update action with result
        success = result.get("success", False)
        action.status = AgentActionStatus.COMPLETED if success else AgentActionStatus.FAILED
        action.result = result
        action.completed_at = datetime.utcnow()
        action.error_message = result.get("error") or result.get("message") if not success else None

        db.commit()

        logger.info(f"Action {action_id} result updated: {action.status}")

        return {
            "success": True,
            "action_id": action_id,
            "status": action.status.value,
            "timestamp": datetime.utcnow().isoformat()
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating action result for {action_id}: {e}")
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update action result: {str(e)}"
        )


@router.post("/")
async def create_action(
    payload: Dict[str, Any],
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Create a new action for execution on a cluster.

    Queues an action to be picked up by the cluster agent.
    """
    try:
        cluster_id = payload.get("cluster_id")
        action_type = payload.get("action_type")
        parameters = payload.get("parameters", {})

        # Verify cluster exists
        cluster = db.query(Cluster).filter(Cluster.id == cluster_id).first()
        if not cluster:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Cluster {cluster_id} not found"
            )

        # Validate action type
        try:
            action_type_enum = AgentActionType(action_type)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid action type: {action_type}"
            )

        # Create the action
        new_action = AgentAction(
            cluster_id=cluster_id,
            action_type=action_type_enum,
            payload=parameters,
            status=AgentActionStatus.PENDING
        )

        db.add(new_action)
        db.commit()
        db.refresh(new_action)

        logger.info(f"Created action {new_action.id} for cluster {cluster_id}")

        return {
            "success": True,
            "action_id": str(new_action.id),
            "cluster_id": cluster_id,
            "status": new_action.status.value,
            "timestamp": datetime.utcnow().isoformat()
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating action: {e}")
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create action: {str(e)}"
        )


@router.get("/{action_id}")
async def get_action(
    action_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Get details of a specific action.
    """
    try:
        action = db.query(AgentAction).filter(AgentAction.id == action_id).first()

        if not action:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Action {action_id} not found"
            )

        return {
            "id": str(action.id),
            "cluster_id": action.cluster_id,
            "action_type": action.action_type.value,
            "parameters": action.payload,
            "status": action.status.value,
            "result": action.result,
            "error_message": action.error_message,
            "created_at": action.created_at.isoformat() if action.created_at else None,
            "picked_up_at": action.picked_up_at.isoformat() if action.picked_up_at else None,
            "completed_at": action.completed_at.isoformat() if action.completed_at else None
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching action {action_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch action: {str(e)}"
        )


@router.get("/cluster/{cluster_id}")
async def list_cluster_actions(
    cluster_id: str,
    limit: int = Query(50, le=200),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    List all actions for a specific cluster.
    """
    try:
        # Verify cluster exists
        cluster = db.query(Cluster).filter(Cluster.id == cluster_id).first()
        if not cluster:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Cluster {cluster_id} not found"
            )

        # Get actions
        actions = db.query(AgentAction).filter(
            AgentAction.cluster_id == cluster_id
        ).order_by(AgentAction.created_at.desc()).limit(limit).all()

        return {
            "cluster_id": cluster_id,
            "total": len(actions),
            "actions": [
                {
                    "id": str(action.id),
                    "action_type": action.action_type.value,
                    "status": action.status.value,
                    "created_at": action.created_at.isoformat() if action.created_at else None,
                    "completed_at": action.completed_at.isoformat() if action.completed_at else None
                }
                for action in actions
            ]
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error listing actions for cluster {cluster_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to list actions: {str(e)}"
        )
