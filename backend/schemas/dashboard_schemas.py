"""
Dashboard Schemas - Response Models for Dashboard Endpoints

These schemas define the structure of dashboard API responses.
"""
from pydantic import BaseModel, Field
from typing import Dict, List, Optional
from datetime import datetime


class DashboardOverviewResponse(BaseModel):
    """
    Dashboard overview with three pricing models.

    MODEL A (actual_cost): From Cost Explorer (invoice-accurate)
    MODEL B (resources_cost): Sum of all resources @ 24/7
    MODEL C (optimization_cost): Potential savings
    """
    actual_cost: float = Field(..., description="MODEL A: Actual cost from Cost Explorer")
    resources_cost: float = Field(..., description="MODEL B: Sum of all resources @ 24/7")
    optimization_cost: float = Field(..., description="MODEL C: Potential savings")
    net_savings: float = Field(..., description="Realized savings (spot vs on-demand)")
    savings_rate: float = Field(..., description="Savings percentage")
    active_instances: int = Field(..., description="Number of running instances")
    total_clusters: int = Field(..., description="Total number of clusters")
    health_scores: Dict[str, Optional[float]] = Field(
        ...,
        description="Health scores for different categories"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "actual_cost": 54.44,
                "resources_cost": 23.62,
                "optimization_cost": 17.30,
                "net_savings": 0.0,
                "savings_rate": 0.0,
                "active_instances": 1,
                "total_clusters": 0,
                "health_scores": {
                    "ri": None,
                    "s3": None,
                    "rds": None,
                    "transfer": None
                }
            }
        }


class CostBreakdownResponse(BaseModel):
    """Cost breakdown by category (MODEL A: Actual Cost)"""
    compute: float = Field(..., description="EC2, ECS, EKS, Lambda")
    storage: float = Field(..., description="S3, EBS, EFS, Backup")
    network: float = Field(..., description="VPC, Data Transfer, Load Balancers")
    security: float = Field(..., description="Security Hub, KMS, Secrets Manager")
    management: float = Field(..., description="Config, Systems Manager, CloudWatch")
    others: float = Field(..., description="All other services")

    class Config:
        json_schema_extra = {
            "example": {
                "compute": 29.99,
                "storage": 0.80,
                "network": 7.39,
                "security": 8.25,
                "management": 7.83,
                "others": 0.18
            }
        }


class SavingsProjectionResponse(BaseModel):
    """Savings projection (MODEL C: Optimization Cost)"""
    current_spend: float = Field(..., description="Current monthly spend (MODEL A)")
    optimized_spend: float = Field(..., description="Spend after optimizations")
    potential_savings: float = Field(..., description="Total potential savings (MODEL C)")
    breakdown: Dict[str, float] = Field(
        ...,
        description="Breakdown of savings opportunities"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "current_spend": 54.44,
                "optimized_spend": 37.14,
                "potential_savings": 17.30,
                "breakdown": {
                    "hygiene_waste": 8.50,
                    "optimization_opportunities": 8.80
                }
            }
        }


class FleetCompositionResponse(BaseModel):
    """Fleet composition breakdown"""
    total_instances: int = Field(..., description="Total number of instances")
    by_type: Dict[str, int] = Field(..., description="Instances by type")
    by_lifecycle: Dict[str, int] = Field(..., description="Instances by lifecycle")
    by_state: Dict[str, int] = Field(..., description="Instances by state")

    class Config:
        json_schema_extra = {
            "example": {
                "total_instances": 1,
                "by_type": {"t3.micro": 1},
                "by_lifecycle": {"on_demand": 1, "spot": 0},
                "by_state": {"running": 1, "stopped": 0, "terminated": 0}
            }
        }


class ActivityItem(BaseModel):
    """Single activity item"""
    timestamp: datetime = Field(..., description="Activity timestamp")
    action: str = Field(..., description="Action type")
    resource_id: str = Field(..., description="Resource ID")
    details: str = Field(..., description="Activity details")


class ActivityFeedResponse(BaseModel):
    """Activity feed response"""
    activities: List[ActivityItem] = Field(..., description="List of recent activities")

    class Config:
        json_schema_extra = {
            "example": {
                "activities": [
                    {
                        "timestamp": "2026-02-12T10:00:00Z",
                        "action": "INSTANCE_DISCOVERED",
                        "resource_id": "i-0123456789abcdef0",
                        "details": "New t3.micro instance discovered"
                    }
                ]
            }
        }
