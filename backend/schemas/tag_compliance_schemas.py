"""
Tag Compliance Pydantic Schemas
"""
from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime


class ComplianceDistribution(BaseModel):
    """Status distribution entry"""
    status: str
    count: int
    pct: float


class ComplianceSummaryResponse(BaseModel):
    """Aggregate compliance summary"""
    total: int = 0
    compliant: int = 0
    passing: int = 0
    review: int = 0
    critical: int = 0
    deletion: int = 0
    cost_at_risk: float = 0.0
    distribution: List[ComplianceDistribution] = []
    last_scan_at: Optional[datetime] = None


class ComplianceResourceEntry(BaseModel):
    """Single resource in compliance list"""
    id: str
    resource_id: str
    resource_name: Optional[str] = None
    resource_type: str
    score: int
    status: str
    tags_present: int = 0
    monthly_cost: float = 0.0
    grace_deadline: Optional[datetime] = None
    days_left: Optional[int] = None
    team: Optional[str] = None
    environment: Optional[str] = None
    scanned_at: datetime

    class Config:
        from_attributes = True


class ComplianceResourceListResponse(BaseModel):
    """Paginated compliance resource list"""
    resources: List[ComplianceResourceEntry]
    total: int
    page: int
    per_page: int


class HeatmapEntry(BaseModel):
    """Coverage percentage for a single tag key"""
    key: str
    coverage_pct: float


class HeatmapResponse(BaseModel):
    """Tag coverage heatmap"""
    entries: List[HeatmapEntry] = []
