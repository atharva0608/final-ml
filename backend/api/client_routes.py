"""
Client Dashboard API Routes

Provides dashboard data and metrics for client users after they log in.
Shows their AWS account status, instances, clusters, and savings.
"""

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from sqlalchemy import func
from datetime import datetime, timedelta
from typing import Optional, List
from pydantic import BaseModel
import io
import csv

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
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


# ============================================================================
# ENDPOINTS
# ============================================================================

@router.get("/accounts")
async def get_connected_accounts(
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    List all accounts connected by this user.
    Returns ALL accounts regardless of status (pending, connected, active, warning, failed).
    Frontend handles status-specific UI rendering.
    """
    try:
        # Get all accounts for this user (no status filtering)
        # This ensures admin-created placeholder accounts (status="pending") are visible
        accounts = db.query(Account).filter(
            Account.user_id == current_user.id
        ).all()

        return [
            AccountSummary(
                id=str(account.id),
                account_id=account.account_id,
                account_name=account.account_name,
                status=account.status,
                connection_method=account.connection_method,
                region=account.region,
                created_at=account.created_at,
                updated_at=account.updated_at
            )
            for account in accounts
        ]

    except Exception as e:
        logger.error(f'Failed to list accounts: {e}', extra={'component': 'ClientAccounts', 'user_id': current_user.id})
        raise HTTPException(
            status_code=500,
            detail=f"Failed to retrieve accounts: {str(e)}"
        )


@router.delete("/accounts/{account_id}")
async def disconnect_account(
    account_id: str,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    Disconnect and remove an AWS account connection.

    Security:
    - Verifies the account belongs to the current user
    - Cascades deletion to related instances and logs

    Returns HTTP 200 (not 204) to allow JSON response body.
    This is intentional to provide user feedback.
    """
    try:
        # Find the account
        account = db.query(Account).filter(
            Account.account_id == account_id
        ).first()

        if not account:
            raise HTTPException(
                status_code=404,
                detail=f"Account {account_id} not found"
            )

        # Security: Verify ownership
        if account.user_id != current_user.id:
            raise HTTPException(
                status_code=403,
                detail="You don't have permission to delete this account"
            )

        # Log the deletion
        logger.info(
            f'User {current_user.username} disconnecting account {account_id}',
            extra={
                'component': 'ClientAccounts',
                'user_id': current_user.id,
                'account_id': account_id
            }
        )

        # Delete all instances associated with this account
        # (This should cascade via FK, but explicit for clarity)
        instance_count = db.query(Instance).filter(
            Instance.account_id == account.id
        ).count()

        db.query(Instance).filter(
            Instance.account_id == account.id
        ).delete()

        # Delete the account
        db.delete(account)
        db.commit()

        logger.info(
            f'Successfully deleted account {account_id} and {instance_count} instances',
            extra={'component': 'ClientAccounts'}
        )

        # Return HTTP 200 with JSON body (NOT 204)
        # This allows frontend to receive confirmation message
        return {
            "success": True,
            "message": "AWS account disconnected successfully",
            "account_id": account_id,
            "instances_deleted": instance_count
        }

    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.error(
            f'Failed to delete account: {e}',
            extra={'component': 'ClientAccounts', 'account_id': account_id}
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
                "next_steps": [
                    "Complete CloudFormation stack setup in AWS Console",
                    "Return here to verify connection"
                ]
            }

        # Get instances for this account
        instances = db.query(Instance).filter(
            Instance.account_id == account.id
        ).all()

        # Calculate metrics
        total_instances = len(instances)
        running_instances = sum(1 for i in instances if i.state == 'running')
        stopped_instances = sum(1 for i in instances if i.state == 'stopped')

        # Get recent experiment logs for savings calculation
        thirty_days_ago = datetime.utcnow() - timedelta(days=30)
        recent_logs = db.query(ExperimentLog).join(Instance).filter(
            Instance.account_id == account.id,
            ExperimentLog.execution_time >= thirty_days_ago
        ).all()

        # Calculate total savings
        total_savings = sum(
            (log.projected_hourly_savings or 0) * 730
            for log in recent_logs
            if log.projected_hourly_savings
        )

        # Get cluster information (simplified)
        clusters = []
        if instances:
            # Group instances by availability zone as a simple clustering
            from collections import defaultdict
            zone_groups = defaultdict(list)
            for instance in instances:
                zone_groups[instance.availability_zone or 'unknown'].append(instance)

            clusters = [
                {
                    "zone": zone,
                    "instance_count": len(instances_in_zone),
                    "running": sum(1 for i in instances_in_zone if i.state == 'running')
                }
                for zone, instances_in_zone in zone_groups.items()
            ]

        # Prepare instance list
        instance_list = [
            {
                "id": str(inst.id),
                "instance_id": inst.instance_id,
                "instance_type": inst.instance_type,
                "state": inst.state,
                "availability_zone": inst.availability_zone,
                "region": inst.region,
                "spot_price": inst.current_spot_price,
                "launch_time": inst.launch_time.isoformat() if inst.launch_time else None
            }
            for inst in instances[:50]  # Limit to 50 for performance
        ]

        # Return comprehensive dashboard data
        return {
            "status": "ok",
            "has_account": True,
            "account_status": account.status,
            "account_info": {
                "account_id": account.account_id,
                "account_name": account.account_name,
                "region": account.region,
                "connection_method": account.connection_method,
                "created_at": account.created_at.isoformat()
            },
            "stats": {
                "nodes": total_instances,
                "clusters": len(clusters),
                "savings": round(total_savings, 2),
                "optimization_rate": round((running_instances / total_instances * 100) if total_instances > 0 else 0, 1),
                "running_instances": running_instances,
                "stopped_instances": stopped_instances
            },
            "instances": instance_list,
            "clusters": clusters,
            "recent_optimizations": len(recent_logs),
            "message": "Dashboard loaded successfully"
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


@router.get("/costs/export")
async def export_costs_csv(
    format: str = "csv",
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    Export cost and savings data as CSV file

    Query Parameters:
    - format: Export format (currently only 'csv' supported)

    Returns:
    - CSV file download with last 30 days of cost optimization data

    CSV Columns:
    - Date: Date of optimization
    - Instance ID: AWS instance identifier
    - Instance Type: EC2 instance type
    - Availability Zone: AWS AZ
    - Old Spot Price: Previous hourly cost
    - New Spot Price: New hourly cost
    - Hourly Savings: Cost reduction per hour
    - Monthly Projected: Projected monthly savings
    - Decision: Optimization decision made
    - Model Used: ML model that made prediction
    """
    try:
        # Security check
        if current_user.role not in ["client", "admin", "super_admin"]:
            raise HTTPException(
                status_code=403,
                detail="Access denied. Client role required."
            )

        # Get user's account
        account = db.query(Account).filter(
            Account.user_id == current_user.id
        ).first()

        if not account:
            raise HTTPException(
                status_code=404,
                detail="No AWS account found. Please connect an account first."
            )

        # Get last 30 days of cost data
        thirty_days_ago = datetime.utcnow() - timedelta(days=30)

        cost_logs = db.query(
            ExperimentLog.execution_time,
            Instance.instance_id,
            Instance.instance_type,
            Instance.availability_zone,
            ExperimentLog.old_spot_price,
            ExperimentLog.new_spot_price,
            ExperimentLog.projected_hourly_savings,
            ExperimentLog.decision,
            ExperimentLog.decision_reason
        ).join(
            Instance, ExperimentLog.instance_id == Instance.id
        ).filter(
            Instance.account_id == account.id,
            ExperimentLog.execution_time >= thirty_days_ago,
            ExperimentLog.old_spot_price.isnot(None),
            ExperimentLog.new_spot_price.isnot(None)
        ).order_by(
            ExperimentLog.execution_time.desc()
        ).all()

        # Create CSV in memory
        output = io.StringIO()
        writer = csv.writer(output)

        # Write header
        writer.writerow([
            'Date',
            'Instance ID',
            'Instance Type',
            'Availability Zone',
            'Old Spot Price ($/hr)',
            'New Spot Price ($/hr)',
            'Hourly Savings ($/hr)',
            'Monthly Projected ($)',
            'Decision',
            'Reason'
        ])

        # Write data rows
        total_savings = 0
        for log in cost_logs:
            monthly_savings = (log.projected_hourly_savings or 0) * 730
            total_savings += monthly_savings

            writer.writerow([
                log.execution_time.strftime('%Y-%m-%d %H:%M:%S'),
                log.instance_id or 'N/A',
                log.instance_type or 'N/A',
                log.availability_zone or 'N/A',
                f'${log.old_spot_price:.4f}' if log.old_spot_price else 'N/A',
                f'${log.new_spot_price:.4f}' if log.new_spot_price else 'N/A',
                f'${log.projected_hourly_savings:.4f}' if log.projected_hourly_savings else 'N/A',
                f'${monthly_savings:.2f}',
                log.decision or 'N/A',
                log.decision_reason or 'N/A'
            ])

        # Add summary row
        writer.writerow([])
        writer.writerow(['TOTAL', '', '', '', '', '', '', f'${total_savings:.2f}', '', ''])
        writer.writerow(['Records', len(cost_logs), '', '', '', '', '', '', '', ''])
        writer.writerow(['Period', '30 days', '', '', '', '', '', '', '', ''])

        # Prepare file for download
        output.seek(0)

        # Generate filename with timestamp
        filename = f"cost_savings_{account.account_name}_{datetime.utcnow().strftime('%Y%m%d')}.csv"

        logger.info(
            f'User {current_user.username} exported {len(cost_logs)} cost records',
            extra={
                'component': 'CostExport',
                'user_id': current_user.id,
                'record_count': len(cost_logs),
                'total_savings': total_savings
            }
        )

        # Return as downloadable file
        return StreamingResponse(
            iter([output.getvalue()]),
            media_type="text/csv",
            headers={
                "Content-Disposition": f"attachment; filename={filename}"
            }
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            f'Failed to export costs: {e}',
            extra={'component': 'CostExport', 'user_id': current_user.id}
        )
        raise HTTPException(
            status_code=500,
            detail=f"Failed to export cost data: {str(e)}"
        )
