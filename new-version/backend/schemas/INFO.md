# Pydantic Schemas - Component Information

> **Last Updated**: 2025-12-31 12:36:00
> **Maintainer**: LLM Agent

---

## Folder Purpose
Contains Pydantic schemas for request/response validation, data serialization, and API contract enforcement.

---

## Component Table (Planned)

| File Name | Schema Category | Key Schemas | Purpose | Status |
|-----------|----------------|-------------|---------|--------|
| auth_schemas.py | Authentication | SignupRequest, LoginRequest, TokenResponse, UserContext | Auth flows | Pending |
| cluster_schemas.py | Clusters | ClusterList, ClusterDetail, AgentCmd, Heartbeat, JobId | Cluster management | Pending |
| template_schemas.py | Templates | TmplList, NodeTemplate, TemplateValidation | Template management | Pending |
| policy_schemas.py | Policies | PolState, PolicyUpdate | Policy configuration | Pending |
| hibernation_schemas.py | Hibernation | ScheduleMatrix, Override | Schedule management | Pending |
| metric_schemas.py | Metrics | KPISet, ChartData, PieData, FeedData | Dashboard data | Pending |
| audit_schemas.py | Audit | AuditLogList, AuditLog, DiffData | Audit and compliance | Pending |
| admin_schemas.py | Admin | ClientList, ClientOrg | Admin operations | Pending |
| lab_schemas.py | Lab | TelemetryData, ABTestConfig, ABResults | ML experimentation | Pending |

---

## Recent Changes

### [2025-12-31 12:36:00] - Initial Schemas Structure Created
**Changed By**: LLM Agent
**Reason**: Create organized folder structure for Pydantic schemas
**Impact**: Created backend/schemas/ directory for data validation
**Files Modified**:
- Created backend/schemas/
- Created backend/schemas/INFO.md (this file)
**Feature IDs Affected**: N/A (Infrastructure setup)
**Breaking Changes**: No

---

## Dependencies

- **Validation**: Pydantic 2.0+
- **Serialization**: JSON, datetime

---

## Schema Design Principles

1. **Input Validation**: All API request bodies use schemas
2. **Output Serialization**: All API responses use schemas
3. **Version Control**: Schema versions tracked in schema_reference.md
4. **Breaking Changes**: Major version bump for breaking changes
5. **Backwards Compatibility**: Non-breaking additions allowed

---

## Example Schema Structure

```python
from pydantic import BaseModel, Field, validator
from typing import List, Optional
from datetime import datetime

class ClusterDetail(BaseModel):
    id: str = Field(..., description="Cluster UUID")
    name: str = Field(..., description="Cluster name")
    region: str = Field(..., description="AWS region")
    node_count: int = Field(..., ge=0, description="Number of nodes")
    monthly_cost: float = Field(..., ge=0, description="Monthly cost in USD")
    status: str = Field(..., description="Cluster status")
    created_at: datetime = Field(..., description="Creation timestamp")

    class Config:
        json_schema_extra = {
            "example": {
                "id": "550e8400-e29b-41d4-a716-446655440000",
                "name": "production-eks",
                "region": "us-east-1",
                "node_count": 15,
                "monthly_cost": 1250.50,
                "status": "active",
                "created_at": "2025-12-31T12:00:00Z"
            }
        }
```

---

## Testing Requirements

- Schema validation tests (valid/invalid inputs)
- Serialization/deserialization tests
- Custom validator tests
- Example data validity tests
- Performance tests for large datasets
