"""
Settings Schemas
Request/Response models for user settings and integrations
"""
from pydantic import BaseModel, Field, EmailStr
from typing import Optional, List, Dict, Any
from datetime import datetime
from enum import Enum

class UserProfileUpdate(BaseModel):
    """Request to update user profile"""
    email: Optional[EmailStr] = Field(None, description="New email address")
    # Add fields here if User model is extended (e.g. first_name, last_name)

class IntegrationType(str, Enum):
    """Supported integration types"""
    SLACK = "SLACK"
    DATADOG = "DATADOG"
    PAGERDUTY = "PAGERDUTY"

class IntegrationStatus(str, Enum):
    """Integration status"""
    ACTIVE = "ACTIVE"
    INACTIVE = "INACTIVE"
    ERROR = "ERROR"

class Integration(BaseModel):
    """Integration details"""
    id: str
    type: IntegrationType
    name: str
    status: IntegrationStatus
    created_at: datetime
    config: Dict[str, Any] = Field(default_factory=dict, description="Integration configuration (masked)")

class IntegrationCreate(BaseModel):
    """Request to add integration"""
    type: IntegrationType
    name: str
    config: Dict[str, Any]

class IntegrationList(BaseModel):
    """List of integrations"""
    items: List[Integration]
    total: int
