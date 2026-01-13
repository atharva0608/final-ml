from sqlalchemy import Column, String, ForeignKey, DateTime, JSON
from sqlalchemy.orm import relationship
from datetime import datetime
import uuid
from backend.models.base import Base

class Team(Base):
    __tablename__ = "teams"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    name = Column(String(100), nullable=False)
    organization_id = Column(String(36), ForeignKey("organizations.id"), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Team-Specific Governance Configuration
    # Stores which actions require approval for members of this team
    # Example: {"CONNECT_ACCOUNT": true, "TERMINATE_INSTANCE": true, "DELETE_VOLUME": false}
    governance_config = Column(JSON, default=dict)

    # Relationships
    members = relationship("User", back_populates="team")
    organization = relationship("Organization", back_populates="teams")

