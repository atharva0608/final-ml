from pydantic import BaseModel, Field
from typing import List, Optional, Any, Dict
from datetime import datetime

class ClientSummary(BaseModel):
    id: str
    email: str
    organization_name: str
    status: str
    total_clusters: int = 0
    total_savings: float = 0.0
    is_active: bool = True
    created_at: datetime

class ClientFilter(BaseModel):
    search: Optional[str] = None
    is_active: Optional[bool] = None
    created_after: Optional[datetime] = None
    created_before: Optional[datetime] = None
    page: int = 1
    page_size: int = 50

class ClientStats(BaseModel):
    client_id: str
    savings_trend: List[Dict[str, Any]]
    active_policies: int

class UserManagement(BaseModel):
    user_id: str
    email: str
    full_name: str
    status: str
    role: str
    created_at: datetime
    last_login: Optional[datetime] = None
    stats: Optional[Dict[str, Any]] = None

class PasswordReset(BaseModel):
    new_password: str

class PlatformStats(BaseModel):
    total_users: int
    total_clusters: int
    total_savings: float
    active_experiments: int

class ClientListItem(ClientSummary): pass

class ClientList(BaseModel):
    clients: List[ClientSummary]
    total: int

class ClientOrganization(BaseModel):
    id: str
    name: str
    domain: Optional[str] = None
    settings: Dict[str, Any] = {}

class SystemHealth(BaseModel):
    status: str
    version: str
    uptime: float
    services: Dict[str, Any]

class UserAction(BaseModel):
    action: str
    target_user_id: str
    reason: Optional[str] = None

class CreateUserRequest(BaseModel):
    email: str
    password: str
    full_name: str
    organization_id: Optional[str] = None
    role: str = "client"

class ImpersonateRequest(BaseModel):
    user_id: str

class ImpersonateResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
