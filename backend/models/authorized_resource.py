from sqlalchemy import Column, String, DateTime, ForeignKey, Text
from sqlalchemy.orm import relationship
from datetime import datetime
from backend.models.base import Base, generate_uuid

class AuthorizedResource(Base):
    __tablename__ = "authorized_resources"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    resource_id = Column(String, nullable=False, index=True)  # e.g., i-12345
    account_id = Column(String(36), ForeignKey("accounts.id"), nullable=False)
    region = Column(String, nullable=False)
    resource_type = Column(String, nullable=False)  # INSTANCE, VOLUME, etc.
    
    notes = Column(Text, nullable=True)
    
    created_at = Column(DateTime, default=datetime.utcnow)
    created_by_id = Column(String(36), ForeignKey("users.id"), nullable=True)

    # Relationships
    account = relationship("Account", backref="authorized_resources")
    created_by = relationship("User")
