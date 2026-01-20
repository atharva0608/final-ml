"""
Auto-Tag Rule Pydantic Schemas
"""
from pydantic import BaseModel, Field, validator
from typing import Optional, List, Dict
from datetime import datetime


class AutoTagRuleCreate(BaseModel):
    """Schema for creating an auto-tag rule"""
    name: str = Field(..., min_length=1, max_length=255, description="Rule name")
    description: Optional[str] = Field(None, description="Rule description")
    resource_types: List[str] = Field(..., min_items=1, description="Resource types to match")
    regions: List[str] = Field(default_factory=lambda: ["*"], description="AWS regions")
    name_pattern: Optional[str] = Field(None, description="Resource name pattern (wildcard or regex)")
    pattern_type: str = Field("wildcard", description="'wildcard' or 'regex'")
    tags_to_apply: Dict[str, str] = Field(..., min_items=1, description="Tags to apply")
    run_mode: str = Field("future_only", description="'future_only' or 'retroactive'")
    priority: int = Field(100, ge=1, le=1000, description="Rule priority (lower = higher)")
    
    @validator('pattern_type')
    def validate_pattern_type(cls, v):
        if v not in ['wildcard', 'regex']:
            raise ValueError("pattern_type must be 'wildcard' or 'regex'")
        return v
    
    @validator('run_mode')
    def validate_run_mode(cls, v):
        if v not in ['future_only', 'retroactive']:
            raise ValueError("run_mode must be 'future_only' or 'retroactive'")
        return v
    
    class Config:
        json_schema_extra = {
            "example": {
                "name": "Tag Prod Resources",
                "description": "Auto-tag resources with 'prod-' prefix",
                "resource_types": ["EC2", "EBS", "RDS"],
                "regions": ["us-east-1"],
                "name_pattern": "prod-*",
                "pattern_type": "wildcard",
                "tags_to_apply": {
                    "Environment": "Production",
                    "AutoTagged": "true"
                },
                "run_mode": "future_only"
            }
        }


class AutoTagRuleUpdate(BaseModel):
    """Schema for updating an auto-tag rule"""
    name: Optional[str] = None
    description: Optional[str] = None
    resource_types: Optional[List[str]] = None
    regions: Optional[List[str]] = None
    name_pattern: Optional[str] = None
    pattern_type: Optional[str] = None
    tags_to_apply: Optional[Dict[str, str]] = None
    run_mode: Optional[str] = None
    priority: Optional[int] = None
    is_active: Optional[bool] = None


class AutoTagRuleResponse(BaseModel):
    """Schema for auto-tag rule response"""
    id: str
    organization_id: str
    name: str
    description: Optional[str]
    is_active: bool
    resource_types: List[str]
    regions: List[str]
    name_pattern: Optional[str]
    pattern_type: str
    tags_to_apply: Dict[str, str]
    tag_count: int
    run_mode: str
    priority: int
    last_run_at: Optional[datetime]
    last_run_matched: int
    last_run_tagged: int
    total_resources_tagged: int
    created_by: Optional[str]
    created_at: datetime
    updated_at: datetime
    
    class Config:
        from_attributes = True


class AutoTagRuleList(BaseModel):
    """Schema for list of auto-tag rules"""
    rules: List[AutoTagRuleResponse]
    total: int
    active_count: int


class RuleTestResult(BaseModel):
    """Schema for rule test/preview results"""
    rule_id: str
    rule_name: str
    matched_resources: List[Dict[str, str]]
    match_count: int
    would_tag_count: int
    sample_resources: List[Dict[str, str]] = Field(default_factory=list, description="Sample of resources (max 10)")


class RuleExecutionResult(BaseModel):
    """Schema for rule execution results"""
    rule_id: str
    rule_name: str
    matched_resources: int
    tagged_resources: int
    failed_resources: int
    skipped_resources: int
    execution_time_seconds: float
    errors: List[str] = Field(default_factory=list)
