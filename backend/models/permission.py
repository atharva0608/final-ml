"""
Permission model - Defines granular capabilities in the system
"""
from sqlalchemy import Column, String, Text
from backend.models.base import Base


class Permission(Base):
    """
    Permission model for fine-grained access control.
    
    Each permission represents a specific capability (e.g., "hygiene:execute").
    Permissions are linked to Roles via the role_permissions table.
    """
    __tablename__ = "permissions"

    # Primary key is the slug itself (e.g., "hygiene:execute")
    slug = Column(String(100), primary_key=True, index=True)
    
    # Module/Category for grouping in UI (e.g., "Resource Hygiene", "Billing")
    module = Column(String(50), nullable=False, index=True)
    
    # Human-readable description
    description = Column(Text, nullable=True)

    def __repr__(self):
        return f"<Permission(slug={self.slug}, module={self.module})>"
