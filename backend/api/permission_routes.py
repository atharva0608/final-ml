"""
Permission Routes - JIT Feature Access Control API

Endpoints for checking permissions and listing user-accessible features.
"""

from fastapi import APIRouter, Depends, HTTPException
from typing import List, Dict, Any
from sqlalchemy.orm import Session

from backend.models.user import User
from backend.services.permission_service import PermissionService
from backend.core.dependencies import get_current_user
from backend.models.base import get_db
from backend.schemas.approval_schemas import PermissionCheckRequest, PermissionCheckResponse
from backend.core.exceptions import GovernanceError

router = APIRouter(prefix="/permissions", tags=["permissions"])


def get_permission_service(db: Session = Depends(get_db)) -> PermissionService:
    return PermissionService(db)


@router.post("/check", response_model=PermissionCheckResponse)
def check_permission(
    request: PermissionCheckRequest,
    current_user: User = Depends(get_current_user),
    service: PermissionService = Depends(get_permission_service)
):
    """
    Check if current user has permission for a specific feature.

    This is a non-blocking check that returns status without raising exceptions.
    Use this endpoint to conditionally show/hide UI elements or check access before attempting actions.

    Example Request:
        POST /api/v1/permissions/check
        {
            "feature_id": "hygiene:execute",
            "resource_id": "vol-123456" (optional)
        }

    Example Response (Allowed):
        {
            "allowed": true,
            "reason": "Active JIT ticket",
            "feature": {
                "id": "hygiene:execute",
                "name": "Execute Resource Cleanup",
                "risk_level": "HIGH"
            },
            "ticket": {
                "id": "ticket-123",
                "expires_at": "2026-02-10T18:00:00Z"
            },
            "expires_at": "2026-02-10T18:00:00Z"
        }

    Example Response (Denied):
        {
            "allowed": false,
            "reason": "JIT ticket required",
            "feature": {
                "id": "hygiene:execute",
                "name": "Execute Resource Cleanup",
                "description": "Terminate, delete, or release resources flagged by hygiene scans",
                "max_duration_hours": 4,
                "min_approver_role": "TEAM_LEAD",
                "risk_level": "HIGH"
            },
            "ticket": null
        }
    """
    result = service.check_permission(
        user=current_user,
        feature_id=request.feature_id,
        resource_id=request.resource_id
    )

    return PermissionCheckResponse(**result)


@router.get("/my-features")
def list_my_features(
    current_user: User = Depends(get_current_user),
    service: PermissionService = Depends(get_permission_service)
) -> Dict[str, Any]:
    """
    Get all features accessible to the current user.

    Returns three categories:
    1. **immediate_access**: Features the user can use right now (admin, active JIT ticket, or no approval needed)
    2. **requires_approval**: Features the user can request via JIT ticket
    3. **denied**: Features the user cannot access (missing base permissions)

    Example Response:
        {
            "immediate_access": [
                {
                    "feature_id": "hygiene:view",
                    "name": "View Resource Hygiene Reports",
                    "ticket": null
                },
                {
                    "feature_id": "hygiene:execute",
                    "name": "Execute Resource Cleanup",
                    "ticket": {
                        "id": "ticket-123",
                        "expires_at": "2026-02-10T18:00:00Z"
                    }
                }
            ],
            "requires_approval": [
                {
                    "feature_id": "compute:terminate",
                    "name": "Terminate EC2 Instances",
                    "description": "Shut down and terminate running instances",
                    "risk_level": "CRITICAL",
                    "min_approver_role": "TEAM_LEAD"
                }
            ],
            "denied": []
        }
    """
    return service.list_user_features(current_user)


@router.post("/{user_id}/revoke-feature/{feature_id}")
def revoke_feature_access(
    user_id: str,
    feature_id: str,
    current_user: User = Depends(get_current_user),
    service: PermissionService = Depends(get_permission_service)
):
    """
    Revoke all active JIT tickets for a specific user + feature combination.

    This is an admin action to immediately terminate access.
    Only ORG_ADMIN or SUPER_ADMIN can revoke others' access.

    Returns:
        {
            "revoked": true/false,
            "user_id": "user-123",
            "feature_id": "hygiene:execute"
        }
    """
    from backend.models.user import UserRole

    # Authorization: Only admins can revoke others' access
    if current_user.id != user_id:
        if current_user.role not in [UserRole.ORG_ADMIN, UserRole.SUPER_ADMIN]:
            raise HTTPException(
                status_code=403,
                detail="Only Organization Admins can revoke access for other users"
            )

    success = service.revoke_feature_access(user_id, feature_id)

    return {
        "revoked": success,
        "user_id": user_id,
        "feature_id": feature_id
    }


@router.get("/feature-registry")
def get_feature_registry() -> Dict[str, Any]:
    """
    Get the complete feature registry with all protected features.

    This is useful for building UI forms, displaying feature catalogs, or documentation.

    Returns:
        {
            "features": {
                "hygiene:execute": {
                    "id": "hygiene:execute",
                    "name": "Execute Resource Cleanup",
                    "description": "...",
                    "category": "HYGIENE",
                    "risk_level": "HIGH",
                    "max_duration_hours": 4,
                    "requires_approval": true,
                    ...
                },
                ...
            },
            "count": 54
        }
    """
    from backend.core.feature_registry import FEATURE_REGISTRY

    features = {}
    for feature_id, feature in FEATURE_REGISTRY.items():
        features[feature_id] = feature.__dict__

    return {
        "features": features,
        "count": len(features)
    }
