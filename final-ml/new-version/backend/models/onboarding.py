from sqlalchemy import Column, String, Enum, ForeignKey, DateTime
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
import enum
from datetime import datetime, timezone
from .base import Base
import uuid

class OnboardingStep(str, enum.Enum):
    WELCOME = "WELCOME"
    CONNECT_AWS = "CONNECT_AWS"
    VERIFYING = "VERIFYING"
    COMPLETED = "COMPLETED"

class ConnectionMode(str, enum.Enum):
    READ_ONLY = "READ_ONLY"
    FULL_ACCESS = "FULL_ACCESS"

class OnboardingState(Base):
    __tablename__ = "onboarding_states"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(String(36), ForeignKey("users.id"), unique=True, nullable=False)
    
    current_step = Column(Enum(OnboardingStep), default=OnboardingStep.WELCOME)
    external_id = Column(String, unique=True, nullable=False) # The secure random ID
    aws_role_arn = Column(String, nullable=True)
    aws_account_id = Column(String, nullable=True)
    connection_mode = Column(Enum(ConnectionMode), default=ConnectionMode.READ_ONLY)
    
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    # Relationship
    user = relationship("User", back_populates="onboarding_state")
