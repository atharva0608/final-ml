"""
Execution State Model (Enterprise Remediation Phase 3)
=======================================================

Database model for durable state machine tracking.

Prevents Celery starvation and zombie resumption with:
- UNIQUE constraint on cluster_id (prevents split-brain)
- Terminal state cleanup (ARCHIVED, COMPLETED, FAILED, etc.)
- Retry tracking and idempotency keys

Enterprise Guardrails:
- Explicit UNIQUE(cluster_id) constraint via UPSERT semantics
- Resume logic: only act on state NOT IN ('COMPLETED', 'FAILED', 'ARCHIVED', 'PDB_BLOCKED', 'CIRCUIT_OPEN')
- Every state transition persists before scheduling next task
"""
from sqlalchemy import Column, String, DateTime, Integer, Text, Index, UniqueConstraint
from sqlalchemy.dialects.postgresql import ENUM
from datetime import datetime
import enum
from backend.models.base import Base, generate_uuid


class ExecutionStateEnum(enum.Enum):
    """Execution state machine states."""
    PENDING = "PENDING"
    VALIDATING = "VALIDATING"
    PREWARMING = "PREWARMING"
    DRAINING = "DRAINING"
    PROVISIONING = "PROVISIONING"
    READY = "READY"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    ARCHIVED = "ARCHIVED"
    PDB_BLOCKED = "PDB_BLOCKED"
    CIRCUIT_OPEN = "CIRCUIT_OPEN"
    ROLLBACK = "ROLLBACK"


class ExecutionState(Base):
    """
    Execution State Model.

    Durable state storage for async state-machine execution.
    Prevents Celery starvation and zombie resumption.
    """
    __tablename__ = "execution_state"

    # Primary key
    id = Column(String(36), primary_key=True, default=generate_uuid, index=True)

    # Cluster ID (UNIQUE constraint to prevent split-brain)
    cluster_id = Column(String(36), nullable=False, index=True)

    # State machine state
    state = Column(
        ENUM(ExecutionStateEnum, name="execution_state_enum"),
        nullable=False,
        default=ExecutionStateEnum.PENDING,
        index=True
    )

    # State transition tracking
    last_transition_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    retry_count = Column(Integer, nullable=False, default=0)

    # Idempotency and error handling
    idempotency_key = Column(String(255), nullable=False, unique=True, index=True)
    error_message = Column(Text, nullable=True)

    # Terminal state cleanup
    archived_at = Column(DateTime, nullable=True, index=True)  # When state was archived

    # Execution metadata
    target_node_name = Column(String(255), nullable=True)  # Target node for drain/provision
    substitute_instance_id = Column(String(255), nullable=True)  # Substitute instance ID

    # Timestamps
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Composite indexes and constraints
    __table_args__ = (
        UniqueConstraint('cluster_id', name='uq_execution_state_cluster_id'),  # Prevent split-brain
        Index("idx_state_archived", "state", "archived_at"),
        Index("idx_cluster_state", "cluster_id", "state"),
        Index("idx_active_executions", "state", "last_transition_at"),
    )

    def __repr__(self):
        return (
            f"<ExecutionState(cluster_id={self.cluster_id}, "
            f"state={self.state.value}, retry={self.retry_count})>"
        )

    @property
    def is_terminal(self) -> bool:
        """Check if state is terminal (no further transitions)."""
        return self.state in [
            ExecutionStateEnum.COMPLETED,
            ExecutionStateEnum.FAILED,
            ExecutionStateEnum.ARCHIVED,
            ExecutionStateEnum.PDB_BLOCKED,
            ExecutionStateEnum.CIRCUIT_OPEN
        ]

    @property
    def can_resume(self) -> bool:
        """Check if execution can be resumed (not terminal, not archived)."""
        return not self.is_terminal and self.archived_at is None

    def to_dict(self):
        """Convert to dictionary for API responses."""
        return {
            "id": self.id,
            "cluster_id": self.cluster_id,
            "state": self.state.value if self.state else None,
            "last_transition_at": self.last_transition_at.isoformat() if self.last_transition_at else None,
            "retry_count": self.retry_count,
            "idempotency_key": self.idempotency_key,
            "error_message": self.error_message,
            "archived_at": self.archived_at.isoformat() if self.archived_at else None,
            "target_node_name": self.target_node_name,
            "substitute_instance_id": self.substitute_instance_id,
            "is_terminal": self.is_terminal,
            "can_resume": self.can_resume,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }
