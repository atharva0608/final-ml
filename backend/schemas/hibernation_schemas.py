"""
Hibernation Schemas - Request/Response models for hibernation schedule management
"""
from pydantic import BaseModel, Field, field_validator
from typing import List, Optional
from datetime import datetime


class ScheduleMatrix(BaseModel):
    """Weekly schedule matrix (168 hours)"""
    matrix: List[int] = Field(..., min_length=168, max_length=168, description="168-element array (0=sleep, 1=awake)")

    @field_validator('matrix')
    @classmethod
    def validate_matrix(cls, v: List[int]) -> List[int]:
        """Validate schedule matrix values"""
        if len(v) != 168:
            raise ValueError('Schedule matrix must have exactly 168 elements (7 days * 24 hours)')
        for i, val in enumerate(v):
            if val not in [0, 1]:
                raise ValueError(f'Matrix element at index {i} must be 0 or 1, got {val}')
        return v

    model_config = {
        "json_schema_extra": {
            "example": {
                "matrix": [0] * 48 + [1] * 72 + [0] * 48  # Sleep weekends, awake weekdays
            }
        }
    }


class HibernationScheduleCreate(BaseModel):
    """Create hibernation schedule request"""
    cluster_id: str = Field(..., description="Cluster UUID")
    schedule_type: str = Field(default="WEEKLY", description="Schedule type: WEEKLY, DAILY, MONTHLY, HYBRID")
    schedule_matrix: List[int] = Field(..., description="Schedule matrix (length varies by type: WEEKLY=168, DAILY=31, MONTHLY=744)")
    date_overrides: Optional[dict] = Field(default={}, description="Date-specific overrides for HYBRID mode: {'2026-12-25': 0}")
    timezone: str = Field(default="UTC", description="Timezone for schedule (e.g., 'America/New_York')")
    pre_warm_minutes: int = Field(default=15, ge=0, le=120, description="Minutes to pre-warm before wake")
    is_active: bool = Field(default=True, description="Whether schedule is active")
    strategy: str = Field(default="NAMESPACE_SLEEP", description="Hibernation strategy: NAMESPACE_SLEEP, NUCLEAR, SNAPSHOT_RESTORE")

    @field_validator('schedule_matrix')
    @classmethod
    def validate_schedule_matrix(cls, v: List[int], info) -> List[int]:
        """Validate schedule matrix based on schedule_type"""
        # Get schedule_type from the data being validated
        schedule_type = info.data.get('schedule_type', 'WEEKLY')

        # Expected lengths for each type
        expected_lengths = {
            'WEEKLY': 168,   # 7 days × 24 hours
            'DAILY': 31,     # 31 days
            'MONTHLY': 744,  # 31 days × 24 hours
            'HYBRID': 168    # Base weekly pattern
        }

        expected_len = expected_lengths.get(schedule_type, 168)

        if len(v) != expected_len:
            raise ValueError(f'Schedule matrix for {schedule_type} must have exactly {expected_len} elements, got {len(v)}')

        for i, val in enumerate(v):
            if val not in [0, 1]:
                raise ValueError(f'Matrix element at index {i} must be 0 or 1')
        return v

    @field_validator('timezone')
    @classmethod
    def validate_timezone(cls, v: str) -> str:
        """Validate timezone string"""
        try:
            import pytz
            pytz.timezone(v)
        except pytz.exceptions.UnknownTimeZoneError:
            raise ValueError(f'Invalid timezone: {v}')
        return v

    model_config = {
        "json_schema_extra": {
            "example": {
                "cluster_id": "550e8400-e29b-41d4-a716-446655440000",
                "schedule_matrix": [0] * 48 + [1] * 72 + [0] * 48,
                "timezone": "America/New_York",
                "pre_warm_minutes": 15,
                "is_active": True,
                "strategy": "NAMESPACE_SLEEP"
            }
        }
    }


class HibernationScheduleUpdate(BaseModel):
    """Update hibernation schedule request"""
    schedule_type: Optional[str] = Field(None, description="Schedule type: WEEKLY, DAILY, MONTHLY, HYBRID")
    schedule_matrix: Optional[List[int]] = Field(None, description="Schedule matrix (length varies by type)")
    date_overrides: Optional[dict] = Field(None, description="Date-specific overrides for HYBRID mode")
    timezone: Optional[str] = Field(None, description="Timezone for schedule")
    pre_warm_minutes: Optional[int] = Field(None, ge=0, le=120, description="Pre-warm minutes")
    is_active: Optional[bool] = Field(None, description="Whether schedule is active")
    strategy: Optional[str] = Field(None, description="Hibernation strategy: NAMESPACE_SLEEP, NUCLEAR, SNAPSHOT_RESTORE")

    @field_validator('schedule_matrix')
    @classmethod
    def validate_schedule_matrix(cls, v: Optional[List[int]], info) -> Optional[List[int]]:
        """Validate schedule matrix based on schedule_type"""
        if v is not None:
            # Get schedule_type if being updated, otherwise allow any valid length
            schedule_type = info.data.get('schedule_type')

            if schedule_type:
                expected_lengths = {
                    'WEEKLY': 168,
                    'DAILY': 31,
                    'MONTHLY': 744,
                    'HYBRID': 168
                }
                expected_len = expected_lengths.get(schedule_type, 168)
                if len(v) != expected_len:
                    raise ValueError(f'Schedule matrix for {schedule_type} must have exactly {expected_len} elements')

            # Validate values
            for i, val in enumerate(v):
                if val not in [0, 1]:
                    raise ValueError(f'Matrix element at index {i} must be 0 or 1')
        return v

    @field_validator('timezone')
    @classmethod
    def validate_timezone(cls, v: Optional[str]) -> Optional[str]:
        """Validate timezone string"""
        if v is not None:
            try:
                import pytz
                pytz.timezone(v)
            except pytz.exceptions.UnknownTimeZoneError:
                raise ValueError(f'Invalid timezone: {v}')
        return v

    model_config = {
        "json_schema_extra": {
            "example": {
                "pre_warm_minutes": 30,
                "is_active": False
            }
        }
    }


class HibernationScheduleResponse(BaseModel):
    """Hibernation schedule response"""
    id: str = Field(..., description="Schedule UUID")
    cluster_id: str = Field(..., description="Cluster UUID")
    schedule_type: str = Field(default="WEEKLY", description="Schedule type: WEEKLY, DAILY, MONTHLY, HYBRID")
    schedule_matrix: List[int] = Field(..., description="Schedule matrix (length varies by type)")
    date_overrides: Optional[dict] = Field(default={}, description="Date-specific overrides for HYBRID mode")
    timezone: str = Field(..., description="Timezone")
    pre_warm_minutes: int = Field(..., description="Pre-warm minutes")
    strategy: str = Field(default="NAMESPACE_SLEEP", description="Hibernation strategy")
    is_active: bool = Field(default=True, description="Whether schedule is active")
    last_action: Optional[str] = Field(None, description="Last action taken (SLEEP/WAKE/PREWARM/ERROR)")
    last_action_at: Optional[datetime] = Field(None, description="When last action was executed")
    created_at: datetime = Field(..., description="Creation timestamp")
    updated_at: datetime = Field(..., description="Last update timestamp")

    model_config = {
        "json_schema_extra": {
            "example": {
                "id": "bb0e8400-e29b-41d4-a716-446655440000",
                "cluster_id": "550e8400-e29b-41d4-a716-446655440000",
                "schedule_matrix": [0] * 48 + [1] * 72 + [0] * 48,
                "timezone": "America/New_York",
                "pre_warm_minutes": 15,
                "strategy": "NAMESPACE_SLEEP",
                "is_active": True,
                "last_action": None,
                "last_action_at": None,
                "created_at": "2025-12-31T10:00:00Z",
                "updated_at": "2025-12-31T10:00:00Z"
            }
        }
    }


class HibernationScheduleList(BaseModel):
    """List of hibernation schedules"""
    schedules: List[HibernationScheduleResponse] = Field(..., description="List of schedules")
    total: int = Field(..., description="Total number of schedules")
    page: int = Field(default=1, description="Current page")
    page_size: int = Field(default=20, description="Items per page")


class HibernationScheduleFilter(BaseModel):
    """Filter criteria for hibernation schedules"""
    cluster_id: Optional[str] = Field(None, description="Filter by cluster UUID")
    is_active: Optional[bool] = Field(None, description="Filter by active status")
    timezone: Optional[str] = Field(None, description="Filter by timezone")
    page: int = Field(default=1, ge=1, description="Page number")
    page_size: int = Field(default=20, ge=1, le=100, description="Items per page")


class ScheduleOverride(BaseModel):
    """One-time schedule override"""
    cluster_id: str = Field(..., description="Cluster UUID")
    start_time: datetime = Field(..., description="Override start time")
    end_time: datetime = Field(..., description="Override end time")
    state: int = Field(..., description="Desired state (0=sleep, 1=awake)")
    reason: Optional[str] = Field(None, max_length=255, description="Override reason")

    @field_validator('state')
    @classmethod
    def validate_state(cls, v: int) -> int:
        if v not in [0, 1]:
            raise ValueError('State must be 0 (sleep) or 1 (awake)')
        return v

    model_config = {
        "json_schema_extra": {
            "example": {
                "cluster_id": "550e8400-e29b-41d4-a716-446655440000",
                "start_time": "2025-12-31T20:00:00Z",
                "end_time": "2025-12-31T23:00:00Z",
                "state": 1,
                "reason": "Emergency deployment"
            }
        }
    }


class SchedulePreview(BaseModel):
    """Preview schedule for date range"""
    date: str = Field(..., description="Date (YYYY-MM-DD)")
    hours: List[int] = Field(..., min_length=24, max_length=24, description="24-hour schedule for this date")

    model_config = {
        "json_schema_extra": {
            "example": {
                "date": "2025-12-31",
                "hours": [0, 0, 0, 0, 0, 0, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 0, 0, 0, 0, 0]
            }
        }
    }


class SchedulePreviewResponse(BaseModel):
    """Schedule preview response"""
    cluster_id: str = Field(..., description="Cluster UUID")
    timezone: str = Field(..., description="Timezone")
    preview: List[SchedulePreview] = Field(..., description="Daily schedule preview")

    model_config = {
        "json_schema_extra": {
            "example": {
                "cluster_id": "550e8400-e29b-41d4-a716-446655440000",
                "timezone": "America/New_York",
                "preview": [
                    {
                        "date": "2025-12-31",
                        "hours": [0, 0, 0, 0, 0, 0, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 0, 0, 0, 0, 0]
                    }
                ]
            }
        }
    }


class ManualOverrideRequest(BaseModel):
    """Manual sleep/wake override request"""
    action: str = Field(..., description="Action to perform: SLEEP or WAKE")
    duration_minutes: Optional[int] = Field(None, ge=1, le=1440, description="Override duration in minutes (optional)")

    @field_validator('action')
    @classmethod
    def validate_action(cls, v: str) -> str:
        if v.upper() not in ['SLEEP', 'WAKE']:
            raise ValueError('Action must be SLEEP or WAKE')
        return v.upper()


class StrategyInfo(BaseModel):
    """Information about a hibernation strategy"""
    name: str = Field(..., description="Strategy identifier")
    display_name: str = Field(..., description="Human-readable name")
    description: str = Field(..., description="Strategy description")
    wake_time: str = Field(..., description="Estimated wake time")
    savings_pct: int = Field(..., description="Estimated savings percentage")
    safety: str = Field(..., description="Safety level: LOW, MEDIUM, HIGH")
    best_for: str = Field(..., description="Best use case")


class StrategyComparisonResponse(BaseModel):
    """Strategy comparison response"""
    strategies: List[StrategyInfo] = Field(..., description="Available strategies")
