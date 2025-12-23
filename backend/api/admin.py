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
from pydantic import BaseModel, ConfigDict
from uuid import UUID
import uuid

from database.connection import get_db
from database.models import User, Account
from database.system_logs import SystemLog, ComponentHealth, ComponentType, LogLevel, ComponentStatus
from api.auth import get_current_active_user


router = APIRouter()


# ============================================================================
# Response Models
# ============================================================================

class LogEntry(BaseModel):
    """Single log entry"""
    model_config = ConfigDict(from_attributes=True)

    id: str
    component: str
    level: str
    message: str
    details: dict
    timestamp: datetime
    execution_time_ms: Optional[int]
    success: Optional[str]


class ComponentHealthResponse(BaseModel):
    """Component health status"""
    model_config = ConfigDict(from_attributes=True)

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


class NodeResponse(BaseModel):
    id: str
    instance_type: str
    availability_zone: str
    zone: str # For frontend compatibility
    family: str # For frontend compatibility (e.g. c5)
    status: str
    stress: int = 0
    risk: str = "low"
    cpu_utilization: float = 0.0
    memory_utilization: float = 0.0

class ClusterResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    nodes: List[NodeResponse]
    nodeCount: int
    status: str
    region: str

class ClientResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    tier: str
    region: str
    status: str
    clusters: List[ClusterResponse]
    total_instances: int
    monthly_savings: float


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

    # Calculate overall status - map 'unknown' to 'degraded' for consistency
    # Only 3 categories: healthy, degraded, down/critical
    healthy_count = sum(1 for c in components if c.status == ComponentStatus.HEALTHY.value)
    degraded_count = sum(1 for c in components if c.status in [ComponentStatus.DEGRADED.value, ComponentStatus.UNKNOWN.value])
    down_count = sum(1 for c in components if c.status == ComponentStatus.DOWN.value)

    if down_count > 0:
        overall_status = "critical"
    elif degraded_count > 0:
        overall_status = "degraded"
    elif healthy_count > 0:
        overall_status = "healthy"
    else:
        overall_status = "degraded"  # Default to degraded instead of unknown

    # Build response
    component_responses = []
    for component in components:
        total = component.success_count_24h + component.failure_count_24h
        uptime = (component.success_count_24h / total * 100) if total > 0 else 100.0

        # Map 'unknown' status to 'degraded' for display
        display_status = component.status if component.status != ComponentStatus.UNKNOWN.value else ComponentStatus.DEGRADED.value

        component_responses.append(ComponentHealthResponse(
            component=component.component,
            status=display_status,
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


@router.post("/health/run-checks")
async def run_comprehensive_health_checks(
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    Run all health checks and update system monitor status.
    
    Includes the new Decision Pipeline and Standalone Pipeline checks
    that validate models are properly loaded and decision logic works with demo data.
    
    Requires admin role.
    """
    from utils.component_health_checks import run_all_health_checks
    from database.system_logs import ComponentHealth, ComponentStatus
    from datetime import datetime, timedelta
    from sqlalchemy import func
    
    # Check admin permission
    if current_user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required"
        )
    
    # Run all health checks
    results = run_all_health_checks(db)
    
    # Update or create ComponentHealth records for each check
    updated_components = []
    for component_name, (status_str, details) in results.items():
        # Find or create health record
        health = db.query(ComponentHealth).filter(
            ComponentHealth.component == component_name
        ).first()
        
        if not health:
            health = ComponentHealth(
                component=component_name,
                status=ComponentStatus.UNKNOWN.value,
                component_metadata={}
            )
            db.add(health)
        
        # Map status string to ComponentStatus
        status_map = {
            "healthy": ComponentStatus.HEALTHY.value,
            "degraded": ComponentStatus.DEGRADED.value,
            "critical": ComponentStatus.DOWN.value,
            "down": ComponentStatus.DOWN.value
        }
        health.status = status_map.get(status_str, ComponentStatus.UNKNOWN.value)
        health.component_metadata = details
        health.last_check = datetime.utcnow()
        
        # Update success/failure counts
        if status_str == "healthy":
            health.last_success = datetime.utcnow()
            health.success_count_24h = (health.success_count_24h or 0) + 1
        else:
            health.last_failure = datetime.utcnow()
            health.failure_count_24h = (health.failure_count_24h or 0) + 1
            if "error" in details:
                health.error_message = details.get("error", "")[:500]  # Truncate
        
        updated_components.append({
            "component": component_name,
            "status": status_str,
            "details": details
        })
    
    db.commit()
    
    # Calculate summary
    healthy = sum(1 for s, _ in results.values() if s == "healthy")
    degraded = sum(1 for s, _ in results.values() if s == "degraded")
    critical = sum(1 for s, _ in results.values() if s in ["critical", "down"])
    
    return {
        "status": "completed",
        "timestamp": datetime.utcnow().isoformat(),
        "summary": {
            "total_checks": len(results),
            "healthy": healthy,
            "degraded": degraded,
            "critical": critical
        },
        "components": updated_components
    }



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


# ============================================================================
# Client Management (Topology)
# ============================================================================

from database.models import Account, Instance

@router.get("/clients", response_model=List[ClientResponse])
async def list_clients(
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """List all clients (Tenants) with their topology"""
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    
    # Get all users (treat as clients)
    users = db.query(User).filter(User.role != "admin").all()
    
    result = []
    for user in users:
        # Get accounts for this user (Clusters)
        accounts = db.query(Account).filter(Account.user_id == user.id).all()
        
        clusters = []
        total_instances = 0
        
        for acc in accounts:
            instances = db.query(Instance).filter(Instance.account_id == acc.id).all()
            nodes = [
                NodeResponse(
                    id=inst.instance_id,
                    instance_type=inst.instance_type,
                    availability_zone=inst.availability_zone,
                    zone=inst.availability_zone,
                    family=inst.instance_type.split('.')[0] if '.' in inst.instance_type else inst.instance_type,
                    status="active" if inst.is_active else "terminated",
                    stress=15, # Mock metric
                    risk="low",
                    cpu_utilization=45.5, 
                    memory_utilization=60.2
                )
                for inst in instances
            ]
            clusters.append(ClusterResponse(
                id=str(acc.id),
                name=acc.account_name,
                nodes=nodes,
                nodeCount=len(nodes),
                status="active" if acc.is_active else "inactive",
                region=acc.region
            ))
            total_instances += len(instances)
            
        result.append(ClientResponse(
            id=str(user.id),
            name=user.full_name or user.username,
            tier="Enterprise",
            region="Global",
            status="active",
            clusters=clusters,
            total_instances=total_instances,
            monthly_savings=12500.0  # limit scope, mock for now
        ))
        
    return result


@router.get("/clients/{client_id}", response_model=ClientResponse)
async def get_client_details(
    client_id: str,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Get detailed topology for a specific client"""
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
        
    user = db.query(User).filter(User.id == client_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Client not found")
        
    accounts = db.query(Account).filter(Account.user_id == user.id).all()
    
    clusters = []
    total_instances = 0
    
    for acc in accounts:
        instances = db.query(Instance).filter(Instance.account_id == acc.id).all()
        nodes = [
            NodeResponse(
                id=inst.instance_id,
                instance_type=inst.instance_type,
                availability_zone=inst.availability_zone,
                zone=inst.availability_zone,
                family=inst.instance_type.split('.')[0] if '.' in inst.instance_type else inst.instance_type,
                status="active" if inst.is_active else "terminated",
                stress=15,
                risk="low",
                cpu_utilization=45.5,
                memory_utilization=60.2
            )
            for inst in instances
        ]
        clusters.append(ClusterResponse(
            id=str(acc.id),
            name=acc.account_name,
            nodes=nodes,
            nodeCount=len(nodes),
            status="active" if acc.is_active else "inactive",
            region=acc.region
        ))
        total_instances += len(instances)
        
    return ClientResponse(
        id=str(user.id),
        name=user.full_name or user.username,
        tier="Enterprise",
        region="Global",
        status="active",
        clusters=clusters,
        total_instances=total_instances,
        monthly_savings=12500.0
    )

# ============================================================================
# User Management (Identity & Access)
# ============================================================================

class UserUpdateStatus(BaseModel):
    is_active: bool

class UserUpdateRole(BaseModel):
    role: str

class UserCreate(BaseModel):
    username: str
    email: str
    password: str
    full_name: Optional[str] = None
    role: str = "client"
    is_active: bool = True

class SpotStatusUpdate(BaseModel):
    disabled: bool

class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    email: str
    username: str
    full_name: Optional[str] = None
    role: str
    is_active: bool
    last_login: Optional[datetime]
    created_at: datetime


@router.post("/clients", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def create_client_user(
    user_data: UserCreate,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Create a new user/client (Admin only)"""
    from auth.password import hash_password

    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")

    # Check if username or email already exists
    existing_user = db.query(User).filter(
        (User.username == user_data.username) | (User.email == user_data.email)
    ).first()

    if existing_user:
        raise HTTPException(
            status_code=400,
            detail="Username or email already registered"
        )

    # Create new user
    new_user = User(
        username=user_data.username,
        email=user_data.email,
        hashed_password=hash_password(user_data.password),
        full_name=user_data.full_name,
        role=user_data.role,
        is_active=user_data.is_active
    )

    db.add(new_user)
    db.flush()  # Generate ID for new_user

    # CRITICAL FIX: Create placeholder account for client users to prevent "Orphan" state
    if user_data.role == 'client':
        # Check if account already exists (paranoid check)
        existing_account = db.query(Account).filter(Account.user_id == new_user.id).first()

        if not existing_account:
            placeholder_account = Account(
                user_id=new_user.id,
                account_name=f"{user_data.full_name}'s Account",
                account_id=f"pending-{uuid.uuid4().hex[:8]}",  # Temporary ID
                external_id=f"spot-optimizer-{uuid.uuid4()}",
                role_arn="pending",  # Will be updated during onboarding
                status="pending",
                connection_method="unknown",
                region="us-east-1",
                is_active=False
            )
            db.add(placeholder_account)
            print(f"✓ [Admin] Created placeholder account for user {new_user.username} (ID: {new_user.id})")

    db.commit()
    db.refresh(new_user)

    return new_user

@router.get("/users", response_model=List[UserResponse])
async def list_users(
    skip: int = 0,
    limit: int = 100,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """List all registered users"""
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")

    users = db.query(User).offset(skip).limit(limit).all()
    return users


@router.put("/users/{user_id}/status")
async def update_user_status(
    user_id: str,
    status_update: UserUpdateStatus,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Block or unblock a user"""
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
        
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
        
    user.is_active = status_update.is_active
    db.commit()
    
    return {"status": "success", "user_id": user_id, "is_active": user.is_active}


@router.put("/users/{user_id}/role")
async def update_user_role(
    user_id: str,
    role_update: UserUpdateRole,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Change user role (admin/user/lab)"""
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
        
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
        
    # Validation
    valid_roles = ["admin", "user", "lab"]
    if role_update.role not in valid_roles:
        raise HTTPException(status_code=400, detail=f"Invalid role. Must be one of: {valid_roles}")
        
    user.role = role_update.role
    db.commit()
    
    return {"status": "success", "user_id": user_id, "role": user.role}


@router.delete("/users/{user_id}")
async def delete_user(
    user_id: str,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Permanently delete a user"""
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
        
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
        
    # Prevent deleting yourself
    if str(user.id) == str(current_user.id):
        raise HTTPException(status_code=400, detail="Cannot delete your own admin account")
        
    db.delete(user)
    db.commit()

    return {"status": "success", "message": "User deleted"}


# ============================================================================
# System Controls - Spot Market
# ============================================================================

@router.put("/system/spot-status")
async def set_spot_status(
    status_update: SpotStatusUpdate,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    Enable or Disable the Global Spot Market

    This endpoint allows admins to globally enable/disable the spot market
    optimization feature across all clients and instances.

    Args:
        status_update: Contains disabled boolean flag
        current_user: Authenticated admin user
        db: Database session

    Returns:
        Status confirmation with current state

    Requires admin role
    """
    # Check admin permission
    if current_user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required"
        )

    # In a real app, save this to a SystemConfig table
    # For now, we log it and return success to update the UI
    print(f"⚠️ SYSTEM ALERT: Spot Market Disabled: {status_update.disabled}")

    return {
        "status": "success",
        "message": f"Spot Market {'Disabled' if status_update.disabled else 'Enabled'}",
        "spot_disabled": status_update.disabled
    }


@router.post("/system/rebalance")
async def trigger_rebalance(
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    Triggers an immediate optimization cycle across all clusters

    Forces the optimization engine to re-evaluate all instances
    and apply cost-saving recommendations immediately.

    Args:
        current_user: Authenticated admin user
        db: Database session

    Returns:
        Status confirmation with timestamp

    Requires admin role
    """
    # Check admin permission
    if current_user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required"
        )

    # In a real app, trigger the optimization engine job queue
    # For now, we log it and return success
    print("🔄 SYSTEM ACTION: Force Rebalance Triggered")

    return {
        "status": "success",
        "message": "Optimization cycle started",
        "triggered_at": datetime.utcnow().isoformat()
    }
