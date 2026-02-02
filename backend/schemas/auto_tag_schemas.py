"""
Auto-Tag Rule Pydantic Schemas
"""
from pydantic import BaseModel, Field, validator
from typing import Optional, List, Dict, Any
from datetime import datetime
from enum import Enum


class ValueSourceType(str, Enum):
    """Dynamic tag value source types"""
    STATIC = "static"
    USER_EMAIL = "user_email"
    USER_ID = "user_id"
    USER_NAME = "user_name"
    ORG_ID = "org_id"
    ORG_NAME = "org_name"
    CREATION_DATE = "creation_date"
    CREATION_TIME = "creation_time"
    ENV_VARIABLE = "env_variable"


class OverrideBehavior(str, Enum):
    """Behavior when tag already exists on resource"""
    SKIP_EXISTING = "skip_existing"
    OVERWRITE = "overwrite"


class ResourceScope(str, Enum):
    """Resource scope for auto-tag rules"""
    ALL = "all"
    COMPUTE_ONLY = "compute_only"
    STORAGE_ONLY = "storage_only"
    DATABASE_ONLY = "database_only"
    NETWORK_ONLY = "network_only"


class DynamicTagConfig(BaseModel):
    """Configuration for a single dynamic tag"""
    source: ValueSourceType = Field(..., description="Value source type")
    static_value: Optional[str] = Field(None, description="Static value (if source is STATIC)")
    env_var_name: Optional[str] = Field(None, description="Environment variable name (if source is ENV_VARIABLE)")
    
    class Config:
        json_schema_extra = {
            "example": {
                "source": "user_email",
                "static_value": None,
                "env_var_name": None
            }
        }


class AutoTagRuleCreate(BaseModel):
    """Schema for creating an auto-tag rule"""
    name: str = Field(..., min_length=1, max_length=255, description="Rule name")
    description: Optional[str] = Field(None, description="Rule description")
    resource_types: List[str] = Field(..., min_items=1, description="Resource types to match")
    regions: List[str] = Field(default_factory=lambda: ["*"], description="AWS regions")
    name_pattern: Optional[str] = Field(None, description="Resource name pattern (wildcard or regex)")
    pattern_type: str = Field("wildcard", description="'wildcard' or 'regex'")
    tags_to_apply: Dict[str, str] = Field(default_factory=dict, description="Static tags to apply")
    dynamic_tags: Optional[Dict[str, DynamicTagConfig]] = Field(default_factory=dict, description="Tags with dynamic value sources")
    resource_scope: ResourceScope = Field(ResourceScope.ALL, description="Broader resource scope filter")
    override_behavior: OverrideBehavior = Field(OverrideBehavior.SKIP_EXISTING, description="How to handle existing tags")
    inject_system_tags: bool = Field(True, description="Auto-inject ManagedBy system tag")
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
    dynamic_tags: Optional[Dict[str, DynamicTagConfig]] = None
    resource_scope: Optional[ResourceScope] = None
    override_behavior: Optional[OverrideBehavior] = None
    inject_system_tags: Optional[bool] = None
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
    dynamic_tags: Optional[Dict[str, Any]] = None
    resource_scope: str = "all"
    override_behavior: str = "skip_existing"
    inject_system_tags: bool = True
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


# NEW: Tag Preview Schemas for Smart Auto-Tag System
class TagPreviewRequest(BaseModel):
    """Request to preview generated tags for a context"""
    resource_type: str = Field(..., description="Type of resource (EC2, S3, etc.)")
    resource_name: Optional[str] = Field(None, description="Optional resource name for pattern matching")
    region: Optional[str] = Field("us-east-1", description="AWS region")
    rule_ids: Optional[List[str]] = Field(None, description="Specific rules to preview (all active if empty)")


class TagPreviewResponse(BaseModel):
    """Response with generated tag preview"""
    tags: Dict[str, str] = Field(..., description="Final resolved tag key-value pairs")
    applied_rules: List[str] = Field(default_factory=list, description="Rule names that contributed tags")
    system_tags_injected: bool = Field(False, description="Whether system tags were added")


class AvailableVariable(BaseModel):
    """A single available dynamic variable"""
    name: str
    source_type: ValueSourceType
    description: str
    example_value: str


class AvailableVariablesResponse(BaseModel):
    """List of available dynamic variables"""
    variables: List[AvailableVariable]
