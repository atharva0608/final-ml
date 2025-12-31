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
    schedule_matrix: List[int] = Field(..., min_length=168, max_length=168, description="168-hour schedule")
    timezone: str = Field(default="UTC", description="Timezone for schedule (e.g., 'America/New_York')")
    prewarm_enabled: bool = Field(default=False, description="Enable pre-warming before wake time")
    prewarm_minutes: int = Field(default=30, ge=0, le=120, description="Minutes to pre-warm before wake")

    @field_validator('schedule_matrix')
    @classmethod
    def validate_schedule_matrix(cls, v: List[int]) -> List[int]:
        """Validate schedule matrix"""
        if len(v) != 168:
            raise ValueError('Schedule matrix must have exactly 168 elements')
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
                "prewarm_enabled": True,
                "prewarm_minutes": 30
            }
        }
    }


class HibernationScheduleUpdate(BaseModel):
    """Update hibernation schedule request"""
    schedule_matrix: Optional[List[int]] = Field(None, min_length=168, max_length=168, description="168-hour schedule")
    timezone: Optional[str] = Field(None, description="Timezone for schedule")
    prewarm_enabled: Optional[bool] = Field(None, description="Enable pre-warming")
    prewarm_minutes: Optional[int] = Field(None, ge=0, le=120, description="Pre-warm minutes")

    @field_validator('schedule_matrix')
    @classmethod
    def validate_schedule_matrix(cls, v: Optional[List[int]]) -> Optional[List[int]]:
        """Validate schedule matrix"""
        if v is not None:
            if len(v) != 168:
                raise ValueError('Schedule matrix must have exactly 168 elements')
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
                "prewarm_enabled": True,
                "prewarm_minutes": 45
            }
        }
    }


class HibernationScheduleResponse(BaseModel):
    """Hibernation schedule response"""
    id: str = Field(..., description="Schedule UUID")
    cluster_id: str = Field(..., description="Cluster UUID")
    schedule_matrix: List[int] = Field(..., description="168-hour schedule")
    timezone: str = Field(..., description="Timezone")
    prewarm_enabled: bool = Field(..., description="Pre-warming enabled")
    prewarm_minutes: int = Field(..., description="Pre-warm minutes")
    created_at: datetime = Field(..., description="Creation timestamp")
    updated_at: datetime = Field(..., description="Last update timestamp")

    model_config = {
        "json_schema_extra": {
            "example": {
                "id": "bb0e8400-e29b-41d4-a716-446655440000",
                "cluster_id": "550e8400-e29b-41d4-a716-446655440000",
                "schedule_matrix": [0] * 48 + [1] * 72 + [0] * 48,
                "timezone": "America/New_York",
                "prewarm_enabled": True,
                "prewarm_minutes": 30,
                "created_at": "2025-12-31T10:00:00Z",
                "updated_at": "2025-12-31T10:00:00Z"
            }
        }
    }


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
