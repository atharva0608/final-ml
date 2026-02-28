"""
Pool Rotation API Routes
========================

Endpoints for monitoring and controlling pool auto-rotation system.
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import List, Optional

from backend.core.dependencies import get_db, get_current_user
from backend.core.redis_client import get_redis_client
from backend.services.pool_rotation_service import PoolRotationService
from backend.schemas.template_schemas import PoolRotationStatus
from backend.models.user import User

router = APIRouter(prefix="/pool-rotation", tags=["Pool Rotation"])


@router.get("/status/{cluster_id}", response_model=dict)
async def get_rotation_status(
    cluster_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Get current pool rotation status for a cluster.

    Returns:
        - Current primary AZ
        - Backup AZs
        - Viable pool count
        - Auto-rotation active/inactive
        - Last rotation timestamp
        - Cascade dampener status
    """
    redis = get_redis_client()
    service = PoolRotationService(db, redis)
    status = service.get_rotation_status(cluster_id)

    if not status:
        # Return a default "never rotated" status — no 404, caller handles gracefully
        return {
            "cluster_id": cluster_id,
            "active": False,
            "rotation_needed": False,
            "primary_az": None,
            "backup_azs": [],
            "viable_pool_count": 0,
            "last_rotation": None,
            "cascade_dampener_active": False,
            "message": "Pool auto-rotation has not yet run for this cluster",
        }

    return status


@router.post("/check/{cluster_id}")
async def trigger_rotation_check(
    cluster_id: str,
    region: str = Query(default="ap-south-1", description="AWS region"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Manually trigger rotation check for a cluster.

    Analyzes pool health and executes rotation if needed.
    Normally runs automatically every 5 minutes via Celery.

    Returns:
        - Rotation needed: bool
        - Pool health status
        - Actions taken (if rotation executed)
    """
    redis = get_redis_client()
    service = PoolRotationService(db, redis)
    result = service.check_and_rotate(cluster_id, region)

    return result


@router.post("/force/{cluster_id}")
async def force_rotation(
    cluster_id: str,
    region: str = Query(default="ap-south-1", description="AWS region"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Force immediate rotation (admin only).

    Bypasses health checks and executes rotation immediately.
    Use only for testing or emergency situations.

    Requires: SUPER_ADMIN or ORG_ADMIN role
    """
    # Role check
    if current_user.role not in ["SUPER_ADMIN", "ORG_ADMIN"]:
        raise HTTPException(
            status_code=403,
            detail="Only admins can force rotation"
        )

    redis = get_redis_client()
    service = PoolRotationService(db, redis)
    result = service.force_rotation(cluster_id, region)

    if "error" in result:
        raise HTTPException(status_code=404, detail=result["error"])

    return result


@router.get("/status")
async def get_all_rotation_statuses(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Get rotation status for all clusters (admin view).

    Returns list of rotation statuses across all clusters.
    """
    # Role check
    if current_user.role not in ["SUPER_ADMIN", "ORG_ADMIN"]:
        raise HTTPException(
            status_code=403,
            detail="Only admins can view all rotation statuses"
        )

    redis = get_redis_client()
    service = PoolRotationService(db, redis)
    statuses = service.get_all_rotation_statuses()

    return {
        "statuses": statuses,
        "total_clusters": len(statuses)
    }


@router.get("/notifications/{cluster_id}")
async def get_rotation_notifications(
    cluster_id: str,
    current_user: User = Depends(get_current_user)
):
    """
    Get recent rotation notifications for a cluster.

    Returns last 24 hours of rotation events.
    """
    import json

    redis = get_redis_client()
    notif_key = f"notifications:rotation:{cluster_id}"
    notif_data = redis.get(notif_key)

    if not notif_data:
        return {
            "cluster_id": cluster_id,
            "notifications": [],
            "count": 0
        }

    notification = json.loads(notif_data)

    return {
        "cluster_id": cluster_id,
        "notifications": [notification],
        "count": 1
    }


@router.delete("/notifications/{cluster_id}")
async def clear_rotation_notifications(
    cluster_id: str,
    current_user: User = Depends(get_current_user)
):
    """
    Clear rotation notifications for a cluster (mark as read).
    """
    redis = get_redis_client()
    notif_key = f"notifications:rotation:{cluster_id}"
    redis.delete(notif_key)

    return {
        "cluster_id": cluster_id,
        "cleared": True
    }
