# Services - Component Information

> **Last Updated**: 2025-12-31 12:36:00
> **Maintainer**: LLM Agent

---

## Folder Purpose
Contains business logic layer for the Spot Optimizer platform. Services implement core business operations and are called by API routes.

---

## Component Table

| File Name | Service ID | Purpose | Key Functions | Dependencies | Status |
|-----------|-----------|---------|---------------|--------------|--------|
| auth_service.py | SVC-AUTH | Authentication and authorization | signup(), login(), refresh_token(), change_password() | models/user.py, bcrypt, JWT | Complete |
| cluster_service.py | SVC-CLUSTER | Cluster management operations | list_managed_clusters(), get_cluster_details(), generate_agent_install() | models/cluster.py, boto3 | Pending |
| template_service.py | SVC-TEMPLATE | Node template management | list_node_templates(), create_node_template(), set_global_default_template() | models/node_template.py | Pending |
| policy_service.py | SVC-POLICY | Optimization policy management | update_karpenter_state(), update_binpack_settings(), update_fallback_policy() | models/cluster_policy.py | Pending |
| hibernation_service.py | SVC-HIBERNATION | Hibernation schedule management | save_weekly_schedule(), trigger_manual_wakeup(), update_prewarm_status() | models/hibernation_schedule.py | Pending |
| metrics_service.py | SVC-METRICS | Metrics calculation and aggregation | calculate_current_spend(), calculate_net_savings(), get_fleet_composition() | models/instance.py | Pending |
| audit_service.py | SVC-AUDIT | Audit logging and compliance | fetch_audit_logs(), generate_audit_checksum_export(), fetch_audit_diff() | models/audit_log.py | Pending |
| admin_service.py | SVC-ADMIN | Admin operations | list_all_clients(), generate_impersonation_token(), check_worker_queue_depth() | models/user.py, Celery | Pending |

---

## Recent Changes

### [2025-12-31 12:36:00] - Initial Services Structure Created
**Changed By**: LLM Agent
**Reason**: Create organized folder structure for service layer
**Impact**: Created backend/services/ directory for business logic
**Files Modified**:
- Created backend/services/
- Created backend/services/INFO.md (this file)
**Feature IDs Affected**: N/A (Infrastructure setup)
**Breaking Changes**: No

### [2025-12-31 13:05:00] - Authentication Service Implemented
**Changed By**: LLM Agent
**Reason**: Complete Phase 4 - Implement authentication service
**Impact**: Full authentication system with signup, login, token management
**Files Modified**:
- Created backend/services/__init__.py
- Created backend/services/auth_service.py
**Feature IDs Affected**: any-auth-*
**Breaking Changes**: No

---

## Dependencies

### Internal Dependencies
- `backend/models/` - Database models
- `backend/schemas/` - Data validation
- `backend/modules/` - Intelligence modules
- `backend/core/` - Core system components

### External Dependencies
- SQLAlchemy (database ORM)
- boto3 (AWS SDK)
- Redis (caching and pub/sub)
- Celery (async tasks)

---

## Service Design Principles

1. **Single Responsibility**: Each service handles one domain
2. **Transaction Management**: Services manage database transactions
3. **Error Handling**: Services raise custom exceptions
4. **Caching**: Use Redis for frequently accessed data
5. **Async Operations**: Delegate long-running tasks to workers

---

## Service Responsibilities

### auth_service.py:
- User registration and organization creation
- Authentication and JWT token management
- Session management and logout
- Smart routing based on account status

### cluster_service.py:
- Cluster discovery and registration
- Agent installation command generation
- Cluster health monitoring
- Heartbeat verification

### template_service.py:
- Node template CRUD operations
- Template validation
- Default template management
- Template usage tracking

### policy_service.py:
- Optimization policy configuration
- Policy validation
- Policy broadcast to agents via Redis pub/sub
- Conflict resolution

### hibernation_service.py:
- Weekly schedule management
- Manual wake/sleep triggers
- Pre-warm configuration
- Timezone handling

### metrics_service.py:
- KPI calculation (spend, savings, health)
- Chart data generation
- Activity feed aggregation
- Cost projection calculations

### audit_service.py:
- Audit log querying and filtering
- Compliance export generation
- Diff viewer for before/after states
- Retention policy enforcement

### admin_service.py:
- Client registry management
- Impersonation token generation
- System health monitoring
- Worker queue depth monitoring
