"""
ClusterMetric model - Stores metrics collected from agents
"""
from sqlalchemy import Column, String, DateTime, ForeignKey, Index
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship
from datetime import datetime
from backend.models.base import Base, generate_uuid


class ClusterMetric(Base):
    """
    Cluster Metric model - Stores pod, node, and event metrics from agents

    Metrics are collected by agents and sent in batches to the backend.
    This model stores both current state and historical metrics.
    """
    __tablename__ = "cluster_metrics"

    # Primary key
    id = Column(String(36), primary_key=True, default=generate_uuid, index=True)

    # Foreign key to clusters
    cluster_id = Column(String(36), ForeignKey("clusters.id", ondelete="CASCADE"), nullable=False, index=True)

    # Metric type (pod, node, event, aggregated)
    metric_type = Column(String(50), nullable=False, index=True)

    # Metric data (JSONB) - flexible storage for different metric types
    # Examples:
    # pod: {"namespace": "default", "pod_name": "app-123", "cpu_usage_millicores": 100, "memory_usage_bytes": 104857600}
    # node: {"node_name": "node-1", "cpu_usage_millicores": 1000, "memory_usage_bytes": 2147483648}
    # event: {"type": "Warning", "reason": "FailedScheduling", "message": "..."}
    # aggregated: {"pod_count": 50, "node_count": 3, "pod_metrics": [...], "node_metrics": [...]}
    metric_data = Column(JSONB, nullable=False, default={})

    # Timestamp
    timestamp = Column(DateTime, nullable=False, default=datetime.utcnow, index=True)

    # Relationships
    cluster = relationship("Cluster", back_populates="metrics")

    # Indexes for querying metrics
    __table_args__ = (
        # Fast lookups by cluster and time range
        Index("idx_cluster_metric_cluster_time", "cluster_id", "timestamp"),
        # Fast lookups by metric type
        Index("idx_cluster_metric_type_time", "metric_type", "timestamp"),
        # Composite index for cluster + type queries
        Index("idx_cluster_metric_cluster_type", "cluster_id", "metric_type"),
    )

    def __repr__(self):
        return f"<ClusterMetric(id={self.id}, cluster_id={self.cluster_id}, type={self.metric_type}, timestamp={self.timestamp})>"
