"""
Governance API Routes (Feature 4)
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import Dict, Any

from backend.core.dependencies import get_db, get_current_user, require_org_admin
from backend.services.governance_service import GovernanceService
from backend.models.user import User
from backend.models.organization import Organization

router = APIRouter(
    prefix="/governance",
    tags=["governance"]
)


@router.get("/policies")
def get_policies(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get governance policies for the current user's organization"""
    service = GovernanceService(db)
    # Check if we need to reload the user/org to get fresh data
    db.refresh(current_user) # Ensure relations are loaded
    
    return {
        "is_governance_enabled": current_user.organization.is_governance_enabled if current_user.organization else False,
        "is_strict_mode": current_user.organization.is_strict_approval_mode if current_user.organization else False,
        "require_automation_approval": current_user.organization.require_automation_approval if current_user.organization else True,
        "required_tags": current_user.organization.required_tags if current_user.organization else [],
        "policies": service.get_organization_policies(current_user.organization_id)
    }


@router.patch("/policies")
def update_policies(
    policy_updates: Dict[str, Any],
    db: Session = Depends(get_db),
    current_user: User = Depends(require_org_admin)
):
    """
    Update governance policies (Org Admin only)
    Expected body: {"is_governance_enabled": true, "policies": {...}, "required_tags": [...]}
    """
    org = db.query(Organization).filter(Organization.id == current_user.organization_id).first()
    if not org:
        raise HTTPException(status_code=404, detail="Organization not found")
    
    # Update master toggle
    if "is_governance_enabled" in policy_updates:
        org.is_governance_enabled = policy_updates["is_governance_enabled"]
    
    if "is_strict_mode" in policy_updates:
        org.is_strict_approval_mode = policy_updates["is_strict_mode"]

    if "require_automation_approval" in policy_updates:
        org.require_automation_approval = policy_updates["require_automation_approval"]
    
    # Update required tags
    if "required_tags" in policy_updates:
        org.required_tags = policy_updates["required_tags"]
    
    # Update policy config
    if "policies" in policy_updates:
        current_config = org.governance_config or {}
        current_config.update(policy_updates["policies"])
        org.governance_config = current_config
    
    db.commit()
    db.refresh(org)
    
    return {"status": "success", "message": "Policies updated"}


@router.post("/run-autopilot")
def run_autopilot(
    account_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_org_admin)
):
    """
    Manually trigger automated governance for an account (Org Admin only).
    In production, this would be called by a scheduled worker.
    """
    service = GovernanceService(db)
    actions = service.run_automated_cleanup(current_user.organization_id, account_id)
    return {
        "status": "success",
        "actions_taken": len(actions),
        "details": actions
    }
