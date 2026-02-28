"""
Node Template Schemas

Pydantic validation schemas for node template management.
"""
from pydantic import BaseModel, Field, validator
from typing import List, Optional, Dict, Any
from datetime import datetime


class FlaggingRulesConfig(BaseModel):
    """
    Configurable flagging rules for pool selection.

    Controls how aggressive the system is in flagging/blacklisting pools.
    """
    # Risk thresholds
    max_risk_threshold: float = Field(
        default=0.50,
        ge=0.0,
        le=1.0,
        description="Maximum ML risk probability (0.0-1.0). Pools above this are hard-rejected."
    )
    max_interruption_rate: int = Field(
        default=15,
        ge=0,
        le=100,
        description="Maximum acceptable interruption rate % (AWS Spot Advisor). 15 = <15%."
    )
    min_ml_score: float = Field(
        default=0.30,
        ge=0.0,
        le=1.0,
        description="Minimum composite ML score (Expected Value). Pools below this are rejected."
    )

    # Blacklist behavior
    blacklist_respect: str = Field(
        default="soft",
        description="How to handle blacklisted pools: 'hard' (reject), 'soft' (penalty), 'ignore'"
    )
    blacklist_penalty_pct: float = Field(
        default=20.0,
        ge=0.0,
        le=100.0,
        description="Savings penalty % for soft-blacklisted pools (default 20%)"
    )

    # Diversity enforcement
    diversity_enforcement: str = Field(
        default="strict",
        description="Diversity constraint strictness: 'strict', 'moderate', 'disabled'"
    )
    max_az_concentration: int = Field(
        default=50,
        ge=0,
        le=100,
        description="Max % of nodes in single AZ (strict=50%, moderate=70%, disabled=100%)"
    )
    max_family_concentration: int = Field(
        default=40,
        ge=0,
        le=100,
        description="Max % of nodes in single family (strict=40%, moderate=60%, disabled=100%)"
    )

    # Auto-rotation & backup
    auto_rotation_enabled: bool = Field(
        default=True,
        description="Automatically rotate to backup AZs when primary AZ is fully blacklisted"
    )
    backup_az_count: int = Field(
        default=2,
        ge=0,
        le=5,
        description="Number of backup AZs to maintain in fresh pool cache (0-5)"
    )
    min_viable_pools: int = Field(
        default=10,
        ge=5,
        le=50,
        description="Minimum number of viable pools to maintain. Triggers auto-rotation if below."
    )

    # Cascade prevention
    cascade_dampener_enabled: bool = Field(
        default=True,
        description="Enable cascade dampener when >70% of pools are blacklisted"
    )
    cascade_threshold_pct: float = Field(
        default=70.0,
        ge=50.0,
        le=95.0,
        description="Blacklist ratio % that triggers cascade dampener (default 70%)"
    )

    @validator("blacklist_respect")
    def validate_blacklist_respect(cls, v):
        if v not in ["hard", "soft", "ignore"]:
            raise ValueError("blacklist_respect must be 'hard', 'soft', or 'ignore'")
        return v

    @validator("diversity_enforcement")
    def validate_diversity_enforcement(cls, v):
        if v not in ["strict", "moderate", "disabled"]:
            raise ValueError("diversity_enforcement must be 'strict', 'moderate', or 'disabled'")
        return v


class NodeTemplateCreate(BaseModel):
    """Schema for creating a new node template."""
    name: str = Field(..., description="Template name")
    description: Optional[str] = Field(None, description="Template description")
    instance_families: List[str] = Field(default_factory=list, description="Allowed instance families")
    instance_types: List[str] = Field(default_factory=list, description="Specific instance types")
    architectures: List[str] = Field(default_factory=list, description="Allowed architectures (x86_64, arm64)")
    min_vcpus: Optional[int] = Field(None, description="Minimum vCPUs")
    max_vcpus: Optional[int] = Field(None, description="Maximum vCPUs")
    min_memory_gb: Optional[float] = Field(None, description="Minimum memory in GB")
    max_memory_gb: Optional[float] = Field(None, description="Maximum memory in GB")
    blacklist: List[str] = Field(default_factory=list, description="Blacklisted instance types")
    template_metadata: Optional[Dict[str, Any]] = Field(default_factory=dict, description="Additional metadata")

    # NEW: Flagging rules configuration
    flagging_rules: Optional[FlaggingRulesConfig] = Field(
        default_factory=FlaggingRulesConfig,
        description="Configurable flagging and rotation rules"
    )


class NodeTemplateUpdate(BaseModel):
    """Schema for updating an existing node template."""
    name: Optional[str] = Field(None, description="Template name")
    description: Optional[str] = Field(None, description="Template description")
    instance_families: Optional[List[str]] = Field(None, description="Allowed instance families")
    instance_types: Optional[List[str]] = Field(None, description="Specific instance types")
    architectures: Optional[List[str]] = Field(None, description="Allowed architectures")
    min_vcpus: Optional[int] = Field(None, description="Minimum vCPUs")
    max_vcpus: Optional[int] = Field(None, description="Maximum vCPUs")
    min_memory_gb: Optional[float] = Field(None, description="Minimum memory in GB")
    max_memory_gb: Optional[float] = Field(None, description="Maximum memory in GB")
    blacklist: Optional[List[str]] = Field(None, description="Blacklisted instance types")
    template_metadata: Optional[Dict[str, Any]] = Field(None, description="Additional metadata")

    # NEW: Flagging rules configuration
    flagging_rules: Optional[FlaggingRulesConfig] = Field(
        None,
        description="Configurable flagging and rotation rules"
    )


class NodeTemplateResponse(BaseModel):
    """Schema for node template response."""
    id: str
    name: str
    description: Optional[str]
    instance_families: List[str]
    instance_types: List[str]
    architectures: List[str]
    min_vcpus: Optional[int]
    max_vcpus: Optional[int]
    min_memory_gb: Optional[float]
    max_memory_gb: Optional[float]
    blacklist: List[str]
    template_metadata: Dict[str, Any]
    flagging_rules: Optional[FlaggingRulesConfig]  # NEW
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class NodeTemplateList(BaseModel):
    """Schema for list of node templates."""
    templates: List[NodeTemplateResponse]
    total: int


class TemplateValidationResult(BaseModel):
    """Schema for template validation result."""
    valid: bool
    errors: List[str] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)
    matched_instances: List[str] = Field(default_factory=list)


class PoolRotationStatus(BaseModel):
    """
    Status of auto-rotation system for a cluster.
    """
    cluster_id: str
    primary_az: str
    backup_azs: List[str]
    primary_az_blacklisted: bool
    auto_rotation_active: bool
    current_active_az: str
    viable_pool_count: int
    min_viable_threshold: int
    last_rotation_at: Optional[datetime]
    cascade_dampener_active: bool

    class Config:
        from_attributes = True
