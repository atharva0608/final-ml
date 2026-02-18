from sqlalchemy import Column, String, ForeignKey, Table
from backend.models.base import Base

hibernation_schedule_clusters = Table(
    "hibernation_schedule_clusters",
    Base.metadata,
    Column("schedule_id", String, ForeignKey("hibernation_schedules.id"), primary_key=True),
    Column("cluster_id", String, ForeignKey("clusters.id"), primary_key=True)
)
