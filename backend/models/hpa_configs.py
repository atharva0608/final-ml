"""
HPA Configs DB Model — T-13
=============================
One row per HPA per cluster. Upserted on each agent heartbeat.
Also stores recommended_max/min populated by T-16 (hpa_recommendation_task).

Table: hpa_configs
Unique constraint: (cluster_id, namespace, workload_name)
"""

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
)

from backend.models.base import Base


class HpaConfig(Base):
    __tablename__ = "hpa_configs"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    cluster_id = Column(String(36), ForeignKey("clusters.id", ondelete="CASCADE"), nullable=False)
    namespace = Column(String(253), nullable=False)
    workload_name = Column(String(253), nullable=False)
    hpa_name = Column(String(253), nullable=True)

    min_replicas = Column(Integer, nullable=True)
    max_replicas = Column(Integer, nullable=True)
    target_cpu_pct = Column(Integer, nullable=True)
    current_replicas = Column(Integer, nullable=True)
    desired_replicas = Column(Integer, nullable=True)
    scale_up_stabilization_seconds = Column(Integer, nullable=True)
    scale_down_stabilization_seconds = Column(Integer, nullable=True)

    recommended_max_replicas = Column(Integer, nullable=True)
    recommended_min_replicas = Column(Integer, nullable=True)

    updated_at = Column(
        DateTime,
        nullable=False,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
    )

    __table_args__ = (
        UniqueConstraint(
            "cluster_id", "namespace", "workload_name",
            name="uq_hpa_configs_cluster_ns_workload",
        ),
    )

    def __repr__(self) -> str:
        return (
            f"<HpaConfig cluster_id={self.cluster_id!r} "
            f"workload={self.namespace}/{self.workload_name} "
            f"min={self.min_replicas} max={self.max_replicas}>"
        )
