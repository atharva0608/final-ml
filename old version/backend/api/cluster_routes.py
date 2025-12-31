"""
Kubernetes Cluster Management API Routes

Provides endpoints for managing Kubernetes cluster connections,
monitoring, optimization, and lifecycle operations.
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy import func
from typing import List, Optional
from pydantic import BaseModel, Field
from datetime import datetime
import uuid

from backend.database import get_db
from backend.database.models import (
    Cluster, ClusterStatus, OptimizationPolicy, HibernationSchedule,
    AutoscalerPolicy, AuditLog, User
)
from backend.api.auth import get_current_user

router = APIRouter(prefix="/v1/client/clusters", tags=["clusters"])


# ============================================================================
# Pydantic Models (Request/Response schemas)
# ============================================================================

class ClusterCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    provider: str = Field(..., description="AWS EKS, GCP GKE, or Azure AKS")
    region: str
    version: Optional[str] = None
    account_id: Optional[str] = None


class ClusterUpdate(BaseModel):
    name: Optional[str] = None
    status: Optional[str] = None
    total_nodes: Optional[int] = None
    spot_nodes: Optional[int] = None
    on_demand_nodes: Optional[int] = None
    fallback_nodes: Optional[int] = None
    platform_managed_nodes: Optional[int] = None
    cloud_managed_nodes: Optional[int] = None
    total_cpu: Optional[int] = None
    total_memory: Optional[int] = None
    total_storage: Optional[int] = None
    total_pods: Optional[int] = None
    scheduled_pods: Optional[int] = None
    pending_pods: Optional[int] = None
    monthly_cost: Optional[float] = None


class ClusterResponse(BaseModel):
    id: str
    name: str
    provider: str
    region: str
    version: Optional[str]
    status: str
    total_nodes: int
    spot_nodes: int
    on_demand_nodes: int
    fallback_nodes: int
    platform_managed_nodes: int
    cloud_managed_nodes: int
    total_cpu: int
    total_memory: int
    monthly_cost: float
    created_at: datetime
    connected_at: Optional[datetime]

    class Config:
        from_attributes = True


class DashboardMetrics(BaseModel):
    cluster: dict
    nodes: dict
    workloads: dict
    autoscaler: dict
    hibernation: dict
    resources: dict


# ============================================================================
# Helper Functions
# ============================================================================

def log_audit_event(
    db: Session,
    user_id: str,
    cluster_id: Optional[str],
    operation: str,
    details: dict,
    ip_address: Optional[str] = None
):
    """Create an audit log entry"""
    audit_log = AuditLog(
        user_id=uuid.UUID(user_id),
        cluster_id=uuid.UUID(cluster_id) if cluster_id else None,
        operation=operation,
        initiated_by=details.get('user_email', 'system'),
        details=details,
        ip_address=ip_address
    )
    db.add(audit_log)
    db.commit()


# ============================================================================
# Cluster CRUD Endpoints
# ============================================================================

@router.get("", response_model=List[ClusterResponse])
async def list_clusters(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Get all clusters for the current user
    """
    clusters = db.query(Cluster).filter(
        Cluster.user_id == current_user.id,
        Cluster.status != ClusterStatus.REMOVED.value
    ).order_by(Cluster.created_at.desc()).all()

    return clusters


@router.post("", response_model=ClusterResponse, status_code=status.HTTP_201_CREATED)
async def create_cluster(
    cluster_data: ClusterCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Create a new cluster connection

    This creates a pending cluster record. The cluster agent
    must be installed in the Kubernetes cluster to complete the connection.
    """
    # Check for duplicate cluster name
    existing = db.query(Cluster).filter(
        Cluster.user_id == current_user.id,
        Cluster.name == cluster_data.name,
        Cluster.status != ClusterStatus.REMOVED.value
    ).first()

    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Cluster with name '{cluster_data.name}' already exists"
        )

    # Generate agent token
    agent_token = f"agent_{uuid.uuid4().hex}"

    # Create cluster
    cluster = Cluster(
        user_id=current_user.id,
        account_id=uuid.UUID(cluster_data.account_id) if cluster_data.account_id else None,
        name=cluster_data.name,
        provider=cluster_data.provider,
        region=cluster_data.region,
        version=cluster_data.version,
        status=ClusterStatus.PENDING.value,
        agent_token=agent_token
    )

    db.add(cluster)
    db.commit()
    db.refresh(cluster)

    # Create default autoscaler policies
    default_policies = [
        {"name": "Unscheduled Pods", "enabled": True, "add_nodes_for_unschedulable_pods": True},
        {"name": "Node Deletion", "enabled": True, "remove_idle_nodes": True, "node_ttl_seconds": 300},
        {"name": "Evictor", "enabled": False, "compact_pods": False}
    ]

    for policy_data in default_policies:
        policy = AutoscalerPolicy(
            cluster_id=cluster.id,
            policy_name=policy_data["name"],
            enabled=policy_data["enabled"],
            **{k: v for k, v in policy_data.items() if k not in ["name", "enabled"]}
        )
        db.add(policy)

    # Create default optimization policy
    opt_policy = OptimizationPolicy(
        cluster_id=cluster.id,
        rightsizing_enabled=False,
        spot_instances_enabled=False,
        arm_enabled=False
    )
    db.add(opt_policy)

    db.commit()

    # Log audit event
    log_audit_event(
        db, str(current_user.id), str(cluster.id),
        "cluster_created",
        {
            "user_email": current_user.email,
            "cluster_name": cluster.name,
            "provider": cluster.provider,
            "region": cluster.region
        }
    )

    return cluster


@router.get("/{cluster_id}", response_model=ClusterResponse)
async def get_cluster(
    cluster_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Get a specific cluster by ID
    """
    try:
        cluster_uuid = uuid.UUID(cluster_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid cluster ID format"
        )

    cluster = db.query(Cluster).filter(
        Cluster.id == cluster_uuid,
        Cluster.user_id == current_user.id
    ).first()

    if not cluster:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Cluster not found"
        )

    return cluster


@router.delete("/{cluster_id}")
async def disconnect_cluster(
    cluster_id: str,
    delete_nodes: bool = False,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Disconnect a cluster

    Args:
        cluster_id: Cluster UUID
        delete_nodes: If True, delete all platform-managed nodes
    """
    try:
        cluster_uuid = uuid.UUID(cluster_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid cluster ID format"
        )

    cluster = db.query(Cluster).filter(
        Cluster.id == cluster_uuid,
        Cluster.user_id == current_user.id
    ).first()

    if not cluster:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Cluster not found"
        )

    # Update cluster status
    cluster.status = ClusterStatus.REMOVING.value
    cluster.disconnected_at = datetime.utcnow()

    # Log audit event
    log_audit_event(
        db, str(current_user.id), str(cluster.id),
        "cluster_disconnect",
        {
            "user_email": current_user.email,
            "cluster_name": cluster.name,
            "delete_nodes": delete_nodes
        }
    )

    db.commit()

    # TODO: Trigger background worker to:
    # 1. Gracefully drain workloads from platform-managed nodes (if delete_nodes=True)
    # 2. Delete platform-managed nodes (if delete_nodes=True)
    # 3. Disconnect agent
    # 4. Update status to REMOVED

    return {
        "success": True,
        "message": f"Cluster '{cluster.name}' disconnection initiated",
        "cluster_id": str(cluster.id),
        "status": cluster.status
    }


@router.get("/{cluster_id}/dashboard", response_model=DashboardMetrics)
async def get_cluster_dashboard(
    cluster_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Get comprehensive dashboard metrics for a cluster
    """
    try:
        cluster_uuid = uuid.UUID(cluster_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid cluster ID format"
        )

    cluster = db.query(Cluster).filter(
        Cluster.id == cluster_uuid,
        Cluster.user_id == current_user.id
    ).first()

    if not cluster:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Cluster not found"
        )

    # Get optimization policy
    opt_policy = db.query(OptimizationPolicy).filter(
        OptimizationPolicy.cluster_id == cluster.id
    ).first()

    # Get autoscaler policies
    autoscaler_policies = db.query(AutoscalerPolicy).filter(
        AutoscalerPolicy.cluster_id == cluster.id
    ).all()

    # Get hibernation schedules
    hibernation_schedules = db.query(HibernationSchedule).filter(
        HibernationSchedule.cluster_id == cluster.id
    ).all()

    # Calculate resource utilization (mock for now)
    cpu_utilization = int((cluster.total_cpu * 0.67)) if cluster.total_cpu else 0
    memory_utilization = int((cluster.total_memory * 0.72)) if cluster.total_memory else 0
    storage_utilization = int((cluster.total_storage * 0.45)) if cluster.total_storage else 0

    return {
        "cluster": {
            "id": str(cluster.id),
            "name": cluster.name,
            "status": cluster.status,
            "provider": cluster.provider,
            "region": cluster.region,
            "version": cluster.version,
            "createdAt": cluster.created_at.isoformat() if cluster.created_at else None
        },
        "nodes": {
            "total": cluster.total_nodes,
            "onDemand": cluster.on_demand_nodes,
            "spot": cluster.spot_nodes,
            "fallback": cluster.fallback_nodes,
            "platformManaged": cluster.platform_managed_nodes,
            "cloudManaged": cluster.cloud_managed_nodes,
            "totalCpu": cluster.total_cpu,
            "totalMemory": cluster.total_memory,
            "cpuUtilization": min(100, max(0, int((cpu_utilization / cluster.total_cpu * 100) if cluster.total_cpu else 0))),
            "memoryUtilization": min(100, max(0, int((memory_utilization / cluster.total_memory * 100) if cluster.total_memory else 0))),
            "storageUtilization": min(100, max(0, int((storage_utilization / cluster.total_storage * 100) if cluster.total_storage else 0)))
        },
        "workloads": {
            "totalPods": cluster.total_pods,
            "scheduledPods": cluster.scheduled_pods,
            "pendingPods": cluster.pending_pods,
            "deployments": 0,  # TODO: Add workload tracking
            "statefulSets": 0,
            "daemonSets": 0
        },
        "autoscaler": {
            "enabled": any(p.enabled for p in autoscaler_policies),
            "totalPolicies": len(autoscaler_policies),
            "enabledPolicies": sum(1 for p in autoscaler_policies if p.enabled),
            "policies": [
                {
                    "name": p.policy_name,
                    "enabled": p.enabled
                }
                for p in autoscaler_policies
            ]
        },
        "hibernation": {
            "totalSchedules": len(hibernation_schedules),
            "activeSchedules": sum(1 for s in hibernation_schedules if s.enabled),
            "schedules": [
                {
                    "name": s.name,
                    "enabled": s.enabled,
                    "nextAction": s.next_action_time.isoformat() if s.next_action_time else None
                }
                for s in hibernation_schedules
            ]
        },
        "resources": {
            "cpu": {
                "total": cluster.total_cpu,
                "used": cpu_utilization,
                "available": cluster.total_cpu - cpu_utilization if cluster.total_cpu else 0,
                "utilization": min(100, max(0, int((cpu_utilization / cluster.total_cpu * 100) if cluster.total_cpu else 0)))
            },
            "memory": {
                "total": cluster.total_memory,
                "used": memory_utilization,
                "available": cluster.total_memory - memory_utilization if cluster.total_memory else 0,
                "utilization": min(100, max(0, int((memory_utilization / cluster.total_memory * 100) if cluster.total_memory else 0)))
            },
            "storage": {
                "total": cluster.total_storage if cluster.total_storage else 0,
                "used": storage_utilization,
                "available": (cluster.total_storage - storage_utilization) if cluster.total_storage else 0,
                "utilization": min(100, max(0, int((storage_utilization / cluster.total_storage * 100) if cluster.total_storage else 0)))
            }
        }
    }
