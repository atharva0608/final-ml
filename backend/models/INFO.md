# Database Models - Component Information

> **Last Updated**: 2025-12-31 12:36:00
> **Maintainer**: LLM Agent

---

## Folder Purpose
Contains SQLAlchemy ORM models for all database tables including users, accounts, clusters, instances, templates, policies, schedules, audit logs, and ML models.

---

## Component Table

| File Name | Model Name | Table Name | Key Fields | Relationships | Status |
|-----------|-----------|------------|------------|---------------|--------|
| base.py | Base | - | - | - | Complete |
| user.py | User | users | id (UUID), email, password_hash, role | → accounts, → node_templates | Complete |
| account.py | Account | accounts | id (UUID), user_id (FK), aws_account_id, role_arn | → user, → clusters | Complete |
| cluster.py | Cluster | clusters | id (UUID), account_id (FK), name, region, status | → account, → instances, → policies, → agent_actions, → api_keys | Complete |
| instance.py | Instance | instances | id (UUID), cluster_id (FK), instance_id, instance_type, lifecycle | → cluster | Complete |
| node_template.py | NodeTemplate | node_templates | id (UUID), user_id (FK), name, families (ARRAY), strategy | → user | Complete |
| cluster_policy.py | ClusterPolicy | cluster_policies | id (UUID), cluster_id (FK), config (JSONB) | → cluster | Complete |
| hibernation_schedule.py | HibernationSchedule | hibernation_schedules | id (UUID), cluster_id (FK), schedule_matrix (JSONB) | → cluster | Complete |
| audit_log.py | AuditLog | audit_logs | id (UUID), timestamp, actor_id, event, resource | Immutable | Complete |
| ml_model.py | MLModel | ml_models | id (UUID), version, file_path, status | → lab_experiments | Complete |
| optimization_job.py | OptimizationJob | optimization_jobs | id (UUID), cluster_id (FK), status, results (JSONB) | → cluster | Complete |
| lab_experiment.py | LabExperiment | lab_experiments | id (UUID), model_id (FK), instance_id, test_type | → ml_model | Complete |
| agent_action.py | AgentAction | agent_actions | id (UUID), cluster_id (FK), action_type, payload (JSONB) | → cluster | Complete |
| api_key.py | APIKey | api_keys | id (UUID), cluster_id (FK), key_hash, prefix | → cluster | Complete |

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

### [2025-12-31 12:45:00] - All Database Models Implemented
**Changed By**: LLM Agent
**Reason**: Complete Phase 2.1 - Implement all SQLAlchemy ORM models
**Impact**: Complete database layer with 13 models and proper relationships
**Files Modified**:
- Created backend/models/__init__.py
- Created backend/models/base.py
- Created backend/models/user.py
- Created backend/models/account.py
- Created backend/models/cluster.py
- Created backend/models/instance.py
- Created backend/models/node_template.py
- Created backend/models/cluster_policy.py
- Created backend/models/hibernation_schedule.py
- Created backend/models/audit_log.py
- Created backend/models/ml_model.py
- Created backend/models/optimization_job.py
- Created backend/models/lab_experiment.py
- Created backend/models/agent_action.py
- Created backend/models/api_key.py
**Feature IDs Affected**: N/A (Database layer)
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
