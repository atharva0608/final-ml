"""
Node Template Routes

FastAPI endpoints for managing node templates (instance families, disk configs, strategies)
"""
from fastapi import APIRouter, Depends, status, Query
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
def get_template_options(current_user: User = Depends(get_current_user)):
    """
    Returns available options for building a node template.
    This replaces hardcoded lists in the frontend.
    """
    return {
        "architectures": ["x86_64", "arm64"],
        "disk_types": ["GP3", "GP2", "IO1", "IO2"],
        "strategies": ["CHEAPEST", "BALANCED", "PERFORMANCE"],
        "families": [
            # General purpose
            't2', 't3', 't3a', 't4g', 'm5', 'm5a', 'm5n', 'm6i', 'm6a', 'm6g', 'm7i', 'm7g',
            # Compute optimized
            'c5', 'c5a', 'c5n', 'c6i', 'c6a', 'c6g', 'c7i', 'c7g',
            # Memory optimized
            'r5', 'r5a', 'r5n', 'r6i', 'r6a', 'r6g', 'r7i', 'r7g', 'x1', 'x2gd',
            # Storage optimized
            'i3', 'i3en', 'i4i', 'd2', 'd3', 'h1',
            # Accelerated computing
            'p3', 'p4', 'g4dn', 'g5', 'inf1', 'inf2'
        ]
    }


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
