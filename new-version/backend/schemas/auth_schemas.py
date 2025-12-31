"""
Authentication Schemas - Request/Response models for auth flows
"""
from pydantic import BaseModel, Field, EmailStr, field_validator
from typing import Optional
from datetime import datetime
import re


class SignupRequest(BaseModel):
    """User signup request"""
    email: EmailStr = Field(..., description="User email address")
    password: str = Field(..., min_length=8, max_length=128, description="User password (min 8 characters)")

    @field_validator('password')
    @classmethod
    def validate_password_strength(cls, v: str) -> str:
        """Validate password strength"""
        if not re.search(r'[A-Z]', v):
            raise ValueError('Password must contain at least one uppercase letter')
        if not re.search(r'[a-z]', v):
            raise ValueError('Password must contain at least one lowercase letter')
        if not re.search(r'[0-9]', v):
            raise ValueError('Password must contain at least one digit')
        return v

    model_config = {
        "json_schema_extra": {
            "example": {
                "email": "user@example.com",
                "password": "SecurePass123"
            }
        }
    }


class LoginRequest(BaseModel):
    """User login request"""
    email: EmailStr = Field(..., description="User email address")
    password: str = Field(..., description="User password")

    model_config = {
        "json_schema_extra": {
            "example": {
                "email": "user@example.com",
                "password": "SecurePass123"
            }
        }
    }


class TokenResponse(BaseModel):
    """JWT token response"""
    access_token: str = Field(..., description="JWT access token")
    token_type: str = Field(default="bearer", description="Token type")
    expires_in: int = Field(..., description="Token expiration time in seconds")

    model_config = {
        "json_schema_extra": {
            "example": {
                "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
                "token_type": "bearer",
                "expires_in": 3600
            }
        }
    }


class UserContext(BaseModel):
    """User context extracted from JWT token"""
    user_id: str = Field(..., description="User UUID")
    email: str = Field(..., description="User email")
    role: str = Field(..., description="User role (CLIENT or SUPER_ADMIN)")

    model_config = {
        "json_schema_extra": {
            "example": {
                "user_id": "550e8400-e29b-41d4-a716-446655440000",
                "email": "user@example.com",
                "role": "CLIENT"
            }
        }
    }


class UserProfile(BaseModel):
    """User profile response"""
    id: str = Field(..., description="User UUID")
    email: str = Field(..., description="User email")
    role: str = Field(..., description="User role")
    created_at: datetime = Field(..., description="Account creation timestamp")

    model_config = {
        "json_schema_extra": {
            "example": {
                "id": "550e8400-e29b-41d4-a716-446655440000",
                "email": "user@example.com",
                "role": "CLIENT",
                "created_at": "2025-12-31T12:00:00Z"
            }
        }
    }


class PasswordChangeRequest(BaseModel):
    """Password change request"""
    old_password: str = Field(..., description="Current password")
    new_password: str = Field(..., min_length=8, max_length=128, description="New password")

    @field_validator('new_password')
    @classmethod
    def validate_password_strength(cls, v: str) -> str:
        """Validate password strength"""
        if not re.search(r'[A-Z]', v):
            raise ValueError('Password must contain at least one uppercase letter')
        if not re.search(r'[a-z]', v):
            raise ValueError('Password must contain at least one lowercase letter')
        if not re.search(r'[0-9]', v):
            raise ValueError('Password must contain at least one digit')
        return v

    model_config = {
        "json_schema_extra": {
            "example": {
                "old_password": "OldPass123",
                "new_password": "NewSecurePass456"
            }
        }
    }


class PasswordResetRequest(BaseModel):
    """Password reset request (forgot password)"""
    email: EmailStr = Field(..., description="User email address")

    model_config = {
        "json_schema_extra": {
            "example": {
                "email": "user@example.com"
            }
        }
    }


class PasswordResetConfirm(BaseModel):
    """Password reset confirmation with token"""
    token: str = Field(..., description="Password reset token")
    new_password: str = Field(..., min_length=8, max_length=128, description="New password")

    @field_validator('new_password')
    @classmethod
    def validate_password_strength(cls, v: str) -> str:
        """Validate password strength"""
        if not re.search(r'[A-Z]', v):
            raise ValueError('Password must contain at least one uppercase letter')
        if not re.search(r'[a-z]', v):
            raise ValueError('Password must contain at least one lowercase letter')
        if not re.search(r'[0-9]', v):
            raise ValueError('Password must contain at least one digit')
        return v

    model_config = {
        "json_schema_extra": {
            "example": {
                "token": "abc123def456",
                "new_password": "NewSecurePass456"
            }
        }
    }
