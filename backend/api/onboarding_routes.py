from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional

from backend.models.base import get_db
from backend.models.user import User
from backend.services.onboarding_service import get_onboarding_service, OnboardingService
from backend.core.dependencies import get_current_user, verify_tenant_action
from backend.models.onboarding import ConnectionMode

router = APIRouter(prefix="/onboarding", tags=["Onboarding"])

class VerifyRequest(BaseModel):
    role_arn: str

class OnboardingStateResponse(BaseModel):
    current_step: str
    external_id: str
    aws_role_arn: Optional[str]
    is_completed: bool

@router.get("/state", response_model=OnboardingStateResponse)
def get_state(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    service = get_onboarding_service(db)
    state = service.get_or_create_state(current_user.id)
    return {
        "current_step": state.current_step.value,
        "external_id": state.external_id,
        "aws_role_arn": state.aws_role_arn,
        "is_completed": current_user.onboarding_completed
    }

@router.get("/aws-link")
def get_aws_link(
    mode: ConnectionMode = ConnectionMode.READ_ONLY,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    service = get_onboarding_service(db)
    url = service.get_cloudformation_deep_link(current_user.id, mode)
    return {"url": url}

from fastapi import Response

@router.get("/template")
def get_template(
    mode: ConnectionMode = ConnectionMode.READ_ONLY,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    service = get_onboarding_service(db)
    yaml_content = service.get_template(current_user.id, mode)
    return Response(content=yaml_content, media_type="application/x-yaml", headers={
        "Content-Disposition": "attachment; filename=spot-optimizer-role.yaml"
    })

@router.post("/verify")
def verify_connection(
    request: VerifyRequest,
    current_user: User = Depends(verify_tenant_action),
    db: Session = Depends(get_db)
):
    service = get_onboarding_service(db)
    success = service.verify_role_connection(current_user.id, request.role_arn)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, 
            detail="Failed to verify Role. Check permissions and ExternalId."
        )
    
    # Get the onboarding state to access external_id and account_id
    state = service.get_or_create_state(current_user.id)
    
    # Create an Account record in the database
    from backend.models.account import Account, AccountStatus
    import uuid
    
    # Check if account already exists
    existing_account = db.query(Account).filter(
        Account.aws_account_id == state.aws_account_id,
        Account.organization_id == current_user.organization_id
    ).first()
    
    if not existing_account:
        new_account = Account(
            id=str(uuid.uuid4()),
            organization_id=current_user.organization_id,
            aws_account_id=state.aws_account_id,
            role_arn=request.role_arn,
            external_id=state.external_id,
            status=AccountStatus.ACTIVE
        )
        db.add(new_account)
        db.commit()
        db.refresh(new_account)
        account_id = new_account.id
    else:
        account_id = existing_account.id
    
    # TRIGGER DATA FETCHING - The critical step from changes.txt
    from backend.workers.tasks.discovery import discovery_worker_loop
    discovery_worker_loop.delay()  # Trigger background scan of all accounts
    
    # Auto-complete onboarding after verification for this flow
    service.complete_onboarding(current_user.id)
    return {"status": "verified", "message": "Connection successful. Discovering clusters..."}


@router.post("/skip")
def skip_onboarding(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Skip onboarding temporarily - does NOT mark as complete.
    User can restart anytime by clicking the Dashboard card.
    """
    # Just return skipped status - don't complete onboarding
    # This allows the Dashboard card to reappear since onboarding_completed stays False
    return {"status": "skipped", "message": "You can connect your AWS account anytime from the Dashboard."}


@router.post("/reset")
def reset_onboarding(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Reset onboarding state to allow user to restart the AWS connection process.
    Only allowed if user has no connected accounts.
    """
    from backend.models.account import Account
    from backend.models.onboarding import OnboardingState, OnboardingStep
    import uuid
    
    # Check if user has any accounts
    existing_accounts = db.query(Account).filter(
        Account.organization_id == current_user.organization_id
    ).count()
    
    if existing_accounts > 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot reset onboarding - accounts are already connected. Remove accounts first."
        )
    
    # Reset onboarding state
    state = db.query(OnboardingState).filter(OnboardingState.user_id == current_user.id).first()
    if state:
        state.current_step = OnboardingStep.WELCOME
        state.aws_role_arn = None
        state.aws_account_id = None
        state.external_id = str(uuid.uuid4())  # Generate new External ID
        db.commit()
    
    # Reset user flag
    current_user.onboarding_completed = False
    db.commit()
    
    return {"status": "reset", "message": "Onboarding reset. You can start fresh."}
