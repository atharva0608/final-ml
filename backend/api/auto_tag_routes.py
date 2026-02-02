"""
Auto-Tag Rule API Routes
Includes dynamic tag preview and available variables endpoints
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from backend.core.dependencies import get_db, get_current_user
from backend.models.user import User
from backend.services.auto_tag_service import AutoTagService
from backend.schemas.auto_tag_schemas import (
    AutoTagRuleCreate,
    AutoTagRuleUpdate,
    AutoTagRuleResponse,
    AutoTagRuleList,
    RuleTestResult,
    RuleExecutionResult,
    TagPreviewRequest,
    TagPreviewResponse,
    AvailableVariablesResponse
)

router = APIRouter(prefix="/tags/rules", tags=["Auto-Tag Rules"])


@router.post("/", response_model=AutoTagRuleResponse, status_code=201)
def create_auto_tag_rule(
    rule_data: AutoTagRuleCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Create a new auto-tag rule (Admin only)"""
    if not current_user.is_org_admin:
        raise HTTPException(status_code=403, detail="Admin access required")
    
    service = AutoTagService(db, current_user.organization_id)
    
    try:
        rule = service.create_rule(rule_data.dict(), current_user.id)
        return AutoTagRuleResponse.from_orm(rule)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/", response_model=AutoTagRuleList)
def list_auto_tag_rules(
    active_only: bool = Query(True, description="Only include active rules"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """List all auto-tag rules"""
    service = AutoTagService(db, current_user.organization_id)
    rules = service.list_rules(active_only=active_only)
    
    return AutoTagRuleList(
        rules=[AutoTagRuleResponse.from_orm(r) for r in rules],
        total=len(rules),
        active_count=len([r for r in rules if r.is_active])
    )


@router.get("/{rule_id}", response_model=AutoTagRuleResponse)
def get_auto_tag_rule(
    rule_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get a specific auto-tag rule"""
    service = AutoTagService(db, current_user.organization_id)
    rule = service.get_rule(rule_id)
    
    if not rule:
        raise HTTPException(status_code=404, detail="Rule not found")
    
    return AutoTagRuleResponse.from_orm(rule)


@router.post("/{rule_id}/test", response_model=RuleTestResult)
def test_auto_tag_rule(
    rule_id: str,
    account_id: str = Query(..., description="AWS account ID to test against"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Test an auto-tag rule to preview matches"""
    service = AutoTagService(db, current_user.organization_id)
    
    try:
        result = service.test_rule(rule_id, account_id)
        return result
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{rule_id}/execute", response_model=RuleExecutionResult)
def execute_auto_tag_rule(
    rule_id: str,
    account_id: str = Query(..., description="AWS account ID to execute on"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Execute an auto-tag rule (Admin only)"""
    if not current_user.is_org_admin:
        raise HTTPException(status_code=403, detail="Admin access required")
    
    service = AutoTagService(db, current_user.organization_id)
    
    try:
        result = service.execute_rule(rule_id, account_id)
        return result
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/{rule_id}", status_code=204)
def delete_auto_tag_rule(
    rule_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Delete an auto-tag rule (Admin only)"""
    if not current_user.is_org_admin:
        raise HTTPException(status_code=403, detail="Admin access required")
    
    service = AutoTagService(db, current_user.organization_id)
    rule = service.get_rule(rule_id)
    
    if not rule:
        raise HTTPException(status_code=404, detail="Rule not found")
    
    rule.is_active = False
    service.db.commit()
    
    return None


# ============================================================================
# NEW: Smart Auto-Tag Preview & Variables Endpoints
# ============================================================================

@router.post("/preview", response_model=TagPreviewResponse)
def preview_generated_tags(
    request: TagPreviewRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Preview what tags would be generated for a resource.
    This is the "Live Preview" feature for the Policy Builder Wizard.
    
    Returns resolved tag values including dynamic variables.
    """
    service = AutoTagService(db, current_user.organization_id)
    
    try:
        return service.preview_tags(request, current_user)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/variables", response_model=AvailableVariablesResponse)
def get_available_variables(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Get list of available dynamic variables for tag values.
    Used by the frontend to populate the "Value Type" dropdown.
    """
    service = AutoTagService(db, current_user.organization_id)
    return service.get_available_variables()
