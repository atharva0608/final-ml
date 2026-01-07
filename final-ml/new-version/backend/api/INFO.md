# API Routes - Component Information

> **Last Updated**: 2025-12-31 19:50:00
> **Maintainer**: LLM Agent

---

## Folder Purpose
Contains FastAPI route handlers for all HTTP endpoints. Routes delegate business logic to services in `backend/services/` and return validated responses using schemas from `backend/schemas/`.

---

## Component Table

| File Name | Module ID | Endpoints Count | Key Routes | Schemas | Status |
|-----------|-----------|-----------------|------------|---------|--------|
| auth_routes.py | CORE-API | 6 | POST /signup, POST /login, POST /refresh, GET /me, POST /change-password, POST /logout | SCHEMA-AUTH-* | Complete |
| template_routes.py | CORE-API | 6 | GET /templates, POST /templates, GET /{id}, PATCH /{id}, DELETE /{id}, POST /{id}/set-default | SCHEMA-TEMPLATE-* | Complete |
| audit_routes.py | CORE-API | 2 | GET /audit, GET /audit/{id} | SCHEMA-AUDIT-* | Complete |
| cluster_routes.py | CORE-API | 9 | POST /discover, POST /clusters, GET /clusters, GET /{id}, PATCH /{id}, DELETE /{id}, GET /{id}/agent-install, POST /{id}/heartbeat | SCHEMA-CLUSTER-* | Complete |
| policy_routes.py | CORE-API | 8 | POST /policies, GET /policies, GET /{id}, GET /cluster/{id}, PATCH /{id}, DELETE /{id}, POST /{id}/toggle | SCHEMA-POLICY-* | Complete |
| hibernation_routes.py | CORE-API | 8 | POST /hibernation, GET /hibernation, GET /{id}, GET /cluster/{id}, PATCH /{id}, DELETE /{id}, POST /{id}/toggle | SCHEMA-HIBERNATION-* | Complete |
| metrics_routes.py | CORE-API | 5 | GET /dashboard, GET /cost, GET /instances, GET /cost/timeseries, GET /cluster/{id} | SCHEMA-METRIC-* | Complete |
| admin_routes.py | CORE-API | 5 | GET /clients, GET /clients/{id}, POST /clients/{id}/toggle, POST /clients/{id}/reset-password, GET /stats | SCHEMA-ADMIN-* | Complete |
| lab_routes.py | CORE-API | 9 | POST /experiments, GET /experiments, GET /{id}, PATCH /{id}, DELETE /{id}, POST /{id}/start, POST /{id}/stop, GET /{id}/results | SCHEMA-LAB-* | Complete |

**Total Endpoints**: 58 endpoints across 9 route modules

---

## Recent Changes

### [2025-12-31 19:50:00] - All API Routes Completed
**Changed By**: LLM Agent
**Reason**: Complete Phase 5-13 - Implement all remaining API routes
**Impact**: Complete REST API with 58 endpoints across 9 route modules
**Files Modified**:
- Created/Updated backend/api/__init__.py with all router exports
- Created backend/api/template_routes.py (6 endpoints)
- Created backend/api/audit_routes.py (2 endpoints)
- Created backend/api/cluster_routes.py (9 endpoints)
- Created backend/api/policy_routes.py (8 endpoints)
- Created backend/api/hibernation_routes.py (8 endpoints)
- Created backend/api/metrics_routes.py (5 endpoints)
- Created backend/api/admin_routes.py (5 endpoints)
- Created backend/api/lab_routes.py (9 endpoints)
- Updated backend/core/api_gateway.py with all router registrations
**Feature IDs Affected**: All client-*, admin-*, lab-* features
**Breaking Changes**: No
**API Documentation**: Available at /docs (Swagger UI)

### [2025-12-31 13:05:00] - Authentication Routes Implemented
**Changed By**: LLM Agent
**Reason**: Complete Phase 4 - Implement authentication API routes
**Impact**: Complete authentication endpoints with 6 routes
**Files Modified**:
- Created backend/api/__init__.py
- Created backend/api/auth_routes.py (6 endpoints)
**Feature IDs Affected**: any-auth-*
**Breaking Changes**: No

### [2025-12-31 12:36:00] - Initial API Routes Structure Created
**Changed By**: LLM Agent
**Reason**: Create organized folder structure for API routes
**Impact**: Created backend/api/ directory for route handlers
**Files Modified**:
- Created backend/api/
- Created backend/api/INFO.md (this file)
**Feature IDs Affected**: N/A (Infrastructure setup)
**Breaking Changes**: No

---

## Dependencies

### Internal Dependencies
- `backend/services/` - All business logic
- `backend/schemas/` - Request/response validation
- `backend/core/api_gateway.py` - Router registration

### External Dependencies
- FastAPI
- Pydantic
- Python-Jose (JWT)
- Passlib (password hashing)

---

## Route Design Principles

1. **Thin Controllers**: Routes should only handle HTTP concerns
2. **Delegate to Services**: All business logic in services layer
3. **Schema Validation**: Use Pydantic schemas for validation
4. **Error Handling**: Return appropriate HTTP status codes
5. **Documentation**: Use FastAPI docstrings for auto-docs

---

## API Endpoints by Category

### Authentication (auth_routes.py):
- `POST /api/auth/signup` - User registration
- `POST /api/auth/token` - Login and token generation
- `POST /api/auth/logout` - Logout and token blacklist
- `GET /api/auth/me` - Current user context

### Cluster Management (cluster_routes.py):
- `GET /clusters` - List all clusters
- `GET /clusters/{id}` - Cluster details
- `POST /clusters/connect` - Generate agent install command
- `POST /clusters/{id}/optimize` - Trigger optimization
- `POST /clusters/{id}/heartbeat` - Agent heartbeat
- `GET /clusters/{id}/actions/pending` - Fetch pending actions for Agent
- `POST /clusters/{id}/actions/{action_id}/result` - Agent reports action result

### Templates (template_routes.py):
- `GET /templates` - List node templates
- `POST /templates` - Create template
- `PATCH /templates/{id}/default` - Set as default
- `DELETE /templates/{id}` - Delete template

### Policies (policy_routes.py):
- `PATCH /policies/karpenter` - Toggle Karpenter
- `PATCH /policies/binpack` - Bin packing settings
- `PATCH /policies/fallback` - Spot fallback
- `PATCH /policies/exclusions` - Namespace exclusions

### Hibernation (hibernation_routes.py):
- `POST /hibernation/schedule` - Save weekly schedule
- `POST /hibernation/override` - Manual wake
- `PATCH /hibernation/prewarm` - Pre-warm toggle

### Audit (audit_routes.py):
- `GET /audit` - Paginated audit logs
- `GET /audit/export` - Export with checksum
- `GET /audit/{id}/diff` - JSON diff viewer

### Admin (admin_routes.py):
- `GET /admin/clients` - Client registry
- `POST /admin/impersonate` - Impersonate client
- `GET /admin/health` - System health
- `GET /admin/stats` - Global statistics

### Lab (lab_routes.py):
- `POST /lab/parallel` - A/B test configuration
- `POST /lab/graduate` - Promote model to production
- `WS /lab/stream/{id}` - Live telemetry stream
