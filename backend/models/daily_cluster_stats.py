"""
Daily Cluster Stats model - Stores aggregated daily metrics per cluster
"""
from sqlalchemy import Column, String, Float, Integer, Date, ForeignKey, Index
from sqlalchemy.orm import relationship
from backend.models.base import Base, generate_uuid
import datetime

class DailyClusterStat(Base):
    __tablename__ = "daily_cluster_stats"

    id = Column(String(36), primary_key=True, default=generate_uuid, index=True)
    cluster_id = Column(String(36), ForeignKey("clusters.id", ondelete="CASCADE"), nullable=False, index=True)
    date_stamp = Column(Date, nullable=False, default=datetime.date.today, index=True)
    
    # Aggregated Stats
    total_cost = Column(Float, default=0.0)
    total_savings = Column(Float, default=0.0)
    spot_nodes = Column(Integer, default=0)
    on_demand_nodes = Column(Integer, default=0)
    total_nodes = Column(Integer, default=0)
    spot_ratio = Column(Float, default=0.0)
    
    # Optional performance stats
    avg_cpu_utilization = Column(Float, default=0.0)
    avg_memory_utilization = Column(Float, default=0.0)

    # Relationships
    cluster = relationship("Cluster")

    # Index by cluster and date together
    __table_args__ = (
        Index("idx_daily_stats_cluster_date", "cluster_id", "date_stamp", unique=True),
    )

    def __repr__(self):
        return f"<DailyClusterStat(cluster_id={self.cluster_id}, date={self.date_stamp})>"
