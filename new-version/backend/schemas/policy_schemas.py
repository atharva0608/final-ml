"""
Policy Schemas - Request/Response models for cluster policy configuration
"""
from pydantic import BaseModel, Field, field_validator
from typing import Optional, List, Dict, Any
from datetime import datetime


class BinpackSettings(BaseModel):
    """Bin packing algorithm settings"""
    cpu_weight: float = Field(default=1.0, ge=0, le=10, description="CPU weight in bin packing")
    memory_weight: float = Field(default=1.0, ge=0, le=10, description="Memory weight in bin packing")
    pod_density_weight: float = Field(default=0.5, ge=0, le=10, description="Pod density weight")

    model_config = {
        "json_schema_extra": {
            "example": {
                "cpu_weight": 1.0,
                "memory_weight": 1.0,
                "pod_density_weight": 0.5
            }
        }
    }


class ExclusionRules(BaseModel):
    """Node exclusion rules"""
    exclude_labels: Optional[Dict[str, str]] = Field(None, description="Exclude nodes with these labels")
    exclude_taints: Optional[List[str]] = Field(None, description="Exclude nodes with these taints")
    exclude_instance_types: Optional[List[str]] = Field(None, description="Exclude specific instance types")

    model_config = {
        "json_schema_extra": {
            "example": {
                "exclude_labels": {"environment": "production-critical"},
                "exclude_taints": ["NoSchedule"],
                "exclude_instance_types": ["t2.micro", "t2.small"]
            }
        }
    }


class PolicyConfig(BaseModel):
    """Complete policy configuration"""
    karpenter_enabled: bool = Field(default=True, description="Enable Karpenter integration")
    strategy: str = Field(default="BALANCED", description="Optimization strategy (CHEAPEST, BALANCED, PERFORMANCE)")
    spot_percentage: int = Field(default=80, ge=0, le=100, description="Target percentage of spot instances")
    binpack_enabled: bool = Field(default=True, description="Enable bin packing optimization")
    binpack_settings: Optional[BinpackSettings] = Field(None, description="Bin packing algorithm settings")
    fallback_on_demand: bool = Field(default=True, description="Fallback to on-demand if spot unavailable")
    exclusions: Optional[ExclusionRules] = Field(None, description="Node exclusion rules")

    @field_validator('strategy')
    @classmethod
    def validate_strategy(cls, v: str) -> str:
        if v not in ['CHEAPEST', 'BALANCED', 'PERFORMANCE']:
            raise ValueError('Strategy must be CHEAPEST, BALANCED, or PERFORMANCE')
        return v

    model_config = {
        "json_schema_extra": {
            "example": {
                "karpenter_enabled": True,
                "strategy": "BALANCED",
                "spot_percentage": 80,
                "binpack_enabled": True,
                "binpack_settings": {
                    "cpu_weight": 1.0,
                    "memory_weight": 1.0,
                    "pod_density_weight": 0.5
                },
                "fallback_on_demand": True,
                "exclusions": {
                    "exclude_labels": {"environment": "production-critical"},
                    "exclude_taints": ["NoSchedule"]
                }
            }
        }
    }


class PolicyCreate(BaseModel):
    """Create policy request"""
    cluster_id: str = Field(..., description="Cluster UUID")
    template_id: str = Field(..., description="Node template UUID")
    spot_percentage: int = Field(default=80, ge=0, le=100, description="Target spot percentage")
    fallback_to_on_demand: bool = Field(default=True, description="Fallback to on-demand if spot unavailable")
    max_price_per_hour: Optional[float] = Field(None, description="Maximum price per hour")
    diversification_enabled: bool = Field(default=True, description="Enable instance type diversification")
    min_nodes: int = Field(default=1, ge=0, description="Minimum number of nodes")
    max_nodes: int = Field(default=10, ge=1, description="Maximum number of nodes")
    target_cpu_utilization: int = Field(default=70, ge=0, le=100, description="Target CPU utilization percentage")
    target_memory_utilization: int = Field(default=70, ge=0, le=100, description="Target memory utilization percentage")
    scale_down_cooldown_minutes: int = Field(default=15, ge=0, description="Cooldown period before scaling down")
    is_active: bool = Field(default=True, description="Whether policy is active")


class PolicyUpdate(BaseModel):
    """Update policy configuration request"""
    template_id: Optional[str] = Field(None, description="Node template UUID")
    spot_percentage: Optional[int] = Field(None, ge=0, le=100, description="Target spot percentage")
    fallback_to_on_demand: Optional[bool] = Field(None, description="Fallback to on-demand")
    max_price_per_hour: Optional[float] = Field(None, description="Maximum price per hour")
    diversification_enabled: Optional[bool] = Field(None, description="Enable diversification")
    min_nodes: Optional[int] = Field(None, ge=0, description="Minimum nodes")
    max_nodes: Optional[int] = Field(None, ge=1, description="Maximum nodes")
    target_cpu_utilization: Optional[int] = Field(None, ge=0, le=100, description="Target CPU utilization")
    target_memory_utilization: Optional[int] = Field(None, ge=0, le=100, description="Target memory utilization")
    scale_down_cooldown_minutes: Optional[int] = Field(None, ge=0, description="Scale down cooldown")
    is_active: Optional[bool] = Field(None, description="Whether policy is active")


class PolicyResponse(PolicyCreate):
    """Policy response model"""
    id: str = Field(..., description="Policy UUID")
    created_at: datetime = Field(..., description="Creation timestamp")
    updated_at: datetime = Field(..., description="Last update timestamp")


class PolicyList(BaseModel):
    """List of policies with pagination"""
    policies: List[PolicyResponse] = Field(..., description="List of policies")
    total: int = Field(..., description="Total number of policies")
    page: int = Field(..., description="Current page number")
    page_size: int = Field(..., description="Number of items per page")


class PolicyFilter(BaseModel):
    """Filter criteria for policies"""
    cluster_id: Optional[str] = Field(None, description="Filter by cluster UUID")
    template_id: Optional[str] = Field(None, description="Filter by template UUID")
    is_active: Optional[bool] = Field(None, description="Filter by active status")
    min_spot_percentage: Optional[int] = Field(None, ge=0, le=100, description="Minimum spot percentage")
    page: int = Field(default=1, ge=1, description="Page number")
    page_size: int = Field(default=50, ge=1, le=100, description="Items per page")


class PolicyState(BaseModel):
    """Current policy state response"""
    id: str = Field(..., description="Policy UUID")
    cluster_id: str = Field(..., description="Cluster UUID")
    config: PolicyConfig = Field(..., description="Policy configuration")
    created_at: datetime = Field(..., description="Creation timestamp")
    updated_at: datetime = Field(..., description="Last update timestamp")

    model_config = {
        "json_schema_extra": {
            "example": {
                "id": "aa0e8400-e29b-41d4-a716-446655440000",
                "cluster_id": "550e8400-e29b-41d4-a716-446655440000",
                "config": {
                    "karpenter_enabled": True,
                    "strategy": "BALANCED",
                    "spot_percentage": 80,
                    "binpack_enabled": True,
                    "binpack_settings": {
                        "cpu_weight": 1.0,
                        "memory_weight": 1.0,
                        "pod_density_weight": 0.5
                    },
                    "fallback_on_demand": True
                },
                "created_at": "2025-12-31T10:00:00Z",
                "updated_at": "2025-12-31T10:00:00Z"
            }
        }
    }


class PolicyValidationResult(BaseModel):
    """Policy validation result"""
    valid: bool = Field(..., description="Whether policy is valid")
    errors: List[str] = Field(default_factory=list, description="Validation errors")
    warnings: List[str] = Field(default_factory=list, description="Validation warnings")
    estimated_impact: Optional[Dict[str, Any]] = Field(None, description="Estimated impact of policy changes")

    model_config = {
        "json_schema_extra": {
            "example": {
                "valid": True,
                "errors": [],
                "warnings": ["High spot percentage may increase interruption risk"],
                "estimated_impact": {
                    "cost_reduction": 45.2,
                    "interruption_risk": "medium"
                }
            }
        }
    }
