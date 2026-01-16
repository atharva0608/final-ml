"""
Role model - Database-driven roles with permission associations
"""
from sqlalchemy import Column, String, DateTime, Enum as SQLEnum, ForeignKey, Table
from sqlalchemy.orm import relationship
from datetime import datetime
import enum
from backend.models.base import Base, generate_uuid


class RoleType(str, enum.Enum):
    """Role type enumeration"""
    SYSTEM = "SYSTEM"   # Built-in roles (Admin, Team Lead, Member) - cannot be deleted
    CUSTOM = "CUSTOM"   # User-created roles - fully customizable


# Association table for Role <-> Permission many-to-many relationship
# Association table for Role <-> Permission many-to-many relationship
role_permissions = Table(
    'role_permissions',
    Base.metadata,
    Column('role_id', String(36), ForeignKey('roles.id', ondelete='CASCADE'), primary_key=True),
    Column('permission_id', String(36), ForeignKey('permissions.id', ondelete='CASCADE'), primary_key=True)
)


class Role(Base):
    """
    Role model for fine-grained access control.
    
    Supports both system-defined roles (immutable) and custom organization roles.
    Each role has a set of permissions that define what users with that role can do.
    """
    __tablename__ = "roles"

    # Primary key
    id = Column(String(36), primary_key=True, default=generate_uuid, index=True)
    
    # Role name (e.g., "Organization Admin", "Finance Viewer", "Junior Dev")
    name = Column(String(100), nullable=False)
    
    # Role type: SYSTEM (built-in, immutable) or CUSTOM (user-created)
    type = Column(SQLEnum(RoleType), nullable=False, default=RoleType.CUSTOM)
    
    # Organization link - NULL for system roles, set for custom roles
    organization_id = Column(String(36), ForeignKey("organizations.id", ondelete='CASCADE'), nullable=True, index=True)
    
    # Description of the role
    description = Column(String(500), nullable=True)
    
    # Timestamps
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    permissions = relationship("Permission", secondary=role_permissions, lazy="joined")
    organization = relationship("Organization", back_populates="custom_roles")
    users = relationship("User", back_populates="assigned_role")

    @property
    def is_system_role(self) -> bool:
        """Check if this is a system role (immutable)"""
        return self.type == RoleType.SYSTEM

    @property
    def permission_slugs(self) -> list:
        """Get list of permission slugs for this role"""
        return [p.slug for p in self.permissions]

    def has_permission(self, permission_slug: str) -> bool:
        """Check if this role has a specific permission"""
        return permission_slug in self.permission_slugs

    def __repr__(self):
        return f"<Role(id={self.id}, name={self.name}, type={self.type.value})>"
