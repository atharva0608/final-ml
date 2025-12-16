"""
Admin API - System Monitoring and Management

Provides endpoints for:
- System health status
- Component logs and monitoring
- System diagnostics
"""

from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from sqlalchemy import desc, func
from typing import List, Optional
from datetime import datetime, timedelta
from pydantic import BaseModel

from database.connection import get_db
from database.models import User
from database.system_logs import SystemLog, ComponentHealth, ComponentType, LogLevel, ComponentStatus
from api.auth import get_current_active_user


router = APIRouter()


# ============================================================================
# Response Models
# ============================================================================

class LogEntry(BaseModel):
    """Single log entry"""
    id: str
    component: str
    level: str
    message: str
    details: dict
    timestamp: datetime
    execution_time_ms: Optional[int]
    success: Optional[str]

    class Config:
        from_attributes = True


class ComponentHealthResponse(BaseModel):
    """Component health status"""
    component: str
    status: str
    last_success: Optional[datetime]
    last_failure: Optional[datetime]
    last_check: datetime
    success_count_24h: int
    failure_count_24h: int
    avg_execution_time_ms: Optional[int]
    error_message: Optional[str]
    uptime_percentage: float  # Calculated field

    class Config:
        from_attributes = True


class ComponentLogsResponse(BaseModel):
    """Component logs with health status"""
    component: str
    health: Optional[ComponentHealthResponse]
    logs: List[LogEntry]
    total_logs: int


class SystemOverviewResponse(BaseModel):
    """System-wide overview"""
    components: List[ComponentHealthResponse]
    overall_status: str
    healthy_count: int
    degraded_count: int
    down_count: int
    last_updated: datetime


class LogStatsResponse(BaseModel):
    """Log statistics"""
    total_logs_24h: int
    error_count_24h: int
    warning_count_24h: int
    avg_execution_time_ms: Optional[int]
    top_errors: List[dict]


# ============================================================================
# Endpoints
# ============================================================================

@router.get("/health/overview", response_model=SystemOverviewResponse)
async def get_system_overview(
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    Get system-wide health overview

    Requires admin role
    """
    # Check admin permission
    if current_user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required"
        )

    # Get all component health records
    components = db.query(ComponentHealth).all()

    # Calculate overall status
    healthy_count = sum(1 for c in components if c.status == ComponentStatus.HEALTHY.value)
    degraded_count = sum(1 for c in components if c.status == ComponentStatus.DEGRADED.value)
    down_count = sum(1 for c in components if c.status == ComponentStatus.DOWN.value)

    if down_count > 0:
        overall_status = "critical"
    elif degraded_count > 0:
        overall_status = "warning"
    elif healthy_count > 0:
        overall_status = "healthy"
    else:
        overall_status = "unknown"

    # Build response
    component_responses = []
    for component in components:
        total = component.success_count_24h + component.failure_count_24h
        uptime = (component.success_count_24h / total * 100) if total > 0 else 100.0

        component_responses.append(ComponentHealthResponse(
            component=component.component,
            status=component.status,
            last_success=component.last_success,
            last_failure=component.last_failure,
            last_check=component.last_check,
            success_count_24h=component.success_count_24h,
            failure_count_24h=component.failure_count_24h,
            avg_execution_time_ms=component.avg_execution_time_ms,
            error_message=component.error_message,
            uptime_percentage=uptime
        ))

    return SystemOverviewResponse(
        components=component_responses,
        overall_status=overall_status,
        healthy_count=healthy_count,
        degraded_count=degraded_count,
        down_count=down_count,
        last_updated=datetime.utcnow()
    )


@router.get("/logs/{component}", response_model=ComponentLogsResponse)
async def get_component_logs(
    component: str,
    limit: int = Query(5, ge=1, le=100),
    level: Optional[str] = None,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    Get logs for a specific component

    Args:
        component: Component name (web_scraper, price_scraper, etc.)
        limit: Number of logs to return (default: 5, max: 100)
        level: Filter by log level (optional)

    Requires admin role
    """
    # Check admin permission
    if current_user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required"
        )

    # Validate component
    try:
        ComponentType(component)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid component: {component}"
        )

    # Get component health
    health = db.query(ComponentHealth).filter(
        ComponentHealth.component == component
    ).first()

    health_response = None
    if health:
        total = health.success_count_24h + health.failure_count_24h
        uptime = (health.success_count_24h / total * 100) if total > 0 else 100.0

        health_response = ComponentHealthResponse(
            component=health.component,
            status=health.status,
            last_success=health.last_success,
            last_failure=health.last_failure,
            last_check=health.last_check,
            success_count_24h=health.success_count_24h,
            failure_count_24h=health.failure_count_24h,
            avg_execution_time_ms=health.avg_execution_time_ms,
            error_message=health.error_message,
            uptime_percentage=uptime
        )

    # Get logs
    query = db.query(SystemLog).filter(SystemLog.component == component)

    if level:
        query = query.filter(SystemLog.level == level)

    logs = query.order_by(desc(SystemLog.timestamp)).limit(limit).all()
    total_logs = query.count()

    log_entries = [
        LogEntry(
            id=str(log.id),
            component=log.component,
            level=log.level,
            message=log.message,
            details=log.details or {},
            timestamp=log.timestamp,
            execution_time_ms=log.execution_time_ms,
            success=log.success
        )
        for log in logs
    ]

    return ComponentLogsResponse(
        component=component,
        health=health_response,
        logs=log_entries,
        total_logs=total_logs
    )


@router.get("/logs/all/recent", response_model=List[LogEntry])
async def get_recent_logs(
    limit: int = Query(20, ge=1, le=100),
    level: Optional[str] = None,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    Get recent logs from all components

    Args:
        limit: Number of logs to return (default: 20, max: 100)
        level: Filter by log level (optional)

    Requires admin role
    """
    # Check admin permission
    if current_user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required"
        )

    query = db.query(SystemLog)

    if level:
        query = query.filter(SystemLog.level == level)

    logs = query.order_by(desc(SystemLog.timestamp)).limit(limit).all()

    return [
        LogEntry(
            id=str(log.id),
            component=log.component,
            level=log.level,
            message=log.message,
            details=log.details or {},
            timestamp=log.timestamp,
            execution_time_ms=log.execution_time_ms,
            success=log.success
        )
        for log in logs
    ]


@router.get("/stats", response_model=LogStatsResponse)
async def get_log_statistics(
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    Get log statistics for the last 24 hours

    Requires admin role
    """
    # Check admin permission
    if current_user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required"
        )

    cutoff = datetime.utcnow() - timedelta(hours=24)

    # Total logs in last 24h
    total_logs = db.query(SystemLog).filter(
        SystemLog.timestamp >= cutoff
    ).count()

    # Error count
    error_count = db.query(SystemLog).filter(
        SystemLog.timestamp >= cutoff,
        SystemLog.level.in_([LogLevel.ERROR.value, LogLevel.CRITICAL.value])
    ).count()

    # Warning count
    warning_count = db.query(SystemLog).filter(
        SystemLog.timestamp >= cutoff,
        SystemLog.level == LogLevel.WARNING.value
    ).count()

    # Average execution time
    avg_time = db.query(func.avg(SystemLog.execution_time_ms)).filter(
        SystemLog.timestamp >= cutoff,
        SystemLog.execution_time_ms.isnot(None)
    ).scalar()

    # Top errors (grouped by message)
    top_errors_query = db.query(
        SystemLog.message,
        SystemLog.component,
        func.count(SystemLog.id).label('count')
    ).filter(
        SystemLog.timestamp >= cutoff,
        SystemLog.level.in_([LogLevel.ERROR.value, LogLevel.CRITICAL.value])
    ).group_by(
        SystemLog.message,
        SystemLog.component
    ).order_by(
        desc('count')
    ).limit(5).all()

    top_errors = [
        {
            "message": error.message,
            "component": error.component,
            "count": error.count
        }
        for error in top_errors_query
    ]

    return LogStatsResponse(
        total_logs_24h=total_logs,
        error_count_24h=error_count,
        warning_count_24h=warning_count,
        avg_execution_time_ms=int(avg_time) if avg_time else None,
        top_errors=top_errors
    )


@router.post("/logs/cleanup")
async def cleanup_old_logs(
    days: int = Query(7, ge=1, le=90),
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    Clean up logs older than specified days

    Args:
        days: Number of days to keep (default: 7, max: 90)

    Requires admin role
    """
    # Check admin permission
    if current_user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required"
        )

    cutoff = datetime.utcnow() - timedelta(days=days)

    deleted = db.query(SystemLog).filter(
        SystemLog.timestamp < cutoff
    ).delete()

    db.commit()

    return {
        "status": "success",
        "deleted_count": deleted,
        "cutoff_date": cutoff.isoformat()
    }
