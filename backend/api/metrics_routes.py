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
            SystemLog.level.in_([LogLevel.INFO, LogLevel.WARNING])
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

        # Recent successes (INFO level logs)
        success_count = db.query(SystemLog).filter(
            SystemLog.timestamp >= since,
            SystemLog.level == LogLevel.INFO
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


# ==============================================================================
# DEDICATED METRIC ENDPOINTS
# ==============================================================================

@router.get('/active-instances')
async def get_active_instances_metric(
    db: Session = Depends(get_db),
    current_user = Depends(get_current_active_user)
):
    """Get count of active instances across all clients"""
    try:
        active_instances = db.query(Instance).filter(
            Instance.is_active == True
        ).count()

        return {
            'count': active_instances,
            'timestamp': datetime.utcnow().isoformat()
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch active instances: {str(e)}")


@router.get('/risk-detected')
async def get_risk_detected_metric(
    db: Session = Depends(get_db),
    current_user = Depends(get_current_active_user)
):
    """Get count of risk detections in last 24 hours"""
    try:
        since = datetime.utcnow() - timedelta(hours=24)

        # Count high-risk instances
        risk_detected = db.query(Instance).filter(
            Instance.is_active == True,
            Instance.instance_metadata.op('->>')('risk_level').in_(['high', 'critical'])
        ).count()

        # Also count rebalance/termination notices from logs
        risk_logs = db.query(SystemLog).filter(
            SystemLog.timestamp >= since,
            SystemLog.message.ilike('%rebalance%') | SystemLog.message.ilike('%termination%')
        ).count()

        total_risk = risk_detected + risk_logs

        return {
            'count': total_risk,
            'high_risk_instances': risk_detected,
            'risk_notices_24h': risk_logs,
            'timestamp': datetime.utcnow().isoformat()
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch risk metrics: {str(e)}")


@router.get('/cost-savings')
async def get_cost_savings_metric(
    db: Session = Depends(get_db),
    current_user = Depends(get_current_active_user)
):
    """Get total cost savings across platform"""
    try:
        # Calculate total savings from experiment logs (all-time or last 30 days)
        since = datetime.utcnow() - timedelta(days=30)

        cost_savings_result = db.query(
            func.sum(ExperimentLog.cost_savings).label('total_savings')
        ).filter(
            ExperimentLog.created_at >= since,
            ExperimentLog.cost_savings.isnot(None)
        ).first()

        total_savings = float(cost_savings_result.total_savings or 0) if cost_savings_result else 0

        return {
            'total_savings': round(total_savings, 2),
            'period_days': 30,
            'timestamp': datetime.utcnow().isoformat()
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch cost savings: {str(e)}")


@router.get('/optimization-rate')
async def get_optimization_rate_metric(
    db: Session = Depends(get_db),
    current_user = Depends(get_current_active_user)
):
    """
    Calculate optimization rate as percentage of instances successfully optimized
    Formula: (successful_optimizations / total_instances) * 100
    """
    try:
        # Total active instances
        total_instances = db.query(Instance).filter(
            Instance.is_active == True
        ).count()

        # Count instances that have been successfully optimized (have experiment logs)
        since = datetime.utcnow() - timedelta(days=7)

        optimized_instances = db.query(
            func.count(func.distinct(ExperimentLog.instance_id)).label('count')
        ).filter(
            ExperimentLog.created_at >= since,
            ExperimentLog.cost_savings > 0
        ).first()

        optimized_count = optimized_instances.count if optimized_instances else 0

        rate = round((optimized_count / max(total_instances, 1)) * 100, 2)

        return {
            'optimization_rate': rate,
            'optimized_instances': optimized_count,
            'total_instances': total_instances,
            'period_days': 7,
            'timestamp': datetime.utcnow().isoformat()
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to calculate optimization rate: {str(e)}")


@router.get('/system-load')
async def get_system_load_metric(
    db: Session = Depends(get_db),
    current_user = Depends(get_current_active_user)
):
    """Get current system load metrics"""
    try:
        # Get request volume in last hour
        since = datetime.utcnow() - timedelta(hours=1)

        request_count = db.query(SystemLog).filter(
            SystemLog.timestamp >= since
        ).count()

        # Calculate error rate
        error_count = db.query(SystemLog).filter(
            SystemLog.timestamp >= since,
            SystemLog.level == LogLevel.ERROR
        ).count()

        error_rate = round((error_count / max(request_count, 1)) * 100, 2)

        # Estimate load percentage (simplified - in production would use actual CPU/memory metrics)
        # Assuming 1000 requests/hour is max capacity
        max_capacity = 1000
        load_percentage = min(round((request_count / max_capacity) * 100, 2), 100)

        return {
            'load_percentage': load_percentage,
            'request_count_1h': request_count,
            'error_rate': error_rate,
            'status': 'normal' if load_percentage < 70 else 'high' if load_percentage < 90 else 'critical',
            'timestamp': datetime.utcnow().isoformat()
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch system load: {str(e)}")


@router.get('/performance')
async def get_performance_metrics(
    instance_id: str = None,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_active_user)
):
    """
    Get application performance metrics
    If instance_id provided, returns instance-specific metrics
    Otherwise returns platform-wide metrics
    """
    try:
        since = datetime.utcnow() - timedelta(hours=24)

        if instance_id:
            # Instance-specific metrics
            instance = db.query(Instance).filter(Instance.id == instance_id).first()
            if not instance:
                raise HTTPException(status_code=404, detail="Instance not found")

            # Get instance experiment logs for performance data
            experiments = db.query(ExperimentLog).filter(
                ExperimentLog.instance_id == instance_id,
                ExperimentLog.created_at >= since
            ).all()

            avg_latency = sum(e.execution_time_ms or 0 for e in experiments) / max(len(experiments), 1)
            error_count = sum(1 for e in experiments if e.cost_savings == 0)
            error_rate = (error_count / max(len(experiments), 1)) * 100

            return {
                'instance_id': instance_id,
                'avg_latency_ms': round(avg_latency, 2),
                'request_count_24h': len(experiments),
                'error_rate': round(error_rate, 2),
                'timestamp': datetime.utcnow().isoformat()
            }
        else:
            # Platform-wide performance metrics
            all_experiments = db.query(ExperimentLog).filter(
                ExperimentLog.created_at >= since
            ).all()

            avg_latency = sum(e.execution_time_ms or 0 for e in all_experiments) / max(len(all_experiments), 1)
            error_count = sum(1 for e in all_experiments if e.cost_savings == 0)
            error_rate = (error_count / max(len(all_experiments), 1)) * 100

            return {
                'platform_wide': True,
                'avg_latency_ms': round(avg_latency, 2),
                'total_requests_24h': len(all_experiments),
                'error_rate': round(error_rate, 2),
                'timestamp': datetime.utcnow().isoformat()
            }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch performance metrics: {str(e)}")


# ==============================================================================
# PHASE 3: DEEP HEALTH MONITORING
# ==============================================================================

@router.get('/system/health')
async def get_system_health(
    db: Session = Depends(get_db),
    current_user = Depends(get_current_active_user)
):
    """
    Deep system health monitoring across 7 critical components

    Returns health status for:
    - Database (connection pool, query latency)
    - Redis (connection, queue depth)
    - K8s Watcher (heartbeat age)
    - Optimizer (last run timestamp)
    - Price Scraper (data freshness)
    - Risk Engine (risk data freshness)
    - ML Inference (active model availability)

    For degraded/critical components, includes recent logs for diagnostics.

    Overall status is worst status across all components.
    """
    try:
        from utils.component_health_checks import run_all_health_checks

        # Run all health checks
        results = run_all_health_checks(db)

        # Determine overall status (worst of all components)
        status_priority = {"healthy": 0, "degraded": 1, "critical": 2}
        overall_status = "healthy"

        for component_status, _ in results.values():
            if status_priority[component_status] > status_priority[overall_status]:
                overall_status = component_status

        # Build response
        components = []
        for component_name, (status, details) in results.items():
            component_data = {
                "name": component_name,
                "status": status,
                **details  # Spread details (latency_ms, message, etc.)
            }

            # Only include logs for unhealthy components (saves bandwidth)
            if status != "healthy":
                try:
                    recent_logs = db.query(SystemLog).filter(
                        SystemLog.component == component_name
                    ).order_by(
                        SystemLog.timestamp.desc()
                    ).limit(5).all()

                    component_data["recent_logs"] = [
                        {
                            "timestamp": log.timestamp.isoformat(),
                            "level": log.level.value if hasattr(log.level, 'value') else str(log.level),
                            "message": log.message
                        }
                        for log in recent_logs
                    ]
                except Exception as e:
                    component_data["recent_logs"] = [{"error": f"Failed to fetch logs: {e}"}]

            components.append(component_data)

        return {
            "overall_status": overall_status,
            "components": components,
            "checked_at": datetime.utcnow().isoformat(),
            "healthy_count": sum(1 for s, _ in results.values() if s == "healthy"),
            "degraded_count": sum(1 for s, _ in results.values() if s == "degraded"),
            "critical_count": sum(1 for s, _ in results.values() if s == "critical")
        }

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Health check system failure: {str(e)}"
        )
