from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session
from typing import List
from backend.models.base import get_db
from backend.models.user import User
from backend.models.account import AccountStatus
from backend.core.dependencies import get_current_user, RequireAccess
from backend.services.account_service import get_account_service
from backend.schemas.account_schemas import AccountResponse, AccountCreate, AccountUpdate

router = APIRouter(prefix="/accounts", tags=["Accounts"])

@router.get(
    "",
    response_model=List[AccountResponse],
    summary="List AWS accounts"
)
def list_accounts(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """List all AWS accounts linked to the user's organization"""
    service = get_account_service(db)
    # Service expects user_id, it should probably filter by user's org for better multi-tenancy?
    # Service implementation currently filters by user_id. 
    # If users share accounts in an org, the service logic might need update, 
    # but for now we follow existing pattern.
    return service.list_accounts(current_user.organization_id)

@router.post(
    "",
    response_model=AccountResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Link AWS account"
)
def link_account(
    account_data: AccountCreate,
    current_user: User = Depends(RequireAccess("EXECUTION")),
    db: Session = Depends(get_db)
):
    """Link a new AWS account"""
    service = get_account_service(db)
    return service.link_aws_account(
        organization_id=current_user.organization_id,
        aws_account_id=account_data.aws_account_id,
        role_arn=account_data.role_arn,
        external_id=account_data.external_id
    )

@router.get(
    "/{account_id}",
    response_model=AccountResponse,
    summary="Get account details"
)
def get_account(
    account_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get details of a specific AWS account"""
    service = get_account_service(db)
    return service.get_account(account_id, current_user.organization_id)

@router.delete(
    "/{account_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Unlink AWS account"
)
def delete_account(
    account_id: str,
    current_user: User = Depends(RequireAccess("FULL")),
    db: Session = Depends(get_db)
):
    service = get_account_service(db)
    service.delete_account(account_id, current_user.organization_id)

@router.post(
    "/{account_id}/validate",
    response_model=AccountResponse,
    summary="Validate account"
)
def validate_account(
    account_id: str,
    current_user: User = Depends(RequireAccess("EXECUTION")),
    db: Session = Depends(get_db)
):
    """
    Validate AWS account credentials and permissions.
    Triggers a live connection check.
    """
    service = get_account_service(db)
    return service.validate_account(account_id, current_user.organization_id)

@router.post(
    "/{account_id}/set-default",
    response_model=AccountResponse,
    summary="Set default account"
)
def set_default_account(
    account_id: str,
    current_user: User = Depends(RequireAccess("FULL")),
    db: Session = Depends(get_db)
):
    """
    Set this account as the default for the organization.
    """
    service = get_account_service(db)
    return service.set_default_account(account_id, current_user.organization_id)
