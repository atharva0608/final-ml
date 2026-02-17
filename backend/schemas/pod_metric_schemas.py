"""
Pod Metric Schemas - For DaemonSet metric collection API
"""
from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
from datetime import datetime


class PodMetricCreate(BaseModel):
    """Schema for creating a single pod metric (from DaemonSet agent)"""
    namespace: str = Field(..., description="Kubernetes namespace")
    pod_name: str = Field(..., description="Pod name")
    node_name: str = Field(..., description="Node where pod is running")

    controller_kind: Optional[str] = Field(None, description="Controller type (Deployment, StatefulSet, etc.)")
    controller_name: Optional[str] = Field(None, description="Controller name")

    cpu_usage_millicores: int = Field(..., description="Current CPU usage in millicores")
    cpu_request_millicores: Optional[int] = Field(None, description="CPU request in millicores")
    cpu_limit_millicores: Optional[int] = Field(None, description="CPU limit in millicores")

    memory_usage_bytes: int = Field(..., description="Current memory usage in bytes")
    memory_request_bytes: Optional[int] = Field(None, description="Memory request in bytes")
    memory_limit_bytes: Optional[int] = Field(None, description="Memory limit in bytes")

    container_count: int = Field(1, description="Number of containers in pod")

    metadata: Optional[Dict[str, Any]] = Field(default_factory=dict, description="Additional metadata")

    class Config:
        json_schema_extra = {
            "example": {
                "namespace": "default",
                "pod_name": "nginx-deployment-7d4c5b7f9d-abc12",
                "node_name": "ip-10-0-1-123.ec2.internal",
                "controller_kind": "Deployment",
                "controller_name": "nginx-deployment",
                "cpu_usage_millicores": 125,
                "cpu_request_millicores": 100,
                "cpu_limit_millicores": 200,
                "memory_usage_bytes": 134217728,
                "memory_request_bytes": 104857600,
                "memory_limit_bytes": 209715200,
                "container_count": 1
            }
        }


class PodMetricBatchCreate(BaseModel):
    """Schema for batch pod metric submission from DaemonSet agent"""
    cluster_id: str = Field(..., description="Cluster UUID")
    node_name: str = Field(..., description="Node where DaemonSet pod is running")
    timestamp: Optional[datetime] = Field(default_factory=datetime.utcnow, description="Collection timestamp")
    metrics: List[PodMetricCreate] = Field(..., description="List of pod metrics from this node")

    class Config:
        json_schema_extra = {
            "example": {
                "cluster_id": "abc-123-def-456",
                "node_name": "ip-10-0-1-123.ec2.internal",
                "timestamp": "2026-02-16T10:30:00Z",
                "metrics": [
                    {
                        "namespace": "default",
                        "pod_name": "nginx-7d4c5b7f9d-abc12",
                        "node_name": "ip-10-0-1-123.ec2.internal",
                        "controller_kind": "Deployment",
                        "controller_name": "nginx",
                        "cpu_usage_millicores": 125,
                        "memory_usage_bytes": 134217728
                    }
                ]
            }
        }


class PodMetricResponse(BaseModel):
    """Schema for pod metric API responses"""
    id: str
    cluster_id: str
    namespace: str
    pod_name: str
    node_name: str
    controller_kind: Optional[str]
    controller_name: Optional[str]

    cpu_usage_millicores: int
    cpu_request_millicores: Optional[int]
    cpu_limit_millicores: Optional[int]
    cpu_utilization_pct: Optional[float]

    memory_usage_bytes: int
    memory_request_bytes: Optional[int]
    memory_limit_bytes: Optional[int]
    memory_utilization_pct: Optional[float]

    container_count: int
    timestamp: datetime
    metadata: Optional[Dict[str, Any]]

    class Config:
        from_attributes = True


class PodMetricQueryParams(BaseModel):
    """Query parameters for fetching pod metrics"""
    cluster_id: Optional[str] = None
    namespace: Optional[str] = None
    controller_name: Optional[str] = None
    node_name: Optional[str] = None
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    limit: int = Field(100, le=1000, description="Max records to return")
    offset: int = Field(0, ge=0, description="Offset for pagination")


class PodMetricBatchResponse(BaseModel):
    """Response for batch pod metric submission"""
    status: str = Field(..., description="success or error")
    metrics_inserted: int = Field(0, description="Number of metrics successfully inserted")
    errors: List[str] = Field(default_factory=list, description="List of errors encountered")
    message: str = Field(..., description="Human-readable message")

    class Config:
        json_schema_extra = {
            "example": {
                "status": "success",
                "metrics_inserted": 25,
                "errors": [],
                "message": "Successfully inserted 25 pod metrics"
            }
        }


class RightSizingRecommendation(BaseModel):
    """Right-sizing recommendation for a workload"""
    cluster_id: str
    namespace: str
    controller_kind: str
    controller_name: str

    # Current configuration
    current_cpu_request_millicores: Optional[int]
    current_memory_request_mb: Optional[int]
    current_replica_count: int

    # Usage statistics (from pod metrics)
    cpu_p95_millicores: int = Field(..., description="95th percentile CPU usage")
    cpu_p99_millicores: int = Field(..., description="99th percentile CPU usage")
    memory_p95_mb: int = Field(..., description="95th percentile memory usage")
    memory_p99_mb: int = Field(..., description="99th percentile memory usage")

    cpu_avg_millicores: int = Field(..., description="Average CPU usage")
    memory_avg_mb: int = Field(..., description="Average memory usage")

    # Recommendations
    recommended_cpu_request_millicores: int = Field(..., description="Recommended CPU request (P95 + 20% buffer)")
    recommended_memory_request_mb: int = Field(..., description="Recommended memory request (P95 + 20% buffer)")

    # Potential savings
    current_cost_monthly: float = Field(..., description="Current monthly cost (estimated)")
    recommended_cost_monthly: float = Field(..., description="Recommended monthly cost (estimated)")
    savings_monthly: float = Field(..., description="Potential monthly savings")
    savings_pct: float = Field(..., description="Savings percentage")

    # Analysis metadata
    data_points: int = Field(..., description="Number of metric data points analyzed")
    analysis_window_hours: int = Field(..., description="Time window analyzed (hours)")
    confidence: str = Field(..., description="Confidence level (HIGH, MEDIUM, LOW)")

    # Safety flags
    is_oversized: bool = Field(False, description="Current requests significantly exceed usage")
    is_undersized: bool = Field(False, description="Current requests below P99 usage (risky)")
    recommendation_action: str = Field(..., description="REDUCE, INCREASE, NO_CHANGE")

    class Config:
        json_schema_extra = {
            "example": {
                "cluster_id": "abc-123",
                "namespace": "production",
                "controller_kind": "Deployment",
                "controller_name": "api-server",
                "current_cpu_request_millicores": 500,
                "current_memory_request_mb": 512,
                "current_replica_count": 3,
                "cpu_p95_millicores": 250,
                "cpu_p99_millicores": 300,
                "memory_p95_mb": 256,
                "memory_p99_mb": 300,
                "cpu_avg_millicores": 150,
                "memory_avg_mb": 200,
                "recommended_cpu_request_millicores": 300,
                "recommended_memory_request_mb": 307,
                "current_cost_monthly": 45.00,
                "recommended_cost_monthly": 27.00,
                "savings_monthly": 18.00,
                "savings_pct": 40.0,
                "data_points": 2016,
                "analysis_window_hours": 168,
                "confidence": "HIGH",
                "is_oversized": True,
                "is_undersized": False,
                "recommendation_action": "REDUCE"
            }
        }
