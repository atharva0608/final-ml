"""
Cluster Schemas - Request/Response models for cluster management
"""
from pydantic import BaseModel, Field, field_validator, field_serializer
from typing import Optional, List, Dict, Any
from datetime import datetime


class ClusterListItem(BaseModel):
    """Single cluster in list view"""
    id: str = Field(..., description="Cluster UUID")
    cluster_uid: Optional[str] = Field(None, description="Short unique display ID (8-char hex)")
    name: str = Field(..., description="Cluster name")
    region: str = Field(..., description="AWS region")
    status: str = Field(..., description="Cluster status (PENDING, ACTIVE, INACTIVE, ERROR)")
    node_count: int = Field(..., ge=0, description="Total number of nodes")
    spot_count: int = Field(..., ge=0, description="Number of spot instances")
    monthly_cost: float = Field(..., ge=0, description="Estimated monthly cost in USD")
    agent_installed: bool = Field(..., description="Whether Kubernetes Agent is installed")
    last_heartbeat: Optional[datetime] = Field(None, description="Last agent heartbeat timestamp")

    # Teaser Fields
    potential_savings_monthly: float = Field(0.0, ge=0, description="Potential savings IF we switch ON_DEMAND to SPOT")
    realized_savings_monthly: float = Field(0.0, ge=0, description="Realized savings we're ALREADY getting from SPOT instances")
    on_demand_node_count: int = Field(0, ge=0, description="Count of On-Demand nodes")
    estimated_savings: float = Field(0.0, ge=0, description="Legacy field - use realized_savings_monthly instead")
    cpu_total: int = Field(0, ge=0, description="Total CPU cores across all nodes")
    mem_total: int = Field(0, ge=0, description="Total memory in GiB across all nodes")
    cpu_usage_pct: float = Field(0.0, ge=0, le=100, description="CPU usage percentage")
    mem_usage_pct: float = Field(0.0, ge=0, le=100, description="Memory usage percentage")

    # Auto-rebalancing
    auto_rebalance_enabled: bool = Field(False, description="Auto on-demand→spot rebalancing enabled")
    rightsizing_enabled: bool = Field(False, description="Right-sizing enabled")

    @field_serializer('last_heartbeat')
    def serialize_heartbeat(self, dt: Optional[datetime], _info):
        """Serialize datetime with UTC timezone indicator"""
        if dt is None:
            return None
        # Ensure ISO format with 'Z' suffix for UTC
        iso_str = dt.isoformat()
        if not iso_str.endswith('Z') and '+' not in iso_str:
            iso_str += 'Z'
        return iso_str

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


class AWSConnectRequest(BaseModel):
    """Request to connect cluster via AWS STS"""
    name: str = Field(..., description="Cluster name")
    region: str = Field(..., description="AWS region")
    role_arn: str = Field(..., description="AWS IAM Role ARN to assume")
    external_id: str = Field(..., description="External ID for security")

    model_config = {
        "json_schema_extra": {
            "example": {
                "name": "production-eks",
                "region": "us-east-1",
                "role_arn": "arn:aws:iam::123456789012:role/SpotOptimizerMonitoring",
                "external_id": "spot-optimizer-123"
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

class ClusterFilter(BaseModel):
    """Filter criteria for listing clusters"""
    account_id: Optional[str] = Field(None, description="Filter by account ID")
    region: Optional[str] = Field(None, description="Filter by AWS region")
    cluster_type: Optional[str] = Field(None, description="Filter by cluster type")
    status: Optional[str] = Field(None, description="Filter by status")
    search: Optional[str] = Field(None, description="Search by name or ARN")
    page: int = Field(default=1, ge=1, description="Page number")
    page_size: int = Field(default=20, ge=1, le=100, description="Items per page")


class ClusterCreate(BaseModel):
    """Schema for creating a new cluster"""
    account_id: str = Field(..., description="Account UUID")
    name: str = Field(..., min_length=1, max_length=255, description="Cluster name")
    arn: str = Field(..., description="AWS ARN")
    region: str = Field(..., description="AWS region")
    cluster_type: str = Field(..., description="Cluster type (EKS, ECS, EMR, etc.)")
    version: Optional[str] = Field(None, description="Cluster version")
    endpoint: Optional[str] = Field(None, description="API endpoint")
    tags: Optional[Dict[str, str]] = Field(default_factory=dict, description="Resource tags")


class ClusterUpdate(BaseModel):
    """Schema for updating cluster details"""
    name: Optional[str] = Field(None, min_length=1, max_length=255, description="Cluster name")
    tags: Optional[Dict[str, str]] = Field(None, description="Resource tags")
    status: Optional[str] = Field(None, description="Cluster status")
    auto_rebalance_enabled: Optional[bool] = Field(None, description="Auto-rebalance toggle")
    rightsizing_enabled: Optional[bool] = Field(None, description="Right-sizing toggle")


class ClusterResponse(BaseModel):
    """Schema for cluster response"""
    id: str = Field(..., description="Cluster UUID")
    cluster_uid: Optional[str] = Field(None, description="Short unique display ID (8-char hex)")
    account_id: str = Field(..., description="Account UUID")
    name: str = Field(..., description="Cluster name")
    arn: str = Field(..., description="AWS ARN")
    region: str = Field(..., description="AWS region")
    cluster_type: str = Field(..., description="Cluster type")
    version: Optional[str] = Field(None, description="Cluster version")
    endpoint: Optional[str] = Field(None, description="API endpoint")
    status: str = Field(..., description="Cluster status")
    agent_installed: Optional[str] = Field(None, description="Agent installation status (Y/N)")
    is_agentless: Optional[str] = Field(None, description="Agentless mode (Y/N)")
    last_heartbeat: Optional[datetime] = Field(None, description="Last heartbeat timestamp")
    tags: Optional[Dict[str, str]] = Field(default_factory=dict, description="Resource tags")
    created_at: datetime = Field(..., description="Creation timestamp")
    updated_at: datetime = Field(..., description="Last update timestamp")

    # Financial fields
    monthly_cost: float = Field(0.0, description="Monthly compute cost")
    estimated_savings: float = Field(0.0, description="Estimated potential savings")
    realized_savings_monthly: float = Field(0.0, description="Realized savings from spot")
    potential_savings_monthly: float = Field(0.0, description="Potential savings")

    # Node counts
    node_count: int = Field(0, description="Total node count")
    spot_count: int = Field(0, description="Spot instance count")
    on_demand_node_count: int = Field(0, description="OD Node Count")
    inventory_summary: Optional[Dict[str, Any]] = Field(default_factory=dict, description="Inventory breakdown")

    # Auto-rebalancing
    auto_rebalance_enabled: bool = Field(False, description="Auto on-demand→spot rebalancing enabled")
    rightsizing_enabled: bool = Field(False, description="Right-sizing enabled")

    # Migration tracking
    managed_node_group_deleted: bool = Field(False, description="True when original managed node group has been deleted")


class AgentInstallCommand(BaseModel):
    """Agent installation command and script"""
    cluster_id: str = Field(..., description="Cluster UUID")
    install_command: str = Field(..., description="kubectl apply command")
    yaml_manifest: str = Field(..., description="Full YAML manifest content")
    instructions: List[str] = Field(..., description="Step-by-step installation instructions")

class InstallScriptRequest(BaseModel):
    """Request to generate install script for a new cluster"""
    provider: str = Field(..., description="K8s provider (eks, aks, etc.)")
    cluster_name: str = Field(..., description="Cluster name")
    region: Optional[str] = Field(None, description="AWS region (defaults to us-east-1)")

class InstallScriptResponse(BaseModel):
    """Response with install script and cluster ID"""
    cluster_id: str = Field(..., description="Cluster UUID")
    script: str = Field(..., description="Installation script/command")
    api_key: Optional[str] = Field(None, description="Auto-generated API key for agent auth")

# --- Unified Optimization Config Schemas ---

class AutomationControlsSchema(BaseModel):
    auto_rebalance_enabled: bool = False
    auto_rightsizing_enabled: bool = False
    instance_aware_rightsizing: bool = False
    cooldown_override_minutes: Optional[int] = None
    # spot_join_timeout_minutes removed — Karpenter manages node readiness timing

    manual_approval_required: bool = False
    target_spot_exposure_pct: int = 100
    
    maintain_standby: bool = False
    diversify_pools: bool = False
    max_family_diversification_cap_pct: int = 40
    instance_type_diversification_pct: int = 100
    failure_cooldown_minutes: int = 30
    min_node_count: int = 1
    scale_down_threshold_pct: int = 20
    scale_down_stabilization_minutes: int = 15
    enable_ascp_auto_scaler: bool = False
    check_interval_seconds: int = 15
    architecture_preference: str = "both"  # "both", "amd64", or "arm64"
    rebalance_batch_percent: Optional[int] = None  # None = auto (PDB-safe or 15%)
    karpenter_only_mode: bool = False  # When True, rebalancer skips all ASG code paths
    min_topology_spread: int = 1  # Min nodes across AZs during rightsizing consolidation (1-5)

class OptimizationStrategySchema(BaseModel):
    strategy_type: str = "BALANCED"
    risk_ceiling_percent: int = 25
    min_savings_percent: int = 15
    volatility_tolerance_percent: int = 20
    migration_penalty_multiplier: float = 1.5
    diversity_strictness_level: str = "Medium"
    risk_savings_tradeoff_pct: int = 20

class StatelessRulesSchema(BaseModel):
    instance_diversification_enabled: bool = True
    respect_pdb_enabled: bool = True
    prewarm_minutes: int = 0
    substitute_strategy: str = "PREWARMED"
    max_rebalances_per_24h: int = 5
    resize_cooldown_minutes: int = 120
    resize_headroom_multiplier: float = 1.2
    volatility_safety_multiplier: float = 1.35
    fresh_cluster_stabilization_minutes: int = 1440

class StatefulRulesSchema(BaseModel):
    manual_resize_allowed: bool = True
    require_approval: bool = True
    block_spot_for_stateful: bool = True
    max_downscale_percent: int = 25

class UnifiedOptimizationSettings(BaseModel):
    # All sections are optional so callers can do partial updates
    # (e.g. ClusterList only sends automation_controls — the rest are preserved)
    automation_controls: Optional[AutomationControlsSchema] = None
    optimization_strategy: Optional[OptimizationStrategySchema] = None
    stateless_rules: Optional[StatelessRulesSchema] = None
    stateful_rules: Optional[StatefulRulesSchema] = None
    # Read-only computed field: max safe batch % based on PDBs (None = no PDBs found)
    pdb_safe_percent: Optional[int] = None
