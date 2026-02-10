from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List, Optional
from uuid import UUID

from backend.core.dependencies import get_db, get_current_user, require_org_admin
from backend.models.hygiene_policy import HygienePolicy
from backend.schemas.hygiene_policy_schemas import (
    HygienePolicyCreate,
    HygienePolicyUpdate,
    HygienePolicyResponse
)
from backend.models.user import User

router = APIRouter(
    prefix="/hygiene-policies",
    tags=["hygiene-policies"]
)

@router.get("/", response_model=List[HygienePolicyResponse])
def list_hygiene_policies(
    resource_type: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """List all hygiene policies"""
    query = db.query(HygienePolicy)

    if current_user.organization_id:
        query = query.filter(HygienePolicy.organization_id == current_user.organization_id)

    if resource_type:
        query = query.filter(HygienePolicy.resource_type == resource_type)

    return query.order_by(HygienePolicy.priority.desc()).all()

@router.post("/", response_model=HygienePolicyResponse)
def create_hygiene_policy(
    policy: HygienePolicyCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_org_admin)
):
    """Create a new hygiene policy"""
    policy_data = policy.dict()
    policy_data['organization_id'] = current_user.organization_id

    db_policy = HygienePolicy(**policy_data)
    db.add(db_policy)
    db.commit()
    db.refresh(db_policy)
    return db_policy

@router.get("/{policy_id}", response_model=HygienePolicyResponse)
def get_hygiene_policy(
    policy_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get a specific policy"""
    policy = db.query(HygienePolicy).filter(HygienePolicy.id == policy_id).first()
    if not policy:
        raise HTTPException(status_code=404, detail="Policy not found")

    if policy.organization_id != current_user.organization_id:
        raise HTTPException(status_code=403, detail="Not authorized to view this policy")

    return policy

@router.patch("/{policy_id}", response_model=HygienePolicyResponse)
def update_hygiene_policy(
    policy_id: UUID,
    policy_update: HygienePolicyUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_org_admin)
):
    """Update a policy"""
    policy = db.query(HygienePolicy).filter(HygienePolicy.id == policy_id).first()
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
def delete_hygiene_policy(
    policy_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_org_admin)
):
    """Delete a policy"""
    policy = db.query(HygienePolicy).filter(HygienePolicy.id == policy_id).first()
    if not policy:
        raise HTTPException(status_code=404, detail="Policy not found")

    if policy.organization_id != current_user.organization_id:
        raise HTTPException(status_code=403, detail="Not authorized to delete this policy")

    db.delete(policy)
    db.commit()
    return {"status": "success", "message": "Policy deleted"}
