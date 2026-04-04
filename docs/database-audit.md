# Database Audit — Spot Optimizer

> **Generated:** 2025-07-24  
> **Database:** PostgreSQL (`spot_optimizer`) on port 5433  
> **ORM:** SQLAlchemy 2.0.25 + psycopg2  
> **Extensions:** TimescaleDB  
> **Total Tables:** ~78 (including association tables)  
> **Total Migrations:** 25 (22 Alembic + 3 standalone)

---

## Table of Contents

1. [Base Schema — Common Patterns](#1-base-schema--common-patterns)
2. [Connection Pool Configuration](#2-connection-pool-configuration)
3. [All Tables — Exact Schema](#3-all-tables--exact-schema)
4. [CRUD Operations Per Table](#4-crud-operations-per-table)
5. [Migration History](#5-migration-history)
6. [Duplicate / Overlapping Tables Analysis](#6-duplicate--overlapping-tables-analysis)
7. [Enum Types](#7-enum-types)
8. [Unused / Dead Tables](#8-unused--dead-tables)

---

## 1. Base Schema — Common Patterns

All models inherit from `declarative_base()` in `backend/models/base.py`.

| Pattern | Value | Used By |
|---|---|---|
| **Primary Key** | `String(36)` with `default=generate_uuid` (uuid4 hex) | ~60 tables |
| **Integer PK** | `Integer` autoincrement | `rebalancing_actions`, `spot_price_history`, `ondemand_pricing`, `spot_advisor_data`, `launch_outcomes`, `termination_events`, `platform_settings`, `pool_risk_scores` |
| **Composite PK** | Two FKs as joint PK | `user_permissions`, `role_permissions`, `hibernation_schedule_clusters` |
| **Single-column PK (FK)** | FK itself is the PK | `cluster_baselines` (cluster_id) |
| **created_at** | `Column(DateTime, default=datetime.utcnow)` | ~65 tables |
| **updated_at** | `Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)` | ~50 tables |
| **Timezone-aware timestamps** | `DateTime(timezone=True)` with `func.now()` | `agent_identities`, `platform_settings`, `cleanup_policies`, `termination_events`, `cluster_cooldown_states` |
| **organization_id FK** | `ForeignKey('organizations.id')` | ~25 tables |
| **cluster_id FK** | `ForeignKey('clusters.id')` | ~15 tables |
| **account_id FK** | `ForeignKey('accounts.id')` | ~8 tables |
| **Soft delete** | `status` column or `is_active` flag | `clusters`, `users`, `tag_policies`, `agent_identities` |
| **JSONB columns** | Flexible metadata storage | `termination_events`, `rebalancing_actions` (state_history) |
| **JSON columns** | Config/list storage | `tag_automation_rules`, `tag_policies`, `tag_templates`, `node_templates`, etc. |

### Session Configuration

```python
engine = create_engine(DATABASE_URL,
    pool_size=20,
    max_overflow=30,
    pool_timeout=30,
    pool_recycle=1800,
    pool_pre_ping=True
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
```

- `get_db()` — FastAPI dependency (yields session, auto-closes)
- `get_db_contextmanager()` — Context manager for Celery workers

---

## 2. Connection Pool Configuration

| Parameter | Value |
|---|---|
| pool_size | 20 |
| max_overflow | 30 |
| pool_timeout | 30s |
| pool_recycle | 1800s (30 min) |
| pool_pre_ping | True |
| Max concurrent connections | 50 (20 + 30) |

---

## 3. All Tables — Exact Schema

### 3.1 `accounts`

| Column | Type | Nullable | Default | Constraints |
|---|---|---|---|---|
| id | String(36) | NO | generate_uuid() | PK |
| name | String(255) | NO | — | — |
| aws_account_id | String(20) | NO | — | Unique, Index |
| role_arn | String(255) | YES | — | — |
| external_id | String(100) | YES | — | — |
| status | Enum(AccountStatus) | — | ACTIVE | — |
| organization_id | String(36) | YES | — | FK → organizations.id |
| default_region | String(50) | YES | — | — |
| created_by | String(36) | YES | — | FK → users.id |
| created_at | DateTime | — | utcnow | — |
| updated_at | DateTime | — | utcnow | — |

---

### 3.2 `agent_actions`

| Column | Type | Nullable | Default | Constraints |
|---|---|---|---|---|
| id | String(36) | NO | generate_uuid() | PK |
| cluster_id | String(36) | NO | — | FK → clusters.id, Index |
| action_type | Enum(AgentActionType) | NO | — | — |
| status | Enum(AgentActionStatus) | — | PENDING | Index |
| payload | JSON | YES | — | — |
| result | JSON | YES | — | — |
| error_message | Text | YES | — | — |
| created_at | DateTime | — | utcnow | — |
| updated_at | DateTime | — | utcnow | — |
| acknowledged_at | DateTime | YES | — | — |
| completed_at | DateTime | YES | — | — |

---

### 3.3 `agent_identities`

| Column | Type | Nullable | Default | Constraints |
|---|---|---|---|---|
| id | String(36) | NO | generate_uuid() | PK |
| cluster_id | String(36) | NO | — | FK → clusters.id (CASCADE), Unique, Index |
| public_key_pem | Text | NO | — | — |
| key_id | String(64) | NO | — | Unique, Index |
| jwks_cache | JSON | YES | — | — |
| is_active | Boolean | — | True | — |
| validation_failures | Integer | — | 0 | — |
| last_key_rotation | DateTime(tz) | YES | — | — |
| created_at | DateTime(tz) | — | func.now() | — |
| updated_at | DateTime(tz) | — | func.now() | — |

---

### 3.4 `alert_config`

| Column | Type | Nullable | Default | Constraints |
|---|---|---|---|---|
| id | String(36) | NO | generate_uuid() | PK, Index |
| organization_id | String(36) | NO | — | Index, FK → organizations.id (CASCADE) |
| cluster_id | String(36) | YES | — | Index |
| alert_type | Enum(AlertType) | NO | — | Index |
| channel | Enum(AlertChannel) | NO | — | — |
| destination | String(500) | NO | — | — |
| severity | Enum(AlertSeverity) | — | WARNING | — |
| enabled | Boolean | — | True | — |
| conditions | JSON | YES | {} | — |
| cooldown_minutes | Integer | — | 30 | — |
| last_triggered_at | DateTime | YES | — | — |
| created_at | DateTime | — | utcnow | — |
| updated_at | DateTime | — | utcnow | — |

---

### 3.5 `alert_history`

| Column | Type | Nullable | Default | Constraints |
|---|---|---|---|---|
| id | String(36) | NO | generate_uuid() | PK, Index |
| config_id | String(36) | NO | — | FK → alert_config.id (CASCADE), Index |
| alert_type | Enum(AlertType) | NO | — | Index |
| severity | Enum(AlertSeverity) | NO | — | — |
| status | Enum(AlertStatus) | — | SENT | Index |
| title | String(500) | NO | — | — |
| message | Text | NO | — | — |
| metadata | JSON | YES | {} | — |
| retry_count | Integer | — | 0 | — |
| next_retry_at | DateTime | YES | — | — |
| sent_at | DateTime | — | utcnow | Index |
| resolved_at | DateTime | YES | — | — |

---

### 3.6 `api_keys`

| Column | Type | Nullable | Default | Constraints |
|---|---|---|---|---|
| id | String(36) | NO | generate_uuid() | PK |
| name | String(100) | NO | — | — |
| key_hash | String(255) | NO | — | Unique, Index |
| prefix | String(10) | NO | — | — |
| organization_id | String(36) | NO | — | FK → organizations.id, Index |
| created_by | String(36) | NO | — | FK → users.id |
| scopes | JSON | — | [] | — |
| is_active | Boolean | — | True | — |
| last_used_at | DateTime | YES | — | — |
| expires_at | DateTime | YES | — | — |
| created_at | DateTime | — | utcnow | — |

---

### 3.7 `approvals`

| Column | Type | Nullable | Default | Constraints |
|---|---|---|---|---|
| id | String(36) | NO | generate_uuid() | PK |
| ticket_type | String(30) | NO | — | Index |
| requested_by | String(36) | NO | — | FK → users.id, Index |
| approved_by | String(36) | YES | — | FK → users.id |
| organization_id | String(36) | NO | — | FK → organizations.id, Index |
| status | String(20) | — | PENDING | Index |
| justification | Text | YES | — | — |
| resource_type | String(30) | YES | — | — |
| resource_id | String(100) | YES | — | — |
| scope | Enum(JitScope) | YES | — | — |
| account_id | String(36) | YES | — | FK → accounts.id |
| access_level | Enum(AccessLevel) | YES | — | — |
| duration_minutes | Integer | YES | — | — |
| expires_at | DateTime | YES | — | — |
| consent_details | JSON | YES | — | — |
| parent_id | String(36) | YES | — | FK → approvals.id |
| created_at | DateTime | — | utcnow | — |
| updated_at | DateTime | — | utcnow | — |

---

### 3.8 `audit_logs`

| Column | Type | Nullable | Default | Constraints |
|---|---|---|---|---|
| id | String(36) | NO | generate_uuid() | PK |
| timestamp | DateTime | — | utcnow | Index |
| actor_id | String(36) | YES | — | Index |
| actor_role | String(30) | YES | — | — |
| event | String(100) | NO | — | Index |
| resource_type | String(50) | YES | — | — |
| resource_id | String(100) | YES | — | — |
| outcome | Enum(AuditOutcome) | — | SUCCESS | — |
| details | JSON | YES | — | — |
| ip_address | String(45) | YES | — | — |
| organization_id | String(36) | YES | — | FK → organizations.id, Index |
| cluster_id | String(36) | YES | — | Index |
| checksum | String(64) | YES | — | — |
| prev_checksum | String(64) | YES | — | — |

---

### 3.9 `authorized_resources`

| Column | Type | Nullable | Default | Constraints |
|---|---|---|---|---|
| id | String(36) | NO | generate_uuid() | PK |
| account_id | String(36) | NO | — | FK → accounts.id (CASCADE), Index |
| resource_id | String(200) | NO | — | Index |
| resource_type | Enum(ResourceType) | NO | — | Index |
| name | String(255) | YES | — | — |
| region | String(50) | YES | — | — |
| status | String(20) | — | authorized | — |
| authorized_by | String(36) | YES | — | FK → users.id |
| created_at | DateTime | — | utcnow | — |
| updated_at | DateTime | — | utcnow | — |

**Unique constraint:** `(account_id, resource_id, resource_type)`

---

### 3.10 `auto_tag_rules`

| Column | Type | Nullable | Default | Constraints |
|---|---|---|---|---|
| id | String(36) | NO | generate_uuid() | PK |
| organization_id | String(36) | NO | — | FK → organizations.id, Index |
| name | String(100) | NO | — | — |
| resource_type | String(50) | NO | — | — |
| conditions | JSON | — | [] | — |
| tags_to_apply | JSON | — | {} | — |
| is_active | Boolean | — | True | — |
| created_at | DateTime | — | utcnow | — |
| updated_at | DateTime | — | utcnow | — |

---

### 3.11 `daily_costs`

| Column | Type | Nullable | Default | Constraints |
|---|---|---|---|---|
| id | String(36) | NO | generate_uuid() | PK |
| account_id | String(36) | NO | — | FK → accounts.id, Index |
| date | Date | NO | — | Index |
| service | String(100) | NO | — | — |
| amount | Numeric(12,4) | NO | — | — |
| currency | String(3) | — | USD | — |
| region | String(50) | YES | — | — |
| created_at | DateTime | — | utcnow | — |

**Unique constraint:** `uq_daily_cost` on `(account_id, date, service, region)`

---

### 3.12 `cost_explorer_sync_status`

| Column | Type | Nullable | Default | Constraints |
|---|---|---|---|---|
| id | String(36) | NO | generate_uuid() | PK |
| account_id | String(36) | NO | — | FK → accounts.id, Unique, Index |
| last_sync_date | Date | YES | — | — |
| status | Enum(SyncStatus) | — | PENDING | — |
| error_message | Text | YES | — | — |
| records_synced | Integer | — | 0 | — |
| sync_started_at | DateTime | YES | — | — |
| sync_completed_at | DateTime | YES | — | — |
| created_at | DateTime | — | utcnow | — |
| updated_at | DateTime | — | utcnow | — |

---

### 3.13 `chaos_experiments`

| Column | Type | Nullable | Default | Constraints |
|---|---|---|---|---|
| id | String(36) | NO | generate_uuid() | PK |
| cluster_id | String(36) | NO | — | FK → clusters.id, Index |
| experiment_type | Enum(ChaosExperimentType) | NO | — | — |
| status | Enum(ChaosExperimentStatus) | — | PENDING | Index |
| config | JSON | YES | {} | — |
| results | JSON | YES | {} | — |
| approval_id | String(36) | YES | — | FK → approvals.id |
| created_by | String(36) | NO | — | FK → users.id |
| started_at | DateTime | YES | — | — |
| completed_at | DateTime | YES | — | — |
| created_at | DateTime | — | utcnow | — |
| updated_at | DateTime | — | utcnow | — |

---

### 3.14 `circuit_breaker_state`

| Column | Type | Nullable | Default | Constraints |
|---|---|---|---|---|
| id | String(36) | NO | generate_uuid() | PK |
| service_name | String(100) | NO | — | Unique, Index |
| state | String(20) | — | CLOSED | — |
| failure_count | Integer | — | 0 | — |
| success_count | Integer | — | 0 | — |
| last_failure_at | DateTime | YES | — | — |
| last_success_at | DateTime | YES | — | — |
| opened_at | DateTime | YES | — | — |
| half_open_at | DateTime | YES | — | — |
| created_at | DateTime | — | utcnow | — |
| updated_at | DateTime | — | utcnow | — |

---

### 3.15 `clusters`

| Column | Type | Nullable | Default | Constraints |
|---|---|---|---|---|
| id | String(36) | NO | generate_uuid() | PK |
| name | String(255) | NO | — | Index |
| account_id | String(36) | NO | — | FK → accounts.id, Index |
| region | String(50) | NO | — | — |
| cluster_type | Enum(ClusterType) | — | EKS | — |
| status | Enum(ClusterStatus) | — | ACTIVE | Index |
| api_key | String(255) | YES | — | Unique, Index |
| agent_version | String(50) | YES | — | — |
| k8s_version | String(20) | YES | — | — |
| vpc_id | String(50) | YES | — | — |
| endpoint | String(500) | YES | — | — |
| node_count | Integer | — | 0 | — |
| last_heartbeat | DateTime | YES | — | — |
| tags | JSON | YES | {} | — |
| metadata | JSON | YES | {} | — |
| connection_mode | Enum(ConnectionMode) | — | AGENT | — |
| karpenter_mode | Enum(KarpenterMode) | YES | — | — |
| created_at | DateTime | — | utcnow | — |
| updated_at | DateTime | — | utcnow | — |

---

### 3.16 `cluster_optimization_settings`

| Column | Type | Nullable | Default | Constraints |
|---|---|---|---|---|
| id | String(36) | NO | generate_uuid() | PK |
| cluster_id | String(36) | NO | — | FK → clusters.id (CASCADE), Unique, Index |
| auto_rebalance_enabled | Boolean | — | False | — |
| auto_rightsizing_enabled | Boolean | — | False | — |
| cost_weight | Float | — | 0.5 | — |
| stability_weight | Float | — | 0.3 | — |
| performance_weight | Float | — | 0.2 | — |
| max_spot_percentage | Integer | — | 70 | — |
| min_od_percentage | Integer | — | 30 | — |
| excluded_instance_families | JSON | YES | [] | — |
| rebalance_cooldown_minutes | Integer | — | 30 | — |
| max_concurrent_replacements | Integer | — | 2 | — |
| diversify_pools | Boolean | — | True | — |
| created_at | DateTime | — | utcnow | — |
| updated_at | DateTime | — | utcnow | — |
| auto_stateful_rightsizing_enabled | Boolean | YES | false | — |
| max_family_diversification_cap_pct | Integer | YES | — | — |
| spot_join_timeout_minutes | Integer | YES | — | — |
| min_node_count | Integer | NO | 1 | — |
| scale_down_threshold_pct | Integer | NO | 20 | — |
| scale_down_stabilization_minutes | Integer | NO | 15 | — |
| enable_ascp_auto_scaler | Boolean | NO | FALSE | — |
| check_interval_seconds | Integer | NO | 15 | — |
| max_concurrent_rebalance_actions | Integer | YES | — | — |

---

### 3.17 `optimization_strategy`

| Column | Type | Nullable | Default | Constraints |
|---|---|---|---|---|
| id | String(36) | NO | generate_uuid() | PK |
| cluster_id | String(36) | NO | — | FK → clusters.id (CASCADE), Unique, Index |
| strategy | Enum(TemplateStrategy) | — | COST_OPTIMIZED | — |
| spot_to_spot_allowed | Boolean | — | True | — |
| max_interruption_rate | Integer | — | 15 | — |
| preferred_families | JSON | YES | [] | — |
| excluded_types | JSON | YES | [] | — |
| risk_savings_tradeoff_pct | Integer | — | 20 | — |
| created_at | DateTime | — | utcnow | — |
| updated_at | DateTime | — | utcnow | — |

---

### 3.18 `cluster_cooldowns`

| Column | Type | Nullable | Default | Constraints |
|---|---|---|---|---|
| id | String(36) | NO | generate_uuid() | PK |
| cluster_id | String(36) | NO | — | FK → clusters.id (CASCADE), Index |
| cooldown_type | String(50) | NO | — | — |
| expires_at | DateTime | NO | — | — |
| reason | String(255) | YES | — | — |
| created_at | DateTime | — | utcnow | — |

---

### 3.19 `cluster_metrics`

| Column | Type | Nullable | Default | Constraints |
|---|---|---|---|---|
| id | String(36) | NO | generate_uuid() | PK |
| cluster_id | String(36) | NO | — | FK → clusters.id, Index |
| timestamp | DateTime | NO | — | Index |
| cpu_utilization | Float | YES | — | — |
| memory_utilization | Float | YES | — | — |
| pod_count | Integer | YES | — | — |
| node_count | Integer | YES | — | — |
| cost_per_hour | Float | YES | — | — |
| spot_percentage | Float | YES | — | — |
| metadata | JSON | YES | {} | — |

**TimescaleDB:** Hypertable on `timestamp`

---

### 3.20 `cluster_policies`

| Column | Type | Nullable | Default | Constraints |
|---|---|---|---|---|
| id | String(36) | NO | generate_uuid() | PK |
| cluster_id | String(36) | NO | — | FK → clusters.id, Index |
| name | String(100) | NO | — | — |
| policy_type | String(50) | NO | — | — |
| config | JSON | NO | — | — |
| is_active | Boolean | — | True | — |
| created_by | String(36) | YES | — | FK → users.id |
| created_at | DateTime | — | utcnow | — |
| updated_at | DateTime | — | utcnow | — |

---

### 3.21 `credential_cache`

| Column | Type | Nullable | Default | Constraints |
|---|---|---|---|---|
| id | String(36) | NO | generate_uuid() | PK |
| approval_id | String(36) | NO | — | FK → approvals.id (CASCADE), Index |
| account_id | String(36) | NO | — | FK → accounts.id (CASCADE), Index |
| user_id | String(36) | NO | — | FK → users.id, Index |
| access_key_id_enc | Text | NO | — | — |
| secret_access_key_enc | Text | NO | — | — |
| session_token_enc | Text | NO | — | — |
| expires_at | DateTime | NO | — | Index |
| is_active | Boolean | — | True | Index |
| rotation_count | Integer | — | 0 | — |
| last_rotation_at | DateTime | YES | — | — |
| created_at | DateTime | — | utcnow | — |

---

### 3.22 `daily_cluster_stats`

| Column | Type | Nullable | Default | Constraints |
|---|---|---|---|---|
| id | String(36) | NO | generate_uuid() | PK |
| cluster_id | String(36) | NO | — | FK → clusters.id, Index |
| date | Date | NO | — | Index |
| total_nodes | Integer | — | 0 | — |
| spot_nodes | Integer | — | 0 | — |
| od_nodes | Integer | — | 0 | — |
| avg_cpu_util | Float | YES | — | — |
| avg_memory_util | Float | YES | — | — |
| total_cost_usd | Float | — | 0 | — |
| savings_usd | Float | — | 0 | — |
| spot_percentage | Float | — | 0 | — |
| created_at | DateTime | — | utcnow | — |
| updated_at | DateTime | — | utcnow | — |

**Unique constraint:** `uq_cluster_date` on `(cluster_id, date)`

---

### 3.23 `execution_state`

| Column | Type | Nullable | Default | Constraints |
|---|---|---|---|---|
| id | String(36) | NO | generate_uuid() | PK |
| cluster_id | String(36) | NO | — | FK → clusters.id (CASCADE), Index |
| instance_id | String(50) | YES | — | Index |
| state | Enum(ExecutionStateEnum) | NO | — | — |
| details | JSON | YES | {} | — |
| started_at | DateTime | — | utcnow | — |
| completed_at | DateTime | YES | — | — |
| updated_at | DateTime | — | utcnow | — |

---

### 3.24 `family_hour_baselines`

| Column | Type | Nullable | Default | Constraints |
|---|---|---|---|---|
| id | String(36) | NO | generate_uuid() | PK |
| instance_family | String(10) | NO | — | Index |
| region | String(20) | NO | — | Index |
| baseline_date | Date | NO | — | Index |
| od_price_hr | Float | NO | — | — |
| spot_p50_hr | Float | NO | — | — |
| spot_p90_hr | Float | NO | — | — |
| savings_pct | Float | NO | — | — |
| sample_count | Integer | NO | — | — |
| computed_at | DateTime | — | utcnow | — |

**Unique constraint:** `uq_family_region_date` on `(instance_family, region, baseline_date)`

---

### 3.25 `hibernation_schedules`

| Column | Type | Nullable | Default | Constraints |
|---|---|---|---|---|
| id | String(36) | NO | generate_uuid() | PK |
| organization_id | String(36) | NO | — | FK → organizations.id, Index |
| name | String(100) | NO | — | — |
| description | Text | YES | — | — |
| schedule_type | String(20) | NO | — | — |
| cron_expression | String(100) | YES | — | — |
| timezone | String(50) | — | UTC | — |
| is_active | Boolean | — | True | — |
| sleep_time | String(5) | YES | — | — |
| wake_time | String(5) | YES | — | — |
| days_of_week | JSON | YES | — | — |
| created_by | String(36) | YES | — | FK → users.id |
| created_at | DateTime | — | utcnow | — |
| updated_at | DateTime | — | utcnow | — |
| last_executed | DateTime | YES | — | — |

---

### 3.26 `hibernation_schedule_clusters` (association)

| Column | Type | Nullable | Default | Constraints |
|---|---|---|---|---|
| schedule_id | String(36) | NO | — | PK, FK → hibernation_schedules.id (CASCADE) |
| cluster_id | String(36) | NO | — | PK, FK → clusters.id (CASCADE) |

---

### 3.27 `cleanup_policies`

| Column | Type | Nullable | Default | Constraints |
|---|---|---|---|---|
| id | UUID | NO | uuid4() | PK |
| organization_id | String(36) | NO | — | FK → organizations.id (CASCADE), Index |
| name | String(255) | NO | — | — |
| resource_type | String(50) | NO | — | — |
| action | Enum(CleanupActionType) | NO | — | — |
| conditions | JSON | — | {} | — |
| exclusions | JSON | — | [] | — |
| is_active | Boolean | — | True | — |
| schedule_cron | String(100) | YES | — | — |
| last_run_at | DateTime(tz) | YES | — | — |
| created_at | DateTime(tz) | — | func.now() | — |
| updated_at | DateTime(tz) | — | func.now() | — |

---

### 3.28 `instances`

| Column | Type | Nullable | Default | Constraints |
|---|---|---|---|---|
| id | String(36) | NO | generate_uuid() | PK |
| instance_id | String(50) | NO | — | Unique (uq_instances_instance_id), Index |
| cluster_id | String(36) | YES | — | FK → clusters.id, Index |
| instance_type | String(50) | NO | — | — |
| availability_zone | String(50) | YES | — | — |
| lifecycle | Enum(InstanceLifecycle) | — | ON_DEMAND | — |
| state | String(20) | — | running | Index |
| node_name | String(255) | YES | — | — |
| private_ip | String(45) | YES | — | — |
| launch_time | DateTime | YES | — | — |
| spot_price | Float | YES | — | — |
| on_demand_price | Float | YES | — | — |
| cpu_cores | Integer | YES | — | — |
| memory_gb | Float | YES | — | — |
| cpu_util | Float | YES | — | — |
| memory_util | Float | YES | — | — |
| pod_count | Integer | YES | 0 | — |
| tags | JSON | YES | {} | — |
| created_at | DateTime | — | utcnow | — |
| updated_at | DateTime | — | utcnow | — |
| launched_by | String(50) | YES | — | Index (ix_instances_launched_by) |

**Composite indexes:**  
- `idx_instance_cluster_state` on `(cluster_id, state)`  
- `idx_instance_cluster_state_type` on `(cluster_id, state, instance_type)`  
- `idx_instance_state_updated` on `(state, updated_at) WHERE state = 'terminated'` (partial)

---

### 3.29 `instance_catalog`

| Column | Type | Nullable | Default | Constraints |
|---|---|---|---|---|
| id | String(36) | NO | generate_uuid() | PK |
| instance_type | String(50) | NO | — | Index |
| region | String(50) | NO | — | Index |
| vcpus | Integer | NO | — | — |
| memory_gb | Float | NO | — | — |
| architecture | String(20) | YES | — | Index |
| instance_family | String(10) | YES | — | Index |
| on_demand_price | Float | YES | — | — |
| spot_price | Float | YES | — | — |
| gpu_count | Integer | — | 0 | — |
| network_performance | String(50) | YES | — | — |
| storage_type | String(50) | YES | — | — |
| created_at | DateTime | — | utcnow | — |
| updated_at | DateTime | — | utcnow | — |

**Unique constraint:** `uq_instance_catalog` on `(instance_type, region)`

---

### 3.30 `organization_invitations`

| Column | Type | Nullable | Default | Constraints |
|---|---|---|---|---|
| id | String(36) | NO | generate_uuid() | PK |
| organization_id | String(36) | NO | — | FK → organizations.id, Index |
| email | String(255) | NO | — | Index |
| role | Enum(UserRole) | — | CLIENT | — |
| status | Enum(InvitationStatus) | — | PENDING | — |
| token | String(255) | NO | — | Unique, Index |
| invited_by | String(36) | NO | — | FK → users.id |
| team_id | String(36) | YES | — | — |
| access_level | Enum(AccessLevel) | YES | — | — |
| expires_at | DateTime | NO | — | — |
| created_at | DateTime | — | utcnow | — |
| accepted_at | DateTime | YES | — | — |

---

### 3.31 `launch_outcomes`

| Column | Type | Nullable | Default | Constraints |
|---|---|---|---|---|
| id | Integer | NO | autoincrement | PK |
| pool_key | String(100) | — | — | Index (with launched_at) |
| cluster_id | String(100) | — | — | Index (with launched_at) |
| instance_type | String(50) | — | — | — |
| az | String(50) | — | — | — |
| region | String(50) | — | — | — |
| outcome | String(20) | — | — | — |
| actual_spot_price_hr | Float | YES | — | — |
| uptime_hours | Float | YES | — | — |
| launched_at | DateTime | — | — | — |
| resolved_at | DateTime | YES | — | — |
| failure_reason | Text | YES | — | — |
| rebalancing_action_id | Integer | YES | — | Index |
| created_at | DateTime | — | func.now() | — |

---

### 3.32 `ml_models`

| Column | Type | Nullable | Default | Constraints |
|---|---|---|---|---|
| id | String(36) | NO | generate_uuid() | PK |
| name | String(100) | NO | — | — |
| model_type | String(50) | NO | — | — |
| version | String(20) | NO | — | — |
| status | Enum(MLModelStatus) | — | TRAINING | — |
| metrics | JSON | YES | {} | — |
| parameters | JSON | YES | {} | — |
| file_path | String(500) | YES | — | — |
| trained_at | DateTime | YES | — | — |
| created_at | DateTime | — | utcnow | — |
| updated_at | DateTime | — | utcnow | — |

---

### 3.33 `model_registry`

| Column | Type | Nullable | Default | Constraints |
|---|---|---|---|---|
| id | String(36) | NO | generate_uuid() | PK |
| name | String(100) | NO | — | — |
| version | String(20) | NO | — | — |
| framework | String(50) | YES | — | — |
| model_path | String(500) | YES | — | — |
| metrics | JSON | YES | {} | — |
| is_active | Boolean | — | True | — |
| created_at | DateTime | — | utcnow | — |
| updated_at | DateTime | — | utcnow | — |

---

### 3.34 `node_metrics`

| Column | Type | Nullable | Default | Constraints |
|---|---|---|---|---|
| id | String(36) | NO | generate_uuid() | PK |
| cluster_id | String(36) | NO | — | FK → clusters.id, Index |
| instance_id | String(50) | NO | — | Index |
| timestamp | DateTime | NO | — | Index |
| cpu_utilization | Float | YES | — | — |
| memory_utilization | Float | YES | — | — |
| disk_utilization | Float | YES | — | — |
| network_in_bytes | Float | YES | — | — |
| network_out_bytes | Float | YES | — | — |
| pod_count | Integer | YES | — | — |

**TimescaleDB:** Hypertable on `timestamp`

---

### 3.35 `node_templates`

| Column | Type | Nullable | Default | Constraints |
|---|---|---|---|---|
| id | String(36) | NO | generate_uuid() | PK |
| name | String(100) | NO | — | — |
| scope | Enum(TemplateScope) | — | SYSTEM | — |
| organization_id | String(36) | YES | — | FK → organizations.id, Index |
| strategy | Enum(TemplateStrategy) | — | COST_OPTIMIZED | — |
| instance_families | JSON | — | [] | — |
| excluded_instance_types | JSON | — | [] | — |
| min_vcpu | Integer | YES | — | — |
| max_vcpu | Integer | YES | — | — |
| min_memory_gb | Float | YES | — | — |
| max_memory_gb | Float | YES | — | — |
| architectures | JSON | — | ["x86_64"] | — |
| max_spot_percentage | Integer | — | 70 | — |
| disk_type | Enum(DiskType) | YES | — | — |
| min_disk_gb | Integer | YES | — | — |
| status | Enum(TemplateStatus) | — | ACTIVE | — |
| created_by | String(36) | YES | — | FK → users.id |
| created_at | DateTime | — | utcnow | — |
| updated_at | DateTime | — | utcnow | — |

---

### 3.36 `node_template_versions`

| Column | Type | Nullable | Default | Constraints |
|---|---|---|---|---|
| id | String(36) | NO | generate_uuid() | PK |
| template_id | String(36) | NO | — | FK → node_templates.id (CASCADE), Index |
| version_number | Integer | NO | — | — |
| config_snapshot | JSON | NO | — | — |
| created_by | String(36) | YES | — | FK → users.id |
| change_reason | Text | YES | — | — |
| is_active | Boolean | — | True | — |
| created_at | DateTime | — | utcnow | — |

**Unique constraint:** `(template_id, version_number)`

---

### 3.37 `cluster_template_mappings`

| Column | Type | Nullable | Default | Constraints |
|---|---|---|---|---|
| id | String(36) | NO | generate_uuid() | PK |
| cluster_id | String(36) | NO | — | FK → clusters.id (CASCADE), Index |
| template_version_id | String(36) | NO | — | FK → node_template_versions.id (CASCADE) |
| is_default | Boolean | — | True | — |
| is_active | Boolean | — | True | — |
| applied_at | DateTime | — | utcnow | — |

---

### 3.38 `onboarding_states`

| Column | Type | Nullable | Default | Constraints |
|---|---|---|---|---|
| id | UUID | NO | uuid4() | PK |
| user_id | String(36) | NO | — | Unique, Index |
| organization_id | String(36) | NO | — | — |
| current_step | Enum(OnboardingStep) | — | WELCOME | — |
| completed_steps | JSON | — | [] | — |
| mode | String(20) | YES | — | — |
| created_at | DateTime | — | utcnow | — |
| updated_at | DateTime | — | utcnow | — |

---

### 3.39 `optimization_jobs`

| Column | Type | Nullable | Default | Constraints |
|---|---|---|---|---|
| id | String(36) | NO | generate_uuid() | PK |
| cluster_id | String(36) | NO | — | FK → clusters.id, Index |
| job_type | String(50) | NO | — | — |
| status | Enum(OptimizationJobStatus) | — | PENDING | Index |
| config | JSON | YES | {} | — |
| results | JSON | YES | {} | — |
| error_message | Text | YES | — | — |
| started_at | DateTime | YES | — | — |
| completed_at | DateTime | YES | — | — |
| created_at | DateTime | — | utcnow | — |
| updated_at | DateTime | — | utcnow | — |

---

### 3.40 `optimizer_proposals`

| Column | Type | Nullable | Default | Constraints |
|---|---|---|---|---|
| id | String(36) | NO | generate_uuid() | PK |
| cluster_id | String(36) | — | — | Index |
| node_name | String(255) | — | — | — |
| current_instance_type | String(50) | — | — | — |
| proposed_instance_type | String(50) | — | — | — |
| proposed_az | String(50) | — | — | — |
| estimated_savings | Float | — | — | — |
| risk_delta | Float | — | — | — |
| status | Enum(ProposalStatus) | — | PENDING | — |
| created_at | DateTime | — | — | — |
| executed_at | DateTime | YES | — | — |

---

### 3.41 `optimizer_states`

| Column | Type | Nullable | Default | Constraints |
|---|---|---|---|---|
| id | String(36) | NO | generate_uuid() | PK |
| cluster_id | String(36) | NO | — | FK → clusters.id (CASCADE), Unique, Index |
| current_phase | Enum(OptimizationPhase) | — | IDLE | — |
| phase_data | JSON | YES | {} | — |
| last_transition_at | DateTime | — | utcnow | — |
| created_at | DateTime | — | utcnow | — |
| updated_at | DateTime | — | utcnow | — |

---

### 3.42 `organizations`

| Column | Type | Nullable | Default | Constraints |
|---|---|---|---|---|
| id | String(36) | NO | generate_uuid() | PK |
| name | String(255) | NO | — | — |
| slug | String(255) | YES | — | Unique |
| external_id | String(100) | YES | — | Unique |
| settings | JSON | YES | {} | — |
| created_at | DateTime | — | utcnow | — |
| updated_at | DateTime | — | utcnow | — |

---

### 3.43 `permissions`

| Column | Type | Nullable | Default | Constraints |
|---|---|---|---|---|
| id | String(36) | NO | generate_uuid() | PK |
| name | String(100) | NO | — | — |
| slug | String(100) | NO | — | Unique |
| description | Text | YES | — | — |
| category | String(50) | YES | — | — |
| created_at | DateTime | — | utcnow | — |

---

### 3.44 `platform_settings`

| Column | Type | Nullable | Default | Constraints |
|---|---|---|---|---|
| id | Integer | NO | autoincrement | PK |
| key | String(100) | NO | — | Unique, Index |
| value | Text | YES | — | — |
| value_type | String(20) | — | string | — |
| description | Text | YES | — | — |
| category | String(50) | YES | — | Index |
| is_secret | Boolean | — | False | — |
| updated_by | String(36) | YES | — | FK → users.id |
| created_at | DateTime(tz) | — | func.now() | — |
| updated_at | DateTime(tz) | — | func.now() | — |

---

### 3.45 `pod_metrics`

| Column | Type | Nullable | Default | Constraints |
|---|---|---|---|---|
| cluster_id | String(36) | NO | — | FK → clusters.id |
| timestamp | DateTime | NO | — | — |
| pod_name | String(255) | NO | — | — |
| namespace | String(255) | YES | — | — |
| node_name | String(255) | YES | — | — |
| cpu_request | Float | YES | — | — |
| cpu_limit | Float | YES | — | — |
| cpu_usage | Float | YES | — | — |
| memory_request | Float | YES | — | — |
| memory_limit | Float | YES | — | — |
| memory_usage | Float | YES | — | — |
| status | String(20) | YES | — | — |

**TimescaleDB:** Hypertable on `timestamp`  
**Views:** `pod_metrics_daily`, `pod_metrics_monthly`

---

### 3.46 `pool_cooldowns`

| Column | Type | Nullable | Default | Constraints |
|---|---|---|---|---|
| id | String(36) | NO | generate_uuid() | PK |
| cluster_id | String(36) | NO | — | FK → clusters.id (CASCADE), Index |
| pool_key | String(100) | NO | — | Index |
| reason | String(50) | NO | — | — |
| expires_at | DateTime | NO | — | — |
| created_at | DateTime | — | utcnow | — |

**Unique constraint:** `(cluster_id, pool_key)`

---

### 3.47 `spot_price_history`

| Column | Type | Nullable | Default | Constraints |
|---|---|---|---|---|
| id | Integer | NO | autoincrement | PK |
| instance_type | String(50) | NO | — | Index |
| availability_zone | String(50) | NO | — | Index |
| spot_price | Float | NO | — | — |
| timestamp | DateTime | NO | — | Index |
| region | String(50) | YES | — | — |

---

### 3.48 `ondemand_pricing`

| Column | Type | Nullable | Default | Constraints |
|---|---|---|---|---|
| id | Integer | NO | autoincrement | PK |
| instance_type | String(50) | NO | — | Index |
| region | String(50) | NO | — | Index |
| price_per_hour | Float | NO | — | — |
| operating_system | String(20) | — | Linux | — |
| updated_at | DateTime | — | utcnow | — |

**Unique constraint:** `uq_od_type_region` on `(instance_type, region)`

---

### 3.49 `spot_advisor_data`

| Column | Type | Nullable | Default | Constraints |
|---|---|---|---|---|
| id | Integer | NO | autoincrement | PK |
| instance_type | String(50) | NO | — | Index |
| region | String(20) | NO | — | Index |
| os_type | String(10) | NO | — | Index |
| savings_pct | Integer | YES | — | — |
| interruption_rate | Integer | YES | — | — |
| scraped_at | DateTime | — | utcnow | — |

**Unique constraint:** `uq_spot_advisor_region_type` on `(region, instance_type, os_type)`

---

### 3.50 `rds_instance_analysis`

| Column | Type | Nullable | Default | Constraints |
|---|---|---|---|---|
| id | String(36) | NO | generate_uuid() | PK, Index |
| organization_id | String(36) | NO | — | FK → organizations.id (CASCADE), Index |
| account_id | String(36) | NO | — | FK → accounts.id (CASCADE), Index |
| db_instance_identifier | String(255) | NO | — | — |
| db_instance_class | String(50) | NO | — | — |
| engine | String(50) | NO | — | — |
| engine_version | String(50) | YES | — | — |
| region | String(50) | NO | — | — |
| multi_az | Boolean | — | False | — |
| storage_type | String(50) | YES | — | — |
| allocated_storage_gb | Integer | YES | — | — |
| monthly_cost | Float | — | 0 | — |
| avg_cpu_utilization | Float | YES | — | — |
| avg_connections | Float | YES | — | — |
| max_connections | Integer | YES | — | — |
| recommendation_type | String(50) | YES | — | — |
| recommended_instance_class | String(50) | YES | — | — |
| estimated_savings | Float | — | 0 | — |
| recommendation_detail | JSON | YES | — | — |
| last_analyzed_at | DateTime | — | utcnow | — |
| created_at | DateTime | NO | utcnow | — |
| updated_at | DateTime | NO | utcnow | — |

---

### 3.51 `rebalancing_actions`

| Column | Type | Nullable | Default | Constraints |
|---|---|---|---|---|
| id | Integer | NO | autoincrement | PK |
| cluster_id | String(36) | NO | — | FK → clusters.id, Index |
| trigger | String(50) | NO | — | — |
| source_instance_type | String(50) | YES | — | — |
| source_az | String(50) | YES | — | — |
| target_instance_type | String(50) | YES | — | — |
| target_az | String(50) | YES | — | — |
| status | String(20) | — | pending | Index |
| reason | Text | YES | — | — |
| metadata | JSON | YES | {} | — |
| created_at | DateTime | — | utcnow | Index |
| completed_at | DateTime | YES | — | — |
| updated_at | DateTime | — | utcnow | — |
| realized_savings_hourly_usd | Float | YES | — | — |
| realized_savings_monthly_usd | Float | YES | — | — |
| source_od_price_hr | Float | YES | — | — |
| target_spot_price_hr | Float | YES | — | — |
| estimated_savings_hr | Float | YES | — | — |
| estimated_savings_mo | Float | YES | — | — |
| actual_instance_type | String(50) | YES | — | — |
| actual_az | String(50) | YES | — | — |
| actual_spot_price_hr | Float | YES | — | — |
| realized_savings_hr | Float | YES | — | — |
| realized_savings_mo | Float | YES | — | — |
| realized_savings_pct | Float | YES | — | — |
| savings_gap_hr | Float | YES | — | — |
| current_state | String(30) | YES | — | Index (idx_rebalancing_current_state) |
| state_entered_at | DateTime | YES | — | — |
| state_history | JSONB | YES | — | — |
| lock_version | Integer | — | 0 | — |
| source_instance_id | String(50) | YES | — | Index |

**Composite indexes:**  
- `idx_rebalancing_actions_source` on `(source_instance_id, current_state)`  
- `idx_active_rebalancing_actions` on `(cluster_id, source_instance_id) WHERE current_state NOT IN ('COMPLETED','FAILED')` (partial)  
- `idx_rebalancing_actions_cluster_state` on `(cluster_id, current_state, created_at)`

**DB Trigger:** `trigger_update_state_entered` — auto-sets `state_entered_at = NOW()` on `current_state` change

---

### 3.52 `ri_utilization`

| Column | Type | Nullable | Default | Constraints |
|---|---|---|---|---|
| id | String(36) | NO | generate_uuid() | PK, Index |
| organization_id | String(36) | NO | — | FK → organizations.id (CASCADE), Index |
| account_id | String(36) | NO | — | FK → accounts.id (CASCADE), Index |
| reservation_id | String(100) | NO | — | — |
| instance_type | String(50) | NO | — | — |
| region | String(50) | NO | — | — |
| platform | String(100) | YES | — | — |
| instance_count | Integer | — | 0 | — |
| utilization_pct | Float | — | 0 | — |
| monthly_cost | Float | — | 0 | — |
| monthly_savings | Float | — | 0 | — |
| start_date | Date | YES | — | — |
| end_date | Date | YES | — | — |
| offering_class | String(20) | YES | — | — |
| recommendation_type | String(50) | YES | — | — |
| estimated_savings | Float | — | 0 | — |
| recommendation_detail | JSON | YES | — | — |
| last_analyzed_at | DateTime | — | utcnow | — |
| created_at | DateTime | NO | utcnow | — |
| updated_at | DateTime | NO | utcnow | — |

---

### 3.53 `rightsizing_proposals`

| Column | Type | Nullable | Default | Constraints |
|---|---|---|---|---|
| id | String(36) | NO | generate_uuid() | PK |
| cluster_id | String(36) | NO | — | FK → clusters.id (CASCADE), Index |
| node_name | String(255) | NO | — | — |
| current_instance_type | String(50) | NO | — | — |
| recommended_type | String(50) | NO | — | — |
| current_cost_hourly | Float | YES | — | — |
| recommended_cost_hourly | Float | YES | — | — |
| savings_percentage | Float | YES | — | — |
| cpu_p95 | Float | YES | — | — |
| memory_p95 | Float | YES | — | — |
| confidence | Float | YES | — | — |
| status | String(20) | — | pending | Index |
| is_actionable | Boolean | — | True | — |
| best_pool | String(150) | YES | — | — |
| reason | Text | YES | — | — |
| created_at | DateTime | — | utcnow | — |
| executed_at | DateTime | YES | — | — |
| updated_at | DateTime | — | utcnow | — |

---

### 3.54 `roles`

| Column | Type | Nullable | Default | Constraints |
|---|---|---|---|---|
| id | String(36) | NO | generate_uuid() | PK |
| name | String(100) | NO | — | — |
| description | Text | YES | — | — |
| role_type | Enum(RoleType) | — | CUSTOM | — |
| organization_id | String(36) | YES | — | FK → organizations.id, Index |
| is_system | Boolean | — | False | — |
| created_at | DateTime | — | utcnow | — |
| updated_at | DateTime | — | utcnow | — |

---

### 3.55 `role_permissions` (association)

| Column | Type | Nullable | Default | Constraints |
|---|---|---|---|---|
| role_id | String(36) | NO | — | PK, FK → roles.id (CASCADE) |
| permission_id | String(36) | NO | — | PK, FK → permissions.id (CASCADE) |

---

### 3.56 `s3_bucket_analysis`

| Column | Type | Nullable | Default | Constraints |
|---|---|---|---|---|
| id | String(36) | NO | generate_uuid() | PK, Index |
| organization_id | String(36) | NO | — | FK → organizations.id (CASCADE), Index |
| account_id | String(36) | NO | — | FK → accounts.id (CASCADE), Index |
| bucket_name | String(255) | NO | — | — |
| region | String(50) | NO | — | — |
| total_size_gb | Float | — | 0 | — |
| object_count | Integer | — | 0 | — |
| current_storage_class | String(50) | YES | — | — |
| monthly_cost | Float | — | 0 | — |
| recommended_class | String(50) | YES | — | — |
| estimated_savings | Float | — | 0 | — |
| access_frequency | String(50) | YES | — | — |
| last_accessed_at | DateTime | YES | — | — |
| recommendation_detail | JSON | YES | — | — |
| last_analyzed_at | DateTime | — | utcnow | — |
| created_at | DateTime | NO | utcnow | — |
| updated_at | DateTime | NO | utcnow | — |

---

### 3.57 `savings_plan_utilization`

| Column | Type | Nullable | Default | Constraints |
|---|---|---|---|---|
| id | String(36) | NO | generate_uuid() | PK, Index |
| organization_id | String(36) | NO | — | FK → organizations.id (CASCADE), Index |
| account_id | String(36) | NO | — | FK → accounts.id (CASCADE), Index |
| savings_plan_id | String(100) | NO | — | — |
| savings_plan_type | Enum(SavingsPlanType) | NO | — | — |
| region | String(50) | YES | — | — |
| commitment_usd_hr | Float | — | 0 | — |
| used_usd_hr | Float | — | 0 | — |
| utilization_pct | Float | — | 0 | — |
| monthly_savings | Float | — | 0 | — |
| start_date | Date | YES | — | — |
| end_date | Date | YES | — | — |
| recommendation_type | String(50) | YES | — | — |
| estimated_savings | Float | — | 0 | — |
| recommendation_detail | JSON | YES | — | — |
| last_analyzed_at | DateTime | — | utcnow | — |
| created_at | DateTime | NO | utcnow | — |
| updated_at | DateTime | NO | utcnow | — |

---

### 3.58 `spot_advisor_rates`

| Column | Type | Nullable | Default | Constraints |
|---|---|---|---|---|
| id | String(36) | NO | generate_uuid() | PK |
| region | String(20) | NO | — | Index |
| instance_type | String(50) | NO | — | Index |
| interruption_rate_category | String(10) | — | — | — |
| interruption_rate_pct | Float | — | — | — |
| scraped_at | DateTime | — | — | — |
| valid_from | Date | — | — | — |

**Unique constraints:**  
- `uq_spot_advisor_rates` on `(region, instance_type, valid_from)`  
- `uq_spot_advisor_region_type` on `(region, instance_type)`

---

### 3.59 `substitute_nodes`

| Column | Type | Nullable | Default | Constraints |
|---|---|---|---|---|
| id | String(36) | NO | generate_uuid() | PK |
| cluster_id | String(36) | — | — | Index |
| instance_id | String(50) | — | — | — |
| instance_type | String(50) | — | — | — |
| az | String(50) | — | — | — |
| state | Enum(SubstituteNodeState) | — | LAUNCHING | — |
| node_name | String(255) | — | — | — |
| created_at | DateTime | — | — | — |
| promoted_at | DateTime | YES | — | — |

---

### 3.60 `substitute_states`

| Column | Type | Nullable | Default | Constraints |
|---|---|---|---|---|
| id | String(36) | NO | generate_uuid() | PK |
| cluster_id | String(36) | NO | — | FK → clusters.id (CASCADE), Index |
| instance_id | String(50) | YES | — | — |
| instance_type | String(50) | YES | — | — |
| az | String(20) | YES | — | — |
| status | String(20) | — | pending | — |
| source_instance_id | String(50) | YES | — | — |
| source_node_name | String(255) | YES | — | — |
| node_name | String(255) | YES | — | — |
| launched_at | DateTime | YES | — | — |
| promoted_at | DateTime | YES | — | — |
| created_at | DateTime | — | utcnow | — |
| updated_at | DateTime | — | utcnow | — |

---

### 3.61 `system_configs`

| Column | Type | Nullable | Default | Constraints |
|---|---|---|---|---|
| id | String(36) | NO | generate_uuid() | PK |
| key | String(100) | NO | — | Unique, Index |
| value | String(500) | YES | — | — |
| description | String(500) | YES | — | — |
| created_at | DateTime | — | utcnow | — |
| updated_at | DateTime | — | utcnow | — |

---

### 3.62 `tag_automation_logs`

| Column | Type | Nullable | Default | Constraints |
|---|---|---|---|---|
| id | String(36) | NO | generate_uuid() | PK, Index |
| organization_id | String(36) | NO | — | Index, FK → organizations.id (CASCADE) |
| rule_id | String(36) | NO | — | Index, FK → tag_automation_rules.id (CASCADE) |
| resource_id | String(100) | NO | — | — |
| resource_type | String(50) | NO | — | — |
| action_taken | String(20) | NO | — | — |
| reason | Text | NO | — | — |
| monthly_cost | Numeric(10,2) | YES | — | — |
| outcome | String(20) | — | success | — |
| error_message | Text | YES | — | — |
| executed_at | DateTime | NO | utcnow | — |

---

### 3.63 `tag_automation_rules`

| Column | Type | Nullable | Default | Constraints |
|---|---|---|---|---|
| id | String(36) | NO | generate_uuid() | PK, Index |
| organization_id | String(36) | NO | — | Index, FK → organizations.id (CASCADE) |
| name | String(255) | NO | — | — |
| trigger_expr | String(100) | NO | — | — |
| resource_types | JSON | NO | [] | — |
| grace_days | SmallInteger | NO | 30 | — |
| action | String(20) | NO | — | — |
| notification_channels | JSON | NO | [] | — |
| safety_conditions | JSON | NO | [] | — |
| enabled | Boolean | NO | True | — |
| last_run_at | DateTime | YES | — | — |
| created_by | String(36) | NO | — | FK → users.id |
| created_at | DateTime | NO | utcnow | — |
| updated_at | DateTime | NO | utcnow | — |

---

### 3.64 `tag_compliance_scores`

| Column | Type | Nullable | Default | Constraints |
|---|---|---|---|---|
| id | String(36) | NO | generate_uuid() | PK, Index |
| organization_id | String(36) | NO | — | FK → organizations.id (CASCADE) |
| resource_id | String(100) | NO | — | — |
| resource_name | String(255) | YES | — | — |
| resource_type | String(50) | NO | — | — |
| environment | String(50) | YES | — | — |
| team | String(100) | YES | — | — |
| score | SmallInteger | NO | — | — |
| status | String(20) | NO | — | — |
| tags_present | Integer | NO | 0 | — |
| monthly_cost | Numeric(10,2) | NO | 0 | — |
| grace_deadline | DateTime | YES | — | — |
| scanned_at | DateTime | NO | utcnow | — |

**Composite indexes:**  
- `ix_tag_compliance_org_scanned` on `(organization_id, scanned_at)`  
- `ix_tag_compliance_org_type` on `(organization_id, resource_type)`  
- `ix_tag_compliance_org_status` on `(organization_id, status)`  
- `ix_tag_compliance_org_resource` on `(organization_id, resource_id)`

---

### 3.65 `tag_policies`

| Column | Type | Nullable | Default | Constraints |
|---|---|---|---|---|
| id | String(36) | NO | generate_uuid() | PK, Index |
| organization_id | String(36) | NO | — | Index, FK → organizations.id (CASCADE) |
| tag_key | String(255) | NO | — | Index |
| description | Text | YES | — | — |
| value_mode | String(20) | — | free_text | — |
| allowed_values | JSON | YES | — | — |
| validation_regex | String(500) | YES | — | — |
| enforcement_level | String(20) | — | advisory | Index |
| resource_types | JSON | — | [] | — |
| regions | JSON | — | [] | — |
| resource_count | Integer | — | 0 | — |
| is_active | Boolean | — | True | Index |
| created_at | DateTime | NO | utcnow | — |
| updated_at | DateTime | NO | utcnow | — |

---

### 3.66 `tag_scoring_configs`

| Column | Type | Nullable | Default | Constraints |
|---|---|---|---|---|
| id | String(36) | NO | generate_uuid() | PK, Index |
| organization_id | String(36) | NO | — | Unique, Index, FK → organizations.id (CASCADE) |
| mode | String(20) | NO | weighted | — |
| threshold | SmallInteger | NO | 60 | — |
| required_keys | JSON | NO | [] | — |
| created_at | DateTime | NO | utcnow | — |
| updated_at | DateTime | NO | utcnow | — |

---

### 3.67 `tag_templates`

| Column | Type | Nullable | Default | Constraints |
|---|---|---|---|---|
| id | String(36) | NO | generate_uuid() | PK, Index |
| organization_id | String(36) | NO | — | Index, FK → organizations.id (CASCADE) |
| name | String(255) | NO | — | — |
| description | Text | YES | — | — |
| tags | JSON | NO | {} | — |
| created_at | DateTime | NO | utcnow | — |
| updated_at | DateTime | NO | utcnow | — |

---

### 3.68 `teams`

| Column | Type | Nullable | Default | Constraints |
|---|---|---|---|---|
| id | String(36) | NO | uuid4() | PK |
| name | String(100) | NO | — | — |
| organization_id | String(36) | NO | — | FK → organizations.id |
| created_at | DateTime | — | utcnow | — |
| governance_config | JSON | — | {} | — |

---

### 3.69 `termination_events`

| Column | Type | Nullable | Default | Constraints |
|---|---|---|---|---|
| id | Integer | NO | autoincrement | PK |
| instance_type | String(50) | NO | — | Index |
| az | String(20) | NO | — | Index |
| region | String(20) | NO | — | — |
| cluster_id | String(100) | YES | — | Index |
| instance_id | String(50) | YES | — | — |
| node_name | String(100) | YES | — | — |
| detected_at | DateTime | NO | — | Index |
| source | String(20) | NO | — | — |
| action_taken | String(50) | YES | — | — |
| metadata | JSONB | YES | — | — |
| created_at | DateTime | — | func.now() | — |

**Composite index:** `idx_termination_cluster_detected` on `(cluster_id, detected_at)`

---

### 3.70 `data_transfer_analysis`

| Column | Type | Nullable | Default | Constraints |
|---|---|---|---|---|
| id | String(36) | NO | generate_uuid() | PK, Index |
| organization_id | String(36) | NO | — | Index, FK → organizations.id (CASCADE) |
| account_id | String(36) | NO | — | Index, FK → accounts.id (CASCADE) |
| region | String(50) | NO | — | — |
| transfer_type | String(100) | NO | — | — |
| total_bytes_gb | Float | — | 0.0 | — |
| monthly_cost | Float | — | 0.0 | — |
| source_resource_id | String(100) | YES | — | — |
| recommendation_type | String(50) | YES | — | — |
| estimated_savings | Float | — | 0.0 | — |
| recommendation_detail | JSON | YES | — | — |
| traffic_direction | String(50) | YES | — | — |
| free_tier_consumed | Integer | — | 0 | — |
| lookback_days | Integer | — | 30 | — |
| last_analyzed_at | DateTime | — | utcnow | — |
| created_at | DateTime | NO | utcnow | — |
| updated_at | DateTime | NO | utcnow | — |

---

### 3.71 `users`

| Column | Type | Nullable | Default | Constraints |
|---|---|---|---|---|
| id | String(36) | NO | generate_uuid() | PK, Index |
| email | String(255) | NO | — | Unique, Index |
| password_hash | String(255) | NO | — | — |
| role | Enum(UserRole) | NO | CLIENT | — |
| is_active | String(1) | NO | "Y" | — |
| organization_id | String(36) | YES | — | FK → organizations.id |
| access_level | Enum(AccessLevel) | — | READ_ONLY | — |
| team_id | String(36) | YES | — | FK → teams.id |
| full_name | String(100) | YES | — | — |
| role_id | String(36) | YES | — | FK → roles.id |
| must_reset_password | Boolean | NO | False | — |
| status | String(20) | — | ACTIVE | — |
| preferences | JSON | YES | — | — |
| team_member_permissions | JSON | YES | {} | — |
| created_at | DateTime | NO | utcnow | — |
| updated_at | DateTime | NO | utcnow | — |
| onboarding_completed | Boolean | — | False | — |

---

### 3.72 `user_permissions` (association)

| Column | Type | Nullable | Default | Constraints |
|---|---|---|---|---|
| user_id | String(36) | NO | — | PK, FK → users.id (CASCADE) |
| permission_id | String(36) | NO | — | PK, FK → permissions.id (CASCADE) |

---

### 3.73 `worker_registrations`

| Column | Type | Nullable | Default | Constraints |
|---|---|---|---|---|
| id | String(36) | NO | generate_uuid() | PK |
| cluster_id | String(36) | NO | — | Index |
| node_name | String(256) | NO | — | Index |
| instance_id | String(64) | YES | — | — |
| instance_type | String(64) | YES | — | — |
| az | String(32) | YES | — | — |
| lifecycle | String(16) | YES | — | — |
| status | String(16) | NO | active | — |
| registered_at | DateTime | NO | utcnow | — |
| last_heartbeat | DateTime | NO | utcnow | — |

**Unique composite index:** `idx_worker_reg_cluster_node` on `(cluster_id, node_name)`

---

### 3.74 `node_alternative_cache` (migration-only, no model file)

| Column | Type | Nullable | Default | Constraints |
|---|---|---|---|---|
| id | Integer | NO | autoincrement | PK |
| cluster_id | String(36) | — | — | FK → clusters.id (CASCADE), Index |
| node_id | String(36) | — | — | Index |
| node_name | String(255) | — | — | — |
| instance_type | String(50) | — | — | — |
| resource_profile | JSONB | — | — | — |
| alternative_pools | JSONB | — | — | — |
| alternative_count | Integer | — | — | — |
| best_pool | String(150) | — | — | — |
| best_saving_pct | Float | — | — | — |
| coverage_status | String(20) | — | — | — |
| computed_at | DateTime | — | — | — |

**Composite index:** `idx_nac_cluster_node` on `(cluster_id, node_name)`

---

### 3.75 `cluster_baselines` (migration-only, no model file)

| Column | Type | Nullable | Default | Constraints |
|---|---|---|---|---|
| cluster_id | String(36) | NO | — | PK, FK → clusters.id (CASCADE) |
| primary_node_type | String(50) | — | — | — |
| primary_az | String(50) | — | — | — |
| baseline_monthly_cost | Float | — | — | — |
| baseline_spot_count | Integer | — | — | — |
| baseline_od_count | Integer | — | — | — |
| computed_at | DateTime | — | — | — |
| updated_at | DateTime | — | — | — |

---

### 3.76 `cluster_cooldown_states` (migration-only, no model file)

| Column | Type | Nullable | Default | Constraints |
|---|---|---|---|---|
| cluster_id | String(36) | NO | — | PK, FK → clusters.id (CASCADE) |
| stabilization_until | DateTime | — | — | — |
| last_action_at | DateTime | — | — | — |
| updated_at | DateTime | — | func.now() | — |

---

### Tables in base_schema.sql with no corresponding model file

These tables exist in the SQL dump but have no active SQLAlchemy model:

| Table | Notes |
|---|---|
| `approval_requests` | Legacy — replaced by `approvals` |
| `chaos_experiment` (singular) | Legacy — replaced by `chaos_experiments` (plural) |
| `lab_experiments` | Experimental/unused |
| `pod_metrics_old` | Legacy backup of pod_metrics |
| `pool_risk_scores` | Used only in base_schema.sql |
| `stateful_rules` | Used only in base_schema.sql |
| `stateless_runtime_rules` | Used only in base_schema.sql |

---

## 4. CRUD Operations Per Table

Summary of which services query each table. **C** = Create, **R** = Read, **U** = Update, **D** = Delete.

| # | Table | Ops | Primary Query Locations |
|---|---|---|---|
| 1 | accounts | CRUD | account_service, cluster_service, onboarding_service, billing_routes, cost_explorer worker, discovery worker |
| 2 | agent_actions | CRD | cluster_service, actions router, karpenter_service, emergency_handler |
| 3 | agent_identities | RU | oidc_federation_service |
| 4 | alert_config | R | notification_service |
| 5 | alert_history | CRUD | notification_service, alert_worker |
| 6 | api_keys | — | **No CRUD found** (keys stored on Cluster.api_key) |
| 7 | approvals | CRUD | approval_service, permission_service, hygiene_service, approval_cleanup worker |
| 8 | audit_logs | CRD | audit_service, governance_service, observability_logger, multiple routes |
| 9 | authorized_resources | CRD | hygiene_service |
| 10 | auto_tag_rules | — | **No CRUD found** |
| 11 | daily_costs | CRUD | cost_explorer worker, resource_cost_service, metrics_service, billing_routes |
| 12 | cost_explorer_sync_status | CRU | cost_explorer worker, billing_routes |
| 13 | chaos_experiments | CRU | chaos_testing_service |
| 14 | circuit_breaker_state | CRU | distributed_locks, chaos_testing_service |
| 15 | clusters | CRUD | cluster_service, agents router, cluster_routes, discovery worker, many workers |
| 16 | cluster_optimization_settings | CRUD | karpenter_routes, cluster_routes, auto_rebalancer, auto_scaler |
| 17 | optimization_strategy | CR | cluster_routes, ascpai_routes, auto_rebalancer |
| 18 | cluster_cooldowns | D | cluster_service (cleanup only) |
| 19 | cluster_metrics | CRD | metrics router, metrics_routes, cluster_service |
| 20 | cluster_policies | CRUD | policy_service, optimization worker |
| 21 | credential_cache | CRU | sts_credential_broker |
| 22 | daily_cluster_stats | CRUD | daily_stats_aggregator worker, multi_cluster_routes |
| 23 | execution_state | R | chaos_testing_service |
| 24 | family_hour_baselines | R | ascpai_routes |
| 25 | hibernation_schedules | CRU | hibernation_service, hibernation_worker, metrics_service |
| 26 | hibernation_schedule_clusters | R | hibernation_service (join filter) |
| 27 | cleanup_policies | — | **No CRUD found** |
| 28 | instances | CRUD | discovery worker, auto_rebalancer, reconciliation_worker, many modules |
| 29 | instance_catalog | CRU | instance_catalog_service, dynamic_instance_helpers |
| 30 | organization_invitations | CRU | auth_service, organization_service |
| 31 | launch_outcomes | CR | pool_reputation_service |
| 32 | ml_models | RU | ml_model_server |
| 33 | model_registry | — | **No CRUD found** |
| 34 | node_metrics | CR | worker_routes, cluster_service |
| 35 | node_templates | CRU | template_service, node_template_routes |
| 36 | node_template_versions | CR | node_template_routes, rightsizing_service |
| 37 | cluster_template_mappings | CRUD | node_template_routes, rightsizing_service, cluster_service |
| 38 | onboarding_states | CRU | onboarding_service, onboarding_routes |
| 39 | optimization_jobs | CRU | optimization worker, metrics_service, report_worker |
| 40 | optimizer_proposals | — | **No CRUD found** |
| 41 | optimizer_states | CRUD | optimizer_coordinator, pool_rotation_service, auto_rebalancer |
| 42 | organizations | CRU | auth_service, admin_service, organization_service |
| 43 | permissions | CR | role_service, seed_rbac, seed_permissions |
| 44 | platform_settings | — | **No CRUD found** |
| 45 | pod_metrics | RD | cluster_service |
| 46 | pool_cooldowns | D | cluster_service (cleanup only) |
| 47 | spot_price_history | CR | aws_pricing_service, ml_feature_service, pricing_collector |
| 48 | ondemand_pricing | CRU | aws_pricing_service, pricing_collector, dynamic_instance_helpers |
| 49 | spot_advisor_data | CRU | spot_advisor_scraper, ml_feature_service, pool_ranking_service |
| 50 | rds_instance_analysis | CRU | rds_analysis_service |
| 51 | rebalancing_actions | CRUD | auto_rebalancer, worker_routes, health_monitor, many workers |
| 52 | ri_utilization | CRU | ri_analysis_service |
| 53 | rightsizing_proposals | CRU | rightsizing_service, optimizer_coordinator, karpenter_routes |
| 54 | roles | CRU | role_service, seed_rbac |
| 55 | role_permissions | — | (managed via Role relationship) |
| 56 | s3_bucket_analysis | CRU | s3_tiering_service |
| 57 | savings_plan_utilization | CRU | savings_plan_service |
| 58 | spot_advisor_rates | CRU | spot_advisor_scraper (upsert on conflict) |
| 59 | substitute_nodes | — | **No CRUD found** |
| 60 | substitute_states | D | cluster_service (cleanup only) |
| 61 | system_configs | CRU | admin_service, cooldown_controller, many services (read credentials) |
| 62 | tag_automation_logs | CR | tag_automation_service, tag_automation_routes |
| 63 | tag_automation_rules | CRUD | tag_automation_service, tag_automation_routes |
| 64 | tag_compliance_scores | CRU | tag_compliance_service, tag_automation_service |
| 65 | tag_policies | CRU | tag_policy_service, tag_scoring_service |
| 66 | tag_scoring_configs | CRU | tag_scoring_service, tag_scoring_routes |
| 67 | tag_templates | R | tag_scoring_service, tag_compliance_routes |
| 68 | teams | CR | team_service |
| 69 | termination_events | CR | termination_monitor worker, ascpai_routes |
| 70 | data_transfer_analysis | CRU | transfer_service |
| 71 | users | CRU | auth_service, cluster_service, audit_service |
| 72 | user_permissions | — | (managed via User relationship) |
| 73 | worker_registrations | CRU | worker_routes |

---

## 5. Migration History

### 5.1 Alembic Migration Chain

```
None
 └─ 001 (base_schema)
     └─ 002 (seed_data)
         └─ eb03c09e15a1 (cluster_id nullable)
             └─ 20260309_spot_advisor_rates
                 └─ 20260309_optimizer_proposals
                     └─ 20260309_substitute_nodes
                         └─ 20260309_cleanup_volume_tables
                             └─ 20260310_stateful_rightsizing_toggle
                                 └─ 20260311_force_delete_node_action
                                     └─ 421d795851e5 (max_family_diversification)
                                         └─ ed7f8dd2b28e (launched_by)
                                             └─ 20260316_spot_join_timeout
                                                 └─ 20260316_autoscaler_settings
                                                     └─ 20260316_ascp_auto_scaler
                                                         └─ 20260316_check_interval
                                                             └─ 20260320_instance_cluster_state_index
                                                                 └─ 20260320_realized_savings
                                                                     └─ 20260320_node_coverage_tables
                                                                         └─ 20260320_savings_columns
                                                                             └─ 20260320_current_state
                                                                                 └─ 20260323_launch_outcomes
                                                                                     └─ 20260325_state_entered_at_trigger
                                                                                         └─ 20260325_max_concurrent_cooldown
```

### 5.2 Migration Details

| # | Revision | Parent | Description | Creates Tables | Alters Tables | Key Changes |
|---|---|---|---|---|---|---|
| 1 | `001` | None | Base schema | All 52+ tables | — | Loads base_schema.sql, creates TimescaleDB hypertables |
| 2 | `002` | `001` | Seed data | — | — | Inserts admin user + 4 node templates |
| 3 | `eb03c09e15a1` | `002` | Make cluster_id nullable | — | instances | DROP NOT NULL on cluster_id |
| 4 | `20260309_spot_advisor_rates` | `eb03c09e15a1` | Add spot_advisor_rates | spot_advisor_rates | — | Unique on (region, instance_type, valid_from) |
| 5 | `20260309_optimizer_proposals` | prev | Add optimizer_proposals | optimizer_proposals | — | ProposalStatus enum |
| 6 | `20260309_substitute_nodes` | prev | Add substitute_nodes | substitute_nodes | — | SubstituteNodeState enum |
| 7 | `20260309_cleanup_volume_tables` | prev | Drop legacy tables | — | — | Drops volume_metrics, volume_recommendations |
| 8 | `20260310_stateful_rightsizing` | prev | Add rightsizing toggle | — | cluster_optimization_settings | +auto_stateful_rightsizing_enabled |
| 9 | `20260311_force_delete_node` | prev | Add action type | — | — | +FORCE_DELETE_NODE to agentactiontype enum |
| 10 | `421d795851e5` | prev | Max family diversification | — | cluster_optimization_settings | +max_family_diversification_cap_pct |
| 11 | `ed7f8dd2b28e` | prev | Add launched_by | — | instances | +launched_by, +index |
| 12 | `20260316_spot_join_timeout` | prev | Spot join timeout | — | cluster_optimization_settings | +spot_join_timeout_minutes |
| 13 | `20260316_autoscaler_settings` | prev | Autoscaler settings | — | cluster_optimization_settings | +min_node_count, +scale_down_threshold_pct, +scale_down_stabilization_minutes |
| 14 | `20260316_ascp_auto_scaler` | prev | ASCP toggle | — | cluster_optimization_settings | +enable_ascp_auto_scaler |
| 15 | `20260316_check_interval` | prev | Check interval | — | cluster_optimization_settings | +check_interval_seconds |
| 16 | `20260320_instance_index` | prev | Performance indexes | — | instances | 3 composite indexes on (cluster_id, state) |
| 17 | `20260320_realized_savings` | prev | Savings tracking | — | rebalancing_actions | +realized_savings_hourly/monthly_usd |
| 18 | `20260320_node_coverage` | prev | Node coverage system | node_alternative_cache, cluster_baselines | — | Per-node alternative tracking |
| 19 | `20260320_savings_columns` | prev | Detailed savings | — | rebalancing_actions | +11 savings columns (source_od_price, target_spot_price, etc.) |
| 20 | `20260320_current_state` | prev | State machine | — | rebalancing_actions | +current_state, state machine for rebalancing |
| 21 | `20260323_launch_outcomes` | prev | Reputation system | launch_outcomes | rebalancing_actions, instances, spot_advisor_rates | +state_entered_at, +state_history, +lock_version, +unique constraints |
| 22 | `20260325_state_trigger` | prev | Auto-timestamp trigger | — | rebalancing_actions | DB trigger for state_entered_at |
| 23 | `20260325_max_concurrent` | prev | Concurrency limits | cluster_cooldown_states | cluster_optimization_settings | +max_concurrent_rebalance_actions |

### 5.3 Standalone Migrations (backend/migrations/)

| File | Description | Creates Tables | Alters Tables | Key Changes |
|---|---|---|---|---|
| 004_add_user_status.py | Add user status | — | users | +status VARCHAR(20) DEFAULT 'ACTIVE' |
| 005_add_team_model.py | Team model | teams | users | +full_name, +team_id FK |
| 006_update_hibernation_schedule.py | Multi-cluster hibernation | hibernation_schedule_clusters | hibernation_schedules | +name, +description, drops cluster_id, migrates to association table |

### 5.4 SQL Files

| File | Description |
|---|---|
| `base_schema.sql` | Full pg_dump (4296 lines): 37 enums, 52+ tables, 100+ indexes, TimescaleDB setup |
| `add_risk_tradeoff_column.sql` | Adds `risk_savings_tradeoff_pct INTEGER DEFAULT 20` to optimization_strategy |

---

## 6. Duplicate / Overlapping Tables Analysis

### 6.1 Spot Advisor Data — TWO tables storing similar info

| Aspect | `spot_advisor_data` (pricing.py) | `spot_advisor_rates` (spot_advisor_rate.py) |
|---|---|---|
| PK | Integer (auto) | String(36) |
| Key cols | instance_type, region, os_type | instance_type, region |
| Data | savings_pct, interruption_rate | interruption_rate_category, interruption_rate_pct |
| Source | spot_advisor_scraper.py | spot_advisor_scraper.py |
| Queried by | ml_feature_service, pool_ranking_service | spot_advisor_scraper (upsert) |
| **Verdict** | **Active — used for ML features + pool ranking** | **Active — used for rate tracking with valid_from dating** |
| **Issue** | Both store interruption data from the same scraper. `spot_advisor_data` has savings_pct; `spot_advisor_rates` has rate_category. Could be merged. |

### 6.2 Cooldowns — THREE tables

| Aspect | `cluster_cooldowns` | `pool_cooldowns` | `cluster_cooldown_states` |
|---|---|---|---|
| Scope | Per-cluster cooldown type | Per-pool within cluster | Per-cluster stabilization |
| Key cols | cluster_id, cooldown_type, expires_at | cluster_id, pool_key, expires_at | cluster_id, stabilization_until |
| Queried by | cluster_service (delete only) | cluster_service (delete only) | (no model — migration-only) |
| **Verdict** | **Likely dead** — only cleanup queries found | **Likely dead** — only cleanup queries found | **New — may replace both** |

### 6.3 ML Models — TWO tables

| Aspect | `ml_models` | `model_registry` |
|---|---|---|
| Key cols | name, model_type, version, status, metrics, file_path | name, version, framework, model_path, metrics |
| Queried by | ml_model_server (R, U) | **No CRUD found** |
| **Verdict** | **Active** | **Dead — unused duplicate** |

### 6.4 Optimization Proposals — TWO tables

| Aspect | `optimizer_proposals` | `rightsizing_proposals` |
|---|---|---|
| Key cols | cluster_id, node_name, current/proposed type, savings, status | cluster_id, node_name, current/recommended type, savings, status |
| Queried by | **No CRUD found** | rightsizing_service, optimizer_coordinator, karpenter_routes |
| **Verdict** | **Dead — unused** | **Active — the real proposal table** |

### 6.5 Substitute Tracking — TWO tables

| Aspect | `substitute_nodes` | `substitute_states` |
|---|---|---|
| Key cols | cluster_id, instance_id, instance_type, az, state | cluster_id, instance_id, instance_type, az, status |
| Queried by | **No CRUD found** | cluster_service (delete only) |
| **Verdict** | **Dead — created by migration, never queried** | **Nearly dead — only cleanup** |
| **Note** | substitute_manager.py uses Redis-backed state machine instead of DB |

### 6.6 Instance Utilization — Overlapping columns

| Aspect | `instances` table | `node_metrics` table |
|---|---|---|
| CPU | cpu_util (Float) | cpu_utilization (Float) |
| Memory | memory_util (Float) | memory_utilization (Float) |
| Disk | — | disk_utilization (Float) |
| Network | — | network_in_bytes, network_out_bytes |
| Cardinality | 1 row per instance (latest) | Time-series (hypertable) |
| **Verdict** | **Not duplicate** — instances has snapshot; node_metrics has history. But instances.cpu_util/memory_util overlap and may diverge. |

### 6.7 Daily Cost Tracking — Overlapping

| Aspect | `daily_costs` | `daily_cluster_stats` |
|---|---|---|
| Scope | Per-account, per-service, per-region | Per-cluster |
| Key cols | account_id, date, service, amount | cluster_id, date, total_cost_usd, savings_usd |
| Source | AWS Cost Explorer API | Calculated from instance data |
| **Verdict** | **Not duplicate** — different granularity (AWS billing vs cluster-level stats) |

### 6.8 Legacy/Dead Tables in base_schema.sql

| Table | Status | Reason |
|---|---|---|
| `approval_requests` | Dead | Replaced by `approvals` |
| `chaos_experiment` (singular) | Dead | Replaced by `chaos_experiments` (plural) |
| `lab_experiments` | Dead | No model, no queries |
| `pod_metrics_old` | Dead | Legacy backup |
| `pool_risk_scores` | Dead | No model, no queries |
| `stateful_rules` | Dead | No model, no queries |
| `stateless_runtime_rules` | Dead | No model, no queries |

---

## 7. Enum Types

All 37+ PostgreSQL enum types defined in the schema:

| Enum | Values | Used By |
|---|---|---|
| `accesslevel` | READ_ONLY, EXECUTION, FULL | users, approvals, invitations |
| `accountstatus` | ACTIVE, INACTIVE, SUSPENDED, SCANNING | accounts |
| `agentactionstatus` | PENDING, ACKNOWLEDGED, IN_PROGRESS, COMPLETED, FAILED, CANCELLED | agent_actions |
| `agentactiontype` | CORDON, UNCORDON, DRAIN, LAUNCH_INSTANCE, TERMINATE_INSTANCE, FORCE_DELETE_NODE, PATCH_KARPENTER_NODEPOOL, ... | agent_actions |
| `alert_channel_enum` | SLACK, EMAIL, WEBHOOK, PAGERDUTY | alert_config |
| `alert_severity_enum` | INFO, WARNING, CRITICAL | alert_config, alert_history |
| `alert_status_enum` | SENT, FAILED, RETRYING, RESOLVED | alert_history |
| `alert_type_enum` | COST_SPIKE, SPOT_INTERRUPTION, REBALANCE, SCALING, HEALTH, ... | alert_config, alert_history |
| `auditoutcome` | SUCCESS, FAILURE, PARTIAL | audit_logs |
| `chaosexperimentstatus` | PENDING, APPROVED, RUNNING, COMPLETED, FAILED, ROLLED_BACK | chaos_experiments |
| `chaosexperimenttype` | SPOT_INTERRUPTION, NODE_FAILURE, AZ_FAILURE, ... | chaos_experiments |
| `cleanupactiontype` | TAG, STOP, TERMINATE, SNAPSHOT_DELETE | cleanup_policies |
| `clusterstatus` | ACTIVE, INACTIVE, MAINTENANCE, DELETING | clusters |
| `clustertype` | EKS, KOPS, CUSTOM | clusters |
| `connectionmode` | AGENT, AGENTLESS, HYBRID | clusters |
| `disktype` | GP2, GP3, IO1, IO2, ST1, SC1 | node_templates |
| `execution_state_enum` | PENDING, IN_PROGRESS, COMPLETED, FAILED, CANCELLED | execution_state |
| `hygieneactiontype` | STOP, TERMINATE, TAG, NOTIFY | (hygiene policies) |
| `instancelifecycle` | SPOT, ON_DEMAND | instances |
| `invitationstatus` | PENDING, ACCEPTED, EXPIRED, REVOKED | organization_invitations |
| `jitscope` | ACCOUNT, CLUSTER, SERVICE, RESOURCE | approvals |
| `karpentermode` | OBSERVE, MANAGED | clusters |
| `mlmodelstatus` | TRAINING, TRAINED, PRODUCTION, ARCHIVED, FAILED | ml_models |
| `onboardingstep` | WELCOME, CONNECT_AWS, ADD_CLUSTER, CONFIGURE, COMPLETE | onboarding_states |
| `optimizationjobstatus` | PENDING, RUNNING, COMPLETED, FAILED | optimization_jobs |
| `optimizationphase` | IDLE, ANALYZING, PROPOSING, EXECUTING, COOLING_DOWN | optimizer_states |
| `proposalstatus` | PENDING, APPROVED, REJECTED, EXECUTED | optimizer_proposals, rightsizing_proposals |
| `resourcetype` | EC2, RDS, S3, EBS, LAMBDA, ... | authorized_resources |
| `roletype` | SYSTEM, CUSTOM | roles |
| `savingsplantype` | COMPUTE, EC2_INSTANCE, SAGEMAKER | savings_plan_utilization |
| `syncstatus` | PENDING, IN_PROGRESS, COMPLETED, FAILED | cost_explorer_sync_status |
| `templatescope` | SYSTEM, ORGANIZATION | node_templates |
| `templatestatus` | ACTIVE, ARCHIVED, DRAFT | node_templates |
| `templatestrategy` | COST_OPTIMIZED, BALANCED, PERFORMANCE, STABILITY | node_templates, optimization_strategy |
| `userrole` | SUPER_ADMIN, ORG_ADMIN, TEAM_LEAD, MEMBER, CLIENT | users, invitations |
| `substitutenodestate` | LAUNCHING, READY, PROMOTING, TERMINATED | substitute_nodes |

---

## 8. Unused / Dead Tables

Tables that exist in the database but have **no active CRUD operations**:

| Table | Model Exists? | Query Activity | Recommendation |
|---|---|---|---|
| `api_keys` | YES | None found | Keys stored on Cluster.api_key instead |
| `auto_tag_rules` | YES | None found | Model defined but never used |
| `cleanup_policies` | YES | None found | Model defined but never used |
| `model_registry` | YES | None found | Duplicate of ml_models — remove |
| `optimizer_proposals` | YES | None found | Replaced by rightsizing_proposals |
| `platform_settings` | YES | None found | Config stored in system_configs instead |
| `substitute_nodes` | YES | None found | Redis state machine used instead |
| `approval_requests` | NO (SQL only) | None | Legacy — replaced by approvals |
| `chaos_experiment` | NO (SQL only) | None | Legacy — replaced by chaos_experiments |
| `lab_experiments` | NO (SQL only) | None | Experimental/dead |
| `pod_metrics_old` | NO (SQL only) | None | Legacy backup — drop |
| `pool_risk_scores` | NO (SQL only) | None | Never integrated |
| `stateful_rules` | NO (SQL only) | None | Never integrated |
| `stateless_runtime_rules` | NO (SQL only) | None | Never integrated |
| `cluster_cooldowns` | YES | Delete only | Likely dead — only cleanup |
| `pool_cooldowns` | YES | Delete only | Likely dead — only cleanup |
| `substitute_states` | YES | Delete only | Substitute manager uses Redis |

**Total dead/unused tables: ~17**
