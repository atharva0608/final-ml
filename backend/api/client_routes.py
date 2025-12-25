"""
Client Dashboard API Routes

Provides dashboard data and metrics for client users after they log in.
Shows their AWS account status, instances, clusters, and savings.
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import func
from datetime import datetime, timedelta
from typing import Optional, List
from pydantic import BaseModel

from database.connection import get_db
from database.models import User, Account, Instance, ExperimentLog, DowntimeLog
from api.auth import get_current_active_user
from utils.system_logger import logger

router = APIRouter(
    prefix="",
    tags=["client_dashboard"]
)


# Pydantic model for account summary
class AccountSummary(BaseModel):
    id: str
    account_id: str
    account_name: str
    status: str
    connection_method: str
    region: str
    created_at: str
    updated_at: str

    class Config:
        from_attributes = True


@router.get("/accounts", response_model=List[AccountSummary])
async def get_connected_accounts(
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    List all accounts connected by this user.
    Returns accounts with status: connected, active, warning (excludes pending/failed if needed)
    """
    try:
        # Get all accounts for this user (filter out 'pending' if desired)
        accounts = db.query(Account).filter(
            Account.user_id == current_user.id,
            Account.status.in_(["connected", "active", "warning"])
        ).all()

        # Convert to response format
        account_summaries = []
        for acc in accounts:
            account_summaries.append({
                "id": str(acc.id),
                "account_id": acc.account_id,
                "account_name": acc.account_name,
                "status": acc.status,
                "connection_method": acc.connection_method,
                "region": acc.region,
                "created_at": acc.created_at.isoformat(),
                "updated_at": acc.updated_at.isoformat()
            })

        return account_summaries

    except Exception as e:
        logger.error(
            f'Failed to list accounts: {e}',
            extra={'component': 'ClientAccounts', 'user_id': current_user.id, 'error': str(e)}
        )
        raise HTTPException(
            status_code=500,
            detail=f"Failed to list accounts: {str(e)}"
        )


@router.delete("/accounts/{account_id}", status_code=200)
async def disconnect_account(
    account_id: str,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    Disconnect and delete an AWS account connection.
    Security: Verifies the account belongs to current_user before deletion.
    Cascade: Deletes related instances and experiment logs.
    Returns: 200 OK with JSON body (not 204 to allow response body)
    """
    try:
        # Find the account
        account = db.query(Account).filter(
            Account.account_id == account_id,
            Account.user_id == current_user.id
        ).first()

        if not account:
            raise HTTPException(
                status_code=404,
                detail="Account not found or does not belong to you"
            )

        # Log the disconnection for audit
        logger.info(
            f'Disconnecting AWS account {account_id}',
            extra={
                'component': 'AccountDisconnect',
                'user_id': current_user.id,
                'account_id': account_id,
                'account_name': account.account_name
            }
        )

        # Delete related instances (cascade will handle experiment logs if configured)
        db.query(Instance).filter(Instance.account_id == account.id).delete()

        # Delete the account record
        db.delete(account)
        db.commit()

        return {
            "success": True,
            "message": f"AWS account {account.account_name} disconnected successfully",
            "account_id": account_id
        }

    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.error(
            f'Failed to disconnect account: {e}',
            extra={'component': 'AccountDisconnect', 'user_id': current_user.id, 'error': str(e)}
        )
        raise HTTPException(
            status_code=500,
            detail=f"Failed to disconnect account: {str(e)}"
        )


@router.get("/dashboard")
async def get_client_dashboard(
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    Returns comprehensive dashboard data for client after login

    Aggregates:
    - Cloud account connection status
    - Instance counts and breakdowns
    - Cost savings metrics
    - Recent activity
    - Cluster/topology data
    """
    try:
        # Security check: Only clients and admins can access
        if current_user.role not in ["client", "admin", "super_admin"]:
            raise HTTPException(
                status_code=403,
                detail="Access denied. Client role required."
            )

        # Get client's AWS account (assuming one account per user)
        account = db.query(Account).filter(
            Account.user_id == current_user.id
        ).first()

        # If no account connected yet, return empty state
        if not account:
            return {
                "status": "no_account",
                "message": "No AWS account connected. Please complete onboarding.",
                "has_account": False,
                "setup_required": True,
                "stats": {
                    "nodes": 0,
                    "clusters": 0,
                    "savings": 0.0,
                    "optimization_rate": 0
                },
                "account_info": None,
                "instances": [],
                "clusters": [],
                "next_steps": ["Connect your AWS account to get started"]
            }

        # Check account discovery status
        if account.status == 'pending':
            return {
                "status": "pending_setup",
                "message": "Cloud connection initiated. Please complete verification.",
                "has_account": True,
                "account_status": account.status,
                "account_info": {
                    "account_name": account.account_name,
                    "created_at": account.created_at.isoformat()
                },
                "stats": {
                    "nodes": 0,
                    "clusters": 0,
                    "savings": 0.0,
                    "optimization_rate": 0
                },
                "instances": [],
                "clusters": [],
                "next_steps": ["Complete cloud account verification"]
            }

        elif account.status == 'connected':
            return {
                "status": "discovering",
                "message": "Scanning your AWS resources... This may take a few minutes.",
                "has_account": True,
                "account_status": account.status,
                "account_info": {
                    "account_name": account.account_name,
                    "aws_account_id": account.account_id,
                    "region": account.region,
                    "created_at": account.created_at.isoformat()
                },
                "stats": {
                    "nodes": 0,
                    "clusters": 0,
                    "savings": 0.0,
                    "optimization_rate": 0
                },
                "instances": [],
                "clusters": [],
                "next_steps": ["Discovery in progress..."],
                "discovery_progress": "Scanning EC2 instances and clusters"
            }

        elif account.status == 'failed':
            error_msg = account.account_metadata.get('last_error', 'Unknown error') if account.account_metadata else 'Unknown error'
            return {
                "status": "failed",
                "message": f"Cloud discovery failed: {error_msg}",
                "has_account": True,
                "account_status": account.status,
                "account_info": {
                    "account_name": account.account_name,
                    "aws_account_id": account.account_id,
                    "created_at": account.created_at.isoformat()
                },
                "stats": {
                    "nodes": 0,
                    "clusters": 0,
                    "savings": 0.0,
                    "optimization_rate": 0
                },
                "instances": [],
                "clusters": [],
                "error": error_msg,
                "next_steps": ["Contact support or retry discovery"]
            }

        # Account is 'active' - return full dashboard data

        # Get all instances for this account
        instances = db.query(Instance).filter(
            Instance.account_id == account.id
        ).all()

        # Count instances by various criteria
        total_instances = len(instances)
        active_instances = sum(1 for i in instances if i.is_active)
        running_instances = sum(1 for i in instances if i.state == 'running')
        authorized_instances = sum(1 for i in instances if i.auth_status == 'authorized')
        spot_instances = sum(1 for i in instances if i.lifecycle == 'spot')
        on_demand_instances = sum(1 for i in instances if i.lifecycle == 'on-demand')

        # Get unique clusters from instance metadata
        cluster_names = set()
        for instance in instances:
            if instance.instance_metadata and 'cluster_hint' in instance.instance_metadata:
                cluster_hint = instance.instance_metadata['cluster_hint']
                if cluster_hint:
                    cluster_names.add(cluster_hint)

        # Calculate cost savings from experiment logs (using projected_hourly_savings)
        since_30_days = datetime.utcnow() - timedelta(days=30)
        cost_savings_result = db.query(
            func.sum(ExperimentLog.projected_hourly_savings).label('total_savings')
        ).join(Instance).filter(
            Instance.account_id == account.id,
            ExperimentLog.execution_time >= since_30_days,
            ExperimentLog.projected_hourly_savings.isnot(None)
        ).first()

        total_savings = float(cost_savings_result.total_savings or 0) if cost_savings_result else 0.0

        # Calculate optimization rate
        optimized_count = db.query(
            func.count(func.distinct(ExperimentLog.instance_id))
        ).join(Instance).filter(
            Instance.account_id == account.id,
            ExperimentLog.execution_time >= since_30_days,
            ExperimentLog.projected_hourly_savings > 0
        ).scalar() or 0

        optimization_rate = round((optimized_count / max(total_instances, 1)) * 100, 1)

        # Build instance list for UI
        instance_list = [
            {
                "id": str(inst.id),
                "instance_id": inst.instance_id,
                "instance_type": inst.instance_type,
                "state": inst.state,
                "lifecycle": inst.lifecycle,
                "region": inst.region,
                "is_active": inst.is_active,
                "auth_status": inst.auth_status,
                "launched_at": inst.launched_at.isoformat() if inst.launched_at else None,
                "cluster": inst.instance_metadata.get('cluster_hint') if inst.instance_metadata else None
            }
            for inst in instances[:50]  # Limit to first 50 for performance
        ]

        # Build cluster topology
        cluster_topology = []
        for cluster_name in cluster_names:
            cluster_instances = [
                i.instance_id for i in instances
                if i.instance_metadata and i.instance_metadata.get('cluster_hint') == cluster_name
            ]
            cluster_topology.append({
                "name": cluster_name,
                "node_count": len(cluster_instances),
                "nodes": cluster_instances[:10]  # Limit to 10 nodes per cluster for dashboard
            })

        # Get scan metadata
        scan_metadata = account.account_metadata or {}
        last_scan = scan_metadata.get('last_scan', account.updated_at.isoformat())

        # Calculate downtime metrics (SLA transparency)
        # Monthly billing period
        billing_period_start = datetime.utcnow().replace(day=1, hour=0, minute=0, second=0, microsecond=0)

        downtime_result = db.query(
            func.sum(DowntimeLog.duration_seconds).label('total_downtime'),
            func.count(DowntimeLog.id).label('incident_count')
        ).filter(
            DowntimeLog.client_id == current_user.id,
            DowntimeLog.start_time >= billing_period_start
        ).first()

        downtime_seconds = int(downtime_result.total_downtime or 0) if downtime_result else 0
        downtime_incidents = int(downtime_result.incident_count or 0) if downtime_result else 0

        # SLA: < 60s monthly downtime target
        sla_compliance = downtime_seconds < 60
        sla_remaining = max(0, 60 - downtime_seconds)

        # Get recent downtime incidents for transparency
        recent_incidents = db.query(DowntimeLog).filter(
            DowntimeLog.client_id == current_user.id,
            DowntimeLog.start_time >= billing_period_start
        ).order_by(DowntimeLog.start_time.desc()).limit(5).all()

        downtime_history = [
            {
                "instance_id": inc.instance_id,
                "duration_seconds": inc.duration_seconds,
                "cause": inc.cause,
                "timestamp": inc.start_time.isoformat()
            }
            for inc in recent_incidents
        ]

        # Determine next steps
        next_steps = []
        if authorized_instances < total_instances:
            next_steps.append(f"Authorize {total_instances - authorized_instances} unauthorized instances")
        if on_demand_instances > 0 and authorized_instances > 0:
            next_steps.append(f"Optimize {on_demand_instances} on-demand instances to spot")
        if len(cluster_names) == 0 and total_instances > 0:
            next_steps.append("Configure instance clusters for better organization")
        if not next_steps:
            next_steps.append("All instances authorized and optimized!")

        return {
            "status": "active",
            "message": "Dashboard data loaded successfully",
            "has_account": True,
            "account_status": account.status,
            "account_info": {
                "account_name": account.account_name,
                "aws_account_id": account.account_id,
                "region": account.region,
                "connection_method": account.connection_method,
                "created_at": account.created_at.isoformat(),
                "last_updated": account.updated_at.isoformat(),
                "last_scan": last_scan
            },
            "stats": {
                "nodes": total_instances,
                "active_nodes": active_instances,
                "running_nodes": running_instances,
                "clusters": len(cluster_names),
                "savings": round(total_savings, 2),
                "savings_period": "30 days",
                "optimization_rate": optimization_rate,
                "authorized_instances": authorized_instances,
                "spot_instances": spot_instances,
                "on_demand_instances": on_demand_instances,
                # SLA & Downtime Metrics (Transparency)
                "downtime_seconds": downtime_seconds,
                "downtime_incidents": downtime_incidents,
                "sla_compliance": sla_compliance,
                "sla_remaining_seconds": sla_remaining,
                "sla_target": 60  # 60s monthly target
            },
            "downtime": {
                "total_seconds": downtime_seconds,
                "incident_count": downtime_incidents,
                "sla_compliance": sla_compliance,
                "sla_target_seconds": 60,
                "sla_remaining_seconds": sla_remaining,
                "billing_period": "monthly",
                "recent_incidents": downtime_history
            },
            "instances": instance_list,
            "clusters": cluster_topology,
            "instance_distribution": {
                "by_lifecycle": {
                    "spot": spot_instances,
                    "on_demand": on_demand_instances
                },
                "by_status": {
                    "authorized": authorized_instances,
                    "unauthorized": total_instances - authorized_instances
                }
            },
            "next_steps": next_steps
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            f'Failed to load client dashboard: {e}',
            extra={'component': 'ClientDashboard', 'user_id': current_user.id, 'error': str(e)}
        )
        raise HTTPException(
            status_code=500,
            detail=f"Failed to load dashboard: {str(e)}"
        )


@router.get("/summary")
async def get_client_summary(
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    Returns a lightweight summary for quick checks (used by header/navbar)
    """
    try:
        account = db.query(Account).filter(
            Account.user_id == current_user.id
        ).first()

        if not account:
            return {
                "has_account": False,
                "instance_count": 0,
                "status": "no_account"
            }

        instance_count = db.query(Instance).filter(
            Instance.account_id == account.id
        ).count()

        return {
            "has_account": True,
            "account_status": account.status,
            "account_name": account.account_name,
            "instance_count": instance_count,
            "status": "ok"
        }

    except Exception as e:
        logger.error(f'Failed to load client summary: {e}')
        return {
            "has_account": False,
            "instance_count": 0,
            "status": "error",
            "error": str(e)
        }
