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
    config: PolicyConfig = Field(..., description="Policy configuration")

    model_config = {
        "json_schema_extra": {
            "example": {
                "cluster_id": "550e8400-e29b-41d4-a716-446655440000",
                "config": {
                    "karpenter_enabled": True,
                    "strategy": "BALANCED",
                    "spot_percentage": 80,
                    "binpack_enabled": True,
                    "fallback_on_demand": True
                }
            }
        }
    }


class PolicyUpdate(BaseModel):
    """Update policy configuration request"""
    karpenter_enabled: Optional[bool] = Field(None, description="Enable Karpenter integration")
    strategy: Optional[str] = Field(None, description="Optimization strategy")
    spot_percentage: Optional[int] = Field(None, ge=0, le=100, description="Target spot percentage")
    binpack_enabled: Optional[bool] = Field(None, description="Enable bin packing")
    binpack_settings: Optional[BinpackSettings] = Field(None, description="Bin packing settings")
    fallback_on_demand: Optional[bool] = Field(None, description="Fallback to on-demand")
    exclusions: Optional[ExclusionRules] = Field(None, description="Exclusion rules")

    @field_validator('strategy')
    @classmethod
    def validate_strategy(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and v not in ['CHEAPEST', 'BALANCED', 'PERFORMANCE']:
            raise ValueError('Strategy must be CHEAPEST, BALANCED, or PERFORMANCE')
        return v

    model_config = {
        "json_schema_extra": {
            "example": {
                "strategy": "PERFORMANCE",
                "spot_percentage": 70
            }
        }
    }


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


class PolicyFilter(BaseModel):
    """Filter criteria for listing policies"""
    cluster_id: Optional[str] = Field(None, description="Filter by cluster UUID")
    karpenter_enabled: Optional[bool] = Field(None, description="Filter by Karpenter status")

    model_config = {
        "json_schema_extra": {
            "example": {
                "cluster_id": "550e8400-e29b-41d4-a716-446655440000",
                "karpenter_enabled": True
            }
        }
    }


class PolicyList(BaseModel):
    """List of policies response"""
    items: List[PolicyState] = Field(..., description="List of policies")
    total: int = Field(..., ge=0, description="Total count")

    model_config = {
        "json_schema_extra": {
            "example": {
                "items": [
                    {
                        "id": "aa0e8400-e29b-41d4-a716-446655440000",
                        "cluster_id": "550e8400-e29b-41d4-a716-446655440000",
                        "config": {
                            "karpenter_enabled": True,
                            "strategy": "BALANCED",
                            "spot_percentage": 80,
                            "binpack_enabled": True,
                            "fallback_on_demand": True
                        },
                        "created_at": "2025-12-31T10:00:00Z",
                        "updated_at": "2025-12-31T10:00:00Z"
                    }
                ],
                "total": 1
            }
        }
    }


# Alias for backward compatibility
PolicyResponse = PolicyState
