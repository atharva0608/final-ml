"""
User model - Platform users (clients and admins)
"""
from sqlalchemy import Column, String, DateTime, Enum as SQLEnum, Boolean, ForeignKey
from sqlalchemy.orm import relationship
from datetime import datetime
import enum
from backend.models.base import Base, generate_uuid


class UserRole(enum.Enum):
    """User role enumeration"""
    CLIENT = "CLIENT"
    SUPER_ADMIN = "SUPER_ADMIN"


class OrgRole(enum.Enum):
    """Organization role enumeration"""
    ORG_ADMIN = "ORG_ADMIN"
    TEAM_LEAD = "TEAM_LEAD"
    MEMBER = "MEMBER"


class AccessLevel(enum.Enum):
    """Access level enumeration"""
    READ_ONLY = "READ_ONLY"
    EXECUTION = "EXECUTION"
    FULL = "FULL"


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
    org_role = Column(SQLEnum(OrgRole), default=OrgRole.MEMBER)
    access_level = Column(SQLEnum(AccessLevel), default=AccessLevel.READ_ONLY)
    
    # Password reset enforcement for invited users
    must_reset_password = Column(Boolean, default=False, nullable=False)

    # Timestamps
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    organization = relationship("Organization", back_populates="users")
    # accounts = relationship("Account", back_populates="user", cascade="all, delete-orphan") # Moving to Organization
    node_templates = relationship("NodeTemplate", back_populates="user", cascade="all, delete-orphan")
    onboarding_state = relationship("OnboardingState", uselist=False, back_populates="user", cascade="all, delete-orphan")

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
