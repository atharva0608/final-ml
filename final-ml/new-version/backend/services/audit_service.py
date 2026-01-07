"""
Audit Service

Business logic for audit logging and compliance reporting
"""
from typing import List, Optional
from sqlalchemy.orm import Session
from sqlalchemy import and_, desc
from backend.models.audit_log import AuditLog, ResourceType, AuditOutcome
from backend.schemas.audit_schemas import (
    AuditLog as AuditLogSchema,
    AuditLogList,
    AuditLogFilter,
)
from backend.core.logger import StructuredLogger
from datetime import datetime

logger = StructuredLogger(__name__)


class AuditService:
    """Service for audit logging and querying"""

    def __init__(self, db: Session):
        self.db = db

    def create_audit_log(
        self,
        actor_id: str,
        actor_name: str,
        event: str,
        resource: str,
        resource_type: ResourceType,
        outcome: AuditOutcome,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
        diff_before: Optional[dict] = None,
        diff_after: Optional[dict] = None
    ) -> AuditLog:
        """
        Create an audit log entry

        Args:
            actor_id: User or system ID performing action
            actor_name: User email or system name
            event: Event type (e.g., "CLUSTER_CREATED", "POLICY_UPDATED")
            resource: Resource identifier
            resource_type: Type of resource
            outcome: SUCCESS or FAILURE
            ip_address: Client IP address
            user_agent: Client user agent
            diff_before: State before change (dict)
            diff_after: State after change (dict)

        Returns:
            AuditLog model
        """
        audit_entry = AuditLog(
            timestamp=datetime.utcnow(),
            actor_id=actor_id,
            actor_name=actor_name,
            event=event,
            resource=resource,
            resource_type=resource_type,
            outcome=outcome,
            ip_address=ip_address,
            user_agent=user_agent,
            diff_before=diff_before,
            diff_after=diff_after
        )

        self.db.add(audit_entry)
        self.db.commit()
        self.db.refresh(audit_entry)

        logger.info(
            "Audit log created",
            audit_id=audit_entry.id,
            event=event,
            actor=actor_name,
            outcome=outcome.value
        )

        return audit_entry

    def get_audit_logs(
        self,
        filters: AuditLogFilter
    ) -> AuditLogList:
        """
        Query audit logs with filters

        Args:
            filters: Filter criteria

        Returns:
            AuditLogList with paginated results
        """
        query = self.db.query(AuditLog)

        # Apply filters
        if filters.start_date:
            query = query.filter(AuditLog.timestamp >= filters.start_date)
        if filters.end_date:
            query = query.filter(AuditLog.timestamp <= filters.end_date)
        if filters.actor_id:
            query = query.filter(AuditLog.actor_id == filters.actor_id)
        if filters.event:
            query = query.filter(AuditLog.event == filters.event)
        if filters.resource_type:
            query = query.filter(AuditLog.resource_type == filters.resource_type)
        if filters.outcome:
            query = query.filter(AuditLog.outcome == filters.outcome)

        # Get total count
        total = query.count()

        # Apply pagination and ordering
        logs = query.order_by(desc(AuditLog.timestamp)).offset(
            (filters.page - 1) * filters.page_size
        ).limit(filters.page_size).all()

        # Convert to schemas
        log_schemas = [
            AuditLogSchema(
                id=log.id,
                timestamp=log.timestamp,
                actor_id=log.actor_id,
                actor_name=log.actor_name,
                event=log.event,
                resource=log.resource,
                resource_type=log.resource_type.value,
                outcome=log.outcome.value,
                ip_address=log.ip_address,
                user_agent=log.user_agent,
                diff_before=log.diff_before,
                diff_after=log.diff_after
            )
            for log in logs
        ]

        return AuditLogList(
            logs=log_schemas,
            total=total,
            page=filters.page,
            page_size=filters.page_size
        )

    def get_audit_log_by_id(self, audit_id: str) -> Optional[AuditLog]:
        """
        Get a specific audit log entry

        Args:
            audit_id: Audit log UUID

        Returns:
            AuditLog model or None
        """
        return self.db.query(AuditLog).filter(AuditLog.id == audit_id).first()


def get_audit_service(db: Session) -> AuditService:
    """Get audit service instance"""
    return AuditService(db)
