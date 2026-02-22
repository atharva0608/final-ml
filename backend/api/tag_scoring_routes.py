"""
Tag Scoring Engine API Routes — Scoring Engine (Tab 3)
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from datetime import datetime

from backend.core.dependencies import get_db, get_current_user
from backend.models.user import User, UserRole
from backend.models.tag_scoring_config import TagScoringConfig
from backend.models.tag_compliance_score import TagComplianceScore
from backend.models.tag_template import TagTemplate
from backend.models.audit_log import AuditLog
from backend.schemas.tag_scoring_schemas import (
    ScoringConfigUpdate,
    ScoringConfigResponse,
    ScoringPreviewResource,
    ScoringPreviewResponse,
)

router = APIRouter(prefix="/tags/scoring", tags=["Tag Scoring"])


@router.get("/config", response_model=ScoringConfigResponse)
def get_scoring_config(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get scoring configuration for the organization (or defaults)"""
    config = db.query(TagScoringConfig).filter(
        TagScoringConfig.organization_id == current_user.organization_id
    ).first()

    if config:
        return ScoringConfigResponse.from_orm(config)

    # Return defaults if no config exists
    return ScoringConfigResponse(
        mode="weighted",
        threshold=60,
        required_keys=[],
    )


@router.put("/config", response_model=ScoringConfigResponse)
def save_scoring_config(
    data: ScoringConfigUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Save/update scoring configuration (upsert)"""
    if current_user.role not in [UserRole.ORG_ADMIN, UserRole.SUPER_ADMIN]:
        raise HTTPException(status_code=403, detail="Admin access required")

    config = db.query(TagScoringConfig).filter(
        TagScoringConfig.organization_id == current_user.organization_id
    ).first()

    if config:
        config.mode = data.mode
        config.threshold = data.threshold if data.threshold is not None else 60
        config.required_keys = data.required_keys or []
        config.updated_at = datetime.utcnow()
    else:
        config = TagScoringConfig(
            organization_id=current_user.organization_id,
            mode=data.mode,
            threshold=data.threshold if data.threshold is not None else 60,
            required_keys=data.required_keys or [],
        )
        db.add(config)

    # Invalidate compliance cache
    try:
        from backend.core.redis_client import get_redis
        redis = get_redis()
        if redis:
            redis.delete(f"tag_compliance:{current_user.organization_id}")
    except Exception:
        pass

    # Audit log
    try:
        log = AuditLog(
            organization_id=current_user.organization_id,
            actor_id=current_user.id,
            actor_name=current_user.email,
            event="SCORING_CONFIG_UPDATED",
            resource=current_user.organization_id,
            resource_type="TAG_SCORING",
            outcome="success",
            details=f"mode={data.mode}, threshold={data.threshold}",
        )
        db.add(log)
    except Exception:
        pass

    db.commit()
    db.refresh(config)

    return ScoringConfigResponse.from_orm(config)


@router.get("/preview", response_model=ScoringPreviewResponse)
def preview_scoring(
    mode: str = Query("weighted", description="Scoring mode"),
    threshold: int = Query(60, ge=0, le=100, description="Score threshold"),
    required_keys: str = Query(None, description="Comma-separated required keys"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Preview scoring on up to 5 recent resources without saving"""
    from backend.services.tag_scoring_service import TagScoringService

    service = TagScoringService(db, current_user.organization_id)

    req_keys_list = [k.strip() for k in required_keys.split(",")] if required_keys else []

    preview = service.compute_preview(
        mode=mode,
        threshold=threshold,
        required_keys=req_keys_list,
    )

    return ScoringPreviewResponse(
        resources=preview,
        mode=mode,
        threshold=threshold,
    )
