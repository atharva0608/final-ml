"""
Tag Template Pydantic Schemas
"""
from pydantic import BaseModel, Field, validator
from typing import Optional, List, Dict, Any
from datetime import datetime


class TagSchemaEntry(BaseModel):
    """Single tag definition within a template's tag_schema"""
    key: str = Field(..., min_length=1, description="Tag key name")
    required: bool = Field(True, description="Whether this tag is required")
    type: str = Field("free", description="Value type: free|enum|email|pattern|number|boolean|arn|date")
    values: Optional[List[str]] = Field(None, description="Allowed values for enum type")
    pattern: Optional[str] = Field(None, description="Regex pattern for pattern type")
    description: Optional[str] = Field(None, description="Help text for this tag")
    weight: int = Field(10, ge=1, le=20, description="Scoring weight (1-20)")

    @validator('type')
    def validate_type(cls, v):
        allowed = ['free', 'enum', 'email', 'pattern', 'number', 'boolean', 'arn', 'date']
        if v not in allowed:
            raise ValueError(f'type must be one of: {allowed}')
        return v


class TagTemplateCreate(BaseModel):
    """Schema for creating a tag template"""
    name: str = Field(..., min_length=1, max_length=255, description="Template name")
    description: Optional[str] = Field(None, description="Template description")
    scope: List[str] = Field(default_factory=list, description="Resource types: ['EC2','EBS','RDS']")
    tag_schema: List[TagSchemaEntry] = Field(default_factory=list, description="Tag definitions with weights")
    is_default: bool = Field(False, description="Set as default template")

    # Legacy fields (backward compat with BulkTagWizard)
    tags: Optional[Dict[str, str]] = Field(None, description="Legacy flat tag pairs")
    resource_scope: Optional[str] = Field(None, description="Legacy single scope")

    @validator('tag_schema')
    def validate_tag_schema(cls, v, values):
        if not v and not values.get('tags'):
            raise ValueError('tag_schema or tags must be provided')
        return v

    class Config:
        json_schema_extra = {
            "example": {
                "name": "EC2 Workload Standard",
                "description": "Standard tags for EC2 production workloads",
                "scope": ["EC2", "EBS"],
                "tag_schema": [
                    {"key": "owner", "required": True, "type": "email", "weight": 15},
                    {"key": "environment", "required": True, "type": "enum",
                     "values": ["production", "staging", "development"], "weight": 20}
                ],
                "is_default": False
            }
        }


class TagTemplateUpdate(BaseModel):
    """Schema for updating a tag template"""
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    description: Optional[str] = None
    scope: Optional[List[str]] = None
    tag_schema: Optional[List[TagSchemaEntry]] = None
    is_default: Optional[bool] = None
    is_active: Optional[bool] = None

    # Legacy
    tags: Optional[Dict[str, str]] = None
    resource_scope: Optional[str] = None


class CoverageHeatmapEntry(BaseModel):
    """Coverage percentage for a single tag key"""
    key: str
    coverage_pct: float


class TagTemplateResponse(BaseModel):
    """Schema for tag template response"""
    id: str
    organization_id: str
    name: str
    description: Optional[str]
    scope: Optional[List[str]] = []
    tag_schema: Optional[List[Dict[str, Any]]] = []
    compliance_score: int = 0
    resource_count: int = 0
    is_default: bool
    is_active: bool
    created_by: Optional[str]
    created_at: datetime
    updated_at: datetime

    # Legacy
    tags: Optional[Dict[str, str]] = None
    resource_scope: Optional[str] = None
    tag_count: Optional[int] = 0

    class Config:
        from_attributes = True


class TagTemplateListResponse(BaseModel):
    """Schema for list of tag templates with coverage heatmap"""
    templates: List[TagTemplateResponse]
    total: int
    default_template_id: Optional[str] = None
    coverage_heatmap: List[CoverageHeatmapEntry] = []


class TagTemplateList(BaseModel):
    """Legacy schema for backward compat"""
    templates: List[TagTemplateResponse]
    total: int
    default_template_id: Optional[str] = None
