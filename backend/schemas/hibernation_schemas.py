"""Hibernation Schedule Schemas"""
from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
from datetime import datetime


class HibernationScheduleCreate(BaseModel):
    """Schema for creating a hibernation schedule"""
    name: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = None
    schedule_type: str = Field(default="WEEKLY")
    schedule_matrix: str = Field(..., description="Binary matrix: '0'=awake, '1'=sleep")
    date_overrides: Optional[Dict[str, int]] = Field(default_factory=dict)
    timezone: str = Field(default="UTC")
    pre_warm_minutes: int = Field(default=30, ge=0, le=120)
    strategy: str = Field(..., description="NAMESPACE_SLEEP, NUCLEAR, or SNAPSHOT_RESTORE")
    cluster_ids: List[str] = Field(..., min_items=1)
    is_active: bool = True


class HibernationScheduleUpdate(BaseModel):
    """Schema for updating a hibernation schedule"""
    name: Optional[str] = None
    description: Optional[str] = None
    schedule_type: Optional[str] = None
    schedule_matrix: Optional[str] = None
    date_overrides: Optional[Dict[str, int]] = None
    timezone: Optional[str] = None
    pre_warm_minutes: Optional[int] = None
    strategy: Optional[str] = None
    cluster_ids: Optional[List[str]] = None
    is_active: Optional[bool] = None


class ClusterInfo(BaseModel):
    """Cluster information in schedule response"""
    id: str
    name: str
    region: str


class HibernationScheduleResponse(BaseModel):
    """Schema for hibernation schedule response"""
    id: str
    name: str
    description: Optional[str]
    schedule_type: str
    schedule_matrix: str
    date_overrides: Dict[str, int]
    timezone: str
    pre_warm_minutes: int
    strategy: str
    is_active: str
    last_action: Optional[str]
    last_action_at: Optional[datetime]
    created_at: datetime
    updated_at: datetime
    clusters: List[ClusterInfo] = []

    class Config:
        from_attributes = True


class HibernationScheduleList(BaseModel):
    """List of hibernation schedules with pagination"""
    schedules: List[HibernationScheduleResponse]
    total: int
    page: int
    page_size: int


class StrategyComparisonResponse(BaseModel):
    """Comparison data for a hibernation strategy"""
    strategy: str
    name: str
    description: str
    savings_percentage: int
    wake_time_minutes: int
    risk_level: str


class SavingsEstimateResponse(BaseModel):
    """Estimated savings for a schedule"""
    sleep_hours_per_week: int
    awake_hours_per_week: int
    hourly_cost: float
    weekly_savings: float
    annual_savings: float
    savings_percentage: float


class ConflictCheckResponse(BaseModel):
    """Schedule conflict check result"""
    has_conflicts: bool
    conflicts: List[Dict[str, Any]]
