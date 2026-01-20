"""
Tag Management API Routes
"""
from fastapi import APIRouter, Depends, HTTPException, Path
from sqlalchemy.orm import Session
from typing import Dict, Any

from backend.core.dependencies import get_db, get_current_user
from backend.models.user import User
from backend.services.tag_management_service import TagManagementService
from backend.services.tag_suggestion_service import TagSuggestionService
from backend.schemas.tag_management_schemas import (
    ResourceTagUpdate,
    BulkTagUpdate,
    ResourceTagsResponse,
    BulkTagResult
)

router = APIRouter(prefix="/tags/resources", tags=["Tag Management"])


@router.get("/{resource_type}/{resource_id}", response_model=ResourceTagsResponse)
def get_resource_tags(
    resource_type: str = Path(..., description="Resource type (EC2, EBS, S3, RDS)"),
    resource_id: str = Path(..., description="Resource ID"),
    account_id: str = None,
    region: str = "us-east-1",
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get current tags for a resource"""
    if not account_id:
        raise HTTPException(status_code=400, detail="account_id is required")
    
    tag_service = TagManagementService(db, current_user.organization_id)
    suggestion_service = TagSuggestionService(db, current_user.organization_id)
    
    try:
        # Get current tags
        response = tag_service.get_resource_tags(resource_type, resource_id, account_id, region)
        
        # Add suggestions
        suggestions = suggestion_service.suggest_tags_for_resource(
            resource_name=resource_id,
            resource_type=resource_type,
            region=region,
            account_id=account_id,
            existing_tags=response.current_tags
        )
        response.suggestions = suggestions
        
        return response
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{resource_type}/{resource_id}", response_model=Dict[str, Any])
def update_resource_tags(
    resource_type: str = Path(..., description="Resource type (EC2, EBS, S3, RDS)"),
    resource_id: str = Path(..., description="Resource ID"),
    update_data: ResourceTagUpdate = ...,
    account_id: str = None,
    region: str = "us-east-1",
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Update tags on a single resource"""
    if not account_id:
        raise HTTPException(status_code=400, detail="account_id is required")
    
    service = TagManagementService(db, current_user.organization_id)
    
    try:
        result = service.update_resource_tags(
            resource_type,
            resource_id,
            account_id,
            update_data,
            region
        )
        
        if not result["success"]:
            raise HTTPException(status_code=500, detail=result.get("error", "Tagging failed"))
        
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/bulk", response_model=BulkTagResult)
def bulk_update_tags(
    bulk_data: BulkTagUpdate,
    account_id: str = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Apply tags to multiple resources"""
    if not account_id:
        raise HTTPException(status_code=400, detail="account_id is required")
    
    service = TagManagementService(db, current_user.organization_id)
    
    try:
        result = service.bulk_update_tags(account_id, bulk_data)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
