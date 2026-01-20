"""
Tag Policy Pydantic Schemas
"""
from pydantic import BaseModel, Field, validator
from typing import Optional, List, Dict, Any
from datetime import datetime


class TagPolicyCreate(BaseModel):
    """Schema for creating a new tag policy"""
    tag_key: str = Field(..., min_length=1, max_length=255, description="Tag key name (e.g., 'Owner')")
    description: Optional[str] = Field(None, description="Help text for users")
    value_mode: str = Field("free_text", description="'free_text' or 'predefined'")
    allowed_values: Optional[List[str]] = Field(None, description="List of allowed values for predefined mode")
    validation_regex: Optional[str] = Field(None, max_length=500, description="Regex pattern for value validation")
    enforcement_level: str = Field("advisory", description="'advisory', 'required', or 'strict'")
    resource_types: List[str] = Field(default_factory=lambda: ["*"], description="Resource types this applies to")
    regions: List[str] = Field(default_factory=lambda: ["*"], description="AWS regions this applies to")
    
    @validator('enforcement_level')
    def validate_enforcement(cls, v):
        allowed = ['advisory', 'required', 'strict']
        if v not in allowed:
            raise ValueError(f'enforcement_level must be one of: {allowed}')
        return v
    
    @validator('value_mode')
    def validate_value_mode(cls, v):
        allowed = ['free_text', 'predefined']
        if v not in allowed:
            raise ValueError(f'value_mode must be one of: {allowed}')
        return v


class TagPolicyUpdate(BaseModel):
    """Schema for updating a tag policy"""
    description: Optional[str] = None
    value_mode: Optional[str] = None
    allowed_values: Optional[List[str]] = None
    validation_regex: Optional[str] = None
    enforcement_level: Optional[str] = None
    resource_types: Optional[List[str]] = None
    regions: Optional[List[str]] = None
    is_active: Optional[bool] = None


class TagPolicyResponse(BaseModel):
    """Schema for tag policy response"""
    id: str
    organization_id: str
    tag_key: str
    description: Optional[str]
    value_mode: str
    allowed_values: Optional[List[str]]
    validation_regex: Optional[str]
    enforcement_level: str
    resource_types: List[str]
    regions: List[str]
    is_active: bool
    created_at: datetime
    updated_at: datetime
    
    # Computed fields
    compliance_percentage: Optional[float] = Field(None, description="% of resources compliant with this policy")
    non_compliant_count: Optional[int] = Field(None, description="Number of non-compliant resources")
    
    class Config:
        from_attributes = True


class ComplianceStats(BaseModel):
    """Schema for compliance statistics"""
    total_resources: int = Field(..., description="Total resources scanned")
    compliant_resources: int = Field(..., description="Resources meeting all required policies")
    non_compliant_resources: int = Field(..., description="Resources missing required tags")
    compliance_percentage: float = Field(..., description="Overall compliance %")
    
    by_policy: List[Dict[str, Any]] = Field(default_factory=list, description="Per-policy breakdown")
    by_resource_type: List[Dict[str, Any]] = Field(default_factory=list, description="Per-resource-type breakdown")
    
    missing_tags_summary: Dict[str, int] = Field(default_factory=dict, description="Count of resources missing each tag")


class TagPolicyList(BaseModel):
    """Schema for list of tag policies"""
    policies: List[TagPolicyResponse]
    total: int
    advisory_count: int
    required_count: int
    strict_count: int
