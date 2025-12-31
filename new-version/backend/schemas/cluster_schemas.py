"""
Cluster Schemas - Request/Response models for cluster management
"""
from pydantic import BaseModel, Field, field_validator
from typing import Optional, List, Dict, Any
from datetime import datetime


class ClusterListItem(BaseModel):
    """Single cluster in list view"""
    id: str = Field(..., description="Cluster UUID")
    name: str = Field(..., description="Cluster name")
    region: str = Field(..., description="AWS region")
    status: str = Field(..., description="Cluster status (PENDING, ACTIVE, INACTIVE, ERROR)")
    node_count: int = Field(..., ge=0, description="Total number of nodes")
    spot_count: int = Field(..., ge=0, description="Number of spot instances")
    monthly_cost: float = Field(..., ge=0, description="Estimated monthly cost in USD")
    agent_installed: bool = Field(..., description="Whether Kubernetes Agent is installed")
    last_heartbeat: Optional[datetime] = Field(None, description="Last agent heartbeat timestamp")

    model_config = {
        "json_schema_extra": {
            "example": {
                "id": "550e8400-e29b-41d4-a716-446655440000",
                "name": "production-eks",
                "region": "us-east-1",
                "status": "ACTIVE",
                "node_count": 15,
                "spot_count": 10,
                "monthly_cost": 1250.50,
                "agent_installed": True,
                "last_heartbeat": "2025-12-31T12:00:00Z"
            }
        }
    }


class ClusterList(BaseModel):
    """List of clusters"""
    clusters: List[ClusterListItem] = Field(..., description="Array of clusters")
    total: int = Field(..., ge=0, description="Total number of clusters")

    model_config = {
        "json_schema_extra": {
            "example": {
                "clusters": [
                    {
                        "id": "550e8400-e29b-41d4-a716-446655440000",
                        "name": "production-eks",
                        "region": "us-east-1",
                        "status": "ACTIVE",
                        "node_count": 15,
                        "spot_count": 10,
                        "monthly_cost": 1250.50,
                        "agent_installed": True,
                        "last_heartbeat": "2025-12-31T12:00:00Z"
                    }
                ],
                "total": 1
            }
        }
    }


class InstanceInfo(BaseModel):
    """Instance information"""
    id: str = Field(..., description="Instance UUID")
    instance_id: str = Field(..., description="AWS instance ID (e.g., i-0abc123)")
    instance_type: str = Field(..., description="EC2 instance type (e.g., m5.large)")
    lifecycle: str = Field(..., description="Instance lifecycle (SPOT or ON_DEMAND)")
    az: str = Field(..., description="Availability zone")
    price: Optional[float] = Field(None, ge=0, description="Hourly price in USD")
    cpu_util: Optional[float] = Field(None, ge=0, le=100, description="CPU utilization percentage")
    memory_util: Optional[float] = Field(None, ge=0, le=100, description="Memory utilization percentage")

    model_config = {
        "json_schema_extra": {
            "example": {
                "id": "660e9500-f30c-52e5-b827-557766551111",
                "instance_id": "i-0abc12345def67890",
                "instance_type": "m5.xlarge",
                "lifecycle": "SPOT",
                "az": "us-east-1a",
                "price": 0.083,
                "cpu_util": 45.2,
                "memory_util": 62.8
            }
        }
    }


class ClusterDetail(BaseModel):
    """Detailed cluster information"""
    id: str = Field(..., description="Cluster UUID")
    name: str = Field(..., description="Cluster name")
    region: str = Field(..., description="AWS region")
    vpc_id: Optional[str] = Field(None, description="VPC ID")
    api_endpoint: Optional[str] = Field(None, description="Kubernetes API endpoint")
    k8s_version: Optional[str] = Field(None, description="Kubernetes version")
    status: str = Field(..., description="Cluster status")
    agent_installed: bool = Field(..., description="Whether Agent is installed")
    last_heartbeat: Optional[datetime] = Field(None, description="Last heartbeat timestamp")
    instances: List[InstanceInfo] = Field(default_factory=list, description="List of instances")
    created_at: datetime = Field(..., description="Creation timestamp")

    model_config = {
        "json_schema_extra": {
            "example": {
                "id": "550e8400-e29b-41d4-a716-446655440000",
                "name": "production-eks",
                "region": "us-east-1",
                "vpc_id": "vpc-0abc123",
                "api_endpoint": "https://ABC123.gr7.us-east-1.eks.amazonaws.com",
                "k8s_version": "1.28",
                "status": "ACTIVE",
                "agent_installed": True,
                "last_heartbeat": "2025-12-31T12:00:00Z",
                "instances": [],
                "created_at": "2025-12-30T10:00:00Z"
            }
        }
    }


class HeartbeatRequest(BaseModel):
    """Agent heartbeat request"""
    cluster_id: str = Field(..., description="Cluster UUID")
    agent_version: str = Field(..., description="Agent version (e.g., v1.0.0)")
    node_count: int = Field(..., ge=0, description="Number of nodes in cluster")
    metrics: Optional[Dict[str, Any]] = Field(None, description="Optional metrics payload")

    model_config = {
        "json_schema_extra": {
            "example": {
                "cluster_id": "550e8400-e29b-41d4-a716-446655440000",
                "agent_version": "v1.2.3",
                "node_count": 15,
                "metrics": {
                    "cpu_avg": 45.2,
                    "memory_avg": 62.8
                }
            }
        }
    }


class AgentCommandResponse(BaseModel):
    """Command for Agent to execute"""
    id: str = Field(..., description="Action UUID")
    action_type: str = Field(..., description="Action type (EVICT_POD, CORDON_NODE, etc.)")
    payload: Dict[str, Any] = Field(..., description="Action payload")
    expires_at: datetime = Field(..., description="Command expiration time")

    model_config = {
        "json_schema_extra": {
            "example": {
                "id": "770e8400-e29b-41d4-a716-446655440000",
                "action_type": "EVICT_POD",
                "payload": {
                    "pod_name": "app-xyz-123",
                    "namespace": "production",
                    "grace_period": 30
                },
                "expires_at": "2025-12-31T13:00:00Z"
            }
        }
    }


class AgentCommandList(BaseModel):
    """List of commands for Agent"""
    commands: List[AgentCommandResponse] = Field(..., description="Array of pending commands")

    model_config = {
        "json_schema_extra": {
            "example": {
                "commands": [
                    {
                        "id": "770e8400-e29b-41d4-a716-446655440000",
                        "action_type": "EVICT_POD",
                        "payload": {"pod_name": "app-xyz-123", "namespace": "production"},
                        "expires_at": "2025-12-31T13:00:00Z"
                    }
                ]
            }
        }
    }


class AgentCommandResult(BaseModel):
    """Agent command execution result"""
    action_id: str = Field(..., description="Action UUID")
    status: str = Field(..., description="Execution status (COMPLETED or FAILED)")
    result: Optional[Dict[str, Any]] = Field(None, description="Result payload for success")
    error_message: Optional[str] = Field(None, description="Error message for failures")

    @field_validator('status')
    @classmethod
    def validate_status(cls, v: str) -> str:
        if v not in ['COMPLETED', 'FAILED']:
            raise ValueError('Status must be COMPLETED or FAILED')
        return v

    model_config = {
        "json_schema_extra": {
            "example": {
                "action_id": "770e8400-e29b-41d4-a716-446655440000",
                "status": "COMPLETED",
                "result": {"evicted_at": "2025-12-31T12:05:00Z"},
                "error_message": None
            }
        }
    }


class OptimizationJobId(BaseModel):
    """Optimization job ID response"""
    job_id: str = Field(..., description="Optimization job UUID")
    status: str = Field(..., description="Job status (QUEUED, RUNNING, COMPLETED, FAILED)")

    model_config = {
        "json_schema_extra": {
            "example": {
                "job_id": "880e8400-e29b-41d4-a716-446655440000",
                "status": "QUEUED"
            }
        }
    }


class OptimizationJobResult(BaseModel):
    """Optimization job result"""
    job_id: str = Field(..., description="Job UUID")
    cluster_id: str = Field(..., description="Cluster UUID")
    status: str = Field(..., description="Job status")
    results: Optional[Dict[str, Any]] = Field(None, description="Optimization results")
    created_at: datetime = Field(..., description="Job creation timestamp")
    completed_at: Optional[datetime] = Field(None, description="Job completion timestamp")

    model_config = {
        "json_schema_extra": {
            "example": {
                "job_id": "880e8400-e29b-41d4-a716-446655440000",
                "cluster_id": "550e8400-e29b-41d4-a716-446655440000",
                "status": "COMPLETED",
                "results": {
                    "recommended_changes": 5,
                    "estimated_savings": 450.25
                },
                "created_at": "2025-12-31T12:00:00Z",
                "completed_at": "2025-12-31T12:05:00Z"
            }
        }
    }
