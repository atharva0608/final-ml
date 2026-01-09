from pydantic import BaseModel, Field
from typing import List, Optional, Any, Dict
from datetime import datetime

class ClientSummary(BaseModel):
    id: str
    email: str
    organization_name: Optional[str] = None
    total_clusters: int = 0
    total_instances: int = 0
    total_cost: float = 0.0
    is_active: bool = True
    created_at: datetime
    last_login: Optional[datetime] = None

class ClientFilter(BaseModel):
    search: Optional[str] = None
    is_active: Optional[bool] = None
    created_after: Optional[datetime] = None
    created_before: Optional[datetime] = None
    page: int = 1
    page_size: int = 50

class ClientStats(BaseModel):
    client_id: str
    savings_trend: List[Dict[str, Any]] = []
    active_policies: int = 0
    total_accounts: int = 0
    total_clusters: int = 0
    total_instances: int = 0
    running_instances: int = 0
    total_cost: float = 0.0

class UserManagement(BaseModel):
    id: str
    email: str
    full_name: Optional[str] = None
    is_active: bool
    role: str
    created_at: datetime
    updated_at: Optional[datetime] = None
    last_login: Optional[datetime] = None
    stats: Optional[ClientStats] = None

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

class OrganizationSummary(BaseModel):
    id: str
    name: str
    slug: str
    owner_email: Optional[str] = None
    total_users: int = 0
    total_clusters: int = 0
    total_instances: int = 0
    created_at: datetime
    is_active: bool = True

class OrganizationFilter(BaseModel):
    search: Optional[str] = None
    page: int = 1
    page_size: int = 50

class OrganizationList(BaseModel):
    organizations: List[OrganizationSummary]
    total: int
    page: int
    page_size: int

class BillingPlan(BaseModel):
    name: str
    price: str
    nodes: str
    clients: int
    status: str

class UpsellOpportunity(BaseModel):
    client: str
    plan: str
    usage: str
    nodes: str
    client_initial: str

class BillingStats(BaseModel):
    mrr: str
    mrr_growth: str
    active_subs: int
    subs_growth: str
    failed_charges: int

class BillingResponse(BaseModel):
    stats: BillingStats
    plans: List[BillingPlan]
    upsell_opportunities: List[UpsellOpportunity]

class SavingsPoint(BaseModel):
    name: str
    savings: float

class ActivityItem(BaseModel):
    id: int
    user: str
    action: str
    detail: str
    time: str
    type: str

class DashboardResponse(BaseModel):
    stats: PlatformStats
    savings_chart: List[SavingsPoint]
    activity_feed: List[ActivityItem]

