from sqlalchemy import Column, String, Boolean, Integer, JSON, Enum as SAEnum, DateTime
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
import uuid

from backend.models.base import Base
from backend.schemas.hygiene_schemas import ResourceType, HygieneActionType

class HygienePolicy(Base):
    __tablename__ = "cleanup_policies"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    name = Column(String, nullable=False)
    description = Column(String, nullable=True)

    # Target Resource Scope
    resource_type = Column(SAEnum(ResourceType), nullable=False)
    region = Column(String, default="global")

    # Logic
    conditions = Column(JSON, nullable=False, default=dict)

    # Action
    action = Column(SAEnum(HygieneActionType), nullable=False, default=HygieneActionType.NOTIFY)

    # Priority (Higher number = Higher priority)
    priority = Column(Integer, default=100)

    # Status
    is_active = Column(Boolean, default=True)

    # Organization/User context
    organization_id = Column(String, nullable=True)
