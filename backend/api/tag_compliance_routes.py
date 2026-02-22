"""
Tag Compliance Monitor API Routes — Compliance Monitor (Tab 5)
"""
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from sqlalchemy import func, distinct
from datetime import datetime
import math

from backend.core.dependencies import get_db, get_current_user
from backend.models.user import User
from backend.models.tag_compliance_score import TagComplianceScore
from backend.schemas.tag_compliance_schemas import (
    ComplianceSummaryResponse,
    ComplianceDistribution,
    ComplianceResourceEntry,
    ComplianceResourceListResponse,
    HeatmapEntry,
    HeatmapResponse,
)

router = APIRouter(prefix="/tags/compliance", tags=["Tag Compliance"])


@router.get("/summary", response_model=ComplianceSummaryResponse)
def get_compliance_summary(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get aggregate compliance summary"""
    org_id = current_user.organization_id

    # Get latest score per resource using subquery
    latest_subq = (
        db.query(
            TagComplianceScore.resource_id,
            func.max(TagComplianceScore.scanned_at).label("max_scan")
        )
        .filter(TagComplianceScore.organization_id == org_id)
        .group_by(TagComplianceScore.resource_id)
        .subquery()
    )

    # Join to get actual rows
    latest_scores = (
        db.query(TagComplianceScore)
        .join(
            latest_subq,
            (TagComplianceScore.resource_id == latest_subq.c.resource_id) &
            (TagComplianceScore.scanned_at == latest_subq.c.max_scan)
        )
        .filter(TagComplianceScore.organization_id == org_id)
        .all()
    )

    total = len(latest_scores)
    if total == 0:
        return ComplianceSummaryResponse()

    status_counts = {"compliant": 0, "passing": 0, "review": 0, "critical": 0, "deletion": 0}
    cost_at_risk = 0.0
    last_scan = None

    for s in latest_scores:
        status = s.status or "critical"
        if status in status_counts:
            status_counts[status] += 1
        if status in ("review", "critical", "deletion"):
            cost_at_risk += float(s.monthly_cost or 0)
        if last_scan is None or (s.scanned_at and s.scanned_at > last_scan):
            last_scan = s.scanned_at

    distribution = []
    for status, count in status_counts.items():
        if count > 0:
            distribution.append(ComplianceDistribution(
                status=status,
                count=count,
                pct=round((count / total) * 100, 1),
            ))

    return ComplianceSummaryResponse(
        total=total,
        compliant=status_counts["compliant"],
        passing=status_counts["passing"],
        review=status_counts["review"],
        critical=status_counts["critical"],
        deletion=status_counts["deletion"],
        cost_at_risk=round(cost_at_risk, 2),
        distribution=distribution,
        last_scan_at=last_scan,
    )


@router.get("/resources", response_model=ComplianceResourceListResponse)
def list_compliance_resources(
    status: str = Query(None, description="Filter by status"),
    search: str = Query(None, description="Search by resource_id, name, or team"),
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """List compliance resources with filtering and pagination"""
    org_id = current_user.organization_id

    # Get latest per resource
    latest_subq = (
        db.query(
            TagComplianceScore.resource_id,
            func.max(TagComplianceScore.scanned_at).label("max_scan")
        )
        .filter(TagComplianceScore.organization_id == org_id)
        .group_by(TagComplianceScore.resource_id)
        .subquery()
    )

    query = (
        db.query(TagComplianceScore)
        .join(
            latest_subq,
            (TagComplianceScore.resource_id == latest_subq.c.resource_id) &
            (TagComplianceScore.scanned_at == latest_subq.c.max_scan)
        )
        .filter(TagComplianceScore.organization_id == org_id)
    )

    if status:
        query = query.filter(TagComplianceScore.status == status)

    if search:
        search_filter = f"%{search}%"
        query = query.filter(
            (TagComplianceScore.resource_id.ilike(search_filter)) |
            (TagComplianceScore.resource_name.ilike(search_filter)) |
            (TagComplianceScore.team.ilike(search_filter))
        )

    total = query.count()
    resources = query.order_by(TagComplianceScore.score.asc()).offset((page - 1) * per_page).limit(per_page).all()

    now = datetime.utcnow()
    entries = []
    for r in resources:
        days_left = None
        if r.grace_deadline:
            delta = (r.grace_deadline - now).total_seconds()
            days_left = max(0, math.ceil(delta / 86400))

        entries.append(ComplianceResourceEntry(
            id=r.id,
            resource_id=r.resource_id,
            resource_name=r.resource_name,
            resource_type=r.resource_type,
            score=r.score,
            status=r.status,
            tags_present=r.tags_present,
            monthly_cost=float(r.monthly_cost or 0),
            grace_deadline=r.grace_deadline,
            days_left=days_left,
            team=r.team,
            environment=r.environment,
            scanned_at=r.scanned_at,
        ))

    return ComplianceResourceListResponse(
        resources=entries,
        total=total,
        page=page,
        per_page=per_page,
    )


@router.get("/heatmap", response_model=HeatmapResponse)
def get_compliance_heatmap(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get per-tag-key coverage percentages"""
    org_id = current_user.organization_id

    # Try Redis cache first
    try:
        from backend.core.redis_client import get_redis
        import json
        redis = get_redis()
        if redis:
            cached = redis.get(f"tag_heatmap:{org_id}")
            if cached:
                data = json.loads(cached)
                return HeatmapResponse(entries=[HeatmapEntry(**e) for e in data])
    except Exception:
        pass

    # Fallback: compute from templates (compliance scan populates Redis)
    from backend.models.tag_template import TagTemplate
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

    entries = [HeatmapEntry(key=k, coverage_pct=0.0) for k in sorted(all_keys)]
    return HeatmapResponse(entries=entries)
