"""
Metric Schemas - Request/Response models for dashboard metrics and KPIs
"""
from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
from datetime import datetime


class KPISet(BaseModel):
    """Key Performance Indicators"""
    total_clusters: int = Field(..., ge=0, description="Total number of clusters")
    total_nodes: int = Field(..., ge=0, description="Total number of nodes")
    spot_nodes: int = Field(..., ge=0, description="Number of spot instances")
    spot_percentage: float = Field(..., ge=0, le=100, description="Percentage of spot instances")
    monthly_cost: float = Field(..., ge=0, description="Current monthly cost in USD")
    monthly_savings: float = Field(..., ge=0, description="Monthly savings from optimization in USD")
    savings_percentage: float = Field(..., ge=0, le=100, description="Percentage savings")
    avg_interruption_rate: float = Field(..., ge=0, le=100, description="Average spot interruption rate")

    model_config = {
        "json_schema_extra": {
            "example": {
                "total_clusters": 5,
                "total_nodes": 78,
                "spot_nodes": 62,
                "spot_percentage": 79.5,
                "monthly_cost": 8750.25,
                "monthly_savings": 3250.75,
                "savings_percentage": 27.1,
                "avg_interruption_rate": 2.3
            }
        }
    }


class ChartDataPoint(BaseModel):
    """Single data point for time series chart"""
    timestamp: datetime = Field(..., description="Data point timestamp")
    value: float = Field(..., description="Data point value")

    model_config = {
        "json_schema_extra": {
            "example": {
                "timestamp": "2025-12-31T12:00:00Z",
                "value": 8750.25
            }
        }
    }


class ChartData(BaseModel):
    """Time series chart data"""
    label: str = Field(..., description="Data series label")
    data: List[ChartDataPoint] = Field(..., description="Array of data points")
    color: Optional[str] = Field(None, description="Chart color (hex)")

    model_config = {
        "json_schema_extra": {
            "example": {
                "label": "Monthly Cost",
                "data": [
                    {"timestamp": "2025-12-01T00:00:00Z", "value": 9500.0},
                    {"timestamp": "2025-12-15T00:00:00Z", "value": 9200.0},
                    {"timestamp": "2025-12-31T00:00:00Z", "value": 8750.25}
                ],
                "color": "#3b82f6"
            }
        }
    }


class MultiSeriesChartData(BaseModel):
    """Multi-series chart data"""
    series: List[ChartData] = Field(..., description="Array of data series")

    model_config = {
        "json_schema_extra": {
            "example": {
                "series": [
                    {
                        "label": "Spot Cost",
                        "data": [{"timestamp": "2025-12-31T12:00:00Z", "value": 2500.0}],
                        "color": "#10b981"
                    },
                    {
                        "label": "On-Demand Cost",
                        "data": [{"timestamp": "2025-12-31T12:00:00Z", "value": 6250.25}],
                        "color": "#ef4444"
                    }
                ]
            }
        }
    }


class PieChartSlice(BaseModel):
    """Single slice of pie chart"""
    label: str = Field(..., description="Slice label")
    value: float = Field(..., ge=0, description="Slice value")
    percentage: float = Field(..., ge=0, le=100, description="Percentage of total")
    color: Optional[str] = Field(None, description="Slice color (hex)")

    model_config = {
        "json_schema_extra": {
            "example": {
                "label": "m5.xlarge",
                "value": 35,
                "percentage": 44.9,
                "color": "#3b82f6"
            }
        }
    }


class PieChartData(BaseModel):
    """Pie chart data"""
    total: float = Field(..., ge=0, description="Total value")
    slices: List[PieChartSlice] = Field(..., description="Array of pie slices")

    model_config = {
        "json_schema_extra": {
            "example": {
                "total": 78,
                "slices": [
                    {"label": "m5.xlarge", "value": 35, "percentage": 44.9, "color": "#3b82f6"},
                    {"label": "c5.2xlarge", "value": 28, "percentage": 35.9, "color": "#10b981"},
                    {"label": "r5.large", "value": 15, "percentage": 19.2, "color": "#f59e0b"}
                ]
            }
        }
    }


class ActivityFeedItem(BaseModel):
    """Single activity feed item"""
    id: str = Field(..., description="Activity UUID")
    timestamp: datetime = Field(..., description="Activity timestamp")
    actor: str = Field(..., description="Actor name (user or system)")
    action: str = Field(..., description="Action performed")
    resource: str = Field(..., description="Resource affected")
    resource_type: str = Field(..., description="Resource type")
    status: str = Field(..., description="Action outcome (SUCCESS or FAILURE)")
    details: Optional[str] = Field(None, description="Additional details")

    model_config = {
        "json_schema_extra": {
            "example": {
                "id": "cc0e8400-e29b-41d4-a716-446655440000",
                "timestamp": "2025-12-31T12:00:00Z",
                "actor": "admin@spotoptimizer.com",
                "action": "CLUSTER_OPTIMIZED",
                "resource": "production-eks",
                "resource_type": "CLUSTER",
                "status": "SUCCESS",
                "details": "Optimized 15 nodes, saved $450/month"
            }
        }
    }


class ActivityFeed(BaseModel):
    """Activity feed response"""
    activities: List[ActivityFeedItem] = Field(..., description="Array of recent activities")
    total: int = Field(..., ge=0, description="Total number of activities")

    model_config = {
        "json_schema_extra": {
            "example": {
                "activities": [
                    {
                        "id": "cc0e8400-e29b-41d4-a716-446655440000",
                        "timestamp": "2025-12-31T12:00:00Z",
                        "actor": "admin@spotoptimizer.com",
                        "action": "CLUSTER_OPTIMIZED",
                        "resource": "production-eks",
                        "resource_type": "CLUSTER",
                        "status": "SUCCESS",
                        "details": "Optimized 15 nodes"
                    }
                ],
                "total": 1
            }
        }
    }


class CostBreakdown(BaseModel):
    """Cost breakdown by category"""
    compute_cost: float = Field(..., ge=0, description="Compute cost")
    storage_cost: float = Field(..., ge=0, description="Storage cost")
    network_cost: float = Field(..., ge=0, description="Network cost")
    other_cost: float = Field(..., ge=0, description="Other costs")
    total_cost: float = Field(..., ge=0, description="Total cost")

    model_config = {
        "json_schema_extra": {
            "example": {
                "compute_cost": 7500.0,
                "storage_cost": 850.25,
                "network_cost": 350.0,
                "other_cost": 50.0,
                "total_cost": 8750.25
            }
        }
    }


class ClusterMetrics(BaseModel):
    """Detailed metrics for a single cluster"""
    cluster_id: str = Field(..., description="Cluster UUID")
    cluster_name: str = Field(..., description="Cluster name")
    node_count: int = Field(..., ge=0, description="Total nodes")
    spot_count: int = Field(..., ge=0, description="Spot instances")
    cpu_utilization: float = Field(..., ge=0, le=100, description="Average CPU utilization %")
    memory_utilization: float = Field(..., ge=0, le=100, description="Average memory utilization %")
    monthly_cost: float = Field(..., ge=0, description="Monthly cost")
    monthly_savings: float = Field(..., ge=0, description="Monthly savings")
    interruption_count_30d: int = Field(..., ge=0, description="Spot interruptions in last 30 days")

    model_config = {
        "json_schema_extra": {
            "example": {
                "cluster_id": "550e8400-e29b-41d4-a716-446655440000",
                "cluster_name": "production-eks",
                "node_count": 15,
                "spot_count": 12,
                "cpu_utilization": 45.2,
                "memory_utilization": 62.8,
                "monthly_cost": 1750.0,
                "monthly_savings": 650.0,
                "interruption_count_30d": 3
            }
        }
    }


class DashboardMetrics(BaseModel):
    """Complete dashboard metrics"""
    kpis: KPISet = Field(..., description="Key performance indicators")
    cost_trend: ChartData = Field(..., description="Cost trend over time")
    instance_distribution: PieChartData = Field(..., description="Instance type distribution")
    recent_activity: ActivityFeed = Field(..., description="Recent activity feed")
    cost_breakdown: CostBreakdown = Field(..., description="Cost breakdown by category")

    model_config = {
        "json_schema_extra": {
            "example": {
                "kpis": {
                    "total_clusters": 5,
                    "total_nodes": 78,
                    "spot_nodes": 62,
                    "spot_percentage": 79.5,
                    "monthly_cost": 8750.25,
                    "monthly_savings": 3250.75,
                    "savings_percentage": 27.1,
                    "avg_interruption_rate": 2.3
                },
                "cost_trend": {
                    "label": "Monthly Cost",
                    "data": [{"timestamp": "2025-12-31T12:00:00Z", "value": 8750.25}]
                },
                "instance_distribution": {
                    "total": 78,
                    "slices": [{"label": "m5.xlarge", "value": 35, "percentage": 44.9}]
                },
                "recent_activity": {"activities": [], "total": 0},
                "cost_breakdown": {
                    "compute_cost": 7500.0,
                    "storage_cost": 850.25,
                    "network_cost": 350.0,
                    "other_cost": 50.0,
                    "total_cost": 8750.25
                }
            }
        }
    }
