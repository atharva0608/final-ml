"""
Tag Policy API Routes — Governance Policies (Tab 1)
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from datetime import datetime

from backend.core.dependencies import get_db, get_current_user
from backend.models.user import User, UserRole
from backend.models.tag_policy import TagPolicy
from backend.models.audit_log import AuditLog
from backend.schemas.tag_policy_schemas import (
    TagPolicyCreate,
    TagPolicyUpdate,
    TagPolicyResponse,
    TagPolicyGroupedResponse,
)

router = APIRouter(prefix="/tags/policies", tags=["Tag Policies"])


def _write_audit(db: Session, user: User, event: str, resource_id: str, details: str = ""):
    """Write audit log entry for tag policy changes"""
    try:
        log = AuditLog(
            organization_id=user.organization_id,
            actor_id=user.id,
            actor_name=user.email,
            event=event,
            resource=resource_id,
            resource_type="TAG_POLICY",
            outcome="success",
            details=details,
        )
        db.add(log)
    except Exception:
        pass  # Don't fail the main operation if audit logging fails


@router.get("/", response_model=TagPolicyGroupedResponse)
def list_tag_policies(
    active_only: bool = Query(False, description="Only include active policies"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """List all tag policies grouped by enforcement level"""
    query = db.query(TagPolicy).filter(
        TagPolicy.organization_id == current_user.organization_id
    )
    if active_only:
        query = query.filter(TagPolicy.is_active == True)

    policies = query.order_by(TagPolicy.tag_key).all()

    grouped = {"strict": [], "required": [], "advisory": []}
    for p in policies:
        resp = TagPolicyResponse.from_orm(p)
        level = p.enforcement_level or "advisory"
        if level in grouped:
            grouped[level].append(resp)
        else:
            grouped["advisory"].append(resp)

    return TagPolicyGroupedResponse(**grouped)


@router.post("/", response_model=TagPolicyResponse, status_code=201)
def create_tag_policy(
    policy_data: TagPolicyCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Create a new tag policy (Admin only)"""
    if current_user.role not in [UserRole.ORG_ADMIN, UserRole.SUPER_ADMIN]:
        raise HTTPException(status_code=403, detail="Admin access required")

    # Check for duplicate tag key
    existing = db.query(TagPolicy).filter(
        TagPolicy.organization_id == current_user.organization_id,
        TagPolicy.tag_key == policy_data.tag_key,
        TagPolicy.is_active == True
    ).first()
    if existing:
        raise HTTPException(status_code=400, detail=f"Active policy for tag '{policy_data.tag_key}' already exists")

    # Validate regex if pattern mode
    if policy_data.value_mode == 'pattern' and policy_data.validation_regex:
        import re
        try:
            re.compile(policy_data.validation_regex)
        except re.error:
            raise HTTPException(status_code=400, detail="Invalid regex pattern")

    policy = TagPolicy(
        organization_id=current_user.organization_id,
        tag_key=policy_data.tag_key,
        description=policy_data.description,
        value_mode=policy_data.value_mode,
        allowed_values=policy_data.allowed_values,
        validation_regex=policy_data.validation_regex,
        enforcement_level=policy_data.enforcement_level,
        resource_types=policy_data.resource_types,
        regions=policy_data.regions,
        is_active=policy_data.is_active,
    )

    db.add(policy)
    _write_audit(db, current_user, "TAG_POLICY_CREATED", policy.id, f"Created policy for tag '{policy.tag_key}'")
    db.commit()
    db.refresh(policy)

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

    policy = db.query(TagPolicy).filter(
        TagPolicy.id == policy_id,
        TagPolicy.organization_id == current_user.organization_id
    ).first()
    if not policy:
        raise HTTPException(status_code=404, detail="Policy not found")

    update_dict = update_data.dict(exclude_unset=True)
    changed_fields = []
    for field, value in update_dict.items():
        old_val = getattr(policy, field, None)
        if old_val != value:
            changed_fields.append(f"{field}: {old_val} → {value}")
        setattr(policy, field, value)

    policy.updated_at = datetime.utcnow()
    _write_audit(db, current_user, "TAG_POLICY_UPDATED", policy_id, "; ".join(changed_fields))
    db.commit()
    db.refresh(policy)

    return TagPolicyResponse.from_orm(policy)


@router.delete("/{policy_id}", status_code=204)
def delete_tag_policy(
    policy_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Delete a tag policy (Admin only)"""
    if current_user.role not in [UserRole.ORG_ADMIN, UserRole.SUPER_ADMIN]:
        raise HTTPException(status_code=403, detail="Admin access required")

    policy = db.query(TagPolicy).filter(
        TagPolicy.id == policy_id,
        TagPolicy.organization_id == current_user.organization_id
    ).first()
    if not policy:
        raise HTTPException(status_code=404, detail="Policy not found")

    tag_key = policy.tag_key
    db.delete(policy)
    _write_audit(db, current_user, "TAG_POLICY_DELETED", policy_id, f"Deleted policy for tag '{tag_key}'")
    db.commit()

    return None


@router.patch("/{policy_id}/toggle")
def toggle_tag_policy(
    policy_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Toggle a tag policy's active status"""
    if current_user.role not in [UserRole.ORG_ADMIN, UserRole.SUPER_ADMIN]:
        raise HTTPException(status_code=403, detail="Admin access required")

    policy = db.query(TagPolicy).filter(
        TagPolicy.id == policy_id,
        TagPolicy.organization_id == current_user.organization_id
    ).first()
    if not policy:
        raise HTTPException(status_code=404, detail="Policy not found")

    policy.is_active = not policy.is_active
    policy.updated_at = datetime.utcnow()
    db.commit()

    return {"id": policy.id, "is_active": policy.is_active}
