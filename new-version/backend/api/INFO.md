# API Routes - Component Information

> **Last Updated**: 2025-12-31 12:36:00
> **Maintainer**: LLM Agent

---

## Folder Purpose
Contains FastAPI route handlers for all HTTP endpoints. Routes delegate business logic to services in `backend/services/` and return validated responses using schemas from `backend/schemas/`.

---

## Component Table

| File Name | Module ID | Endpoints | Schemas | Feature IDs | Status |
|-----------|-----------|-----------|---------|-------------|--------|
| auth_routes.py | CORE-API | POST /auth/signup, POST /auth/login, POST /auth/refresh, POST /auth/change-password, POST /auth/logout, GET /auth/me | SCHEMA-AUTH-* | any-auth-* | Complete |
| cluster_routes.py | CORE-API | GET /clusters, GET /clusters/{id}, POST /clusters/connect, POST /clusters/{id}/optimize | SCHEMA-CLUSTER-* | client-cluster-* | Pending |
| template_routes.py | CORE-API | GET /templates, POST /templates, PATCH /templates/{id}/default, DELETE /templates/{id} | SCHEMA-TEMPLATE-* | client-tmpl-* | Pending |
| policy_routes.py | CORE-API | PATCH /policies/* | SCHEMA-POLICY-* | client-pol-* | Pending |
| hibernation_routes.py | CORE-API | POST /hibernation/schedule, POST /hibernation/override | SCHEMA-HIBERNATION-* | client-hib-* | Pending |
| audit_routes.py | CORE-API | GET /audit, GET /audit/export, GET /audit/{id}/diff | SCHEMA-AUDIT-* | client-audit-* | Pending |
| admin_routes.py | CORE-API | GET /admin/clients, POST /admin/impersonate, GET /admin/health | SCHEMA-ADMIN-* | admin-* | Pending |
| lab_routes.py | CORE-API | POST /lab/parallel, POST /lab/graduate, WS /lab/stream/{id} | SCHEMA-LAB-* | admin-lab-* | Pending |

---

## Recent Changes

### [2025-12-31 12:36:00] - Initial API Routes Structure Created
**Changed By**: LLM Agent
**Reason**: Create organized folder structure for API routes
**Impact**: Created backend/api/ directory for route handlers
**Files Modified**:
- Created backend/api/
- Created backend/api/INFO.md (this file)
**Feature IDs Affected**: N/A (Infrastructure setup)
**Breaking Changes**: No

### [2025-12-31 13:05:00] - Authentication Routes Implemented
**Changed By**: LLM Agent
**Reason**: Complete Phase 4 - Implement authentication API routes
**Impact**: Complete authentication endpoints with 6 routes
**Files Modified**:
- Created backend/api/__init__.py
- Created backend/api/auth_routes.py
**Feature IDs Affected**: any-auth-*
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
