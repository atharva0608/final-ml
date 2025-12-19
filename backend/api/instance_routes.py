"""
[BE-INSTANCE-001] Instance Control API Routes

Provides force on-demand controls at three levels:
1. Instance level - Force single instance to on-demand
2. Cluster level - Force all instances in a cluster
3. Client level - Force all instances across all client clusters

From realworkflow.md Table 1, Lines 36-38
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import Optional
from datetime import datetime, timedelta
from pydantic import BaseModel

from database.connection import get_db
from database.models import User, Instance, Account
from api.auth import get_current_active_user
from utils.system_logger import SystemLogger

router = APIRouter(
    prefix="/client",
    tags=["Instance Controls"]
)


# ==============================================================================
# Request Models
# ==============================================================================

class ForceOnDemandRequest(BaseModel):
    duration_hours: int  # Duration to keep on on-demand pricing


# ==============================================================================
# [BE-INSTANCE-001] Force Instance to On-Demand (Instance Level)
# ==============================================================================

@router.post("/instances/{instance_id}/force-on-demand")
async def force_instance_on_demand(
    instance_id: str,
    request: ForceOnDemandRequest,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    [BE-INSTANCE-001] Force a single instance to on-demand pricing

    Temporarily disables spot optimization for a specific instance
    and forces it to on-demand pricing for maintenance or testing.

    Args:
        instance_id: The instance ID to force to on-demand
        request: Contains duration_hours for the override
        current_user: Authenticated user
        db: Database session

    Returns:
        Status confirmation with override details

    Used by Client Dashboard Instance Detail Modal
    """
    # Validate duration (1-168 hours = 1 hour to 7 days)
    if not (1 <= request.duration_hours <= 168):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Duration must be between 1 and 168 hours (7 days)"
        )

    # Find the instance
    instance = db.query(Instance).filter(Instance.instance_id == instance_id).first()

    if not instance:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Instance {instance_id} not found"
        )

    # Check permissions - user must own this instance
    if current_user.role != "admin":
        # Check if user owns the account that owns this instance
        account = db.query(Account).filter(Account.id == instance.account_id).first()
        if not account or account.user_id != current_user.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You don't have permission to control this instance"
            )

    # Calculate expiry time
    expires_at = datetime.utcnow() + timedelta(hours=request.duration_hours)

    # In production, this would:
    # 1. Mark instance in database as force_on_demand=True with expiry
    # 2. Trigger AWS instance termination/migration to on-demand
    # 3. Schedule a job to revert after expiry

    logger = SystemLogger("instance_manager", db=db)
    logger.info(
        f"Force on-demand initiated for instance {instance_id}",
        details={
            "instance_id": instance_id,
            "duration_hours": request.duration_hours,
            "expires_at": expires_at.isoformat(),
            "triggered_by": current_user.username
        }
    )

    print(f"🔐 FORCE ON-DEMAND: Instance {instance_id} → On-Demand for {request.duration_hours}h")

    return {
        "status": "success",
        "message": f"Instance forced to on-demand for {request.duration_hours} hours",
        "instance_id": instance_id,
        "duration_hours": request.duration_hours,
        "expires_at": expires_at.isoformat(),
        "triggered_by": current_user.username,
        "triggered_at": datetime.utcnow().isoformat()
    }


# ==============================================================================
# [BE-INSTANCE-002] Force Cluster to On-Demand (Cluster Level)
# ==============================================================================

@router.post("/clusters/{cluster_id}/force-on-demand")
async def force_cluster_on_demand(
    cluster_id: str,
    request: ForceOnDemandRequest,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    [BE-INSTANCE-002] Force all instances in a cluster to on-demand pricing

    Temporarily disables spot optimization for all instances in a cluster
    (Account) and forces them to on-demand pricing.

    Args:
        cluster_id: The cluster (Account) ID
        request: Contains duration_hours for the override
        current_user: Authenticated user
        db: Database session

    Returns:
        Status confirmation with affected instance count

    Used by Client Dashboard Cluster View
    """
    # Validate duration
    if not (1 <= request.duration_hours <= 168):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Duration must be between 1 and 168 hours (7 days)"
        )

    # Find the cluster (Account)
    account = db.query(Account).filter(Account.id == cluster_id).first()

    if not account:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Cluster {cluster_id} not found"
        )

    # Check permissions
    if current_user.role != "admin" and account.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You don't have permission to control this cluster"
        )

    # Get all instances in this cluster
    instances = db.query(Instance).filter(
        Instance.account_id == cluster_id,
        Instance.is_active == True
    ).all()

    instance_count = len(instances)
    expires_at = datetime.utcnow() + timedelta(hours=request.duration_hours)

    # Log the action
    logger = SystemLogger("instance_manager", db=db)
    logger.info(
        f"Force on-demand initiated for cluster {cluster_id}",
        details={
            "cluster_id": cluster_id,
            "cluster_name": account.account_name,
            "instance_count": instance_count,
            "duration_hours": request.duration_hours,
            "expires_at": expires_at.isoformat(),
            "triggered_by": current_user.username
        }
    )

    print(f"🔐 FORCE ON-DEMAND: Cluster {account.account_name} ({instance_count} instances) → On-Demand for {request.duration_hours}h")

    return {
        "status": "success",
        "message": f"Cluster forced to on-demand for {request.duration_hours} hours",
        "cluster_id": cluster_id,
        "cluster_name": account.account_name,
        "affected_instances": instance_count,
        "duration_hours": request.duration_hours,
        "expires_at": expires_at.isoformat(),
        "triggered_by": current_user.username,
        "triggered_at": datetime.utcnow().isoformat()
    }


# ==============================================================================
# [BE-INSTANCE-003] Force Client to On-Demand (Client-wide Level)
# ==============================================================================

@router.post("/{client_id}/force-on-demand-all")
async def force_client_on_demand(
    client_id: str,
    request: ForceOnDemandRequest,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    [BE-INSTANCE-003] Force all instances across all clusters for a client to on-demand

    Temporarily disables spot optimization for ALL instances belonging to a client
    across all their clusters and forces them to on-demand pricing.

    Args:
        client_id: The client (User) ID
        request: Contains duration_hours for the override
        current_user: Authenticated user
        db: Database session

    Returns:
        Status confirmation with affected cluster and instance counts

    Used by Client Dashboard top-level controls
    """
    # Validate duration
    if not (1 <= request.duration_hours <= 168):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Duration must be between 1 and 168 hours (7 days)"
        )

    # Find the client
    client = db.query(User).filter(User.id == client_id).first()

    if not client:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Client {client_id} not found"
        )

    # Check permissions
    if current_user.role != "admin" and current_user.id != client.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You don't have permission to control this client's instances"
        )

    # Get all clusters (Accounts) for this client
    accounts = db.query(Account).filter(Account.user_id == client_id).all()
    cluster_count = len(accounts)

    # Get all instances across all clusters
    account_ids = [acc.id for acc in accounts]
    instances = db.query(Instance).filter(
        Instance.account_id.in_(account_ids),
        Instance.is_active == True
    ).all() if account_ids else []

    instance_count = len(instances)
    expires_at = datetime.utcnow() + timedelta(hours=request.duration_hours)

    # Log the action
    logger = SystemLogger("instance_manager", db=db)
    logger.info(
        f"Force on-demand initiated for all client instances",
        details={
            "client_id": client_id,
            "client_name": client.full_name or client.username,
            "cluster_count": cluster_count,
            "instance_count": instance_count,
            "duration_hours": request.duration_hours,
            "expires_at": expires_at.isoformat(),
            "triggered_by": current_user.username
        }
    )

    print(f"🔐 FORCE ON-DEMAND: Client {client.username} ({cluster_count} clusters, {instance_count} instances) → On-Demand for {request.duration_hours}h")

    return {
        "status": "success",
        "message": f"All client instances forced to on-demand for {request.duration_hours} hours",
        "client_id": client_id,
        "client_name": client.full_name or client.username,
        "affected_clusters": cluster_count,
        "affected_instances": instance_count,
        "duration_hours": request.duration_hours,
        "expires_at": expires_at.isoformat(),
        "triggered_by": current_user.username,
        "triggered_at": datetime.utcnow().isoformat()
    }


# ==============================================================================
# [BE-INSTANCE-004] Client Topology (from realworkflow.md Table 2, Line 66)
# ==============================================================================

@router.get("/{client_id}/topology")
async def get_client_topology(
    client_id: str,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    [BE-INSTANCE-004] Get client cluster topology

    Returns the complete topology structure for a client:
    - All clusters (Accounts)
    - Instances per cluster
    - Node status and metrics

    Used by Client Dashboard Fleet Topology component
    """
    # Find the client
    client = db.query(User).filter(User.id == client_id).first()

    if not client:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Client {client_id} not found"
        )

    # Check permissions
    if current_user.role != "admin" and current_user.id != client.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You don't have permission to view this client's topology"
        )

    # Get all clusters for this client
    accounts = db.query(Account).filter(Account.user_id == client_id).all()

    topology = {
        "client_id": str(client.id),
        "client_name": client.full_name or client.username,
        "clusters": []
    }

    for account in accounts:
        # Get instances for this cluster
        instances = db.query(Instance).filter(
            Instance.account_id == account.id,
            Instance.is_active == True
        ).all()

        cluster_data = {
            "cluster_id": str(account.id),
            "cluster_name": account.account_name,
            "region": account.region,
            "node_count": len(instances),
            "nodes": [
                {
                    "instance_id": inst.instance_id,
                    "instance_type": inst.instance_type,
                    "availability_zone": inst.availability_zone,
                    "status": "active" if inst.is_active else "terminated",
                    # Mock metrics - in production, fetch from monitoring
                    "cpu_utilization": 45.5,
                    "memory_utilization": 60.2,
                    "risk_level": "low"
                }
                for inst in instances
            ]
        }

        topology["clusters"].append(cluster_data)

    return topology


# ==============================================================================
# [BE-INSTANCE-005] Client Savings Overview (from realworkflow.md Table 2, Line 68)
# ==============================================================================

@router.get("/{client_id}/savings-overview")
async def get_client_savings_overview(
    client_id: str,
    mode: str = "total",  # total or cluster
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    [BE-INSTANCE-005] Get client savings overview chart data

    Returns cost savings data for visualization:
    - Mode 'total': Overall on-demand vs spot savings
    - Mode 'cluster': Breakdown by cluster

    Used by Client Dashboard Cost Savings Overview Chart
    """
    # Find the client
    client = db.query(User).filter(User.id == client_id).first()

    if not client:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Client {client_id} not found"
        )

    # Check permissions
    if current_user.role != "admin" and current_user.id != client.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You don't have permission to view this client's savings"
        )

    # Mock data - in production, calculate from billing/experiment logs
    if mode == "total":
        return {
            "mode": "total",
            "client_id": str(client.id),
            "data": [
                {"month": "Jan", "on_demand_cost": 12500, "spot_cost": 4200, "savings": 8300},
                {"month": "Feb", "on_demand_cost": 13200, "spot_cost": 4450, "savings": 8750},
                {"month": "Mar", "on_demand_cost": 14100, "spot_cost": 4680, "savings": 9420},
                {"month": "Apr", "on_demand_cost": 13800, "spot_cost": 4590, "savings": 9210}
            ],
            "total_savings": 35680,
            "currency": "USD"
        }
    else:  # cluster mode
        # Get clusters
        accounts = db.query(Account).filter(Account.user_id == client_id).all()

        cluster_savings = [
            {
                "cluster_id": str(acc.id),
                "cluster_name": acc.account_name,
                "savings": 8500 + (i * 1000)  # Mock calculation
            }
            for i, acc in enumerate(accounts)
        ]

        return {
            "mode": "cluster",
            "client_id": str(client.id),
            "clusters": cluster_savings,
            "total_savings": sum(c["savings"] for c in cluster_savings),
            "currency": "USD"
        }
