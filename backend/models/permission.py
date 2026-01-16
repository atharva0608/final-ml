"""
Permission model - Defines granular capabilities in the system
"""
from sqlalchemy import Column, String, Text
from backend.models.base import Base, generate_uuid


class Permission(Base):
    """
    Permission model for fine-grained access control.
    
    Each permission represents a specific capability (e.g., "hygiene:execute").
    Permissions are linked to Roles via the role_permissions table.
    """
    __tablename__ = "permissions"

    # Primary key
    id = Column(String(36), primary_key=True, default=generate_uuid, index=True)

    # Slug (e.g., "hygiene:execute") - Unique Identifier Logic
    slug = Column(String(100), unique=True, index=True, nullable=False)
    
    # Human-readable name (e.g. "Execute Hygiene Scans")
    name = Column(String(200), nullable=False)
    
    # Module/Category for grouping in UI (e.g., "Resource Hygiene", "Billing")
    module = Column(String(50), nullable=False, index=True)
    
    # Human-readable description
    description = Column(Text, nullable=True)

    def __repr__(self):
        return f"<Permission(slug={self.slug}, module={self.module})>"
