"""
Template Schemas - Request/Response models for node template management
"""
from pydantic import BaseModel, Field, field_validator
from typing import List, Optional
from datetime import datetime


class NodeTemplateCreate(BaseModel):
    """Create node template request"""
    name: str = Field(..., min_length=1, max_length=255, description="Template name")
    families: List[str] = Field(..., min_length=1, description="EC2 instance families (e.g., ['m5', 'm6i'])")
    architecture: str = Field(default="x86_64", description="CPU architecture (x86_64 or arm64)")
    strategy: str = Field(..., description="Selection strategy (CHEAPEST, BALANCED, PERFORMANCE)")
    disk_type: str = Field(..., description="EBS disk type (GP3, GP2, IO1, IO2)")
    disk_size: int = Field(..., ge=10, le=16000, description="Disk size in GB")
    is_default: bool = Field(default=False, description="Set as default template")

    @field_validator('architecture')
    @classmethod
    def validate_architecture(cls, v: str) -> str:
        if v not in ['x86_64', 'arm64']:
            raise ValueError('Architecture must be x86_64 or arm64')
        return v

    @field_validator('strategy')
    @classmethod
    def validate_strategy(cls, v: str) -> str:
        if v not in ['CHEAPEST', 'BALANCED', 'PERFORMANCE']:
            raise ValueError('Strategy must be CHEAPEST, BALANCED, or PERFORMANCE')
        return v

    @field_validator('disk_type')
    @classmethod
    def validate_disk_type(cls, v: str) -> str:
        if v not in ['GP3', 'GP2', 'IO1', 'IO2']:
            raise ValueError('Disk type must be GP3, GP2, IO1, or IO2')
        return v

    @field_validator('families')
    @classmethod
    def validate_families(cls, v: List[str]) -> List[str]:
        """Validate instance families"""
        valid_families = {
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
        }
        for family in v:
            if family not in valid_families:
                raise ValueError(f'Invalid instance family: {family}')
        return v

    model_config = {
        "json_schema_extra": {
            "example": {
                "name": "Production General Purpose",
                "families": ["m5", "m6i", "m7i"],
                "architecture": "x86_64",
                "strategy": "BALANCED",
                "disk_type": "GP3",
                "disk_size": 100,
                "is_default": True
            }
        }
    }


class NodeTemplateUpdate(BaseModel):
    """Update node template request"""
    name: Optional[str] = Field(None, min_length=1, max_length=255, description="Template name")
    families: Optional[List[str]] = Field(None, min_length=1, description="EC2 instance families")
    architecture: Optional[str] = Field(None, description="CPU architecture")
    strategy: Optional[str] = Field(None, description="Selection strategy")
    disk_type: Optional[str] = Field(None, description="EBS disk type")
    disk_size: Optional[int] = Field(None, ge=10, le=16000, description="Disk size in GB")
    is_default: Optional[bool] = Field(None, description="Set as default template")

    @field_validator('architecture')
    @classmethod
    def validate_architecture(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and v not in ['x86_64', 'arm64']:
            raise ValueError('Architecture must be x86_64 or arm64')
        return v

    @field_validator('strategy')
    @classmethod
    def validate_strategy(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and v not in ['CHEAPEST', 'BALANCED', 'PERFORMANCE']:
            raise ValueError('Strategy must be CHEAPEST, BALANCED, or PERFORMANCE')
        return v

    @field_validator('disk_type')
    @classmethod
    def validate_disk_type(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and v not in ['GP3', 'GP2', 'IO1', 'IO2']:
            raise ValueError('Disk type must be GP3, GP2, IO1, or IO2')
        return v

    model_config = {
        "json_schema_extra": {
            "example": {
                "name": "Updated Production Template",
                "disk_size": 150
            }
        }
    }


class NodeTemplateResponse(BaseModel):
    """Node template response"""
    id: str = Field(..., description="Template UUID")
    user_id: str = Field(..., description="Owner user UUID")
    name: str = Field(..., description="Template name")
    families: List[str] = Field(..., description="EC2 instance families")
    architecture: str = Field(..., description="CPU architecture")
    strategy: str = Field(..., description="Selection strategy")
    disk_type: str = Field(..., description="EBS disk type")
    disk_size: int = Field(..., description="Disk size in GB")
    is_default: bool = Field(..., description="Is default template")
    created_at: datetime = Field(..., description="Creation timestamp")
    updated_at: datetime = Field(..., description="Last update timestamp")

    model_config = {
        "json_schema_extra": {
            "example": {
                "id": "990e8400-e29b-41d4-a716-446655440000",
                "user_id": "550e8400-e29b-41d4-a716-446655440000",
                "name": "Production General Purpose",
                "families": ["m5", "m6i", "m7i"],
                "architecture": "x86_64",
                "strategy": "BALANCED",
                "disk_type": "GP3",
                "disk_size": 100,
                "is_default": True,
                "created_at": "2025-12-31T10:00:00Z",
                "updated_at": "2025-12-31T10:00:00Z"
            }
        }
    }


class NodeTemplateList(BaseModel):
    """List of node templates"""
    templates: List[NodeTemplateResponse] = Field(..., description="Array of templates")
    total: int = Field(..., ge=0, description="Total number of templates")

    model_config = {
        "json_schema_extra": {
            "example": {
                "templates": [
                    {
                        "id": "990e8400-e29b-41d4-a716-446655440000",
                        "user_id": "550e8400-e29b-41d4-a716-446655440000",
                        "name": "Production General Purpose",
                        "families": ["m5", "m6i", "m7i"],
                        "architecture": "x86_64",
                        "strategy": "BALANCED",
                        "disk_type": "GP3",
                        "disk_size": 100,
                        "is_default": True,
                        "created_at": "2025-12-31T10:00:00Z",
                        "updated_at": "2025-12-31T10:00:00Z"
                    }
                ],
                "total": 1
            }
        }
    }


class TemplateValidationResult(BaseModel):
    """Template validation result"""
    valid: bool = Field(..., description="Whether template is valid")
    errors: List[str] = Field(default_factory=list, description="Validation errors")
    warnings: List[str] = Field(default_factory=list, description="Validation warnings")
    estimated_cost_range: Optional[dict] = Field(None, description="Estimated cost range (min/max per hour)")

    model_config = {
        "json_schema_extra": {
            "example": {
                "valid": True,
                "errors": [],
                "warnings": ["Family m7i may have limited spot availability in some regions"],
                "estimated_cost_range": {
                    "min_hourly": 0.083,
                    "max_hourly": 0.192
                }
            }
        }
    }
