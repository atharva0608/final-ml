"""
Audit Schemas - Request/Response models for audit logs and compliance
"""
from pydantic import BaseModel, Field, field_validator
from typing import Optional, List, Dict, Any
from datetime import datetime


class DiffData(BaseModel):
    """Diff data for audit log (before/after)"""
    changes: Dict[str, Any] = Field(..., description="Changed fields")

    model_config = {
        "json_schema_extra": {
            "example": {
                "changes": {
                    "strategy": {"old": "BALANCED", "new": "PERFORMANCE"},
                    "spot_percentage": {"old": 80, "new": 70}
                }
            }
        }
    }


class AuditLog(BaseModel):
    """Single audit log entry"""
    id: str = Field(..., description="Audit log UUID")
    timestamp: datetime = Field(..., description="Event timestamp")
    actor_id: str = Field(..., description="Actor UUID (user or system)")
    actor_name: str = Field(..., description="Actor name or email")
    event: str = Field(..., description="Event type (e.g., CLUSTER_CREATED, POLICY_UPDATED)")
    resource: str = Field(..., description="Resource name or identifier")
    resource_type: str = Field(..., description="Resource type (CLUSTER, INSTANCE, TEMPLATE, etc.)")
    outcome: str = Field(..., description="Event outcome (SUCCESS or FAILURE)")
    ip_address: Optional[str] = Field(None, description="Client IP address")
    user_agent: Optional[str] = Field(None, description="Client user agent")
    diff_before: Optional[Dict[str, Any]] = Field(None, description="State before change")
    diff_after: Optional[Dict[str, Any]] = Field(None, description="State after change")

    model_config = {
        "json_schema_extra": {
            "example": {
                "id": "dd0e8400-e29b-41d4-a716-446655440000",
                "timestamp": "2025-12-31T12:00:00Z",
                "actor_id": "550e8400-e29b-41d4-a716-446655440000",
                "actor_name": "admin@spotoptimizer.com",
                "event": "POLICY_UPDATED",
                "resource": "production-eks",
                "resource_type": "CLUSTER",
                "outcome": "SUCCESS",
                "ip_address": "203.0.113.42",
                "user_agent": "Mozilla/5.0...",
                "diff_before": {"strategy": "BALANCED"},
                "diff_after": {"strategy": "PERFORMANCE"}
            }
        }
    }


class AuditLogList(BaseModel):
    """List of audit logs"""
    logs: List[AuditLog] = Field(..., description="Array of audit logs")
    total: int = Field(..., ge=0, description="Total number of logs")
    page: int = Field(..., ge=1, description="Current page number")
    page_size: int = Field(..., ge=1, le=100, description="Number of logs per page")

    model_config = {
        "json_schema_extra": {
            "example": {
                "logs": [
                    {
                        "id": "dd0e8400-e29b-41d4-a716-446655440000",
                        "timestamp": "2025-12-31T12:00:00Z",
                        "actor_id": "550e8400-e29b-41d4-a716-446655440000",
                        "actor_name": "admin@spotoptimizer.com",
                        "event": "POLICY_UPDATED",
                        "resource": "production-eks",
                        "resource_type": "CLUSTER",
                        "outcome": "SUCCESS",
                        "ip_address": "203.0.113.42",
                        "user_agent": "Mozilla/5.0...",
                        "diff_before": {"strategy": "BALANCED"},
                        "diff_after": {"strategy": "PERFORMANCE"}
                    }
                ],
                "total": 1,
                "page": 1,
                "page_size": 50
            }
        }
    }


class AuditLogFilter(BaseModel):
    """Audit log filter criteria"""
    start_date: Optional[datetime] = Field(None, description="Filter logs after this date")
    end_date: Optional[datetime] = Field(None, description="Filter logs before this date")
    actor_id: Optional[str] = Field(None, description="Filter by actor UUID")
    event: Optional[str] = Field(None, description="Filter by event type")
    resource_type: Optional[str] = Field(None, description="Filter by resource type")
    outcome: Optional[str] = Field(None, description="Filter by outcome (SUCCESS or FAILURE)")
    page: int = Field(default=1, ge=1, description="Page number")
    page_size: int = Field(default=50, ge=1, le=100, description="Number of logs per page")

    @field_validator('outcome')
    @classmethod
    def validate_outcome(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and v not in ['SUCCESS', 'FAILURE']:
            raise ValueError('Outcome must be SUCCESS or FAILURE')
        return v

    model_config = {
        "json_schema_extra": {
            "example": {
                "start_date": "2025-12-01T00:00:00Z",
                "end_date": "2025-12-31T23:59:59Z",
                "resource_type": "CLUSTER",
                "outcome": "SUCCESS",
                "page": 1,
                "page_size": 50
            }
        }
    }


class AuditEventStats(BaseModel):
    """Audit event statistics"""
    event: str = Field(..., description="Event type")
    count: int = Field(..., ge=0, description="Number of occurrences")
    success_count: int = Field(..., ge=0, description="Number of successful events")
    failure_count: int = Field(..., ge=0, description="Number of failed events")

    model_config = {
        "json_schema_extra": {
            "example": {
                "event": "CLUSTER_OPTIMIZED",
                "count": 125,
                "success_count": 120,
                "failure_count": 5
            }
        }
    }


class AuditSummary(BaseModel):
    """Audit summary statistics"""
    total_events: int = Field(..., ge=0, description="Total number of events")
    unique_actors: int = Field(..., ge=0, description="Number of unique actors")
    event_stats: List[AuditEventStats] = Field(..., description="Statistics by event type")
    success_rate: float = Field(..., ge=0, le=100, description="Overall success rate percentage")
    date_range: Dict[str, datetime] = Field(..., description="Date range of summary")

    model_config = {
        "json_schema_extra": {
            "example": {
                "total_events": 1250,
                "unique_actors": 15,
                "event_stats": [
                    {
                        "event": "CLUSTER_OPTIMIZED",
                        "count": 125,
                        "success_count": 120,
                        "failure_count": 5
                    }
                ],
                "success_rate": 96.8,
                "date_range": {
                    "start": "2025-12-01T00:00:00Z",
                    "end": "2025-12-31T23:59:59Z"
                }
            }
        }
    }


class ComplianceReport(BaseModel):
    """Compliance report"""
    report_id: str = Field(..., description="Report UUID")
    generated_at: datetime = Field(..., description="Report generation timestamp")
    date_range: Dict[str, datetime] = Field(..., description="Report date range")
    total_changes: int = Field(..., ge=0, description="Total number of changes")
    user_changes: int = Field(..., ge=0, description="Changes by users")
    system_changes: int = Field(..., ge=0, description="Changes by system")
    critical_events: int = Field(..., ge=0, description="Number of critical events")
    failed_events: int = Field(..., ge=0, description="Number of failed events")
    top_actors: List[Dict[str, Any]] = Field(..., description="Most active actors")
    top_events: List[Dict[str, Any]] = Field(..., description="Most common events")

    model_config = {
        "json_schema_extra": {
            "example": {
                "report_id": "ee0e8400-e29b-41d4-a716-446655440000",
                "generated_at": "2025-12-31T23:59:59Z",
                "date_range": {
                    "start": "2025-12-01T00:00:00Z",
                    "end": "2025-12-31T23:59:59Z"
                },
                "total_changes": 1250,
                "user_changes": 850,
                "system_changes": 400,
                "critical_events": 15,
                "failed_events": 42,
                "top_actors": [
                    {"actor": "admin@spotoptimizer.com", "count": 250}
                ],
                "top_events": [
                    {"event": "CLUSTER_OPTIMIZED", "count": 125}
                ]
            }
        }
    }
