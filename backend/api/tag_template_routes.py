"""
Tag Template API Routes
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List

from backend.core.dependencies import get_db, get_current_user
from backend.models.user import User
from backend.models.tag_template import TagTemplate
from backend.schemas.tag_template_schemas import (
    TagTemplateCreate,
    TagTemplateUpdate,
    TagTemplateResponse,
    TagTemplateList
)

router = APIRouter(prefix="/tags/templates", tags=["Tag Templates"])


@router.post("/", response_model=TagTemplateResponse, status_code=201)
def create_template(
    template_data: TagTemplateCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Create a new tag template"""
    # If setting as default, unset other defaults
    if template_data.is_default:
        db.query(TagTemplate).filter(
            TagTemplate.organization_id == current_user.organization_id,
            TagTemplate.is_default == True
        ).update({"is_default": False})
    
    template = TagTemplate(
        organization_id=current_user.organization_id,
        created_by=current_user.id,
        **template_data.dict()
    )
    
    db.add(template)
    db.commit()
    db.refresh(template)
    
    return TagTemplateResponse.from_orm(template)


@router.get("/", response_model=TagTemplateList)
def list_templates(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """List all tag templates"""
    templates = db.query(TagTemplate).filter(
        TagTemplate.organization_id == current_user.organization_id,
        TagTemplate.is_active == True
    ).all()
    
    default_template = next((t for t in templates if t.is_default), None)
    
    return TagTemplateList(
        templates=[TagTemplateResponse.from_orm(t) for t in templates],
        total=len(templates),
        default_template_id=default_template.id if default_template else None
    )


@router.get("/{template_id}", response_model=TagTemplateResponse)
def get_template(
    template_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get a specific template"""
    template = db.query(TagTemplate).filter(
        TagTemplate.id == template_id,
        TagTemplate.organization_id == current_user.organization_id
    ).first()
    
    if not template:
        raise HTTPException(status_code=404, detail="Template not found")
    
    return TagTemplateResponse.from_orm(template)


@router.put("/{template_id}", response_model=TagTemplateResponse)
def update_template(
    template_id: str,
    update_data: TagTemplateUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Update a template"""
    template = db.query(TagTemplate).filter(
        TagTemplate.id == template_id,
        TagTemplate.organization_id == current_user.organization_id
    ).first()
    
    if not template:
        raise HTTPException(status_code=404, detail="Template not found")
    
    # If setting as default, unset other defaults
    if update_data.is_default:
        db.query(TagTemplate).filter(
            TagTemplate.organization_id == current_user.organization_id,
            TagTemplate.is_default == True,
            TagTemplate.id != template_id
        ).update({"is_default": False})
    
    update_dict = update_data.dict(exclude_unset=True)
    for field, value in update_dict.items():
        setattr(template, field, value)
    
    db.commit()
    db.refresh(template)
    
    return TagTemplateResponse.from_orm(template)


@router.delete("/{template_id}", status_code=204)
def delete_template(
    template_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Delete a template"""
    template = db.query(TagTemplate).filter(
        TagTemplate.id == template_id,
        TagTemplate.organization_id == current_user.organization_id
    ).first()
    
    if not template:
        raise HTTPException(status_code=404, detail="Template not found")
    
    # Soft delete
    template.is_active =False
    db.commit()
    
    return None
