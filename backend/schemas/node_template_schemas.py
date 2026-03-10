from pydantic import BaseModel, Field, validator
from typing import List, Optional, Dict, Any
from datetime import datetime
from backend.models.node_template import TemplateStatus, TemplateScope, WorkloadScope, OptimizationPolicy, SubstituteStrategy

class NodeTemplateConstraints(BaseModel):
    """
    The 28-point constraint envelope logic stored as JSONB in the template version.
    """
    
    architectures: List[str] = Field(default_factory=lambda: ["amd64"])
    min_vcpu: int = Field(default=2, ge=1)
    max_vcpu: int = Field(default=64, ge=1)
    min_memory: float = Field(default=4.0, ge=0.5)
    max_memory: float = Field(default=256.0, ge=0.5)
    
    allowed_families: List[str] = Field(default_factory=list)
    excluded_families: List[str] = Field(default_factory=lambda: ["metal", "g", "p", "trn", "inf", "i"])
    
    allowed_zones: List[str] = Field(default_factory=list)
    cross_az_rebalance: bool = True
    
    optimization_policy: OptimizationPolicy = OptimizationPolicy.COST_FIRST
    risk_threshold: float = Field(default=10.0, ge=0.0, le=100.0)
    savings_threshold: float = Field(default=5.0, ge=0.0, le=100.0)

# --- Template Registry (Layer 1) ---

class NodeTemplateCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255) # reduced min_length from 3 to 1 to support simple names like "AA"
    scope: TemplateScope = TemplateScope.GLOBAL
    # For creation, we accept the initial constraints to immediately create Version 1
    initial_constraints: NodeTemplateConstraints

class NodeTemplateRead(BaseModel):
    id: str
    name: str
    scope: Optional[TemplateScope] = None
    created_by: Optional[str] = None
    created_at: datetime
    
    class Config:
        from_attributes = True

# --- Template Version (Layer 2) ---

class NodeTemplateVersionCreate(BaseModel):
    constraints: NodeTemplateConstraints

class NodeTemplateVersionRead(BaseModel):
    id: str
    template_id: str
    version_number: int
    status: TemplateStatus
    constraints_json: dict
    
    class Config:
        from_attributes = True

# --- Cluster Mapping (Layer 3) ---

class ClusterTemplateAssignRequest(BaseModel):
    template_id: str
    # If version_id is None, we pull the latest ACTIVE version of that template
    version_id: Optional[str] = None

class ClusterTemplateMappingRead(BaseModel):
    id: str
    cluster_id: str
    template_id: str
    version_id: str
    is_default: bool
    assigned_at: datetime
    
    # Optional embeds
    template: Optional[NodeTemplateRead] = None
    version: Optional[NodeTemplateVersionRead] = None
    
    class Config:
        from_attributes = True

# --- Validation / Preview ---

class NodeTemplateValidationRequest(NodeTemplateConstraints):
    cluster_id: str

class NodeTemplateValidationResponse(BaseModel):
    is_valid: bool
    candidate_pools_count: int
    estimated_savings_pct: float
    warnings: List[str] = Field(default_factory=list)
    sample_instances: List[str] = Field(default_factory=list)

class TemplateRegistryListResponse(BaseModel):
    """
    Response listing templates with aggregate usage.
    """
    templates: List[NodeTemplateRead]
    attached_clusters_count: Dict[str, int] = Field(description="Maps template_id to count of clusters using it")
