"""
Tag Scoring Configuration Pydantic Schemas
"""
from pydantic import BaseModel, Field, validator
from typing import Optional, List, Dict, Any
from datetime import datetime


class ScoringConfigUpdate(BaseModel):
    """Schema for updating scoring configuration"""
    mode: str = Field("weighted", description="Scoring mode: weighted|all|custom")
    threshold: Optional[int] = Field(60, ge=0, le=100, description="Minimum passing score (0-100)")
    required_keys: Optional[List[str]] = Field(None, description="Required keys for custom mode")

    @validator('mode')
    def validate_mode(cls, v):
        allowed = ['weighted', 'all', 'custom']
        if v not in allowed:
            raise ValueError(f'mode must be one of: {allowed}')
        return v

    @validator('required_keys')
    def validate_required_keys(cls, v, values):
        if values.get('mode') == 'custom' and (not v or len(v) == 0):
            raise ValueError('required_keys must be non-empty when mode is custom')
        return v


class ScoringConfigResponse(BaseModel):
    """Schema for scoring configuration response"""
    id: Optional[str] = None
    mode: str = "weighted"
    threshold: int = 60
    required_keys: List[str] = []
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class ScoringPreviewResource(BaseModel):
    """Single resource in scoring preview"""
    resource_id: str
    resource_name: Optional[str] = None
    resource_type: str
    score: int
    status: str
    tags_present: int = 0


class ScoringPreviewResponse(BaseModel):
    """Response for scoring preview"""
    resources: List[ScoringPreviewResource] = []
    mode: str
    threshold: int
