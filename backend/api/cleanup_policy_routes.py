from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List, Optional
from uuid import UUID

from backend.core.dependencies import get_db, get_current_user, require_org_admin
from backend.models.cleanup_policy import CleanupPolicy
from backend.schemas.cleanup_policy_schemas import (
    CleanupPolicyCreate, 
    CleanupPolicyUpdate, 
    CleanupPolicyResponse
)
from backend.models.user import User

router = APIRouter(
    prefix="/cleanup-policies",
    tags=["cleanup-policies"]
)

@router.get("/", response_model=List[CleanupPolicyResponse])
def list_cleanup_policies(
    resource_type: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """List all cleanup policies"""
    query = db.query(CleanupPolicy)
    
    # Filter by organization if applicable
    if current_user.organization_id:
        query = query.filter(CleanupPolicy.organization_id == current_user.organization_id)
        
    if resource_type:
        query = query.filter(CleanupPolicy.resource_type == resource_type)
        
    return query.order_by(CleanupPolicy.priority.desc()).all()

@router.post("/", response_model=CleanupPolicyResponse)
def create_cleanup_policy(
    policy: CleanupPolicyCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_org_admin)
):
    """Create a new cleanup policy"""
    # Force organization ID
    policy_data = policy.dict()
    policy_data['organization_id'] = current_user.organization_id
    
    db_policy = CleanupPolicy(**policy_data)
    db.add(db_policy)
    db.commit()
    db.refresh(db_policy)
    return db_policy

@router.get("/{policy_id}", response_model=CleanupPolicyResponse)
def get_cleanup_policy(
    policy_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get a specific policy"""
    policy = db.query(CleanupPolicy).filter(CleanupPolicy.id == policy_id).first()
    if not policy:
        raise HTTPException(status_code=404, detail="Policy not found")
        
    if policy.organization_id != current_user.organization_id:
        raise HTTPException(status_code=403, detail="Not authorized to view this policy")
        
    return policy

@router.patch("/{policy_id}", response_model=CleanupPolicyResponse)
def update_cleanup_policy(
    policy_id: UUID,
    policy_update: CleanupPolicyUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_org_admin)
):
    """Update a policy"""
    policy = db.query(CleanupPolicy).filter(CleanupPolicy.id == policy_id).first()
    if not policy:
        raise HTTPException(status_code=404, detail="Policy not found")
        
    if policy.organization_id != current_user.organization_id:
        raise HTTPException(status_code=403, detail="Not authorized to update this policy")
        
    update_data = policy_update.dict(exclude_unset=True)
    for key, value in update_data.items():
        setattr(policy, key, value)
        
    db.commit()
    db.refresh(policy)
    return policy

@router.delete("/{policy_id}")
def delete_cleanup_policy(
    policy_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_org_admin)
):
    """Delete a policy"""
    policy = db.query(CleanupPolicy).filter(CleanupPolicy.id == policy_id).first()
    if not policy:
        raise HTTPException(status_code=404, detail="Policy not found")
        
    if policy.organization_id != current_user.organization_id:
        raise HTTPException(status_code=403, detail="Not authorized to delete this policy")
        
    db.delete(policy)
    db.commit()
    return {"status": "success", "message": "Policy deleted"}
