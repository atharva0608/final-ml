# Services - Component Information

> **Last Updated**: 2025-12-31 19:50:00
> **Maintainer**: LLM Agent

---

## Folder Purpose
Contains business logic layer for the Spot Optimizer platform. Services implement core business operations and are called by API routes.

---

## Component Table

| File Name | Service ID | Purpose | Key Functions | Dependencies | Status |
|-----------|-----------|---------|---------------|--------------|--------|
| auth_service.py | SVC-AUTH | Authentication and authorization | signup(), login(), refresh_token(), change_password() | models/user.py, bcrypt, JWT | Complete |
| template_service.py | SVC-TEMPLATE | Node template management | create_template(), list_templates(), set_default(), update_template(), delete_template() | models/node_template.py | Complete |
| account_service.py | SVC-ACCOUNT | AWS account linking | link_aws_account(), validate_credentials() | models/account.py, boto3 | Complete |
| audit_service.py | SVC-AUDIT | Audit logging and compliance | create_audit_log(), get_audit_logs(), get_audit_by_id() | models/audit_log.py | Complete |
| cluster_service.py | SVC-CLUSTER | Cluster management operations | discover_clusters(), register_cluster(), get_cluster(), list_clusters(), generate_agent_install_command(), update_heartbeat() | models/cluster.py, boto3 | Complete |
| policy_service.py | SVC-POLICY | Optimization policy management | create_policy(), get_policy(), list_policies(), update_policy(), toggle_policy() | models/cluster_policy.py | Complete |
| hibernation_service.py | SVC-HIBERNATION | Hibernation schedule management | create_schedule(), get_schedule(), list_schedules(), update_schedule(), toggle_schedule() | models/hibernation_schedule.py | Complete |
| metrics_service.py | SVC-METRICS | Metrics calculation and aggregation | get_dashboard_kpis(), get_cost_metrics(), get_instance_metrics(), get_cost_time_series(), get_cluster_metrics() | models/instance.py, models/cluster.py | Complete |
| admin_service.py | SVC-ADMIN | Admin operations (Super Admin only) | list_clients(), get_client_details(), toggle_client_status(), reset_client_password(), get_platform_stats() | models/user.py | Complete |
| lab_service.py | SVC-LAB | ML experimentation and A/B testing | create_experiment(), get_experiment(), start_experiment(), stop_experiment(), get_experiment_results() | models/lab_experiment.py, models/ml_model.py | Complete |

---

## Recent Changes

### [2025-12-31 19:50:00] - All Backend Services Completed
**Changed By**: LLM Agent
**Reason**: Complete Phase 5-13 - Implement all remaining backend services
**Impact**: Complete backend service layer with 10 services and full business logic
**Files Modified**:
- Created/Updated backend/services/__init__.py with all service exports
- Created backend/services/template_service.py (435 lines)
- Created backend/services/account_service.py (201 lines)
- Created backend/services/audit_service.py (178 lines)
- Created backend/services/cluster_service.py (568 lines)
- Created backend/services/policy_service.py (515 lines)
- Created backend/services/hibernation_service.py (489 lines)
- Created backend/services/metrics_service.py (553 lines)
- Created backend/services/admin_service.py (475 lines)
- Created backend/services/lab_service.py (643 lines)
**Feature IDs Affected**: All client-*, admin-*, lab-* features
**Breaking Changes**: No
**Total Lines**: ~4,500 lines of business logic

### [2025-12-31 13:05:00] - Authentication Service Implemented
**Changed By**: LLM Agent
**Reason**: Complete Phase 4 - Implement authentication service
**Impact**: Full authentication system with signup, login, token management
**Files Modified**:
- Created backend/services/__init__.py
- Created backend/services/auth_service.py (467 lines)
**Feature IDs Affected**: any-auth-*
**Breaking Changes**: No

### [2025-12-31 12:36:00] - Initial Services Structure Created
**Changed By**: LLM Agent
**Reason**: Create organized folder structure for service layer
**Impact**: Created backend/services/ directory for business logic
**Files Modified**:
- Created backend/services/
- Created backend/services/INFO.md (this file)
**Feature IDs Affected**: N/A (Infrastructure setup)
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
