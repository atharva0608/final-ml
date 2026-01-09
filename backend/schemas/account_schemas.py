from pydantic import BaseModel, Field, field_validator
from typing import List, Optional
from datetime import datetime
from backend.models.account import AccountStatus

class AccountCreate(BaseModel):
    """Create AWS account request"""
    aws_account_id: str = Field(..., min_length=12, max_length=12, pattern=r"^\d{12}$", description="AWS Account ID (12 digits)")
    role_arn: str = Field(..., pattern=r"^arn:aws:iam::\d{12}:role/.+$", description="Cross-account IAM role ARN")
    external_id: str = Field(..., min_length=6, description="External ID for security")

    model_config = {
        "json_schema_extra": {
            "example": {
                "aws_account_id": "123456789012",
                "role_arn": "arn:aws:iam::123456789012:role/SpotOptimizerRole",
                "external_id": "random-secure-string"
            }
        }
    }

class AccountUpdate(BaseModel):
    """Update AWS account request"""
    role_arn: Optional[str] = Field(None, pattern=r"^arn:aws:iam::\d{12}:role/.+$")
    external_id: Optional[str] = Field(None, min_length=6)
    status: Optional[str] = Field(None, description="Account status")

    @field_validator('status')
    @classmethod
    def validate_status(cls, v: Optional[str]) -> Optional[str]:
        if v and v not in ['PENDING', 'ACTIVE', 'ERROR']:
             raise ValueError('Status must be PENDING, ACTIVE, or ERROR')
        return v

class AccountResponse(BaseModel):
    """Account response model"""
    id: str
    user_id: str
    aws_account_id: str
    role_arn: str
    external_id: str
    status: str
    created_at: datetime
    updated_at: datetime

    model_config = {
        "from_attributes": True,
        "json_schema_extra": {
            "example": {
                "id": "uuid-string",
                "user_id": "user-uuid",
                "aws_account_id": "123456789012",
                "role_arn": "arn:aws:iam::123456789012:role/SpotOptimizerRole",
                "external_id": "secret123",
                "status": "ACTIVE",
                "created_at": "2026-01-01T00:00:00Z",
                "updated_at": "2026-01-01T00:00:00Z"
            }
        }
    }
