"""
Tag Template Pydantic Schemas
"""
from pydantic import BaseModel, Field
from typing import Optional, List, Dict
from datetime import datetime


class TagTemplateCreate(BaseModel):
    """Schema for creating a tag template"""
    name: str = Field(..., min_length=1, max_length=255, description="Template name")
    description: Optional[str] = Field(None, description="Template description")
    resource_scope: str = Field("all", description="Resource scope (all, ec2, s3, etc)")
    tags: Dict[str, str] = Field(..., min_items=1, description="Tag key-value pairs")
    is_default: bool = Field(False, description="Set as default template")
    
    class Config:
        json_schema_extra = {
            "example": {
                "name": "Cost Center Standard",
                "description": "Standard tags for all production resources",
                "tags": {
                    "Owner": "TeamA",
                    "Environment": "Production",
                    "CostCenter": "CC-1234"
                },
                "is_default": False
            }
        }


class TagTemplateUpdate(BaseModel):
    """Schema for updating a tag template"""
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    description: Optional[str] = None
    tags: Optional[Dict[str, str]] = None
    is_default: Optional[bool] = None
    is_active: Optional[bool] = None


class TagTemplateResponse(BaseModel):
    """Schema for tag template response"""
    id: str
    organization_id: str
    name: str
    description: Optional[str]
    resource_scope: str
    tags: Dict[str, str]
    tag_count: int
    is_default: bool
    is_active: bool
    created_by: Optional[str]
    created_at: datetime
    updated_at: datetime
    
    class Config:
        from_attributes = True


class TagTemplateList(BaseModel):
    """Schema for list of tag templates"""
    templates: List[TagTemplateResponse]
    total: int
    default_template_id: Optional[str] = None
