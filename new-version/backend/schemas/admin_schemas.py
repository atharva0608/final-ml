"""
Admin Schemas - Request/Response models for admin portal operations
"""
from pydantic import BaseModel, Field, EmailStr
from typing import List, Optional, Dict, Any
from datetime import datetime


class ClientListItem(BaseModel):
    """Single client in admin list view"""
    user_id: str = Field(..., description="User UUID")
    email: str = Field(..., description="User email")
    role: str = Field(..., description="User role (CLIENT or SUPER_ADMIN)")
    total_clusters: int = Field(..., ge=0, description="Number of clusters")
    total_nodes: int = Field(..., ge=0, description="Total number of nodes")
    monthly_cost: float = Field(..., ge=0, description="Monthly cost in USD")
    account_status: str = Field(..., description="Account status (ACTIVE, INACTIVE, SUSPENDED)")
    created_at: datetime = Field(..., description="Account creation timestamp")
    last_login: Optional[datetime] = Field(None, description="Last login timestamp")

    model_config = {
        "json_schema_extra": {
            "example": {
                "user_id": "550e8400-e29b-41d4-a716-446655440000",
                "email": "client@example.com",
                "role": "CLIENT",
                "total_clusters": 3,
                "total_nodes": 45,
                "monthly_cost": 5250.0,
                "account_status": "ACTIVE",
                "created_at": "2025-11-15T10:00:00Z",
                "last_login": "2025-12-31T08:30:00Z"
            }
        }
    }


class ClientList(BaseModel):
    """List of clients for admin view"""
    clients: List[ClientListItem] = Field(..., description="Array of clients")
    total: int = Field(..., ge=0, description="Total number of clients")
    page: int = Field(..., ge=1, description="Current page number")
    page_size: int = Field(..., ge=1, le=100, description="Number of clients per page")

    model_config = {
        "json_schema_extra": {
            "example": {
                "clients": [
                    {
                        "user_id": "550e8400-e29b-41d4-a716-446655440000",
                        "email": "client@example.com",
                        "role": "CLIENT",
                        "total_clusters": 3,
                        "total_nodes": 45,
                        "monthly_cost": 5250.0,
                        "account_status": "ACTIVE",
                        "created_at": "2025-11-15T10:00:00Z",
                        "last_login": "2025-12-31T08:30:00Z"
                    }
                ],
                "total": 1,
                "page": 1,
                "page_size": 50
            }
        }
    }


class ClientOrganization(BaseModel):
    """Detailed client organization view"""
    user_id: str = Field(..., description="User UUID")
    email: str = Field(..., description="User email")
    role: str = Field(..., description="User role")
    created_at: datetime = Field(..., description="Account creation timestamp")
    aws_accounts: List[Dict[str, Any]] = Field(..., description="Connected AWS accounts")
    clusters: List[Dict[str, Any]] = Field(..., description="Kubernetes clusters")
    templates: List[Dict[str, Any]] = Field(..., description="Node templates")
    total_monthly_cost: float = Field(..., ge=0, description="Total monthly cost")
    total_monthly_savings: float = Field(..., ge=0, description="Total monthly savings")

    model_config = {
        "json_schema_extra": {
            "example": {
                "user_id": "550e8400-e29b-41d4-a716-446655440000",
                "email": "client@example.com",
                "role": "CLIENT",
                "created_at": "2025-11-15T10:00:00Z",
                "aws_accounts": [
                    {
                        "account_id": "123456789012",
                        "status": "ACTIVE",
                        "clusters_count": 3
                    }
                ],
                "clusters": [
                    {
                        "cluster_id": "660e9500-f30c-52e5-b827-557766551111",
                        "name": "production-eks",
                        "nodes": 15,
                        "cost": 1750.0
                    }
                ],
                "templates": [
                    {"template_id": "770e8400-e29b-41d4-a716-446655440000", "name": "Production GP"}
                ],
                "total_monthly_cost": 5250.0,
                "total_monthly_savings": 1950.0
            }
        }
    }


class SystemHealth(BaseModel):
    """System health status"""
    status: str = Field(..., description="Overall system status (HEALTHY, DEGRADED, DOWN)")
    database_status: str = Field(..., description="Database connection status")
    redis_status: str = Field(..., description="Redis connection status")
    celery_worker_status: str = Field(..., description="Celery worker status")
    celery_beat_status: str = Field(..., description="Celery beat scheduler status")
    active_users_24h: int = Field(..., ge=0, description="Active users in last 24 hours")
    total_requests_24h: int = Field(..., ge=0, description="Total API requests in last 24 hours")
    avg_response_time_ms: float = Field(..., ge=0, description="Average response time in milliseconds")
    error_rate_24h: float = Field(..., ge=0, le=100, description="Error rate percentage in last 24 hours")

    model_config = {
        "json_schema_extra": {
            "example": {
                "status": "HEALTHY",
                "database_status": "CONNECTED",
                "redis_status": "CONNECTED",
                "celery_worker_status": "RUNNING",
                "celery_beat_status": "RUNNING",
                "active_users_24h": 45,
                "total_requests_24h": 12500,
                "avg_response_time_ms": 125.3,
                "error_rate_24h": 0.5
            }
        }
    }


class PlatformStats(BaseModel):
    """Platform-wide statistics"""
    total_users: int = Field(..., ge=0, description="Total registered users")
    total_clusters: int = Field(..., ge=0, description="Total clusters across all users")
    total_nodes: int = Field(..., ge=0, description="Total nodes across all clusters")
    total_spot_nodes: int = Field(..., ge=0, description="Total spot instances")
    platform_monthly_cost: float = Field(..., ge=0, description="Platform-wide monthly cost")
    platform_monthly_savings: float = Field(..., ge=0, description="Platform-wide monthly savings")
    total_optimizations_30d: int = Field(..., ge=0, description="Total optimizations in last 30 days")
    avg_savings_percentage: float = Field(..., ge=0, le=100, description="Average savings percentage")

    model_config = {
        "json_schema_extra": {
            "example": {
                "total_users": 150,
                "total_clusters": 425,
                "total_nodes": 6750,
                "total_spot_nodes": 5400,
                "platform_monthly_cost": 875000.0,
                "platform_monthly_savings": 325000.0,
                "total_optimizations_30d": 1250,
                "avg_savings_percentage": 27.1
            }
        }
    }


class UserAction(BaseModel):
    """Admin action on user account"""
    action: str = Field(..., description="Action type (SUSPEND, ACTIVATE, DELETE, RESET_PASSWORD)")
    reason: Optional[str] = Field(None, max_length=512, description="Reason for action")

    model_config = {
        "json_schema_extra": {
            "example": {
                "action": "SUSPEND",
                "reason": "Payment overdue for 30 days"
            }
        }
    }


class CreateUserRequest(BaseModel):
    """Create new user (admin only)"""
    email: EmailStr = Field(..., description="User email address")
    password: str = Field(..., min_length=8, max_length=128, description="User password")
    role: str = Field(..., description="User role (CLIENT or SUPER_ADMIN)")

    model_config = {
        "json_schema_extra": {
            "example": {
                "email": "newuser@example.com",
                "password": "SecurePass123",
                "role": "CLIENT"
            }
        }
    }


class ImpersonateRequest(BaseModel):
    """Impersonate user request (admin only)"""
    user_id: str = Field(..., description="User UUID to impersonate")
    reason: str = Field(..., min_length=10, max_length=512, description="Reason for impersonation")

    model_config = {
        "json_schema_extra": {
            "example": {
                "user_id": "550e8400-e29b-41d4-a716-446655440000",
                "reason": "Debug cluster optimization issue reported by user"
            }
        }
    }


class ImpersonateResponse(BaseModel):
    """Impersonate user response"""
    impersonation_token: str = Field(..., description="Temporary JWT token for impersonation")
    user_id: str = Field(..., description="Impersonated user UUID")
    user_email: str = Field(..., description="Impersonated user email")
    expires_in: int = Field(..., description="Token expiration time in seconds")

    model_config = {
        "json_schema_extra": {
            "example": {
                "impersonation_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
                "user_id": "550e8400-e29b-41d4-a716-446655440000",
                "user_email": "client@example.com",
                "expires_in": 3600
            }
        }
    }


class PasswordReset(BaseModel):
    """Password reset request (admin)"""
    new_password: str = Field(..., min_length=8, max_length=128, description="New password")

    model_config = {
        "json_schema_extra": {
            "example": {
                "new_password": "NewSecurePassword123!"
            }
        }
    }


class ClientStats(BaseModel):
    """Client usage statistics"""
    total_accounts: int = Field(..., ge=0, description="Number of cloud accounts")
    total_clusters: int = Field(..., ge=0, description="Number of clusters")
    total_instances: int = Field(..., ge=0, description="Total instances tracked")
    running_instances: int = Field(..., ge=0, description="Currently running instances")
    total_cost: float = Field(..., ge=0, description="Estimated monthly cost")

    model_config = {
        "json_schema_extra": {
            "example": {
                "total_accounts": 2,
                "total_clusters": 5,
                "total_instances": 50,
                "running_instances": 45,
                "total_cost": 4500.50
            }
        }
    }


class UserManagement(BaseModel):
    """Detailed user management view with stats"""
    id: str = Field(..., description="User UUID")
    email: str = Field(..., description="User email")
    role: str = Field(..., description="User role")
    is_active: bool = Field(..., description="Is user active")
    created_at: datetime = Field(..., description="Creation timestamp")
    updated_at: Optional[datetime] = Field(None, description="Last update timestamp")
    last_login: Optional[datetime] = Field(None, description="Last login timestamp")
    stats: ClientStats = Field(..., description="User usage statistics")

    model_config = {
        "json_schema_extra": {
            "example": {
                "id": "550e8400-e29b-41d4-a716-446655440000",
                "email": "client@example.com",
                "role": "CLIENT",
                "is_active": True,
                "created_at": "2025-11-01T10:00:00Z",
                "last_login": "2025-12-31T08:30:00Z",
                "stats": {
                    "total_accounts": 2,
                    "total_clusters": 5,
                    "total_instances": 50,
                    "running_instances": 45,
                    "total_cost": 4500.50
                }
            }
        }
    }


class ClientFilter(BaseModel):
    """Filter for checking client list"""
    search: Optional[str] = Field(None, description="Search by email or ID")
    is_active: Optional[bool] = Field(None, description="Filter by active status")
    created_after: Optional[datetime] = Field(None, description="Filter by creation date (after)")
    created_before: Optional[datetime] = Field(None, description="Filter by creation date (before)")


# Alias for backward compatibility or different views
ClientSummary = ClientListItem
