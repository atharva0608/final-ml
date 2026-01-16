"""
User model - Platform users (clients and admins)
"""
from sqlalchemy import Column, String, DateTime, Enum as SQLEnum, Boolean, ForeignKey, Table
from sqlalchemy.orm import relationship
from datetime import datetime
import enum
from backend.models.base import Base, generate_uuid


# Association table for User <-> Permission (Custom/Direct Permissions)
user_permissions = Table(
    'user_permissions',
    Base.metadata,
    Column('user_id', String(36), ForeignKey('users.id', ondelete='CASCADE'), primary_key=True),
    Column('permission_id', String(36), ForeignKey('permissions.id', ondelete='CASCADE'), primary_key=True)
)



class UserRole(str, enum.Enum):
    """User role enumeration"""
    SUPER_ADMIN = "SUPER_ADMIN"     # Platform Owner
    ORG_ADMIN = "ORG_ADMIN"         # Organization Owner
    TEAM_LEAD = "TEAM_LEAD"         # Can approve actions
    MEMBER = "MEMBER"               # Needs approval for critical actions
    CLIENT = "CLIENT"               # Legacy support, maps to ORG_ADMIN usually

# OrgRole is now redundant but kept for DB compatibility if needed, though AccessLevel covers permissions.
# We will primarily use UserRole for the new RBAC system.


class AccessLevel(enum.Enum):
    """Access level enumeration"""
    READ_ONLY = "READ_ONLY"
    EXECUTION = "EXECUTION"
    FULL = "FULL"


class UserStatus(str, enum.Enum):
    """User status enumeration"""
    ACTIVE = "ACTIVE"
    PENDING_INVITE = "PENDING_INVITE"


class User(Base):
    """
    User model for authentication and authorization

    Represents both client users and super admin users
    """
    __tablename__ = "users"

    # Primary key
    id = Column(String(36), primary_key=True, default=generate_uuid, index=True)

    # Authentication fields
    email = Column(String(255), unique=True, nullable=False, index=True)
    password_hash = Column(String(255), nullable=False)

    # Role
    role = Column(SQLEnum(UserRole), nullable=False, default=UserRole.CLIENT)
    is_active = Column(String(1), nullable=False, default="Y")

    # Organization Link
    organization_id = Column(String(36), ForeignKey("organizations.id"), nullable=True)
    # org_role = Column(SQLEnum(OrgRole), default=OrgRole.MEMBER) # Deprecated in favor of role
    access_level = Column(SQLEnum(AccessLevel), default=AccessLevel.READ_ONLY)
    
    # Optional: Link specific users to a "Team" within an Org
    team_id = Column(String(36), ForeignKey("teams.id"), nullable=True)
    full_name = Column(String(100), nullable=True) # For "Enter Name" requirement
    
    # Fine-Grained RBAC: Link to database-driven Role
    role_id = Column(String(36), ForeignKey("roles.id"), nullable=True)
    
    # Password reset enforcement for invited users
    must_reset_password = Column(Boolean, default=False, nullable=False)

    # Status: ACTIVE vs PENDING_INVITE
    status = Column(String(20), default="ACTIVE", nullable=False)

    # Timestamps
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    team = relationship("Team", back_populates="members")
    organization = relationship("Organization", back_populates="users")
    assigned_role = relationship("Role", back_populates="users")
    accounts = relationship("Account", back_populates="user", cascade="all, delete-orphan")
    node_templates = relationship("NodeTemplate", back_populates="user", cascade="all, delete-orphan")
    onboarding_state = relationship("OnboardingState", uselist=False, back_populates="user", cascade="all, delete-orphan")

    # Direct/Custom Permissions (overrides or adds to Role)
    custom_permissions = relationship("Permission", secondary=user_permissions, lazy="joined")

    @property
    def aws_accounts_count(self) -> int:
        return len(self.accounts) if self.accounts else 0

    # Onboarding status
    onboarding_completed = Column(Boolean, default=False)

    def __repr__(self):
        return f"<User(id={self.id}, email={self.email}, role={self.role.value})>"

    def verify_password(self, password: str) -> bool:
        """
        Verify password against stored hash

        Args:
            password: Plain text password

        Returns:
            True if password matches, False otherwise
        """
        from passlib.context import CryptContext
        pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
        return pwd_context.verify(password, self.password_hash)

    @staticmethod
    def hash_password(password: str) -> str:
        """
        Hash a password using bcrypt

        Args:
            password: Plain text password

        Returns:
            Hashed password
        """
        from passlib.context import CryptContext
        pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
        return pwd_context.hash(password)
