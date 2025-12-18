"""
Metrics API Routes

Provides real-time metrics for the Live Operations dashboard.
Includes activity feed and live pipeline metrics.
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import desc, func
from typing import List, Dict
from datetime import datetime, timedelta

from database.connection import get_db
from database.models import Instance, ExperimentLog, Account
from database.system_logs import SystemLog, LogLevel
from api.auth import get_current_active_user

router = APIRouter(
    prefix="",
    tags=["metrics"]
)


@router.get('/activity')
async def get_activity_metrics(
    db: Session = Depends(get_db),
    current_user = Depends(get_current_active_user)
):
    """
    Returns recent activity metrics for the Live Operations dashboard

    Includes:
    - Recent system events
    - Active instances count
    - Recent optimizations
    - Cost savings
    """
    try:
        # Get activity from last 24 hours
        since = datetime.utcnow() - timedelta(hours=24)

        # Recent system logs (activity feed)
        recent_logs = db.query(SystemLog).filter(
            SystemLog.timestamp >= since,
            SystemLog.level.in_([LogLevel.INFO, LogLevel.SUCCESS, LogLevel.WARNING])
        ).order_by(desc(SystemLog.timestamp)).limit(20).all()

        # Active instances count
        active_instances = db.query(Instance).filter(
            Instance.is_active == True
        ).count()

        # Recent optimizations from experiment logs
        recent_experiments = db.query(ExperimentLog).filter(
            ExperimentLog.created_at >= since
        ).count()

        # Calculate cost savings from experiment logs
        cost_savings_result = db.query(
            func.sum(ExperimentLog.cost_savings).label('total_savings')
        ).filter(
            ExperimentLog.created_at >= since,
            ExperimentLog.cost_savings.isnot(None)
        ).first()

        total_cost_savings = float(cost_savings_result.total_savings or 0) if cost_savings_result else 0

        # Risk detections (instances with high risk)
        risk_detected = db.query(Instance).filter(
            Instance.is_active == True,
            Instance.instance_metadata.op('->>')('risk_level').in_(['high', 'critical'])
        ).count()

        activity_events = [
            {
                'id': str(log.id),
                'timestamp': log.timestamp.isoformat(),
                'component': log.component.value if hasattr(log.component, 'value') else str(log.component),
                'level': log.level.value if hasattr(log.level, 'value') else str(log.level),
                'message': log.message,
                'details': log.details or {}
            }
            for log in recent_logs
        ]

        return {
            'metrics': {
                'activeInstances': active_instances,
                'riskDetected': risk_detected,
                'costSavings': round(total_cost_savings, 2),
                'optimizations': recent_experiments
            },
            'activity': activity_events,
            'timestamp': datetime.utcnow().isoformat()
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch activity metrics: {str(e)}")


@router.get('/live')
async def get_live_metrics(
    db: Session = Depends(get_db),
    current_user = Depends(get_current_active_user)
):
    """
    Returns live pipeline metrics for real-time monitoring

    Includes:
    - Pipeline processing stats
    - Component health metrics
    - Resource utilization
    """
    try:
        # Get recent logs from last hour
        since = datetime.utcnow() - timedelta(hours=1)

        # Count logs by component
        component_stats = db.query(
            SystemLog.component,
            func.count(SystemLog.id).label('log_count'),
            func.avg(SystemLog.execution_time_ms).label('avg_execution_time')
        ).filter(
            SystemLog.timestamp >= since
        ).group_by(SystemLog.component).all()

        # Active accounts
        active_accounts = db.query(Account).filter(
            Account.is_active == True
        ).count()

        # Total instances
        total_instances = db.query(Instance).filter(
            Instance.is_active == True
        ).count()

        # Recent errors
        error_count = db.query(SystemLog).filter(
            SystemLog.timestamp >= since,
            SystemLog.level == LogLevel.ERROR
        ).count()

        # Recent successes
        success_count = db.query(SystemLog).filter(
            SystemLog.timestamp >= since,
            SystemLog.level.in_([LogLevel.SUCCESS, LogLevel.INFO])
        ).count()

        component_metrics = [
            {
                'component': stat.component.value if hasattr(stat.component, 'value') else str(stat.component),
                'operations': stat.log_count,
                'avg_execution_time_ms': round(stat.avg_execution_time or 0, 2)
            }
            for stat in component_stats
        ]

        return {
            'pipeline': {
                'activeAccounts': active_accounts,
                'activeInstances': total_instances,
                'successRate': round((success_count / max(success_count + error_count, 1)) * 100, 2),
                'errorCount': error_count
            },
            'components': component_metrics,
            'timestamp': datetime.utcnow().isoformat()
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch live metrics: {str(e)}")
