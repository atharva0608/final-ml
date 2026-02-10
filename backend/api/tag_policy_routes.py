"""
Tag Policy API Routes
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import List

from backend.core.dependencies import get_db, get_current_user
from backend.models.user import User, UserRole
from backend.services.tag_policy_service import TagPolicyService
from backend.schemas.tag_policy_schemas import (
    TagPolicyCreate,
    TagPolicyUpdate,
    TagPolicyResponse,
    TagPolicyList,
    ComplianceStats
)

router = APIRouter(prefix="/tags/policies", tags=["Tag Policies"])


@router.post("/", response_model=TagPolicyResponse, status_code=201)
def create_tag_policy(
    policy_data: TagPolicyCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Create a new tag policy (Admin only)"""
    if current_user.role not in [UserRole.ORG_ADMIN, UserRole.SUPER_ADMIN]:
        raise HTTPException(status_code=403, detail="Admin access required")
    
    service = TagPolicyService(db, current_user.organization_id)
    
    try:
        policy = service.create_policy(policy_data)
        response = TagPolicyResponse.from_orm(policy)
        return response
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/", response_model=TagPolicyList)
def list_tag_policies(
    active_only: bool = Query(True, description="Only include active policies"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """List all tag policies for the organization"""
    service = TagPolicyService(db, current_user.organization_id)
    policies = service.list_policies(active_only=active_only)
    
    policy_responses = [TagPolicyResponse.from_orm(p) for p in policies]
    
    return TagPolicyList(
        policies=policy_responses,
        total=len(policies),
        advisory_count=len([p for p in policies if p.enforcement_level == "advisory"]),
        required_count=len([p for p in policies if p.enforcement_level == "required"]),
        strict_count=len([p for p in policies if p.enforcement_level == "strict"])
    )


@router.get("/{policy_id}", response_model=TagPolicyResponse)
def get_tag_policy(
    policy_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get a specific tag policy"""
    service = TagPolicyService(db, current_user.organization_id)
    policy = service.get_policy(policy_id)
    
    if not policy:
        raise HTTPException(status_code=404, detail="Policy not found")
    
    return TagPolicyResponse.from_orm(policy)


@router.put("/{policy_id}", response_model=TagPolicyResponse)
def update_tag_policy(
    policy_id: str,
    update_data: TagPolicyUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Update a tag policy (Admin only)"""
    if current_user.role not in [UserRole.ORG_ADMIN, UserRole.SUPER_ADMIN]:
        raise HTTPException(status_code=403, detail="Admin access required")
    
    service = TagPolicyService(db, current_user.organization_id)
    
    try:
        policy = service.update_policy(policy_id, update_data)
        return TagPolicyResponse.from_orm(policy)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.delete("/{policy_id}", status_code=204)
def delete_tag_policy(
    policy_id: str,
    hard_delete: bool = Query(False, description="Permanently delete (vs soft delete)"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Delete a tag policy (Admin only)"""
    if current_user.role not in [UserRole.ORG_ADMIN, UserRole.SUPER_ADMIN]:
        raise HTTPException(status_code=403, detail="Admin access required")
    
    service = TagPolicyService(db, current_user.organization_id)
    success = service.delete_policy(policy_id, hard_delete=hard_delete)
    
    if not success:
        raise HTTPException(status_code=404, detail="Policy not found")
    
    return None


@router.get("/compliance/stats", response_model=ComplianceStats)
def get_compliance_stats(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Get tag compliance statistics.
    Note: This requires recent cleanup scan data to calculate stats.
    """
    service = TagPolicyService(db, current_user.organization_id)
    
    # In a real implementation, fetch recent scan data from HygieneService
    # For now, return empty stats
    scanned_resources = []  # Would come from recent hygiene scans
    
    return service.get_compliance_stats(scanned_resources)
