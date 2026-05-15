import logging
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session
from sqlalchemy import func

from backend.core.config import settings
from backend.models.placement_policy import PlacementPolicyRecord
from backend.schemas.placement_policy_schemas import (
    PlacementPolicyResponse,
    PlacementPolicySummaryResponse,
    PlacementPolicyListResponse,
    PlacementPolicyGenerateRequest
)
from backend.models.base import get_db
from backend.core.dependencies import get_current_user
from backend.workers.tasks.placement_advisor_task import run_placement_cycle_task
# Note: assuming get_current_user returns a user object and we might check cluster ownership
# For this implementation, we will follow the existing pattern assumed in the spec

router = APIRouter(tags=["Placement Policies"])
logger = logging.getLogger(__name__)

CURRENT_SCHEMA_VERSION = "5.10"

def sanitize_placement_policy_output(policy_dict: dict) -> dict:
    """
    SANITIZATION CONTRACT — read before modifying this function.

    MAY do:
    - Remove internal debug fields not in the public schema
    - Format datetime fields to ISO strings
    - Add computed display-only fields (e.g., tier_label, savings_formatted)

    MUST NOT do:
    - Change any boolean field (spot_friendly, actionable, rollout_eligible)
    - Change any score (ondemand_target, spot_target, estimated_savings_pct)
    - Change confidence_state or tier
    - Apply safety logic (that belongs in consumers, not here)

    Violation of this contract = P0 bug. See plan.md §0 Invariant 1.
    """
    # Create a copy to avoid mutating the original
    safe_dict = dict(policy_dict)

    # Task 1.21: Schema Version Enforcement
    if safe_dict.get("schema_version") != CURRENT_SCHEMA_VERSION:
        logger.warning(
            "placement_policy_schema_mismatch",
            extra={
                "workload_id": safe_dict.get("workload_id"),
                "stored_version": safe_dict.get("schema_version"),
                "expected_version": CURRENT_SCHEMA_VERSION
            }
        )
        safe_dict["schema_warning"] = True
    else:
        safe_dict["schema_warning"] = False

    return safe_dict


def _check_feature_flag():
    if not settings.FEATURE_PLACEMENT_ADVISOR_ENABLED:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Placement Intelligence Advisor is disabled"
        )


@router.get(
    "/{cluster_id}/placement-policies",
    response_model=PlacementPolicyListResponse,
    dependencies=[Depends(get_current_user)]
)
def list_placement_policies(
    cluster_id: str,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=100),
    tier: Optional[str] = None,
    actionable: Optional[bool] = None,
    rollout_eligible: Optional[bool] = None,
    db: Session = Depends(get_db)
):
    _check_feature_flag()
    
    query = db.query(PlacementPolicyRecord).filter(PlacementPolicyRecord.cluster_id == cluster_id)
    
    if tier:
        query = query.filter(PlacementPolicyRecord.criticality_tier == tier)
    if actionable is not None:
        query = query.filter(PlacementPolicyRecord.actionable == actionable)
    if rollout_eligible is not None:
        query = query.filter(PlacementPolicyRecord.rollout_eligible == rollout_eligible)
        
    total = query.count()
    items = query.order_by(PlacementPolicyRecord.workload_id).offset((page - 1) * page_size).limit(page_size).all()
    
    # Needs to go through pydantic serialization to convert dict
    results = []
    for item in items:
        # Convert SQLAlchemy object to dict using Pydantic, then sanitize
        item_dict = PlacementPolicyResponse.from_orm(item).dict()
        sanitized = sanitize_placement_policy_output(item_dict)
        results.append(sanitized)
        
    return {
        "items": results,
        "total": total,
        "page": page,
        "page_size": page_size
    }


@router.get(
    "/{cluster_id}/placement-policies/summary",
    response_model=PlacementPolicySummaryResponse,
    dependencies=[Depends(get_current_user)]
)
def get_placement_policy_summary(cluster_id: str, db: Session = Depends(get_db)):
    _check_feature_flag()
    
    results = db.query(
        func.count(PlacementPolicyRecord.id).label("total_workloads"),
        func.sum(PlacementPolicyRecord.spot_target).label("total_spot_target"),
        func.sum(PlacementPolicyRecord.ondemand_target).label("total_od_target"),
        func.sum(PlacementPolicyRecord.estimated_monthly_saving_usd).label("total_savings_usd"),
    ).filter(PlacementPolicyRecord.cluster_id == cluster_id).one()
    
    # Aggregated counts
    spot_workloads = db.query(PlacementPolicyRecord).filter(
        PlacementPolicyRecord.cluster_id == cluster_id, 
        PlacementPolicyRecord.spot_target > 0
    ).count()
    
    od_workloads = results.total_workloads - spot_workloads if results.total_workloads else 0
    
    actionable_count = db.query(PlacementPolicyRecord).filter(
        PlacementPolicyRecord.cluster_id == cluster_id, 
        PlacementPolicyRecord.actionable == True
    ).count()
    
    rollout_count = db.query(PlacementPolicyRecord).filter(
        PlacementPolicyRecord.cluster_id == cluster_id, 
        PlacementPolicyRecord.rollout_eligible == True
    ).count()
    
    return {
        "total_workloads": results.total_workloads or 0,
        "spot_workload_count": spot_workloads,
        "od_workload_count": od_workloads,
        "total_spot_target": int(results.total_spot_target or 0),
        "total_od_target": int(results.total_od_target or 0),
        "total_estimated_savings_usd": float(results.total_savings_usd or 0.0),
        "actionable_count": actionable_count,
        "rollout_eligible_count": rollout_count,
        "observation_mode": settings.PLACEMENT_ADVISOR_OBSERVATION_MODE
    }


@router.get(
    "/{cluster_id}/placement-policies/{workload_id:path}",
    response_model=PlacementPolicyResponse,
    dependencies=[Depends(get_current_user)]
)
def get_placement_policy(cluster_id: str, workload_id: str, db: Session = Depends(get_db)):
    _check_feature_flag()
    
    record = db.query(PlacementPolicyRecord).filter(
        PlacementPolicyRecord.cluster_id == cluster_id,
        PlacementPolicyRecord.workload_id == workload_id
    ).first()
    
    if not record:
        raise HTTPException(status_code=404, detail="Placement policy not found")
        
    item_dict = PlacementPolicyResponse.from_orm(record).dict()
    return sanitize_placement_policy_output(item_dict)


@router.post(
    "/{cluster_id}/placement-policies/generate",
    status_code=status.HTTP_202_ACCEPTED,
    dependencies=[Depends(get_current_user)]
)
def generate_placement_policies(
    cluster_id: str,
    request: PlacementPolicyGenerateRequest,
    db: Session = Depends(get_db)
):
    _check_feature_flag()

    # Guard: prevent duplicate dispatches while a cycle is already running.
    try:
        from backend.core.redis_client import get_redis_client as _grc
        _r = _grc()
        if _r and _r.exists(f"spot:placement:cycle_lock:{cluster_id}"):
            raise HTTPException(status_code=409, detail="Advisor cycle already in progress for this cluster")
    except HTTPException:
        raise
    except Exception:
        pass  # Redis unavailable — allow dispatch (fail-open)

    # Dispatch to Celery
    run_placement_cycle_task.delay(cluster_id)

    return {"status": "triggered", "cluster_id": cluster_id}
