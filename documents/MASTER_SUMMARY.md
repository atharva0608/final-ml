# Spot Optimizer Platform — Master Summary

> **Platform Mission**: Automated cloud infrastructure optimization using AI/ML to reduce Kubernetes and AWS costs by up to 70% while maintaining 99.99% availability.
> **Last Updated**: 2026-02-17
> **Version**: 1.0.0

---

## Table of Contents

1. [Platform Overview](#1-platform-overview)
2. [System Architecture](#2-system-architecture)
3. [AtharvaAI ML Pipeline](#3-atharvaai-ml-pipeline)
4. [Pod Metrics & Right-Sizing](#4-pod-metrics--right-sizing)
5. [Termination Monitoring (System B)](#5-termination-monitoring-system-b)
6. [Karpenter Integration](#6-karpenter-integration)
7. [Three Pricing Models](#7-three-pricing-models)
8. [JIT Approval System](#8-jit-approval-system)
9. [Automation Settings](#9-automation-settings)
10. [Security & RBAC](#10-security--rbac)
11. [API Reference](#11-api-reference)
12. [Backend Catalog](#12-backend-catalog)
13. [Frontend Catalog](#13-frontend-catalog)
14. [User Flow Architecture](#14-user-flow-architecture)
15. [Deployment Guide](#15-deployment-guide)
16. [Change Ledger (Recurring Issues & Fixes)](#16-change-ledger)
17. [Known Issues & Next Steps](#17-known-issues--next-steps)

---

## 1. Platform Overview

### What It Does

The **Spot Optimizer Platform** is a SaaS application that:

- Connects to customer AWS accounts via IAM roles
- Discovers EKS clusters and EC2 instances
- Deploys DaemonSet agents for real-time monitoring
- Uses ML models (ONNX) to rank the safest/cheapest spot instance pools
- Provides right-sizing recommendations based on P95/P99 pod usage analysis
- Automates Karpenter NodePool updates for optimal node provisioning
- Detects spot termination notices and triggers auto-rebalancing
- Offers a full-featured React dashboard with RBAC, approvals, and team management

### Tech Stack

| Layer | Technologies |
|:------|:------------|
| **Backend** | Python 3.11, FastAPI, SQLAlchemy, Celery, Redis, PostgreSQL |
| **Frontend** | React 18, Vite, Zustand, React Router v6, Recharts |
| **ML** | ONNX Runtime, NumPy, scikit-learn (training), 45-feature pipeline |
| **Infrastructure** | Docker, Docker Compose, AWS (EKS, EC2, S3, Cost Explorer, STS) |
| **Agent** | Python DaemonSet, kubernetes-client, metrics.k8s.io API |

### File Counts

| Directory | Files | Purpose |
|:----------|:------|:--------|
| `backend/api/` | 36 | FastAPI route handlers |
| `backend/services/` | 24+ | Core business logic |
| `backend/models/` | 20+ | SQLAlchemy database models |
| `backend/workers/tasks/` | 8+ | Celery background workers |
| `frontend/src/components/` | ~90 | React UI components |
| `frontend/src/pages/` | 10+ | Page-level layouts |
| `agent/` | 5 | Kubernetes DaemonSet agent |
| `decision_engine/` | 3+ | ML inference and web scrapers |

---

## 2. System Architecture

### Service Dependency Diagram

```
┌──────────────── API Layer ─────────────────┐
│ AuthRoutes → AuthService                    │
│ ClusterRoutes → ClusterService              │
│ ApprovalRoutes → ApprovalService            │
│ HygieneRoutes → HygieneService             │
│ PermissionRoutes → PermissionService        │
│ MetricsRoutes → MetricsService              │
│ AtharvaAIRoutes → PoolRankingService        │
│ PodMetricsRoutes → RightSizingService       │
└──────────────────┬──────────────────────────┘
                   │
┌──────────────── Service Layer ──────────────┐
│ CostExplorerService → AWS Cost Explorer API  │
│ AgentInjectorService → Kubernetes API        │
│ PoolRankingService → ONNX Models + Redis     │
│ KarpenterService → EKS + Karpenter CRD      │
│ MLFeatureService → 45-feature engineering    │
│ RightSizingService → P95/P99 analysis        │
└──────────────────┬──────────────────────────┘
                   │
┌──────────────── Worker Layer ───────────────┐
│ cost_explorer (every 6 hours)                │
│ discovery_worker (every 30 minutes)          │
│ atharvaai_worker (ML ranking every 30s)      │
│ termination_monitor (every 30s)              │
│ auto_rebalancer (every 15s)                  │
│ karpenter_sync (every 30s)                   │
│ pod_metrics_cleanup (daily)                  │
│ spot_price_collector (every 10 min)          │
└──────────────────┬──────────────────────────┘
                   │
┌──────────────── Data Layer ─────────────────┐
│ PostgreSQL: users, orgs, clusters, instances │
│ PostgreSQL: approvals, teams, permissions    │
│ PostgreSQL: pod_metrics, spot_price_history  │
│ PostgreSQL: termination_events, rebalancing  │
│ Redis: session cache, ML rankings, blacklist │
└─────────────────────────────────────────────┘
```

### Backend Services (24+)

| Service | File | Purpose |
|:--------|:-----|:--------|
| AuthService | `auth_service.py` | JWT auth, signup, login, token refresh |
| ClusterService | `cluster_service.py` | EKS discovery, cluster onboarding |
| AgentInjectorService | `agent_injector.py` | DaemonSet deployment to clusters |
| CostExplorerService | `cost_explorer.py` | AWS Cost Explorer integration |
| MetricsService | `metrics_service.py` | Dashboard KPIs, instance metrics |
| PoolRankingService | `pool_ranking_service.py` | 8-step ML pool selection pipeline |
| MLFeatureService | `ml_feature_service.py` | 45-feature engineering for ML |
| RightSizingService | `rightsizing_service.py` | P95/P99 analysis, cost recommendations |
| KarpenterService | `karpenter_service.py` | Karpenter NodePool YAML management |
| OrganizationService | `organization_service.py` | Org CRUD, settings, impersonation |
| TeamService | `team_service.py` | Team management, member permissions |
| ApprovalService | `approval_service.py` | JIT approval workflows |
| HygieneService | `hygiene_service.py` | Resource cleanup scanning |
| PermissionService | `permission_service.py` | RBAC enforcement, feature gates |
| ExperimentService | `experiment_service.py` | A/B test experiments |

### Background Workers (8+)

| Worker | Schedule | Purpose |
|:-------|:---------|:--------|
| `cost_explorer` | Every 6 hours | Fetch AWS Cost Explorer data |
| `discovery_worker` | Every 30 min | Discover new clusters/instances |
| `atharvaai_worker` | Every 30s | ML pool ranking pipeline |
| `spot_price_collector` | Every 10 min | Collect spot pricing |
| `family_baseline_compute` | Weekly | Pre-compute family baselines |
| `termination_monitor` | Every 30s | Monitor termination events |
| `auto_rebalancer` | Every 15s | Execute rebalancing actions |
| `karpenter_nodepool_sync` | Every 30s | Sync ML rankings → Karpenter |
| `pod_metrics_cleanup` | Daily | Clean pod_metrics > 7 days |

---

## 3. AtharvaAI ML Pipeline

### Overview

The AtharvaAI system is the core ML-driven pool selection engine. It uses ONNX models (classifier + regressor) with 45 engineered features to rank the safest and cheapest AWS spot instance pools.

### 8-Step Pool Selection Pipeline

```
Step 1: Node Template Filtering
         (architecture, vCPU, memory, families, sizes)
                       ↓
Step 2: AZ Filtering
         (user AZ preferences)
                       ↓
Step 3: Spot Advisor Filter
         (29,794 pools from AWS — REAL DATA)
                       ↓
Step 4: Global Blacklist Check
         (System B flags from Redis, 12h TTL)
                       ↓
Step 5: Capacity Check
         (AWS API validation)
                       ↓
Step 6: Price Fetch
         (AWS Pricing API)
                       ↓
Step 7: ML Model Scoring
         (ONNX: classifier + regressor)
         • Engineer 45 features
         • Predict savings % (0-1)
         • Predict cost (USD)
         • Apply System B penalty (-0.50 if flagged)
         • Final score: (savings×100) - (cost×0.1)
                       ↓
Step 8: Final Ranking & Caching
         (Sort by score, cache in Redis 30s TTL)
         → API: POST /api/v1/atharvaai/pools/rankings
```

### 45-Feature Engineering Breakdown

| Category | Count | Examples |
|:---------|:------|:--------|
| Temporal | 10 | hour, day, cyclical sin/cos encodings |
| Lag | 3 | 1h, 4h, 24h lookback prices |
| Rolling Statistics | 8 | 4h/24h mean, std, min, max |
| Price Dynamics | 5 | velocity, volatility, headroom, saturation, stability |
| Family-Time Patterns | 6 | learned from historical data |
| Family Stress | 3 | cross-instance contagion metrics |
| Event Features | 3 | holidays, stress events |
| Pool Risk | 1 | historical failure rate |
| Categorical | 6 | family, size, AZ + padding |

**Graceful Degradation**: When full history unavailable, falls back to 15 minimum features (~75% accuracy vs ~95% with full features).

### ML Model Files

- `ml_model/model/classifier_6.onnx` — Predicts savings probability
- `ml_model/model/regressor_6.onnx` — Predicts cost estimate

### Spot Advisor Web Scraper

- **Source**: `https://spot-bid-advisor.s3.amazonaws.com/spot-advisor-data.json`
- **Total pools**: 29,794 instance/region combinations
- **Fetch time**: ~2 seconds
- **Cache**: 1 hour (in-memory + Redis)
- **File**: `decision_engine/webscraper/spot_advisor_enhanced.py` (600 lines)

### Performance

- Pipeline execution: ~500ms per cycle
- ML inference: <50ms per pool (both models)
- Redis cache TTL: 30 seconds
- Celery schedule: Every 30 seconds
- API response: <500ms (from Redis cache)

### Frontend Integration

- **LivePoolRankings**: `components/atharva/LivePoolRankings.jsx` — Real-time rankings table with ML scores, savings %, cost estimates, interruption ratings
- **OptimizationStatusHeader**: `components/atharva/OptimizationStatusHeader.jsx` — System health, top pool, rebalancing status, flagged pools
- **Zustand Store**: `store/useAtharvaStore.js` — State management with auto-refresh every 30s

### API Endpoints

| Method | Path | Auth | Description |
|:-------|:-----|:-----|:------------|
| `POST` | `/api/v1/atharvaai/pools/rankings` | Yes | Get ML-scored pool rankings |
| `GET` | `/api/v1/atharvaai/blacklist` | Yes | Get globally flagged risky pools |
| `GET` | `/api/v1/atharvaai/rebalancing/status` | Yes | Get rebalancing action history |
| `GET` | `/api/v1/atharvaai/health` | No | Health check |

### Database Tables

| Table | Purpose |
|:------|:--------|
| `spot_price_history` | 144-point rolling buffer per pool |
| `family_hour_baselines` | Pre-computed family-time patterns |
| `pool_risk_scores` | Historical interruption rates |
| `node_templates` | User-defined filtering requirements |
| `termination_events` | Termination notice log |
| `rebalancing_actions` | Auto-rebalancing history |

---

## 4. Pod Metrics & Right-Sizing

### Overview

DaemonSet agents collect pod-level CPU/memory metrics every 5 minutes. The Right-Sizing Service analyzes P95/P99 usage to generate cost optimization recommendations.

### Data Flow

```
DaemonSet Agents (every 5 min)
    → POST /api/v1/pod-metrics/batch (25-100 pods per node)
    → PostgreSQL pod_metrics table (7-day retention, 2016 data points/pod)
    → Right-Sizing Service (P95/P99 + 20% safety buffer)
    → GET /api/v1/pod-metrics/right-sizing/recommendations
```

### Agent Module: `pod_metrics_collector.py` (340 lines)

**Key Features**:
1. **Controller Detection**: Resolves ReplicaSet → Deployment hierarchy
2. **Resource Metrics**: CPU (millicores) + Memory (bytes) from metrics.k8s.io API
3. **DaemonSet Optimization**: Only collects for local node; skips system namespaces
4. **Batch Submission**: POST to `/api/v1/pod-metrics/batch` every 5 min

**Environment Variables**:

| Variable | Default | Description |
|:---------|:--------|:------------|
| `POD_METRICS_INTERVAL` | 300 | Collection interval (seconds) |
| `NODE_NAME` | Required | Current node name (DaemonSet downward API) |
| `BACKEND_URL` | Required | Backend API URL |
| `API_KEY` | Required | Authentication key |
| `CLUSTER_ID` | Required | Cluster identifier |

### Docker Image

- **Repository**: `atharva608/spot-optimizer-agent`
- **Tags**: `latest`, `v1.1-pod-metrics`
- **Base**: Python 3.11-slim, ~150 MB

### Database Schema: `pod_metrics` Table

18 columns, 12 indexes. Key columns:

| Column | Type | Description |
|:-------|:-----|:------------|
| `cluster_id` | VARCHAR(36) | FK to clusters |
| `namespace` | VARCHAR(253) | Kubernetes namespace |
| `pod_name` / `node_name` | VARCHAR(253) | Pod/node identity |
| `controller_kind` / `controller_name` | VARCHAR | Deployment, StatefulSet, etc. |
| `cpu_usage_millicores` | INTEGER | Current CPU usage |
| `cpu_request_millicores` | INTEGER | Configured CPU request |
| `memory_usage_bytes` | BIGINT | Current memory usage |
| `memory_request_bytes` | BIGINT | Configured memory request |
| `cpu_utilization_pct` / `memory_utilization_pct` | FLOAT | usage / request × 100 |
| `timestamp` | TIMESTAMP | Collection time |
| `metadata` | JSONB | Labels, annotations |

### Right-Sizing Algorithm

```
1. Fetch all pod metrics for workload in time window (7 days)
2. Validate minimum data points (100)
3. Calculate P50, P95, P99 for CPU and memory
4. Apply 20% safety buffer: recommended = P95 × 1.20
5. Estimate costs: CPU $0.04/vCPU-hr, Memory $0.005/GB-hr, × 730 hr/month × replicas
6. Classify: REDUCE (usage < 50% request), INCREASE (P99 > 95% request), NO_CHANGE
7. Assign confidence: HIGH (≥80% coverage), MEDIUM (50-80%), LOW (<50%)
```

### Example Recommendation

| Metric | Current | Recommended | Savings |
|:-------|:--------|:------------|:--------|
| CPU | 500m | 300m (P95+20%) | 40% |
| Memory | 512 MB | 307 MB (P95+20%) | 40% |
| Monthly Cost | $45.00 | $27.00 | **$18/month** |
| Confidence | — | HIGH (2016 data points) | — |

### API Endpoints

| Method | Path | Description |
|:-------|:-----|:------------|
| `POST` | `/api/v1/pod-metrics/batch` | DaemonSet batch submission |
| `GET` | `/api/v1/pod-metrics` | Query metrics with filters |
| `GET` | `/api/v1/pod-metrics/right-sizing/recommendations` | Generate recommendations |
| `DELETE` | `/api/v1/pod-metrics/cleanup` | Manual cleanup trigger |

### Performance

- DB inserts: ~33/sec (100 nodes × 50 pods / 5 min)
- 7-day storage: ~2.5 GB for 10M rows
- API response: <1 second for recommendations
- Agent memory: ~80 MB per DaemonSet pod

---

## 5. Termination Monitoring (System B)

### Flow

```
AWS Spot Termination Notice (2-minute warning)
    ├── EventBridge Listener
    └── DaemonSet Agent
                ↓
    detect_termination_notice()
        ├── Flag pool in Redis blacklist (12h TTL)
        ├── Log to termination_events table
        └── Trigger emergency rebalancing (90s)
                ↓
    Auto-rebalancer picks it up (every 15s)
        ├── Cordon nodes on source pool
        ├── Update Karpenter NodePool
        ├── Drain pods (graceful eviction, 30s grace)
        └── Mark action completed
```

### Redis Blacklist

```python
# SET of blacklisted pools
risky_pools: {'m5.xlarge:aps1-az1', 'c5.large:aps1-az2', ...}

# Metadata per pool (TTL: 12 hours)
risky_pool_meta:<pool_key> → {
    "instance_type": "m5.xlarge",
    "az": "aps1-az1",
    "flagged_at": "...",
    "reason": "termination_detected",
    "ttl_seconds": 43200
}
```

### Rebalancing Modes

| Mode | Trigger | Time Budget | Priority |
|:-----|:--------|:------------|:---------|
| Emergency | Termination notice | 90 seconds | Move pods immediately |
| Graceful | Risk prediction | 10 minutes | Drain with grace period |

### Key Files

- `backend/workers/tasks/termination_monitor.py` (300 lines) — Detection + blacklisting
- `backend/workers/tasks/auto_rebalancer.py` (350 lines) — Cordon → drain → complete
- `backend/models/termination_event.py` — Termination event model
- `backend/models/rebalancing_action.py` — Rebalancing action model

---

## 6. Karpenter Integration

### NodePool Sync Flow

```
ML Pool Ranking Pipeline (every 30s)
    → Ranks pools: Top 10 safe instance types
    → sync_karpenter_nodepools() Celery task
        → For each active EKS cluster:
            → Get ML rankings for cluster region
            → Extract top 10 instance types + safe AZs
            → KarpenterService.sync_ml_rankings_to_nodepool()
                → Get Kubernetes API client (EKS token via SigV4)
                → PATCH existing NodePool or CREATE new one
    → Karpenter reads updated NodePool
        → Provisions nodes from ML-approved list only
```

### Generated NodePool YAML

```yaml
apiVersion: karpenter.sh/v1beta1
kind: NodePool
metadata:
  name: ml-optimized
  labels:
    managed-by: spot-optimizer
spec:
  template:
    spec:
      requirements:
        - key: karpenter.sh/capacity-type
          operator: In
          values: ["spot"]
        - key: node.kubernetes.io/instance-type
          operator: In
          values: ["m5a.xlarge", "m5.large", "c5.xlarge", ...]  # ML top 10
        - key: topology.kubernetes.io/zone
          operator: In
          values: ["aps1-az1", "aps1-az2", "aps1-az3"]  # Safe AZs
  disruption:
    consolidationPolicy: WhenUnderutilized
    expireAfter: "720h"  # 30 days
```

### EKS Authentication

Uses SigV4 presigned URL for `sts:GetCallerIdentity` → base64-encoded as `k8s-aws-v1.<token>` bearer token.

### Key File

- `backend/services/karpenter_service.py` (418 lines)

---

## 7. Three Pricing Models

### Model A: Actual Cost (AWS Cost Explorer)

- **Source**: AWS Cost Explorer API
- **What**: Invoice-accurate cost — what AWS actually charged
- **Update**: Every 6 hours via Celery worker
- **Used in**: Dashboard KPIs, cost trends, billing reports

### Model B: Calculated Cost (Instance Pricing × Hours)

- **Source**: Internal calculation: `instance_price × running_hours`
- **What**: Theoretical cost based on instance types and uptime
- **Used in**: Savings calculations, cost comparisons, what-if analysis

### Model C: Reserved/Savings Plan Cost

- **Source**: AWS Cost Explorer + pricing API
- **What**: Compares current spend against RI/SP coverage
- **Used in**: RI waste detection, S3 intelligent tiering audit, RDS Multi-AZ analysis

### Cost Optimization Features

1. **RI Waste Detection** — Identifies underutilized Reserved Instances
2. **S3 Intelligent-Tiering Audit** — Recommends S3 storage class changes
3. **RDS Multi-AZ Analysis** — Evaluates RDS Multi-AZ necessity
4. **Data Transfer Optimization** — Identifies cross-AZ/region transfer waste

---

## 8. JIT Approval System

### Overview

Production-grade Just-In-Time Feature Escalation model enforcing time-bound access control for sensitive operations.

### Flow

```
User clicks protected action
    → ProtectedButton checks permission
    → If not permitted: Opens ApprovalRequestModal
        → Approval request created (status: pending)
        → Admin reviews in Approval Queue
        → Approved: Time-limited access granted (1-8 hours)
        → Denied: Access rejected with reason
    → If permitted: Action executes immediately
```

### Key Components

- **ProtectedButton**: React component wrapping sensitive actions
- **73+ protected features** across 54 JIT registry items + 19 granular additions
- **Approval flow**: pending → approved/denied → expired
- **Time windows**: 1, 2, 4, 8 hours (configurable)

---

## 9. Automation Settings

Two independent toggles on the Organization model:

| Setting | Default | Effect When OFF |
|:--------|:--------|:----------------|
| Auto-Apply Recommendations | OFF | ML suggestions displayed but not applied; user must manually approve |
| Auto-Rebalancing | OFF | Termination notices flagged but no auto-rebalancing; user must trigger manually |

---

## 10. Security & RBAC

### Role Hierarchy

```
SUPER_ADMIN (Platform Owner)
├── Full platform access, impersonation, billing
├── Never sees client sidebar (uses admin navigation)
└── Cannot be assigned to teams

ORG_ADMIN (Client Organization Owner)
├── All operations within own org
├── Manages teams, users, permissions
└── Creates approval policies

TEAM_LEAD (Team Manager)
├── Team-level operations
├── Approves JIT requests for team
└── Manages team members

MEMBER (Standard User)
├── Read access to assigned resources
├── Must request JIT approval for write ops
└── Cannot manage teams or permissions
```

### Protected Features: 73+

Categories: Cluster Management, Cost Management, Resource Hygiene, Experiments, Team Management, Approvals, Settings, AtharvaAI Pool Management.

---

## 11. API Reference

### Endpoint Summary (100+)

| Domain | Prefix | Count | Key Operations |
|:-------|:-------|:------|:---------------|
| Authentication | `/auth` | 4 | signup, login, refresh, logout |
| Users | `/users` | 5 | CRUD, profile, role management |
| Organizations | `/organizations` | 8 | CRUD, settings, impersonation |
| Clusters | `/clusters` | 6 | discover, connect, status |
| Instances | `/instances` | 4 | list, details, lifecycle |
| Metrics | `/metrics` | 6 | KPIs, costs, time-series |
| Approvals | `/approvals` | 8 | create, approve, deny, history |
| Permissions | `/permissions` | 5 | check, grant, revoke |
| Teams | `/teams` | 6 | CRUD, members, permissions |
| Hygiene | `/hygiene` | 4 | scan, cleanup, multi-region |
| Experiments | `/experiments` | 5 | CRUD, status, results |
| Tagging Policies | `/tagging-policies` | 4 | CRUD, compliance audit |
| AtharvaAI | `/atharvaai` | 4 | rankings, blacklist, rebalancing, health |
| Pod Metrics | `/pod-metrics` | 4 | batch, query, recommendations, cleanup |
| Admin | `/admin` | 6 | platform health, user management |

**Base URL**: `/api/v1` | **Auth**: JWT Bearer token (unless noted)

---

## 12. Backend Catalog

### Directory Structure (169 files across 9 subdirectories)

```
backend/
├── api/          (36 files) — Route handlers per domain
├── core/         (10 files) — Config, database, exceptions, middleware
├── models/       (20+ files) — SQLAlchemy ORM models
├── schemas/      (15+ files) — Pydantic request/response schemas
├── services/     (24+ files) — Business logic services
├── workers/      (8+ files) — Celery background tasks
├── migrations/   — Alembic database migrations
├── utils/        — Shared utilities
└── tests/        — Unit/integration tests
```

### Naming Convention

Reflects Global Naming Synchronization applied 2026-02-10:
- `tickets` → `approvals`
- `cleanup` → `hygiene`
- Old names may appear in Change Ledger entries before that date.

---

## 13. Frontend Catalog

### Key Sections (~90 components, 38 routes)

| Section | Components | Key Files |
|:--------|:-----------|:----------|
| Authentication | 4 | Login.jsx, Signup.jsx, FirstLoginReset.jsx |
| Dashboard | 12 | Dashboard.jsx, KPI widgets, charts |
| Clusters | 6 | ClusterList.jsx, ClusterDetail.jsx |
| Instances | 4 | InstanceList.jsx, SpotSavingsChart.jsx |
| Cost Management | 8 | CostTrends.jsx, CostBreakdown.jsx |
| Resource Hygiene | 6 | HygieneDashboard.jsx, ScanResults.jsx |
| Teams | 4 | TeamList.jsx, TeamDetail.jsx |
| Approvals | 5 | ApprovalQueue.jsx, ApprovalHistory.jsx |
| Experiments | 4 | ExperimentList.jsx, ExperimentDetail.jsx |
| AtharvaAI | 6 | LivePoolRankings.jsx, OptimizationStatusHeader.jsx |
| Settings | 4 | OrgSettings.jsx, ProfileSettings.jsx |
| Admin | 6 | AdminDashboard.jsx, UserManagement.jsx |

### State Management

- **Zustand stores**: auth, dashboard, clusters, atharva, settings
- **API client**: `services/api.js` with JWT interceptors

---

## 14. User Flow Architecture

### 186 API Endpoints Mapped

Complete user journey coverage:
1. **Onboarding**: Signup → Login → Connect AWS → Discover Clusters
2. **Operations**: View Dashboard → Manage Clusters → View Costs → Run Hygiene Scans
3. **Optimization**: View AtharvaAI Rankings → Configure Templates → Monitor Rebalancing
4. **Administration**: Manage Teams → Process Approvals → Configure Permissions

---

## 15. Deployment Guide

### Docker Compose (Local Development)

```bash
cd /path/to/final-ml
docker-compose up -d  # Starts backend, frontend, postgres, redis, celery
```

### Quick Start: Pod Metrics & Right-Sizing

```bash
# 1. Build & push agent
cd agent && ./build-and-push.sh

# 2. Restart backend
docker-compose restart backend celery-worker celery-beat

# 3. Run migration
docker exec spot-optimizer-backend alembic upgrade head

# 4. Deploy to cluster
kubectl rollout restart daemonset/spot-agent -n spot-optimizer

# 5. Verify
kubectl logs -n spot-optimizer -l app=spot-agent | grep "PodMetrics"
docker exec spot-optimizer-postgres psql -U postgres -d spot_optimizer -c "SELECT COUNT(*) FROM pod_metrics;"
```

### AtharvaAI Deployment

```bash
# 1. Install ONNX Runtime
pip install onnxruntime numpy

# 2. Run migration
cd backend && alembic upgrade head

# 3. Restart workers
docker-compose restart celery-worker celery-beat

# 4. Verify
curl http://localhost:8000/api/v1/atharvaai/health
```

### Agent Docker Image

```bash
docker build -t atharva608/spot-optimizer-agent:latest \
             -t atharva608/spot-optimizer-agent:v1.1-pod-metrics .
docker push atharva608/spot-optimizer-agent:latest
docker push atharva608/spot-optimizer-agent:v1.1-pod-metrics
```

---

## 16. Change Ledger

### Recurring Issues & Solutions

#### Dashboard Cost Display ($0.00)

**Root Cause**: Multiple issues across cost service, metrics service, and frontend.
- Cost Explorer returns data keyed by service name, not instance ID
- Metrics service queried by `user_id` instead of `organization_id`
- Frontend components not awaiting async data before rendering

**Fix**: Updated cost attribution logic, fixed org-based queries, added loading states.

#### Import Errors on Backend Startup

**Pattern**: Circular imports between models, services, and schemas.
- `ExperimentStatus` enum not found → Defined in `lab_experiment.py`
- `UnauthorizedError` not exported → Added to `exceptions/__init__.py`
- `CORS_ORIGINS` parsing failure → Added Pydantic validator in `config.py`

**Prevention**: Define enums in model files, export all exceptions from `__init__.py`.

#### Cluster Connection Failures

**Root Cause**: `Cluster` model has `account_id`, not `user_id`.
**Fix**: Updated `cluster_service.py` to use correct foreign key relationship.

#### RBAC/Permission Gaps

**Pattern**: Routes missing `require_permission()` dependency.
**Fix**: Comprehensive audit added `Depends(require_permission(feature))` to all protected routes.

#### Agent Injection 500 Error

**Root Cause**: Indentation error in `agent_injector.py` try/finally block + CA certificate handling.
**Fix**: Corrected indentation, added robust CA cert validation.

### Global Naming Synchronization (2026-02-10)

| Old Name | New Name |
|:---------|:---------|
| tickets | approvals |
| cleanup | hygiene |
| tagging rules | tagging policies |
| A/B tests | experiments |

---

## 17. Known Issues & Next Steps

### Implementation Status

| System | Status | Completion |
|:-------|:-------|:-----------|
| System 1: ML Pool Selection | ✅ Complete | 100% |
| System 2: Termination Monitoring | ✅ Complete | 100% (pending AWS EventBridge setup) |
| System 3: Karpenter Integration | ✅ Complete | 100% (pending cluster deployment) |
| System 4: Right-Sizing | ✅ Backend Complete | Agent deployed, UI pending |

### Dashboard Components Still Using Hardcoded Data

| Component | Real Endpoint Available | Fix |
|:----------|:------------------------|:----|
| FleetComposition | `GET /api/v1/metrics/instances` | Wire up existing endpoint |
| PendingApprovalsCard | `GET /api/v1/approvals/` | Wire up existing endpoint |
| PlatformHealthCard | `GET /api/v1/admin/health` | Implement health service |

### Pending Work

1. **Frontend**: Right-sizing recommendations UI component
2. **AWS Setup**: EventBridge rule for termination notices
3. **DaemonSet**: Deploy termination detection to clusters
4. **Monitoring**: Prometheus/Grafana dashboards
5. **Alerting**: Slack/PagerDuty integration for terminations
6. **ML Enhancement**: Add pod utilization as feature (89% → 93% accuracy)
7. **Auto-apply**: Karpenter auto-apply right-sizing recommendations

---

## Appendix: Master Index of Consolidated Documents

This master summary consolidates the following 25 source documents:

**docs/ (4 files)**:
1. `ATHARVAAI_IMPLEMENTATION_SUMMARY.md` — AtharvaAI ML pipeline details
2. `FULL_DEPLOYMENT_COMPLETE.md` — Deployment status
3. `MASTER_SUMMARY.md` — Previous master summary (architecture, lessons learned, recurring errors)
4. `USER_FLOW_ARCHITECTURE.md` — 186 API endpoints mapped

**documents/ (10 files)**:
5. `API_REFERENCE.md` — Full API endpoint catalog
6. `AUTOMATION_GUIDE.md` — Automation toggle specs
7. `BACKEND_CATALOG.md` — 169-file backend registry
8. `CHANGE_LEDGER.md` — History of fixes and known issues
9. `FRONTEND_CATALOG.md` — 90 component / 38 route registry
10. `JIT_APPROVAL_SYSTEM.md` — JIT approval flow details
11. `MASTER_INDEX.md` — Document hub index
12. `PRICING_MODELS_ARCHITECTURE.md` — Three pricing models
13. `SECURITY_RBAC.md` — RBAC permissions registry
14. `SYSTEM_ARCHITECTURE.md` — Core logic and data flow

**Root directory (11 files)**:
15. `AGENT_POD_METRICS_UPGRADE.md` — Agent pod metrics module docs
16. `COMPLETE_IMPLEMENTATION_SUMMARY.md` — Pod metrics full system overview
17. `DEPLOYMENT_FINAL_SUMMARY.md` — AtharvaAI deployment summary
18. `FIXES_COMPLETE.md` — Integration fixes (mock → real data)
19. `IMPLEMENTATION_SUMMARY_GAPS_1_2.md` — Gaps 1 & 2 implementation
20. `INTEGRATION_STATUS.md` — Three-system integration status
21. `POD_METRICS_RIGHT_SIZING_IMPLEMENTATION.md` — Right-sizing technical reference
22. `QUICK_START_DEPLOYMENT.md` — Quick start deployment guide
23. `README_POD_METRICS.md` — Pod metrics README
24. `SYSTEM_2_3_IMPLEMENTATION_COMPLETE.md` — System B + Karpenter implementation
25. `UI_INTEGRATION_COMPLETE.md` — UI integration with real APIs

---

**End of Master Summary**
