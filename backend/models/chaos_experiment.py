"""
Chaos Experiment Model (Enterprise Remediation Phase 9)
========================================================

Tracks chaos testing experiments with results, safety guardrails, and audit trail.

Enterprise Guardrails:
- Chaos MUST be disabled in production by default
- Require explicit opt-in per cluster
- Auto-rollback if error rate > 10%
- Maximum blast radius: single cluster
- Require manual approval for production chaos
"""
from sqlalchemy import Column, String, DateTime, ForeignKey, Enum, Text, Boolean, Integer, JSON, Float
from sqlalchemy.orm import relationship
from datetime import datetime
import enum
from backend.models.base import Base


class ChaosExperimentType(enum.Enum):
    """Chaos experiment types"""
    REDIS_FLUSH = "REDIS_FLUSH"                        # Simulate Redis flush
    DB_CONNECTION_LOSS = "DB_CONNECTION_LOSS"          # Simulate DB connection failure
    API_LATENCY = "API_LATENCY"                        # Inject artificial latency
    SPOT_INTERRUPTION = "SPOT_INTERRUPTION"            # Simulate spot termination notice
    PRICING_OUTAGE = "PRICING_OUTAGE"                  # Simulate AWS Pricing API failure
    POOL_BLACKLIST = "POOL_BLACKLIST"                  # Blacklist 60% of pools
    KARPENTER_SLOW = "KARPENTER_SLOW"                  # Slow Karpenter provisioning
    PDB_DEADLOCK = "PDB_DEADLOCK"                      # PodDisruptionBudget deadlock
    CELERY_CRASH = "CELERY_CRASH"                      # Worker crash simulation
    NETWORK_PARTITION = "NETWORK_PARTITION"            # Network partition simulation


class ChaosExperimentStatus(enum.Enum):
    """Chaos experiment execution status"""
    PENDING = "PENDING"                                # Scheduled but not started
    RUNNING = "RUNNING"                                # Currently executing
    COMPLETED = "COMPLETED"                            # Successfully completed
    FAILED = "FAILED"                                  # Failed to complete
    ROLLED_BACK = "ROLLED_BACK"                        # Auto-rolled back due to high error rate
    CANCELLED = "CANCELLED"                            # Manually cancelled


class ChaosExperiment(Base):
    """
    Chaos experiment tracking with safety guardrails and observability.

    Tracks chaos testing experiments to validate system resilience.
    """
    __tablename__ = "chaos_experiments"

    id = Column(String, primary_key=True)
    cluster_id = Column(String, ForeignKey("clusters.id"), nullable=True)  # Null = platform-wide
    organization_id = Column(String, ForeignKey("organizations.id"), nullable=False)

    # Experiment Configuration
    experiment_type = Column(Enum(ChaosExperimentType), nullable=False)
    status = Column(Enum(ChaosExperimentStatus), default=ChaosExperimentStatus.PENDING)

    # Safety Settings
    is_production_enabled = Column(Boolean, default=False)  # MUST be false by default
    requires_manual_approval = Column(Boolean, default=True)
    approved_by_user_id = Column(String, ForeignKey("users.id"), nullable=True)
    approved_at = Column(DateTime, nullable=True)

    # Blast Radius Control
    max_affected_clusters = Column(Integer, default=1)  # Enterprise guardrail: single cluster
    max_error_rate_threshold = Column(Float, default=0.10)  # Auto-rollback if > 10%
    max_duration_minutes = Column(Integer, default=5)  # Maximum experiment duration

    # Experiment Parameters (JSON)
    parameters = Column(JSON, default={})
    # Example parameters:
    # - REDIS_FLUSH: {"flush_all": true}
    # - API_LATENCY: {"target_endpoint": "/api/v1/clusters", "latency_ms": 5000}
    # - POOL_BLACKLIST: {"blacklist_percentage": 60}
    # - SPOT_INTERRUPTION: {"instance_ids": ["i-123", "i-456"]}

    # Execution Tracking
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    duration_seconds = Column(Float, nullable=True)

    # Results & Metrics
    result_summary = Column(JSON, default={})
    # Example result_summary:
    # {
    #   "error_rate": 0.05,
    #   "execution_state_created": 0,
    #   "clusters_marked_stale": 3,
    #   "alerts_emitted": 1,
    #   "api_requests_total": 1000,
    #   "api_requests_failed": 50,
    #   "rollback_triggered": false,
    #   "deterministic_assertions_passed": true
    # }

    # Observability Metrics
    metrics_snapshot = Column(JSON, default={})
    # Example metrics:
    # {
    #   "cpu_usage_before": 45.2,
    #   "cpu_usage_during": 78.5,
    #   "cpu_usage_after": 46.1,
    #   "memory_usage_before": 62.3,
    #   "memory_usage_during": 88.7,
    #   "memory_usage_after": 63.5,
    #   "redis_keys_before": 15000,
    #   "redis_keys_after": 0,
    #   "db_connections_before": 18,
    #   "db_connections_during": 5,
    #   "api_latency_p95_before": 150,
    #   "api_latency_p95_during": 5200
    # }

    # Rollback Information
    rollback_triggered = Column(Boolean, default=False)
    rollback_reason = Column(Text, nullable=True)
    rollback_completed_at = Column(DateTime, nullable=True)

    # Audit Trail
    error_logs = Column(JSON, default=[])  # Array of error messages during experiment
    execution_logs = Column(JSON, default=[])  # Step-by-step execution log

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    cluster = relationship("Cluster", foreign_keys=[cluster_id])
    organization = relationship("Organization")
    approved_by = relationship("User", foreign_keys=[approved_by_user_id])
