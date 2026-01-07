"""
User model - Platform users (clients and admins)
"""
from sqlalchemy import Column, String, DateTime, Enum as SQLEnum
from sqlalchemy.orm import relationship
from datetime import datetime
import enum
from backend.models.base import Base, generate_uuid


class UserRole(enum.Enum):
    """User role enumeration"""
    CLIENT = "client"
    SUPER_ADMIN = "super_admin"


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

    # Timestamps
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    accounts = relationship("Account", back_populates="user", cascade="all, delete-orphan")
    node_templates = relationship("NodeTemplate", back_populates="user", cascade="all, delete-orphan")

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
