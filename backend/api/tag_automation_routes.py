"""
Tag Automation Rules API Routes — Automation Rules (Tab 4)
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import func
from datetime import datetime, timedelta
import logging

from backend.core.dependencies import get_db, get_current_user
from backend.models.user import User, UserRole
from backend.models.tag_automation_rule import TagAutomationRule
from backend.models.tag_automation_log import TagAutomationLog
from backend.models.tag_compliance_score import TagComplianceScore
from backend.models.audit_log import AuditLog
from backend.schemas.tag_automation_schemas import (
    AutomationRuleCreate,
    AutomationRuleUpdate,
    AutomationRuleResponse,
    AutomationSummary,
    AutomationRulesListResponse,
    AutomationLogEntry,
    AutomationLogResponse,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/tags/automation", tags=["Tag Automation"])


def _write_audit(db: Session, user: User, event: str, resource_id: str, details: str = ""):
    try:
        log = AuditLog(
            organization_id=user.organization_id,
            actor_id=user.id,
            actor_name=user.email,
            event=event,
            resource=resource_id,
            resource_type="TAG_AUTOMATION",
            outcome="success",
            details=details,
        )
        db.add(log)
    except Exception:
        pass


def _compute_summary(db: Session, org_id: str) -> AutomationSummary:
    """Compute automation summary stats"""
    now = datetime.utcnow()

    # Next cycle: next midnight UTC
    tomorrow = (now + timedelta(days=1)).replace(hour=2, minute=0, second=0, microsecond=0)

    # Resources in grace period
    in_grace = db.query(func.count(TagComplianceScore.id)).filter(
        TagComplianceScore.organization_id == org_id,
        TagComplianceScore.grace_deadline != None,
        TagComplianceScore.grace_deadline > now,
    ).scalar() or 0

    # Pending deletion
    pending_del = db.query(func.count(TagComplianceScore.id)).filter(
        TagComplianceScore.organization_id == org_id,
        TagComplianceScore.status == "deletion",
    ).scalar() or 0

    return AutomationSummary(
        next_cycle_at=tomorrow,
        resources_in_grace_period=in_grace,
        pending_deletion=pending_del,
    )


@router.get("/rules", response_model=AutomationRulesListResponse)
def list_automation_rules(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """List all automation rules with summary stats"""
    rules = db.query(TagAutomationRule).filter(
        TagAutomationRule.organization_id == current_user.organization_id
    ).order_by(TagAutomationRule.created_at.desc()).all()

    rule_responses = [AutomationRuleResponse.from_orm(r) for r in rules]
    summary = _compute_summary(db, current_user.organization_id)

    return AutomationRulesListResponse(rules=rule_responses, summary=summary)


@router.post("/rules", response_model=AutomationRuleResponse, status_code=201)
def create_automation_rule(
    data: AutomationRuleCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Create a new automation rule"""
    if current_user.role not in [UserRole.ORG_ADMIN, UserRole.SUPER_ADMIN]:
        raise HTTPException(status_code=403, detail="Admin access required")

    if data.action == "delete":
        logger.warning(
            f"Automation rule with 'delete' action created by {current_user.email} — "
            "approval gate required for execution"
        )

    rule = TagAutomationRule(
        organization_id=current_user.organization_id,
        name=data.name,
        trigger_expr=data.trigger_expr,
        resource_types=data.resource_types,
        grace_days=data.grace_days,
        action=data.action,
        notification_channels=data.notification_channels,
        safety_conditions=data.safety_conditions,
        created_by=current_user.id,
    )

    db.add(rule)
    _write_audit(db, current_user, "AUTOMATION_RULE_CREATED", rule.id, f"Created rule '{data.name}' action={data.action}")
    db.commit()
    db.refresh(rule)

    return AutomationRuleResponse.from_orm(rule)


@router.put("/rules/{rule_id}", response_model=AutomationRuleResponse)
def update_automation_rule(
    rule_id: str,
    data: AutomationRuleUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Update an automation rule"""
    if current_user.role not in [UserRole.ORG_ADMIN, UserRole.SUPER_ADMIN]:
        raise HTTPException(status_code=403, detail="Admin access required")

    rule = db.query(TagAutomationRule).filter(
        TagAutomationRule.id == rule_id,
        TagAutomationRule.organization_id == current_user.organization_id
    ).first()
    if not rule:
        raise HTTPException(status_code=404, detail="Rule not found")

    update_dict = data.dict(exclude_unset=True)
    for field, value in update_dict.items():
        setattr(rule, field, value)
    rule.updated_at = datetime.utcnow()

    _write_audit(db, current_user, "AUTOMATION_RULE_UPDATED", rule_id, f"Updated rule '{rule.name}'")
    db.commit()
    db.refresh(rule)

    return AutomationRuleResponse.from_orm(rule)


@router.delete("/rules/{rule_id}", status_code=204)
def delete_automation_rule(
    rule_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Delete an automation rule"""
    if current_user.role not in [UserRole.ORG_ADMIN, UserRole.SUPER_ADMIN]:
        raise HTTPException(status_code=403, detail="Admin access required")

    rule = db.query(TagAutomationRule).filter(
        TagAutomationRule.id == rule_id,
        TagAutomationRule.organization_id == current_user.organization_id
    ).first()
    if not rule:
        raise HTTPException(status_code=404, detail="Rule not found")

    name = rule.name
    db.delete(rule)
    _write_audit(db, current_user, "AUTOMATION_RULE_DELETED", rule_id, f"Deleted rule '{name}'")
    db.commit()

    return None


@router.patch("/rules/{rule_id}/toggle")
def toggle_automation_rule(
    rule_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Toggle an automation rule's enabled status"""
    if current_user.role not in [UserRole.ORG_ADMIN, UserRole.SUPER_ADMIN]:
        raise HTTPException(status_code=403, detail="Admin access required")

    rule = db.query(TagAutomationRule).filter(
        TagAutomationRule.id == rule_id,
        TagAutomationRule.organization_id == current_user.organization_id
    ).first()
    if not rule:
        raise HTTPException(status_code=404, detail="Rule not found")

    rule.enabled = not rule.enabled
    rule.updated_at = datetime.utcnow()
    db.commit()

    return {"id": rule.id, "enabled": rule.enabled}


@router.get("/log", response_model=AutomationLogResponse)
def get_automation_log(
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get paginated automation execution log"""
    query = db.query(TagAutomationLog).filter(
        TagAutomationLog.organization_id == current_user.organization_id
    ).order_by(TagAutomationLog.executed_at.desc())

    total = query.count()
    entries = query.offset((page - 1) * per_page).limit(per_page).all()

    return AutomationLogResponse(
        entries=[AutomationLogEntry.from_orm(e) for e in entries],
        total=total,
        page=page,
        per_page=per_page,
    )
