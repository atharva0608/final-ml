# Database Models - Component Information

> **Last Updated**: 2025-12-31 12:36:00
> **Maintainer**: LLM Agent

---

## Folder Purpose
Contains SQLAlchemy ORM models for all database tables including users, accounts, clusters, instances, templates, policies, schedules, audit logs, and ML models.

---

## Component Table (Planned)

| File Name | Model Name | Table Name | Key Fields | Relationships | Status |
|-----------|-----------|------------|------------|---------------|--------|
| user.py | User | users | id (UUID), email, password_hash, role | → accounts | Pending |
| account.py | Account | accounts | id (UUID), user_id (FK), aws_account_id, role_arn | → users, → clusters | Pending |
| cluster.py | Cluster | clusters | id (UUID), account_id (FK), name, region, status | → account, → instances, → policies | Pending |
| instance.py | Instance | instances | id (UUID), cluster_id (FK), instance_id, instance_type, lifecycle | → cluster | Pending |
| node_template.py | NodeTemplate | node_templates | id (UUID), user_id (FK), name, families (ARRAY), strategy | → user | Pending |
| cluster_policy.py | ClusterPolicy | cluster_policies | id (UUID), cluster_id (FK), config (JSONB) | → cluster | Pending |
| hibernation_schedule.py | HibernationSchedule | hibernation_schedules | id (UUID), cluster_id (FK), schedule_matrix (JSONB) | → cluster | Pending |
| audit_log.py | AuditLog | audit_logs | id (UUID), timestamp, actor_id, event, resource | Immutable | Pending |
| ml_model.py | MLModel | ml_models | id (UUID), version, file_path, status | None | Pending |
| optimization_job.py | OptimizationJob | optimization_jobs | id (UUID), cluster_id (FK), status, results (JSONB) | → cluster | Pending |
| agent_action.py | AgentAction | agent_actions | id (UUID), cluster_id (FK), action_type, payload (JSONB) | → cluster, → optimization_jobs | Pending |
| api_key.py | APIKey | api_keys | id (UUID), cluster_id (FK), key_hash, prefix | → cluster | Pending |

---

## Recent Changes

### [2025-12-31 12:36:00] - Initial Models Structure Created
**Changed By**: LLM Agent
**Reason**: Create organized folder structure for database models
**Impact**: Created backend/models/ directory for SQLAlchemy models
**Files Modified**:
- Created backend/models/
- Created backend/models/INFO.md (this file)
**Feature IDs Affected**: N/A (Infrastructure setup)
**Breaking Changes**: No

---

## Dependencies

- **ORM**: SQLAlchemy 2.0+
- **Migrations**: Alembic
- **Database**: PostgreSQL 13+
- **Connection**: psycopg2-binary

---

## Database Schema Overview

### User Management:
- `users`: Platform users (clients and admins)
- `accounts`: AWS account connections
- `api_keys`: Agent authentication tokens

### Infrastructure:
- `clusters`: Kubernetes clusters
- `instances`: EC2 instances
- `node_templates`: Instance selection templates
- `cluster_policies`: Optimization policies

### Operations:
- `hibernation_schedules`: Schedule matrices (168 elements)
- `optimization_jobs`: Optimization run tracking
- `agent_actions`: K8s action queue (Worker → Agent)

### Intelligence:
- `ml_models`: ML model registry
- `audit_logs`: Immutable audit trail

---

## Key Model Features

### UUID Primary Keys:
All models use UUID for primary keys to prevent enumeration attacks and support distributed systems.

### Timestamps:
All models include `created_at` and `updated_at` (except audit_logs which is immutable).

### JSONB Fields:
- `cluster_policies.config`: Flexible policy configuration
- `hibernation_schedules.schedule_matrix`: 168-element array
- `agent_actions.payload`: Action-specific parameters
- `optimization_jobs.results`: Optimization results

### Indexes:
- Foreign keys (automatic)
- Frequently queried fields (status, timestamp, cluster_id)
- Composite indexes for common queries

---

## Testing Requirements

- Model creation and validation tests
- Relationship tests (joins)
- Migration tests (up and down)
- Constraint violation tests
- Performance tests for large datasets
