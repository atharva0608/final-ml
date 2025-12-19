"""
[BE-STORAGE-001] Storage Cleanup API Routes

Provides endpoints for AWS storage management:
1. List unmapped/unattached EBS volumes
2. Delete flagged volumes
3. List unused AMI snapshots
4. Delete flagged snapshots

From realworkflow.md Table 1, Lines 40-41 and Table 2, Lines 73-76
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List
from datetime import datetime, timedelta
from pydantic import BaseModel

from database.connection import get_db
from database.models import User
from api.auth import get_current_active_user
from utils.system_logger import SystemLogger

router = APIRouter(
    prefix="/storage",
    tags=["Storage Management"]
)


# ==============================================================================
# Request/Response Models
# ==============================================================================

class VolumeResponse(BaseModel):
    volume_id: str
    size_gb: int
    volume_type: str
    availability_zone: str
    created_at: str
    last_attached: str | None
    cost_per_month: float


class SnapshotResponse(BaseModel):
    snapshot_id: str
    size_gb: int
    description: str | None
    created_at: str
    ami_id: str | None
    cost_per_month: float


class CleanupRequest(BaseModel):
    volume_ids: List[str] | None = None
    snapshot_ids: List[str] | None = None


# ==============================================================================
# [BE-STORAGE-001] Get Unmapped Volumes (from realworkflow.md Table 2, Line 73)
# ==============================================================================

@router.get("/unmapped-volumes", response_model=List[VolumeResponse])
async def get_unmapped_volumes(
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    [BE-STORAGE-001] List unattached EBS volumes

    Returns a list of EBS volumes that are:
    - Not attached to any instance
    - Older than 7 days (to avoid cleanup of temporary volumes)

    Used by Node Fleet dashboard Volumes section
    Requires admin role
    """
    # Check admin permission
    if current_user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required"
        )

    # In production, this would query AWS EBS API
    # For now, return mock data
    mock_volumes = [
        {
            "volume_id": "vol-0123456789abcdef0",
            "size_gb": 100,
            "volume_type": "gp3",
            "availability_zone": "us-east-1a",
            "created_at": (datetime.utcnow() - timedelta(days=45)).isoformat(),
            "last_attached": (datetime.utcnow() - timedelta(days=30)).isoformat(),
            "cost_per_month": 8.00
        },
        {
            "volume_id": "vol-0abcdef123456789a",
            "size_gb": 250,
            "volume_type": "gp3",
            "availability_zone": "us-east-1b",
            "created_at": (datetime.utcnow() - timedelta(days=60)).isoformat(),
            "last_attached": None,
            "cost_per_month": 20.00
        },
        {
            "volume_id": "vol-0fedcba987654321b",
            "size_gb": 500,
            "volume_type": "io2",
            "availability_zone": "us-east-1c",
            "created_at": (datetime.utcnow() - timedelta(days=90)).isoformat(),
            "last_attached": (datetime.utcnow() - timedelta(days=75)).isoformat(),
            "cost_per_month": 62.50
        }
    ]

    logger = SystemLogger("waste_scanner", db=db)
    logger.info(
        f"Unmapped volumes queried by {current_user.username}",
        details={"volume_count": len(mock_volumes)}
    )

    return [VolumeResponse(**vol) for vol in mock_volumes]


# ==============================================================================
# [BE-STORAGE-002] Cleanup Volumes (from realworkflow.md Table 2, Line 74)
# ==============================================================================

@router.post("/volumes/cleanup")
async def cleanup_volumes(
    request: CleanupRequest,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    [BE-STORAGE-002] Delete flagged EBS volumes

    Deletes the specified unattached EBS volumes to reduce costs.

    Args:
        request: Contains list of volume_ids to delete
        current_user: Authenticated admin user
        db: Database session

    Returns:
        Status confirmation with deletion count

    Used by Node Fleet dashboard Volumes cleanup action
    Requires admin role
    """
    # Check admin permission
    if current_user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required"
        )

    if not request.volume_ids or len(request.volume_ids) == 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No volume IDs provided"
        )

    # In production, this would:
    # 1. Validate volumes are unattached
    # 2. Call AWS EBS API to delete volumes
    # 3. Track deletion status

    deleted_count = len(request.volume_ids)
    estimated_monthly_savings = deleted_count * 15.0  # Mock calculation

    logger = SystemLogger("waste_scanner", db=db)
    logger.info(
        f"Volume cleanup initiated by {current_user.username}",
        details={
            "volume_ids": request.volume_ids,
            "deleted_count": deleted_count,
            "estimated_savings": estimated_monthly_savings
        }
    )

    print(f"🗑️  VOLUME CLEANUP: {deleted_count} volumes deleted by {current_user.username}")

    return {
        "status": "success",
        "message": f"Successfully deleted {deleted_count} volumes",
        "deleted_volumes": request.volume_ids,
        "deleted_count": deleted_count,
        "estimated_monthly_savings_usd": estimated_monthly_savings,
        "triggered_by": current_user.username,
        "triggered_at": datetime.utcnow().isoformat()
    }


# ==============================================================================
# [BE-STORAGE-003] Get AMI Snapshots (from realworkflow.md Table 2, Line 75)
# ==============================================================================

@router.get("/ami-snapshots", response_model=List[SnapshotResponse])
async def get_ami_snapshots(
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    [BE-STORAGE-003] List unused AMI snapshots

    Returns a list of EBS snapshots that:
    - Are older than 90 days
    - Are not associated with any active AMI
    - Are not being used for volume creation

    Used by Node Fleet dashboard Snapshots section
    Requires admin role
    """
    # Check admin permission
    if current_user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required"
        )

    # In production, this would query AWS snapshot API
    # For now, return mock data
    mock_snapshots = [
        {
            "snapshot_id": "snap-0123456789abcdef0",
            "size_gb": 50,
            "description": "Backup from old deployment",
            "created_at": (datetime.utcnow() - timedelta(days=180)).isoformat(),
            "ami_id": None,
            "cost_per_month": 2.50
        },
        {
            "snapshot_id": "snap-0abcdef123456789a",
            "size_gb": 100,
            "description": "Test environment snapshot",
            "created_at": (datetime.utcnow() - timedelta(days=120)).isoformat(),
            "ami_id": "ami-obsolete-12345",
            "cost_per_month": 5.00
        },
        {
            "snapshot_id": "snap-0fedcba987654321b",
            "size_gb": 200,
            "description": None,
            "created_at": (datetime.utcnow() - timedelta(days=365)).isoformat(),
            "ami_id": None,
            "cost_per_month": 10.00
        },
        {
            "snapshot_id": "snap-0987654321fedcbac",
            "size_gb": 150,
            "description": "Legacy system backup",
            "created_at": (datetime.utcnow() - timedelta(days=200)).isoformat(),
            "ami_id": "ami-legacy-98765",
            "cost_per_month": 7.50
        }
    ]

    logger = SystemLogger("waste_scanner", db=db)
    logger.info(
        f"AMI snapshots queried by {current_user.username}",
        details={"snapshot_count": len(mock_snapshots)}
    )

    return [SnapshotResponse(**snap) for snap in mock_snapshots]


# ==============================================================================
# [BE-STORAGE-004] Cleanup Snapshots (from realworkflow.md Table 2, Line 76)
# ==============================================================================

@router.post("/snapshots/cleanup")
async def cleanup_snapshots(
    request: CleanupRequest,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    [BE-STORAGE-004] Delete flagged AMI snapshots

    Deletes the specified unused AMI snapshots to reduce costs.

    Args:
        request: Contains list of snapshot_ids to delete
        current_user: Authenticated admin user
        db: Database session

    Returns:
        Status confirmation with deletion count

    Used by Node Fleet dashboard Snapshots cleanup action
    Requires admin role
    """
    # Check admin permission
    if current_user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required"
        )

    if not request.snapshot_ids or len(request.snapshot_ids) == 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No snapshot IDs provided"
        )

    # In production, this would:
    # 1. Validate snapshots are unused
    # 2. Call AWS snapshot API to delete
    # 3. Track deletion status

    deleted_count = len(request.snapshot_ids)
    estimated_monthly_savings = deleted_count * 6.0  # Mock calculation

    logger = SystemLogger("waste_scanner", db=db)
    logger.info(
        f"Snapshot cleanup initiated by {current_user.username}",
        details={
            "snapshot_ids": request.snapshot_ids,
            "deleted_count": deleted_count,
            "estimated_savings": estimated_monthly_savings
        }
    )

    print(f"🗑️  SNAPSHOT CLEANUP: {deleted_count} snapshots deleted by {current_user.username}")

    return {
        "status": "success",
        "message": f"Successfully deleted {deleted_count} snapshots",
        "deleted_snapshots": request.snapshot_ids,
        "deleted_count": deleted_count,
        "estimated_monthly_savings_usd": estimated_monthly_savings,
        "triggered_by": current_user.username,
        "triggered_at": datetime.utcnow().isoformat()
    }
