# Pydantic Schemas - Component Information

> **Last Updated**: 2025-12-31 12:36:00
> **Maintainer**: LLM Agent

---

## Folder Purpose
Contains Pydantic schemas for request/response validation, data serialization, and API contract enforcement.

---

## Component Table

| File Name | Schema Category | Key Schemas | Purpose | Status |
|-----------|----------------|-------------|---------|--------|
| auth_schemas.py | Authentication | SignupRequest, LoginRequest, TokenResponse, UserContext, PasswordChange | Auth flows | Complete |
| cluster_schemas.py | Clusters | ClusterList, ClusterDetail, HeartbeatRequest, AgentCommandList, OptimizationJobResult | Cluster management | Complete |
| template_schemas.py | Templates | NodeTemplateCreate, NodeTemplateResponse, NodeTemplateList, TemplateValidationResult | Template management | Complete |
| policy_schemas.py | Policies | PolicyConfig, PolicyUpdate, PolicyState, PolicyValidationResult | Policy configuration | Complete |
| hibernation_schemas.py | Hibernation | HibernationScheduleCreate, ScheduleMatrix, ScheduleOverride, SchedulePreview | Schedule management | Complete |
| metric_schemas.py | Metrics | KPISet, ChartData, PieChartData, ActivityFeed, DashboardMetrics | Dashboard data | Complete |
| audit_schemas.py | Audit | AuditLog, AuditLogList, AuditLogFilter, ComplianceReport | Audit and compliance | Complete |
| admin_schemas.py | Admin | ClientList, ClientOrganization, SystemHealth, PlatformStats | Admin operations | Complete |
| lab_schemas.py | Lab | TelemetryData, ABTestConfig, ABTestResults, MLModelResponse | ML experimentation | Complete |

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

### [2025-12-31 12:55:00] - All Pydantic Schemas Implemented
**Changed By**: LLM Agent
**Reason**: Complete Phase 2.3 - Implement all Pydantic validation schemas
**Impact**: Complete request/response validation for all API endpoints
**Files Modified**:
- Created backend/schemas/__init__.py
- Created backend/schemas/auth_schemas.py (8 schemas)
- Created backend/schemas/cluster_schemas.py (10 schemas)
- Created backend/schemas/template_schemas.py (5 schemas)
- Created backend/schemas/policy_schemas.py (6 schemas)
- Created backend/schemas/hibernation_schemas.py (7 schemas)
- Created backend/schemas/metric_schemas.py (11 schemas)
- Created backend/schemas/audit_schemas.py (7 schemas)
- Created backend/schemas/admin_schemas.py (9 schemas)
- Created backend/schemas/lab_schemas.py (10 schemas)
**Total Schemas**: 73 schemas across 9 categories
**Feature IDs Affected**: N/A (API validation layer)
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
