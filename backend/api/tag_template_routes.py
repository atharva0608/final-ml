"""
Tag Template API Routes — Tag Templates (Tab 2)
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from datetime import datetime

from backend.core.dependencies import get_db, get_current_user
from backend.models.user import User, UserRole
from backend.models.tag_template import TagTemplate
from backend.models.tag_compliance_score import TagComplianceScore
from backend.models.audit_log import AuditLog
from backend.schemas.tag_template_schemas import (
    TagTemplateCreate,
    TagTemplateUpdate,
    TagTemplateResponse,
    TagTemplateListResponse,
    CoverageHeatmapEntry,
)

router = APIRouter(prefix="/tags/templates", tags=["Tag Templates"])


def _write_audit(db: Session, user: User, event: str, resource_id: str, details: str = ""):
    try:
        log = AuditLog(
            organization_id=user.organization_id,
            actor_id=user.id,
            actor_name=user.email,
            event=event,
            resource=resource_id,
            resource_type="TAG_TEMPLATE",
            outcome="success",
            details=details,
        )
        db.add(log)
    except Exception:
        pass


def _compute_coverage_heatmap(db: Session, org_id: str):
    """Compute per-tag-key coverage from compliance scores"""
    from sqlalchemy import func, distinct

    total_resources = (
        db.query(func.count(distinct(TagComplianceScore.resource_id)))
        .filter(TagComplianceScore.organization_id == org_id)
        .scalar()
    ) or 0

    if total_resources == 0:
        # Return keys from templates with 0% coverage
        templates = db.query(TagTemplate).filter(
            TagTemplate.organization_id == org_id,
            TagTemplate.is_active == True
        ).all()
        all_keys = set()
        for t in templates:
            if t.tag_schema:
                for entry in t.tag_schema:
                    if isinstance(entry, dict) and entry.get("key"):
                        all_keys.add(entry["key"])
        return [CoverageHeatmapEntry(key=k, coverage_pct=0.0) for k in sorted(all_keys)]

    # Try to get cached heatmap from Redis
    try:
        from backend.core.redis_client import get_redis
        import json
        redis = get_redis()
        if redis:
            cached = redis.get(f"tag_heatmap:{org_id}")
            if cached:
                data = json.loads(cached)
                return [CoverageHeatmapEntry(**e) for e in data]
    except Exception:
        pass

    # Fallback: extract keys from templates
    templates = db.query(TagTemplate).filter(
        TagTemplate.organization_id == org_id,
        TagTemplate.is_active == True
    ).all()
    all_keys = set()
    for t in templates:
        if t.tag_schema:
            for entry in t.tag_schema:
                if isinstance(entry, dict) and entry.get("key"):
                    all_keys.add(entry["key"])

    return [CoverageHeatmapEntry(key=k, coverage_pct=0.0) for k in sorted(all_keys)]


@router.get("/", response_model=TagTemplateListResponse)
def list_tag_templates(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """List all tag templates with coverage heatmap"""
    templates = db.query(TagTemplate).filter(
        TagTemplate.organization_id == current_user.organization_id,
        TagTemplate.is_active == True
    ).order_by(TagTemplate.name).all()

    default_id = None
    responses = []
    for t in templates:
        resp = TagTemplateResponse.from_orm(t)
        if t.is_default:
            default_id = t.id
        responses.append(resp)

    heatmap = _compute_coverage_heatmap(db, current_user.organization_id)

    return TagTemplateListResponse(
        templates=responses,
        total=len(responses),
        default_template_id=default_id,
        coverage_heatmap=heatmap,
    )


@router.post("/", response_model=TagTemplateResponse, status_code=201)
def create_tag_template(
    data: TagTemplateCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Create a new tag template with schema and scope"""
    if current_user.role not in [UserRole.ORG_ADMIN, UserRole.SUPER_ADMIN]:
        raise HTTPException(status_code=403, detail="Admin access required")

    # If setting as default, unset others
    if data.is_default:
        db.query(TagTemplate).filter(
            TagTemplate.organization_id == current_user.organization_id,
            TagTemplate.is_default == True
        ).update({"is_default": False})

    tag_schema_dicts = [entry.dict() for entry in data.tag_schema] if data.tag_schema else []

    template = TagTemplate(
        organization_id=current_user.organization_id,
        name=data.name,
        description=data.description,
        scope=data.scope or [],
        tag_schema=tag_schema_dicts,
        is_default=data.is_default,
        created_by=current_user.id,
        tags=data.tags or {},
        resource_scope=data.resource_scope or "all",
    )

    db.add(template)
    _write_audit(db, current_user, "TAG_TEMPLATE_CREATED", template.id, f"Created template '{data.name}'")
    db.commit()
    db.refresh(template)

    return TagTemplateResponse.from_orm(template)


@router.get("/{template_id}", response_model=TagTemplateResponse)
def get_tag_template(
    template_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get a specific template"""
    template = db.query(TagTemplate).filter(
        TagTemplate.id == template_id,
        TagTemplate.organization_id == current_user.organization_id
    ).first()
    if not template:
        raise HTTPException(status_code=404, detail="Template not found")
    return TagTemplateResponse.from_orm(template)


@router.put("/{template_id}", response_model=TagTemplateResponse)
def update_tag_template(
    template_id: str,
    data: TagTemplateUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Update a tag template"""
    if current_user.role not in [UserRole.ORG_ADMIN, UserRole.SUPER_ADMIN]:
        raise HTTPException(status_code=403, detail="Admin access required")

    template = db.query(TagTemplate).filter(
        TagTemplate.id == template_id,
        TagTemplate.organization_id == current_user.organization_id
    ).first()
    if not template:
        raise HTTPException(status_code=404, detail="Template not found")

    update_dict = data.dict(exclude_unset=True)

    if update_dict.get("is_default"):
        db.query(TagTemplate).filter(
            TagTemplate.organization_id == current_user.organization_id,
            TagTemplate.is_default == True,
            TagTemplate.id != template_id
        ).update({"is_default": False})

    if "tag_schema" in update_dict and update_dict["tag_schema"]:
        update_dict["tag_schema"] = [
            entry.dict() if hasattr(entry, 'dict') else entry
            for entry in update_dict["tag_schema"]
        ]

    for field, value in update_dict.items():
        setattr(template, field, value)
    template.updated_at = datetime.utcnow()

    # Invalidate compliance cache
    try:
        from backend.core.redis_client import get_redis
        redis = get_redis()
        if redis:
            redis.delete(f"tag_compliance:{current_user.organization_id}")
    except Exception:
        pass

    _write_audit(db, current_user, "TAG_TEMPLATE_UPDATED", template_id, f"Updated template '{template.name}'")
    db.commit()
    db.refresh(template)

    return TagTemplateResponse.from_orm(template)


@router.delete("/{template_id}", status_code=204)
def delete_tag_template(
    template_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Delete a tag template"""
    if current_user.role not in [UserRole.ORG_ADMIN, UserRole.SUPER_ADMIN]:
        raise HTTPException(status_code=403, detail="Admin access required")

    template = db.query(TagTemplate).filter(
        TagTemplate.id == template_id,
        TagTemplate.organization_id == current_user.organization_id
    ).first()
    if not template:
        raise HTTPException(status_code=404, detail="Template not found")

    if template.is_default:
        other_count = db.query(TagTemplate).filter(
            TagTemplate.organization_id == current_user.organization_id,
            TagTemplate.is_active == True,
            TagTemplate.id != template_id
        ).count()
        if other_count == 0:
            raise HTTPException(status_code=400, detail="Cannot delete the only template")

    name = template.name
    template.is_active = False
    template.updated_at = datetime.utcnow()
    _write_audit(db, current_user, "TAG_TEMPLATE_DELETED", template_id, f"Deleted template '{name}'")
    db.commit()

    return None
