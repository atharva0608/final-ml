from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional

from backend.models.base import get_db
from backend.models.user import User
from backend.services.onboarding_service import get_onboarding_service, OnboardingService
from backend.core.dependencies import get_current_user
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

@router.post("/verify")
def verify_connection(
    request: VerifyRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    service = get_onboarding_service(db)
    success = service.verify_role_connection(current_user.id, request.role_arn)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, 
            detail="Failed to verify Role. Check permissions and ExternalId."
        )
    
    # Auto-complete onboarding after verification for this flow
    service.complete_onboarding(current_user.id)
    return {"status": "verified", "message": "Connection successful"}

@router.post("/skip")
def skip_onboarding(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    service = get_onboarding_service(db)
    service.complete_onboarding(current_user.id)
    return {"status": "skipped"}
