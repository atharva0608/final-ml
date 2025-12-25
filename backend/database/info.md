# Backend Database Module - Complete Schema Reference

## Purpose

Complete PostgreSQL database schema with SQLAlchemy ORM models for multi-tenant AWS optimization platform.

**Last Updated**: 2025-12-25 (Comprehensive Enhancement)
**Authority Level**: CRITICAL
**Total Models**: 10 tables + 4 enums (14 classes)
**Schema Lines**: 485

---

## Complete Model Reference

### 1. User - AUTHENTICATION (Lines 37-58)
**Table**: `users` | **Purpose**: User accounts with RBAC

**Fields** (10 total):
- `id`: UUID PRIMARY KEY
- `email`: String(255) UNIQUE INDEXED - Login identifier
- `username`: String(50) UNIQUE INDEXED - Username
- `hashed_password`: String(255) - Bcrypt hash (12 rounds) ⚠️ PROTECTED
- `full_name`: String(100)
- `role`: String(20) - UserRole enum (super_admin/admin/client/user/lab)
- `is_active`: Boolean DEFAULT=True
- `created_at`, `updated_at`, `last_login`: DateTime

**Relationships**: accounts (1→N), approval_requests, downtime_logs
**APIs**: auth.py (login), admin.py (management)
**Frontend**: LoginPage.jsx, AuthContext.jsx

---

### 2. Account - AWS CONNECTIONS (Lines 64-113) ⭐ CRITICAL
**Table**: `accounts` | **Purpose**: Dual-mode AWS authentication

**Key Fields** (16 total):
- `account_id`: String(64) UNIQUE - AWS ID or "pending-xxx" ⚠️ GLOBAL UNIQUENESS
- `connection_method`: 'iam_role' (CloudFormation) or 'access_keys' (Credentials)
- `role_arn` + `external_id`: For CloudFormation method
- `aws_access_key_id` + `aws_secret_access_key`: AES-256 encrypted for Credentials method
- `status`: 'pending' → 'connected' → 'active' (or 'failed')

**Cascade**: Account DELETE → Instance DELETE → ExperimentLog DELETE
**Protected**: Global uniqueness check (P-2025-12-25-001), status transitions
**APIs**: onboarding_routes.py, client_routes.py
**Frontend**: ClientSetup.jsx (all 9 buttons), AuthGateway.jsx

---

### 3. Instance - EC2 TRACKING (Lines 119-166)
**Table**: `instances` | **Purpose**: EC2 instance tracking

**Key Fields** (17 total):
- `instance_id`: String(50) UNIQUE - EC2 ID (i-xxxxx)
- `orchestrator_type`: KUBERNETES or STANDALONE
- `cluster_membership`: JSONB - K8s cluster metadata
- `is_replica` + `replica_of_id`: Zero-downtime safety net
- `pipeline_mode`: CLUSTER or LINEAR

**Relationships**: account (N→1), experiment_logs (1→N)
**APIs**: client_routes.py (dashboard), metrics_routes.py
**Worker**: discovery_worker.py (INSERT on discovery)

---

### 4. ExperimentLog - ML TRACKING (Lines 174-214)
**Table**: `experiment_logs` | **Purpose**: ML experiment logs

**Key Fields** (17 total):
- `prediction_score`: Float - Crash probability
- `decision`: SWITCH, HOLD, FAILED
- `features_used`: JSONB - Feature vector snapshot
- `old_spot_price` + `new_spot_price`: Price comparison
- `projected_hourly_savings`: Float

**APIs**: lab.py
**Frontend**: ModelExperiments.jsx, LabInstanceDetails.jsx

---

### 5. MLModel - MODEL GOVERNANCE (Lines 230-272)
**Table**: `ml_models` | **Purpose**: Model lifecycle management

**Status Flow**:
CANDIDATE → TESTING → GRADUATED → ENABLED → ARCHIVED

**Key Fields** (14 total):
- `is_active_prod`: Boolean - Only ONE can be True
- `file_hash`: SHA256 integrity check
- `total_predictions`, `success_count`, `failure_count`: Performance metrics

**APIs**: governance_routes.py, lab.py
**Frontend**: ModelGovernance.jsx

---

### 6. WasteResource - COST OPTIMIZATION (Lines 286-319)
**Table**: `waste_resources` | **Purpose**: Unused resource tracking

**Types**: elastic_ip, ebs_volume, ebs_snapshot, ami
**Status**: DETECTED → FLAGGED → SCHEDULED_DELETE → DELETED

**Key Fields** (12 total):
- `monthly_cost`: Float - Waste cost estimate
- `days_unused`: Integer
- `scheduled_deletion_date`: DateTime - Grace period

**APIs**: waste_routes.py
**Worker**: waste_scanner.py

---

### 7. SpotPoolRisk - HIVE INTELLIGENCE (Lines 326-353)
**Table**: `spot_pool_risks` | **Purpose**: Global risk tracking

**Business Logic**: One client's disruption blocks pool globally for 15 days

**Key Fields** (11 total):
- `is_poisoned`: Boolean - Pool blocked?
- `poison_expires_at`: DateTime - 15-day cooldown
- `interruption_count`: Integer

**Composite Key**: region + availability_zone + instance_type

---

### 8. ApprovalRequest - APPROVAL WORKFLOW (Lines 368-401)
**Table**: `approval_requests` | **Purpose**: High-risk action gates

**Status**: PENDING → APPROVED/REJECTED/EXPIRED
**Action Types**: SWITCH_INSTANCE, TERMINATE_ROGUE, DELETE_WASTE

**Key Fields** (13 total):
- `action_payload`: JSONB - Execution details
- `risk_level`: LOW, MEDIUM, HIGH, CRITICAL
- `expires_at`: DateTime - Auto-reject deadline

**APIs**: approval_routes.py

---

### 9. GlobalRiskEvent - RISK LOG (Lines 408-440)
**Table**: `global_risk_events` | **Purpose**: Append-only disruption log

**Event Types**: rebalance_notice, termination_notice
**Never Delete**: Used for ML training

**Key Fields** (9 total):
- `pool_id`: String(128) - "region:az:instance_type"
- `expires_at`: reported_at + 15 days

---

### 10. DowntimeLog - SLA TRACKING (Lines 443-485)
**Table**: `downtime_logs` | **Purpose**: SLA accountability

**SLA Target**: < 60 seconds monthly downtime

**Causes**: emergency_switch, no_replica, optimizer_failure, worker_crash
**NOT Logged**: AWS-caused downtime

**Key Fields** (9 total):
- `duration_seconds`: Integer - Downtime duration
- `cause`: String(64) INDEXED

---

## Schema Relationships

```
User
├─ accounts (1→N cascade)
│  └─ instances (1→N cascade)
│     └─ experiment_logs (1→N cascade)
│
├─ ml_models (uploaded_by)
├─ approval_requests (requester/approver)
└─ downtime_logs

Global Tables (no FK):
├─ SpotPoolRisk
└─ GlobalRiskEvent
```

---

## Critical Operations

### Cascade Deletes ⚠️
User DELETE → Account DELETE → Instance DELETE → ExperimentLog DELETE

### Status Transitions ⚠️ PROTECTED
Account: pending → connected → active
See: `/progress/regression_guard.md#4`

### Global Uniqueness ⚠️ PROTECTED
One AWS account_id → One user only
See: `/progress/regression_guard.md#2`, P-2025-12-25-001

---

## APIs Using Database

| Model | Primary APIs | Workers | Frontend |
|-------|-------------|---------|----------|
| User | auth.py, admin.py | - | LoginPage, AuthContext |
| Account | onboarding_routes, client_routes | discovery_worker | ClientSetup, AuthGateway |
| Instance | client_routes, metrics_routes | discovery_worker | NodeFleet, InstanceFlow |
| ExperimentLog | lab.py | ML workers | ModelExperiments, LabInstance |
| MLModel | governance_routes, lab.py | - | ModelGovernance |
| WasteResource | waste_routes.py | waste_scanner | Waste dashboard |
| SpotPoolRisk | - | spot_detector | Risk dashboard |
| ApprovalRequest | approval_routes | approval_notifier | Approval dashboard |
| GlobalRiskEvent | - | event_logger | - |
| DowntimeLog | - | downtime_detector | SLA dashboard |

---

_Last Updated: 2025-12-25 (Complete 10-Model Documentation)_
_Authority: CRITICAL - Complete schema reference_
