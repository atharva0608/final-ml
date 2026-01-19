from fastapi import APIRouter, Depends, Body, status
from sqlalchemy.orm import Session
from typing import List
from backend.models.base import get_db
from backend.core.dependencies import get_current_user, RequireRole
from backend.models.user import User
from backend.services.role_service import RoleService

router = APIRouter(prefix="/users", tags=["User Profile"])

@router.patch("/me")
def update_profile(
    full_name: str = Body(..., embed=True),
    db: Session = Depends(get_db), 
    user: User = Depends(get_current_user)
):
    user.full_name = full_name
    db.commit()
    return {"status": "success", "user": {"id": user.id, "email": user.email, "full_name": user.full_name}}


@router.post("/{user_id}/permissions", status_code=status.HTTP_200_OK)
async def update_user_permissions(
    user_id: str,
    permissions: List[str] = Body(..., embed=True),
    db: Session = Depends(get_db),
    current_user: User = Depends(RequireRole("ORG_ADMIN"))
):
    """
    Update direct/custom permissions for a user.
    """
    service = RoleService(db)
    user = service.update_user_permissions(user_id, permissions)
    return {"status": "success", "message": f"Updated permissions for user {user.email}", "permissions": [p.slug for p in user.custom_permissions]}


# Allowed widgets per role for validation
ROLE_ALLOWED_WIDGETS = {
    "SUPER_ADMIN": [
        "platform_health", "tenant_list", "global_audit", "revenue_chart",
        "cost_kpi", "savings_kpi", "savings_chart", "fleet_composition",
        "cluster_health", "activity_feed", "pending_approvals"
    ],
    "ORG_ADMIN": [
        "cost_kpi", "savings_kpi", "savings_chart", "fleet_composition",
        "cluster_health", "activity_feed", "pending_approvals", "team_budget"
    ],
    "CLIENT": [
        "cost_kpi", "savings_kpi", "savings_chart", "fleet_composition",
        "cluster_health", "activity_feed", "pending_approvals", "team_budget"
    ],
    "TEAM_LEAD": [
        "team_budget", "pending_approvals", "team_activity", "member_list",
        "cost_kpi", "savings_kpi", "activity_feed", "cluster_health"
    ],
    "MEMBER": [
        "my_resources", "my_tickets", "activity_feed", "cost_kpi", "savings_kpi"
    ]
}


@router.patch("/me/preferences")
def update_preferences(
    preferences: dict = Body(...),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user)
):
    """
    Update current user's dashboard preferences.
    
    Accepts: { dashboard_layout: ['widget1', 'widget2', ...], theme: 'dark' }
    Validates widget keys against allowed widgets for user's role.
    """
    # Validate dashboard_layout if provided
    if "dashboard_layout" in preferences:
        layout = preferences["dashboard_layout"]
        if not isinstance(layout, list):
            return {"status": "error", "message": "dashboard_layout must be an array"}
        
        # Get allowed widgets for this role
        role_name = user.role.value if hasattr(user.role, 'value') else str(user.role)
        allowed = ROLE_ALLOWED_WIDGETS.get(role_name, [])
        
        # Filter out any disallowed widgets
        valid_layout = [w for w in layout if w in allowed]
        preferences["dashboard_layout"] = valid_layout
    
    # Merge with existing preferences
    existing = user.preferences or {}
    existing.update(preferences)
    user.preferences = existing
    
    db.commit()
    db.refresh(user)
    
    return {
        "status": "success",
        "preferences": user.preferences
    }


@router.get("/me/preferences")
def get_preferences(
    user: User = Depends(get_current_user)
):
    """Get current user's preferences"""
    return {
        "preferences": user.preferences or {},
        "role": user.role.value if hasattr(user.role, 'value') else str(user.role)
    }
