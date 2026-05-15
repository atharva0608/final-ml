"""
PodMetric model - Stores pod-level resource usage time-series data

This model stores high-frequency pod metrics collected by DaemonSet agents:
- CPU usage (millicores)
- Memory usage (bytes)
- CPU requests/limits
- Memory requests/limits

Used by Right-Sizing engine to calculate P95/P99 recommendations.
"""
from sqlalchemy import Column, String, Integer, Float, DateTime, ForeignKey, Index, BigInteger
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship
from datetime import datetime
from backend.models.base import Base, generate_uuid


class PodMetric(Base):
    """
    Pod-level resource usage metrics collected from DaemonSet agents.

    Data retention: 7 days (168 hours * 12 samples/hour = 2,016 data points per pod)
    Collection frequency: Every 5 minutes (12 samples/hour)
    """
    __tablename__ = "pod_metrics"

    # Primary key
    id = Column(String(36), primary_key=True, default=generate_uuid, index=True)

    # Foreign key to clusters
    cluster_id = Column(String(36), ForeignKey("clusters.id", ondelete="CASCADE"), nullable=False, index=True)

    # Pod identification
    namespace = Column(String(253), nullable=False, index=True)  # k8s max namespace length
    pod_name = Column(String(253), nullable=False, index=True)   # k8s max pod name length
    node_name = Column(String(253), nullable=False, index=True)  # Node where pod is running

    # Workload controller (for aggregation)
    controller_kind = Column(String(50), nullable=True, index=True)  # Deployment, StatefulSet, DaemonSet, Job
    controller_name = Column(String(253), nullable=True, index=True)

    # CPU metrics (millicores)
    cpu_usage_millicores = Column(Integer, nullable=False)         # Current CPU usage
    cpu_request_millicores = Column(Integer, nullable=True)        # CPU request (if set)
    cpu_limit_millicores = Column(Integer, nullable=True)          # CPU limit (if set)

    # Memory metrics (bytes)
    memory_usage_bytes = Column(BigInteger, nullable=False)        # Current memory usage
    memory_request_bytes = Column(BigInteger, nullable=True)       # Memory request (if set)
    memory_limit_bytes = Column(BigInteger, nullable=True)         # Memory limit (if set)

    # Utilization percentages (computed from usage/request)
    cpu_utilization_pct = Column(Float, nullable=True)             # usage / request * 100
    memory_utilization_pct = Column(Float, nullable=True)          # usage / request * 100

    # Pod phase and start time (T-12 — migration 20260427_pod_metrics_phase_starttime)
    phase = Column(String(20), nullable=True, index=True)
    start_time = Column(DateTime, nullable=True)

    # Container count
    container_count = Column(Integer, nullable=False, default=1)

    # Timestamp
    timestamp = Column(DateTime, nullable=False, default=datetime.utcnow, index=True)

    # Additional metadata (labels, annotations, etc.)
    pod_metadata = Column(JSONB, nullable=True, default={})

    # Relationships
    cluster = relationship("Cluster", back_populates="pod_metrics")

    # Indexes for efficient querying
    __table_args__ = (
        # Time-series queries by cluster
        Index("idx_pod_metric_cluster_time", "cluster_id", "timestamp"),

        # Queries by namespace + controller (for right-sizing aggregation)
        Index("idx_pod_metric_controller", "cluster_id", "namespace", "controller_kind", "controller_name", "timestamp"),

        # Queries by node (for node-level analysis)
        Index("idx_pod_metric_node_time", "cluster_id", "node_name", "timestamp"),

        # Unique pod queries (latest metric for a pod)
        Index("idx_pod_metric_pod_time", "cluster_id", "namespace", "pod_name", "timestamp"),

        # Phase filtering (T-12)
        Index("idx_pod_metric_phase", "cluster_id", "phase"),
    )

    def __repr__(self):
        return f"<PodMetric(cluster={self.cluster_id}, pod={self.namespace}/{self.pod_name}, cpu={self.cpu_usage_millicores}m, mem={self.memory_usage_bytes}, time={self.timestamp})>"

    @property
    def cpu_usage_cores(self) -> float:
        """Convert millicores to cores (e.g., 500m -> 0.5 cores)"""
        return self.cpu_usage_millicores / 1000.0

    @property
    def memory_usage_mb(self) -> float:
        """Convert bytes to MB"""
        return self.memory_usage_bytes / (1024 * 1024)

    @property
    def memory_usage_gb(self) -> float:
        """Convert bytes to GB"""
        return self.memory_usage_bytes / (1024 * 1024 * 1024)

    def to_dict(self):
        """Convert to dictionary for API responses"""
        return {
            "id": self.id,
            "cluster_id": self.cluster_id,
            "namespace": self.namespace,
            "pod_name": self.pod_name,
            "node_name": self.node_name,
            "controller_kind": self.controller_kind,
            "controller_name": self.controller_name,
            "cpu_usage_millicores": self.cpu_usage_millicores,
            "cpu_request_millicores": self.cpu_request_millicores,
            "cpu_limit_millicores": self.cpu_limit_millicores,
            "memory_usage_bytes": self.memory_usage_bytes,
            "memory_request_bytes": self.memory_request_bytes,
            "memory_limit_bytes": self.memory_limit_bytes,
            "cpu_utilization_pct": self.cpu_utilization_pct,
            "memory_utilization_pct": self.memory_utilization_pct,
            "container_count": self.container_count,
            "timestamp": self.timestamp.isoformat() if self.timestamp else None,
            "metadata": self.metadata
        }
