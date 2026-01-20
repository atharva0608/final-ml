"""
Tag Management Pydantic Schemas
"""
from pydantic import BaseModel, Field
from typing import Optional, List, Dict
from datetime import datetime


class ResourceTagUpdate(BaseModel):
    """Schema for updating tags on a single resource"""
    tags: Dict[str, str] = Field(..., description="Tags to apply (key-value pairs)")
    propagate_to_related: bool = Field(False, description="Also apply tags to related resources (snapshots, etc.)")
    overwrite_existing: bool = Field(False, description="Overwrite existing tag values")


class BulkTagUpdate(BaseModel):
    """Schema for bulk tag operations"""
    resource_ids: List[str] = Field(..., min_items=1, description="List of resource IDs to tag")
    resource_type: str = Field(..., description="Resource type (EC2, EBS, S3, etc.)")
    operation_mode: str = Field("merge", description="'merge' (update/add) or 'replace' (wipe and set)")
    tags: Dict[str, str] = Field(..., description="Tags to apply")
    region: Optional[str] = Field(None, description="AWS region")
    
    class Config:
        json_schema_extra = {
            "example": {
                "resource_ids": ["vol-123", "vol-456"],
                "resource_type": "EBS",
                "operation_mode": "merge",
                "tags": {"Owner": "Alice", "Environment": "Prod"}
            }
        }


class TagSuggestion(BaseModel):
    """Schema for tag suggestions"""
    key: str = Field(..., description="Suggested tag key")
    value: str = Field(..., description="Suggested tag value")
    confidence: float = Field(..., ge=0.0, le=1.0, description="Confidence score (0-1)")
    reason: str = Field(..., description="Why this tag is suggested")
    source: str = Field(..., description="Source of suggestion (pattern, ml, common)")


class ResourceTagsResponse(BaseModel):
    """Schema for resource tags response"""
    resource_id: str
    resource_type: str
    region: Optional[str]
    current_tags: Dict[str, str]
    missing_required_tags: List[str]
    is_compliant: bool
    suggestions: List[TagSuggestion] = Field(default_factory=list)


class BulkTagResult(BaseModel):
    """Schema for bulk tag operation results"""
    total_requested: int
    successful: int
    failed: int
    skipped: int
    failed_resources: List[Dict[str, str]] = Field(default_factory=list)
    operation_mode: str
    tags_applied: Dict[str, str]


class TagValidationResult(BaseModel):
    """Schema for tag validation against policies"""
    is_valid: bool
    tag_key: str
    tag_value: str
    policy_id: Optional[str]
    errors: List[str] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)
