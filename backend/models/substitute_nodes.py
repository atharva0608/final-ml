"""
SubstituteNode model — tracks substitute nodes launched during rebalancing.
"""
from sqlalchemy import Column, String, DateTime, Enum
from backend.models.base import Base
from uuid import uuid4
from datetime import datetime
import enum


class SubstituteNodeState(enum.Enum):
    LAUNCHING = "LAUNCHING"
    READY = "READY"
    PROMOTING = "PROMOTING"
    TERMINATED = "TERMINATED"


class SubstituteNode(Base):
    __tablename__ = 'substitute_nodes'

    id = Column(String(36), primary_key=True, default=lambda: str(uuid4()))
    cluster_id = Column(String(36), nullable=False, index=True)
    instance_id = Column(String(50), nullable=True)
    instance_type = Column(String(50))
    az = Column(String(50))
    state = Column(Enum(SubstituteNodeState), default=SubstituteNodeState.LAUNCHING)
    node_name = Column(String(255), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    promoted_at = Column(DateTime, nullable=True)
