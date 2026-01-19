from fastapi import APIRouter, Depends, status, HTTPException
from sqlalchemy.orm import Session
from backend.core.dependencies import get_db, get_current_user, RequireRole
from backend.models.user import User
from backend.schemas.organization_schemas import (
    InviteMemberRequest,
    UpdateMemberRoleRequest,
    MemberListResponse,
    InviteResponse,
    MemberResponse,
    AcceptInvitationRequest,
    AcceptInvitationResponse
)
from backend.services.organization_service import get_organization_service

router = APIRouter(
    prefix="/organization",
    tags=["Organization"]
)
@router.get(
    "/members",
    response_model=MemberListResponse,
    summary="List organization members"
)
def list_members(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """List all members of the current user's organization"""
    if not current_user.organization_id:
        raise HTTPException(status_code=400, detail="User does not belong to an organization")
        
    service = get_organization_service(db)
    return service.list_members(current_user.organization_id)

@router.post(
    "/members",
    response_model=InviteResponse,
    summary="Add a new member",
    status_code=status.HTTP_201_CREATED
)
def invite_member(
    request: InviteMemberRequest,
    current_user: User = Depends(RequireRole("ORG_ADMIN")),
    db: Session = Depends(get_db)
):
    """
    Directly add a new member to the organization.
    Creates the user immediately with default password 'demo1234'.
    Requires ORG_ADMIN role.
    """
    service = get_organization_service(db)
    result = service.create_invitation(
        organization_id=current_user.organization_id,
        email=request.email,
        role_str=request.role,
        access_level_str=request.access_level,
        requesting_user=current_user
    )
    
    return InviteResponse(
        message=result["message"],
        invitation=result["invitation"],
        temporary_password=result["temporary_password"]
    )

@router.get(
    "/invitations",
    summary="List pending invitations",
    description="Get all pending invitations for the organization"
)
def list_invitations(
    current_user: User = Depends(RequireRole("ORG_ADMIN")),
    db: Session = Depends(get_db)
):
    service = get_organization_service(db)
    return {"invitations": service.list_invitations(current_user.organization_id)}

@router.delete(
    "/members/{user_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Remove a member"
)
def remove_member(
    user_id: str,
    current_user: User = Depends(RequireRole("ORG_ADMIN")),
    db: Session = Depends(get_db)
):
    """
    Remove a member from the organization.
    Requires ORG_ADMIN role - only organization admins can remove members.
    """
    service = get_organization_service(db)
    service.remove_member(
        organization_id=current_user.organization_id,
        target_user_id=user_id,
        requesting_user=current_user
    )

@router.patch(
    "/members/{user_id}",
    response_model=MemberResponse,
    summary="Update member role"
)
def update_member_role(
    user_id: str,
    request: UpdateMemberRoleRequest,
    current_user: User = Depends(RequireRole("ORG_ADMIN")),
    db: Session = Depends(get_db)
):
    """
    Update a member's role or access level.
    Requires ORG_ADMIN role - only organization admins can update roles.
    """
    service = get_organization_service(db)
    return service.update_member_role(
        organization_id=current_user.organization_id,
        target_user_id=user_id,
        new_role_str=request.role,
        new_access_str=request.access_level,
        requesting_user=current_user
    )

@router.post(
    "/invitations/{token}/accept",
    response_model=AcceptInvitationResponse,
    summary="Accept an organization invitation",
    status_code=status.HTTP_201_CREATED
)
def accept_invitation(
    token: str,
    db: Session = Depends(get_db)
):
    """
    Accept an organization invitation.
    
    This is a public endpoint - no authentication required.
    The invitation token serves as the authentication mechanism.
    
    Creates a new user account with:
    - Role and access_level from the invitation
    - Default password: demo1234 (must be reset on first login)
    """
    service = get_organization_service(db)
    result = service.accept_invitation(token)
    
    return AcceptInvitationResponse(
        message=result["message"],
        user_id=result["user_id"],
        email=result["email"],
        organization_id=result["organization_id"],
        org_role=result["org_role"],
        access_level=result["access_level"],
        must_reset_password=result["must_reset_password"],
        temporary_password=result["temporary_password"]
    )

@router.get(
    "/connection-info",
    summary="Get AWS connection parameters",
    description="Get the unique External ID and Platform Account ID for configuring AWS trust"
)
def get_connection_info(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Get standard connection parameters for AWS Trust Policy.
    Returns the Organization's unique External ID.
    """
    if not current_user.organization_id:
        raise HTTPException(status_code=400, detail="User does not belong to an organization")
        
    service = get_organization_service(db)
    organization = service.get_organization(current_user.organization_id)
    
    # Get Platform AWS Account ID - Priority Order:
    # 1. SystemConfig in DB (Admin-configured)
    # 2. Environment Variable
    # 3. Auto-detect via STS GetCallerIdentity
    import os
    import boto3
    from backend.models.system_config import SystemConfig
    
    platform_account_id = None
    detection_method = "unknown"
    
    # 1. Try DB config first
    platform_account_config = db.query(SystemConfig).filter(SystemConfig.key == "PLATFORM_AWS_ACCOUNT_ID").first()
    if platform_account_config and platform_account_config.value:
        platform_account_id = platform_account_config.value
        detection_method = "database_config"
    
    # 2. Try environment variable
    if not platform_account_id:
        env_id = os.getenv("PLATFORM_AWS_ACCOUNT_ID")
        if env_id and env_id != "123456789012":  # Ignore placeholder
            platform_account_id = env_id
            detection_method = "environment_variable"
    
    # 3. Auto-detect via STS
    if not platform_account_id:
        try:
            sts = boto3.client('sts')
            identity = sts.get_caller_identity()
            platform_account_id = identity.get('Account')
            detection_method = "auto_detected"
        except Exception as e:
            # Fallback to placeholder if AWS creds not configured
            platform_account_id = "NOT_CONFIGURED"
            detection_method = "error"
    
    # Get Template URL
    api_url = os.getenv("API_URL", "http://localhost:8000")
    template_url = f"{api_url}/api/v1/onboarding/template?external_id={organization.external_id}"
    
    return {
        "external_id": organization.external_id,
        "platform_account_id": platform_account_id,
        "platform_account_id_source": detection_method,
        "template_url": template_url
    }

@router.post(
    "/connection-info/regenerate",
    summary="Regenerate External ID",
    description="Regenerate the Organization's External ID. WARNING: This will break existing setups if not updated."
)
def regenerate_connection_info(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    if not current_user.organization_id:
        raise HTTPException(status_code=400, detail="User does not belong to an organization")
        
    service = get_organization_service(db)
    new_id = service.regenerate_external_id(current_user.organization_id, current_user)
    
    return {"external_id": new_id, "message": "External ID regenerated successfully"}
