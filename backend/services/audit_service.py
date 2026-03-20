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
import hashlib
import json

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

        # Compute tamper-evidence checksum
        audit_entry.checksum = self._compute_checksum(audit_entry)

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

    def _compute_checksum(self, log: AuditLog) -> str:
        """
        Compute SHA-256 checksum for tamper evidence.
        Hash of critical fields that should never change after insertion.
        """
        payload = (
            f"{log.actor_id}|"
            f"{log.event}|"
            f"{log.resource}|"
            f"{log.timestamp.isoformat() if log.timestamp else ''}|"
            f"{json.dumps(log.diff_before, sort_keys=True, default=str) if log.diff_before else ''}|"
            f"{json.dumps(log.diff_after, sort_keys=True, default=str) if log.diff_after else ''}"
        )
        return hashlib.sha256(payload.encode('utf-8')).hexdigest()

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
        if filters.actor_role:
            query = query.join(User, AuditLog.actor_id == User.id).filter(User.role == filters.actor_role)
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

    # ── Task 4.1: Retention Policy ──────────────────────────────────────

    def enforce_retention_policy(self, retention_days: Optional[int] = None) -> dict:
        """
        Delete audit log entries older than retention_days.

        Reads default from SystemConfig key 'AUDIT_RETENTION_DAYS' (default 365).
        Returns count of deleted entries.
        """
        if retention_days is None:
            try:
                from backend.models.system_config import SystemConfig
                cfg = self.db.query(SystemConfig).filter(
                    SystemConfig.key == "AUDIT_RETENTION_DAYS"
                ).first()
                retention_days = int(cfg.value) if cfg and cfg.value else 365
            except Exception:
                retention_days = 365

        from datetime import timedelta
        cutoff = datetime.utcnow() - timedelta(days=retention_days)

        count = self.db.query(AuditLog).filter(
            AuditLog.timestamp < cutoff
        ).delete(synchronize_session='fetch')
        self.db.commit()

        logger.info(
            "Audit retention enforced",
            retention_days=retention_days,
            deleted_count=count,
            cutoff=cutoff.isoformat(),
        )
        return {
            "deleted": count,
            "retention_days": retention_days,
            "cutoff": cutoff.isoformat(),
        }

    # ── Task 4.1: Integrity Verification ────────────────────────────────

    def verify_integrity(self, hours: int = 24, limit: int = 1000) -> dict:
        """
        Re-compute checksums for recent audit logs and detect tampering.

        Args:
            hours: How far back to check (default 24h)
            limit: Max logs to check per run

        Returns:
            {"checked": int, "tampered": list[str], "ok": bool}
        """
        from datetime import timedelta
        since = datetime.utcnow() - timedelta(hours=hours)

        recent_logs = self.db.query(AuditLog).filter(
            AuditLog.timestamp >= since
        ).order_by(AuditLog.timestamp.desc()).limit(limit).all()

        tampered = []
        for log in recent_logs:
            expected = self._compute_checksum(log)
            if log.checksum and log.checksum != expected:
                tampered.append(log.id)
                logger.error(
                    "TAMPER DETECTED: audit log checksum mismatch",
                    audit_id=log.id,
                    expected=expected[:16],
                    actual=log.checksum[:16] if log.checksum else "None",
                )

        if tampered:
            logger.critical(
                f"INTEGRITY ALERT: {len(tampered)} tampered audit log(s) detected"
            )

        return {
            "checked": len(recent_logs),
            "tampered": tampered,
            "ok": len(tampered) == 0,
            "hours_checked": hours,
        }

    def get_retention_settings(self) -> dict:
        """Get current retention policy settings."""
        try:
            from backend.models.system_config import SystemConfig
            cfg = self.db.query(SystemConfig).filter(
                SystemConfig.key == "AUDIT_RETENTION_DAYS"
            ).first()
            days = int(cfg.value) if cfg and cfg.value else 365
        except Exception:
            days = 365
        return {"retention_days": days}

    def update_retention_settings(self, retention_days: int) -> dict:
        """Update retention policy days in SystemConfig."""
        from backend.models.system_config import SystemConfig
        cfg = self.db.query(SystemConfig).filter(
            SystemConfig.key == "AUDIT_RETENTION_DAYS"
        ).first()
        if cfg:
            cfg.value = str(retention_days)
        else:
            cfg = SystemConfig(key="AUDIT_RETENTION_DAYS", value=str(retention_days))
            self.db.add(cfg)
        self.db.commit()
        logger.info("Audit retention updated", retention_days=retention_days)
        return {"retention_days": retention_days, "updated": True}


def get_audit_service(db: Session) -> AuditService:
    """Get audit service instance"""
    return AuditService(db)

