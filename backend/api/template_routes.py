"""
Node Template Routes

FastAPI endpoints for managing node templates (instance families, disk configs, strategies)
"""
from fastapi import APIRouter, Depends, status, Query, HTTPException
from sqlalchemy.orm import Session
from typing import Optional

from backend.models.base import get_db
from backend.models.user import User
from backend.core.dependencies import get_current_user
from backend.services.template_service import get_template_service
from backend.schemas.template_schemas import (
    NodeTemplateCreate,
    NodeTemplateUpdate,
    NodeTemplateResponse,
    NodeTemplateList,
)

router = APIRouter(prefix="/templates", tags=["Templates"])


@router.get(
    "/options",
    summary="Get template configuration options",
    description="Returns valid AWS instance families, volume types, and strategies"
)
def get_template_options(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Returns available options for building a node template.
    Groups instance families by category with metadata.
    """
    service = get_template_service(db)
    return service.get_template_options()


@router.get("/", response_model=NodeTemplateList, summary="List node templates")
def list_templates(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get all node templates for the current user"""
    service = get_template_service(db)
    return service.list_templates(current_user.id)


@router.post("/", response_model=NodeTemplateResponse, status_code=status.HTTP_201_CREATED, summary="Create node template")
def create_template(
    template_data: NodeTemplateCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Create a new node template"""
    service = get_template_service(db)
    return service.create_template(current_user.id, template_data)


@router.get("/default", response_model=NodeTemplateResponse, summary="Get default template")
def get_default_template(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get the user's default node template"""
    service = get_template_service(db)
    template = service.get_default_template(current_user.id)
    if not template:
        raise HTTPException(status_code=404, detail="No default template set")

    return NodeTemplateResponse(
        id=template.id,
        user_id=template.user_id,
        name=template.name,
        families=template.families,
        architecture=template.architecture,
        strategy=template.strategy.value,
        disk_type=template.disk_type.value,
        disk_size=template.disk_size,
        is_default=(template.is_default == "Y"),
        created_at=template.created_at,
        updated_at=template.updated_at
    )


@router.get("/{template_id}", response_model=NodeTemplateResponse, summary="Get template details")
def get_template(
    template_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get details of a specific node template"""
    service = get_template_service(db)
    return service.get_template(template_id, current_user.id)


@router.put("/{template_id}", response_model=NodeTemplateResponse, summary="Update node template")
def update_template(
    template_id: str,
    template_data: NodeTemplateUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Update an existing node template"""
    service = get_template_service(db)
    return service.update_template(template_id, current_user.id, template_data)


@router.delete("/{template_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Delete node template")
def delete_template(
    template_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Delete a node template"""
    service = get_template_service(db)
    service.delete_template(template_id, current_user.id)
    return None


@router.post("/{template_id}/set-default", response_model=NodeTemplateResponse, summary="Set default template")
def set_default_template(
    template_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Set a template as the default for cluster provisioning"""
    service = get_template_service(db)
    return service.set_default(template_id, current_user.id)
