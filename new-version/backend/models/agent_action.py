"""
AgentAction model - Kubernetes action queue for Agent
"""
from sqlalchemy import Column, String, DateTime, ForeignKey, Enum as SQLEnum, Index, CheckConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship
from datetime import datetime, timedelta
import enum
from backend.models.base import Base, generate_uuid


class AgentActionType(enum.Enum):
    """Agent action type enumeration"""
    EVICT_POD = "evict_pod"
    CORDON_NODE = "cordon_node"
    DRAIN_NODE = "drain_node"
    LABEL_NODE = "label_node"
    UPDATE_DEPLOYMENT = "update_deployment"


class AgentActionStatus(enum.Enum):
    """Agent action status enumeration"""
    PENDING = "pending"
    PICKED_UP = "picked_up"
    COMPLETED = "completed"
    FAILED = "failed"
    EXPIRED = "expired"


class AgentAction(Base):
    """
    Agent Action model - Queue for Kubernetes actions

    Actions that must be executed by the Kubernetes Agent (not Boto3)
    Hybrid routing: AWS actions go to scripts/aws/*.py, K8s actions go here
    """
    __tablename__ = "agent_actions"

    # Primary key
    id = Column(String(36), primary_key=True, default=generate_uuid, index=True)

    # Foreign key to clusters
    cluster_id = Column(String(36), ForeignKey("clusters.id", ondelete="CASCADE"), nullable=False, index=True)

    # Action details
    action_type = Column(SQLEnum(AgentActionType), nullable=False, index=True)

    # Payload (JSONB) - action-specific parameters
    # Examples:
    # evict_pod: {"pod_name": "app-xyz-123", "namespace": "production", "grace_period": 30}
    # cordon_node: {"node_name": "ip-10-0-1-234.ec2.internal"}
    # drain_node: {"node_name": "ip-10-0-1-234.ec2.internal", "ignore_daemonsets": true}
    # label_node: {"node_name": "ip-10-0-1-234.ec2.internal", "labels": {"spot": "true"}}
    payload = Column(JSONB, nullable=False, default={})

    # Status tracking
    status = Column(SQLEnum(AgentActionStatus), nullable=False, default=AgentActionStatus.PENDING, index=True)

    # Timestamps
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow, index=True)
    expires_at = Column(DateTime, nullable=False, default=lambda: datetime.utcnow() + timedelta(hours=1), index=True)
    picked_up_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)

    # Result and error tracking
    result = Column(JSONB, nullable=True)  # Success result details
    error_message = Column(String(1024), nullable=True)  # Error message if failed

    # Relationships
    cluster = relationship("Cluster", back_populates="agent_actions")

    # Indexes for Agent polling and cleanup
    __table_args__ = (
        # Fast polling by Agent: GET /clusters/{id}/actions/pending
        Index("idx_agent_action_cluster_status", "cluster_id", "status"),
        # Cleanup of expired actions
        Index("idx_agent_action_expires", "expires_at"),
        # Chronological ordering
        Index("idx_agent_action_created", "created_at"),
        # Constraint: expires_at must be after created_at
        CheckConstraint("expires_at > created_at", name="check_expires_after_created"),
    )

    def __repr__(self):
        return f"<AgentAction(id={self.id}, type={self.action_type.value}, status={self.status.value}, cluster_id={self.cluster_id})>"
