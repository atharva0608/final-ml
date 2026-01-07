"""
Audit API Routes

Endpoints for querying audit logs and compliance reporting
"""
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from typing import Optional
from datetime import datetime
from backend.models.base import get_db
from backend.models.user import User
from backend.schemas.audit_schemas import (
    AuditLogList,
    AuditLogFilter,
    AuditLog as AuditLogSchema,
)
from backend.services.audit_service import get_audit_service
from backend.core.dependencies import get_current_user
from backend.core.exceptions import ResourceNotFoundError
from backend.core.logger import StructuredLogger

logger = StructuredLogger(__name__)

router = APIRouter(prefix="/audit", tags=["Audit Logs"])


@router.get(
    "",
    response_model=AuditLogList,
    summary="Get audit logs",
    description="Query audit logs with filters and pagination"
)
def get_audit_logs(
    start_date: Optional[datetime] = Query(None, description="Filter logs after this date"),
    end_date: Optional[datetime] = Query(None, description="Filter logs before this date"),
    event: Optional[str] = Query(None, description="Filter by event type"),
    resource_type: Optional[str] = Query(None, description="Filter by resource type"),
    outcome: Optional[str] = Query(None, description="Filter by outcome (SUCCESS/FAILURE)"),
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(50, ge=1, le=100, description="Items per page"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
) -> AuditLogList:
    """
    Get audit logs with optional filters

    Returns paginated audit log entries
    """
    filters = AuditLogFilter(
        start_date=start_date,
        end_date=end_date,
        event=event,
        resource_type=resource_type,
        outcome=outcome,
        page=page,
        page_size=page_size
    )

    service = get_audit_service(db)
    return service.get_audit_logs(filters)


@router.get(
    "/{audit_id}",
    response_model=AuditLogSchema,
    summary="Get audit log details",
    description="Get detailed information for a specific audit log entry"
)
def get_audit_log(
    audit_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
) -> AuditLogSchema:
    """
    Get audit log by ID

    Includes before/after diff data if available
    """
    service = get_audit_service(db)
    audit_log = service.get_audit_log_by_id(audit_id)

    if not audit_log:
        raise ResourceNotFoundError("AuditLog", audit_id)

    return AuditLogSchema(
        id=audit_log.id,
        timestamp=audit_log.timestamp,
        actor_id=audit_log.actor_id,
        actor_name=audit_log.actor_name,
        event=audit_log.event,
        resource=audit_log.resource,
        resource_type=audit_log.resource_type.value,
        outcome=audit_log.outcome.value,
        ip_address=audit_log.ip_address,
        user_agent=audit_log.user_agent,
        diff_before=audit_log.diff_before,
        diff_after=audit_log.diff_after
    )
