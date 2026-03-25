# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**Spot Optimizer Platform** — A comprehensive Kubernetes cost optimization platform combining ML-driven spot instance selection, automated right-sizing, intelligent hibernation, and resource hygiene for AWS EKS clusters.

**Tech Stack:**
- **Backend:** FastAPI + Python 3.11, PostgreSQL 13, Redis 6, Celery 5.3
- **Frontend:** React 18, served via Nginx (uses both Tailwind CSS and inline styles)
- **Infrastructure:** Docker Compose (6 containers: backend, frontend, postgres, redis, celery-worker, celery-beat)
- **ML/AI:** XGBoost for spot pool risk prediction (ASCP.AI engine)
- **Deployment:** Kubernetes agent DaemonSet for live pod metrics collection
- **State Management:** Zustand (frontend), SQLAlchemy ORM (backend)

---

## Build & Development Commands

### Docker Environment (Primary Workflow)

**Start entire platform (fresh rebuild — nuclear option):**
```bash
./start.sh up
# Stops everything, cleans images, rebuilds from scratch, seeds demo data
# Access: http://localhost (frontend), http://localhost:8000 (API docs)
```

**Rebuild & restart specific service:**
```bash
# Frontend only (after UI changes)
docker-compose -f docker/docker-compose.yml build frontend
docker-compose -f docker/docker-compose.yml up -d frontend

# Backend only (after Python code changes)
docker-compose -f docker/docker-compose.yml build backend
docker-compose -f docker/docker-compose.yml up -d backend

# IMPORTANT: Always restart Celery after backend code changes
docker-compose -f docker/docker-compose.yml up -d celery-worker celery-beat
```

**Rebuild everything (recommended after multi-file changes):**
```bash
docker-compose -f docker/docker-compose.yml build && docker-compose -f docker/docker-compose.yml up -d
```

**View logs:**
```bash
./start.sh logs backend          # Backend API logs
./start.sh logs celery-worker    # Background task logs
./start.sh logs frontend         # Nginx access logs
docker logs --tail 50 spot-optimizer-backend   # Last 50 lines
docker logs --tail 50 spot-optimizer-celery-worker
```

**Other commands:**
```bash
./start.sh status     # Service health check
./start.sh restart    # Restart all containers
./start.sh down       # Stop all containers
./start.sh fresh      # Full clean install (stops, rebuilds, migrates, seeds)
./start.sh build      # Rebuild all images without starting
./start.sh shell backend  # Open bash inside backend container
```

**Container names (use exactly as shown):**
| Container | Image | Purpose |
|-----------|-------|---------|
| `spot-optimizer-postgres` | PostgreSQL 13 Alpine | Primary database (port 5433) |
| `spot-optimizer-redis` | Redis 6 Alpine | Cache + Celery broker (port 6379) |
| `spot-optimizer-backend` | FastAPI | REST API server (port 8000) |
| `spot-optimizer-celery-worker` | Celery | Background task execution |
| `spot-optimizer-celery-beat` | Celery Beat | Periodic task scheduler |
| `spot-optimizer-frontend` | Nginx | React production build (port 80) |

### Database Operations

```bash
# Access PostgreSQL directly
docker exec -it spot-optimizer-postgres psql -U postgres -d spot_optimizer

# Run migrations
docker-compose -f docker/docker-compose.yml run --rm backend alembic upgrade head

# Create migration
docker-compose -f docker/docker-compose.yml run --rm backend alembic revision --autogenerate -m "description"

# Merge migration heads (if multiple heads exist)
docker-compose -f docker/docker-compose.yml exec backend alembic merge -m "merge_heads" heads

# Clear Redis cache (use after database updates)
docker exec spot-optimizer-redis redis-cli FLUSHALL
```

### Frontend Development (Local)

```bash
cd frontend
npm install
npm start         # Dev server at http://localhost:3000
npm run build     # Production build (~365kB gzipped)
npm run lint      # ESLint check
npm run lint:fix  # Auto-fix linting issues
```

### Backend Development (Local)

```bash
pip install -r requirements.txt

export DATABASE_URL="postgresql://postgres:password@localhost:5433/spot_optimizer"
export REDIS_URL="redis://localhost:6379/0"
export JWT_SECRET_KEY="your-secret-key"

# Run FastAPI dev server
uvicorn main:app --reload --host 0.0.0.0 --port 8000

# Run Celery worker (separate terminal)
celery -A backend.workers worker -l info --concurrency=4

# Run Celery beat (separate terminal)
celery -A backend.workers beat -l info
```

---

## Project Structure — Complete Reference

### Backend (`backend/`)

```
backend/
├── api/                         # 41 FastAPI route files
│   ├── __init__.py              # Router registration (all routers mounted here)
│   ├── auth_routes.py           # Login, registration, password reset, token refresh
│   ├── cluster_routes.py        # Cluster CRUD, discovery, connection
│   ├── dashboard_routes.py      # Dashboard KPIs, cost trends, summaries
│   ├── karpenter_routes.py      # Karpenter mode management, recommendations, apply (26KB)
│   ├── optimization_routes.py   # Right-sizing enriched recommendations
│   ├── pod_metrics_routes.py    # Agent pod metric ingestion & analysis
│   ├── hibernation_routes.py    # Hibernation schedule CRUD
│   ├── hygiene_routes.py        # Resource cleanup scanning
│   ├── ascpai_routes.py      # ML pool rankings, decision engine telemetry, blacklist (17KB)
│   ├── billing_routes.py        # Billing & usage tracking (17KB)
│   ├── metrics_routes.py        # Instance metrics, cost metrics (19KB)
│   ├── admin_routes.py          # Super admin operations (12KB)
│   ├── template_routes.py       # Node template CRUD
│   ├── team_routes.py           # Team management
│   ├── organization_routes.py   # Organization management
│   ├── approval_routes.py       # Change approval workflows
│   ├── policy_routes.py         # Governance policies
│   ├── ri_routes.py             # Reserved Instance analysis
│   ├── s3_routes.py             # S3 tiering analysis
│   ├── rds_routes.py            # RDS Multi-AZ analysis
│   ├── transfer_routes.py       # Data transfer optimization
│   ├── lab_routes.py            # Experiment lab
│   ├── installer_routes.py      # Agent installer & injection
│   ├── onboarding_routes.py     # User onboarding flow
│   ├── permission_routes.py     # RBAC permission management
│   ├── role_routes.py           # Role CRUD
│   ├── user_routes.py           # User profile management
│   ├── settings_routes.py       # Platform settings
│   ├── audit_routes.py          # Audit log queries
│   ├── governance_routes.py     # Governance dashboard
│   ├── account_routes.py        # AWS account management
│   ├── agent_routes.py          # Agent status & configuration
│   ├── auto_tag_routes.py       # Auto-tagging rules
│   ├── tag_management_routes.py # Tag CRUD
│   ├── tag_policy_routes.py     # Tag compliance policies
│   ├── tag_template_routes.py   # Tag templates
│   ├── smart_tag_routes.py      # AI-driven tag suggestions
│   ├── hygiene_policy_routes.py # Hygiene policy rules
│   └── health_routes.py         # Health check endpoint
│
├── services/                    # 38 service files (business logic layer)
│   ├── cluster_service.py       # Cluster CRUD + 5s Redis cache (32KB)
│   ├── metrics_service.py       # KPIs, cost aggregation (53KB — largest service)
│   ├── hygiene_service.py       # Resource cleanup scanning (128KB — most complex)
│   ├── agent_injector.py        # K8s agent DaemonSet injection (32KB)
│   ├── karpenter_service.py     # Karpenter mode management
│   ├── rightsizing_service.py   # Right-sizing recommendations
│   ├── pool_ranking_service.py  # ML pool risk scoring
│   ├── template_service.py      # Node template management (21KB)
│   ├── resource_pricing_service.py  # AWS pricing lookups (23KB)
│   ├── admin_service.py         # Super admin operations (22KB)
│   ├── ri_analysis_service.py   # RI waste detection (19KB)
│   ├── auto_tag_service.py      # Auto-tagging engine (19KB)
│   ├── role_service.py          # Role hierarchy management (19KB)
│   ├── ml_feature_service.py    # ML feature engineering (18KB)
│   ├── lab_service.py           # Experiment A/B testing (18KB)
│   ├── s3_tiering_service.py    # S3 storage class recommendations (17KB)
│   ├── approval_service.py      # Change approval workflows (17KB)
│   ├── hibernation_service.py   # Hibernation orchestration (12KB)
│   ├── savings_plan_service.py  # Savings plan utilization (13KB)
│   ├── policy_service.py        # Governance policy evaluation (13KB)
│   ├── rightsizing_service.py   # Enriched recommendations
│   ├── permission_service.py    # RBAC enforcement
│   ├── organization_service.py  # Org management
│   ├── account_service.py       # AWS account linking
│   ├── auth_service.py          # Authentication logic
│   ├── transfer_service.py      # Data transfer cost analysis
│   ├── tag_policy_service.py    # Tag compliance checking
│   ├── tag_management_service.py # Tag CRUD
│   ├── smart_tag_service.py     # AI tag suggestions
│   ├── team_service.py          # Team management
│   ├── audit_service.py         # Audit logging
│   ├── governance_service.py    # Governance dashboard
│   ├── resource_cost_service.py # Resource-level cost calculations
│   ├── rds_analysis_service.py  # RDS optimization
│   ├── settings_service.py      # Platform settings
│   ├── tag_suggestion_service.py # Tag suggestions
│   └── onboarding_service.py    # Onboarding flow
│
├── models/                      # 44 SQLAlchemy ORM models
│   ├── base.py                  # Base model with common fields (id, timestamps)
│   ├── user.py                  # User model (roles, org membership)
│   ├── organization.py          # Multi-tenant organization
│   ├── account.py               # AWS account (credentials, ARN)
│   ├── cluster.py               # Cluster model (karpenter_mode ENUM: dry_run/auto)
│   ├── instance.py              # EC2 instance tracking (lifecycle, architecture)
│   ├── pod_metric.py            # Pod CPU/memory metrics (agent-collected)
│   ├── node_template.py         # Instance type templates
│   ├── hibernation_schedule.py  # 168-hour sleep grid
│   ├── approval.py              # Change approval records
│   ├── audit_log.py             # System audit trail
│   ├── role.py                  # RBAC roles
│   ├── permission.py            # RBAC permissions
│   ├── billing.py               # Billing/usage records
│   ├── ri_utilization.py        # Reserved Instance utilization tracking
│   ├── s3_analysis.py           # S3 bucket analysis
│   ├── rds_analysis.py          # RDS instance analysis
│   ├── tag_policy.py            # Tag compliance policies
│   ├── ... and 26 more models
│
├── schemas/                     # 25 Pydantic validation schemas
│   ├── auth_schemas.py          # Login/register request/response
│   ├── cluster_schemas.py       # Cluster CRUD schemas (15KB)
│   ├── pod_metric_schemas.py    # Pod metric batch ingestion (8KB)
│   ├── policy_schemas.py        # Policy evaluation schemas (10KB)
│   ├── template_schemas.py      # Node template schemas (8KB)
│   └── ... 20 more schema files
│
├── core/                        # 15 core infrastructure modules
│   ├── api_gateway.py           # FastAPI app factory, startup events, seeding (16KB)
│   ├── feature_registry.py      # Feature flag & permission registry (48KB — largest)
│   ├── dependencies.py          # Dependency injection (auth, DB session) (13KB)
│   ├── decision_engine.py       # Optimization decision engine (18KB)
│   ├── action_executor.py       # Recommendation action execution (19KB)
│   ├── config.py                # Environment variable configuration (9KB)
│   ├── exceptions.py            # Custom exception classes (12KB)
│   ├── health_service.py        # Service health monitoring (14KB)
│   ├── validators.py            # Input validation utilities (10KB)
│   ├── logger.py                # Structured JSON logging (8KB)
│   ├── crypto.py                # Encryption (AWS credentials) (7KB)
│   ├── redis_client.py          # Redis connection factory
│   └── sse_manager.py           # Server-Sent Events for real-time updates
│
├── workers/                     # Celery task system
│   ├── app.py                   # Celery app config, beat schedule, task registration
│   └── tasks/                   # 18 individual task files
│
├── hibernation_strategy/        # Modular hibernation strategies
│   ├── namespace_sleep.py       # Scale deployments to 0 replicas (14KB)
│   ├── snapshot_restore.py      # EBS snapshot + delete nodes
│   └── nuclear.py               # Complete cluster teardown
│
├── scrapers/                    # AWS data collectors
│   ├── spot_advisor_scraper.py  # AWS Spot Advisor data (13KB)
│   └── pricing_collector.py     # Instance pricing data (18KB)
│
└── migrations/                  # Alembic database migrations
    └── versions/                # Migration version files
```

### Frontend (`frontend/src/`)

```
frontend/src/
├── App.js                       # Main routing & layout (382 lines)
│                                  Routes: /dashboard, /right-sizing, /hibernation,
│                                  /ascpai, /templates, /cleanup, /settings, etc.
│
├── services/
│   ├── api.js                   # Axios API client (19KB) — ALL backend endpoints
│   │                              Exports: clusterAPI, karpenterAPI, optimizationAPI,
│   │                              templateAPI, metricsAPI, adminAPI, billingAPI, etc.
│   └── hibernationApi.js        # Dedicated hibernation API client (2KB)
│
├── store/
│   └── useStore.js              # Zustand store (clusters, auth, selectedCluster)
│
├── pages/                       # 7 top-level page components
│   ├── ASCPAiPage.jsx        # ML pool rankings page
│   ├── Approvals.jsx            # Change approval workflows (29KB)
│   ├── TeamDetails.jsx          # Team details & members (28KB)
│   ├── AccountAnalytics.jsx     # AWS account analytics
│   ├── Onboarding.jsx           # New user onboarding flow
│   ├── Roles.jsx                # Role management
│   └── Teams.jsx                # Team listing
│
├── components/                  # 22 component directories
│   ├── right-sizing/
│   │   └── RightSizingDashboard.jsx  # Consolidated right-sizing UI (50KB)
│   │                                   Merged: old RightSizing.jsx, ManualRightSizing.jsx,
│   │                                   KarpenterDashboard.jsx into single dashboard
│   │                                   Uses: optimizationAPI, karpenterAPI
│   │                                   Features: KPIs, recommendations table, detail drawer,
│   │                                   apply confirmation modal, cost trend chart, bin-packing view
│   │
│   ├── hibernation/             # 29 files — Hibernation scheduling system
│   │   ├── HibernationDashboardNew.jsx  # Main dashboard (39KB, 1086 lines)
│   │   ├── ScheduleMatrix.jsx   # 168-hour click-and-drag grid
│   │   ├── AuditHistory.jsx     # Hibernation audit trail
│   │   └── index.js             # Public exports
│   │
│   ├── dashboard/               # 16 files — Main dashboard
│   ├── clusters/                # 11 files — Cluster management
│   ├── cleanup/                 # 10 files — Resource hygiene
│   ├── admin/                   # 10 files — Admin panel
│   ├── settings/                # 12 files — Platform settings
│   ├── shared/                  # 11 files — Reusable primitives (Button, Card, Modal, etc.)
│   ├── ascpai/               # 5 files — ML pool rankings
│   ├── auth/                    # 4 files — Login, registration
│   ├── governance/              # 4 files — PermissionGate, governance views
│   ├── onboarding/              # 4 files — Onboarding wizard
│   ├── policies/                # 4 files — Policy management
│   ├── templates/               # 3 files — Node template management
│   ├── teams/                   # 3 files — Team management
│   ├── approvals/               # 3 files — Approval workflows
│   ├── audit/                   # 2 files — Audit log views
│   ├── ri/                      # 2 files — Reserved Instance analysis
│   ├── s3/                      # 2 files — S3 tiering analysis
│   ├── rds/                     # 2 files — RDS analysis
│   ├── transfer/                # 2 files — Data transfer optimization
│   └── layout/                  # 1 file — Main layout wrapper
```

---

## Architecture Deep Dive

### Three-System Integration

The platform has **three interconnected systems** that share data:

**1. Node Templates → ASCP.AI → Right-Sizing Flow:**
```
User creates template (instance families, architecture constraints)
    ↓
Template ID passed to ASCP.AI: /ascpai?template=abc123
    ↓
ASCP.AI filters pools by template, ranks by ML risk score
    ↓
Right-sizing validates recommendations against template blacklist
    ↓
Pool health (Healthy/Risky) displayed in recommendations table
```

**Key files:**
- `frontend/src/components/templates/TemplateList.jsx` — Template management
- `frontend/src/components/ascpai/PoolRankings.jsx` — ML pool rankings
- `frontend/src/components/ascpai/DecisionEngine.jsx` — Execution Timeline UI
- `frontend/src/components/right-sizing/RightSizingDashboard.jsx` — Consolidated recommendations dashboard
- `backend/api/template_routes.py` — Template CRUD
- `backend/api/ascpai_routes.py` — ML rankings + blacklist checking + Execution Status
- `backend/api/pod_metrics_routes.py` — Enriched recommendations endpoint
- `backend/core/decision_engine.py` — 15-step execution Rules Layer

### Zero-Downtime Decision Engine v3 (Substitute Engine)

The pipeline controls how Spot pool replacements actually happen without impacting running workloads:

**1. Workload Classification:** Differentiates `STATEFUL`, `STATELESS_ELIGIBLE`, and `SYSTEM` pods.
**2. Substitute Prewarming:** Launches an identical backup node (`PREWARMING` state).
**3. Safe Swap:** Waits for the substitute to reach `READY` in Kubernetes, then Cordons and Drains the target node.
**4. Execution Tracking:** Frontend visualizes all 15 steps via `GET /api/v1/ascpai/decision-engine/{cluster_id}`.

### Dual-Mode Architecture (Karpenter)

**Database model:**
```sql
clusters.karpenter_mode ENUM('dry_run', 'auto')
```

**Modes:**
- **Insights Mode (`dry_run`):** Karpenter generates recommendations, user manually approves each change. Banner displays: "K8s-aware", "Live spot", "Dry-run" tags.
- **Auto Mode (`auto`):** Karpenter autonomously provisions/terminates nodes.

**Critical endpoints:**
```
GET  /api/v1/karpenter/recommendations           # Dry-run recommendations
POST /api/v1/karpenter/apply-recommendation/:id  # Apply single recommendation
POST /api/v1/karpenter/apply-recommendations/batch # Bulk apply
PATCH /api/v1/karpenter/mode/:cluster_id         # Switch modes
```

**Frontend routing:**
```javascript
// App.js routes /right-sizing to:
<RightSizingDashboard />
// Dashboard internally manages mode state (karpenter_insights vs auto_sizing)
```

### Agent DaemonSet Data Flow

```
1. Agent runs on every Kubernetes node (DaemonSet)
2. Every 60 seconds: scrapes Kubelet /stats/summary endpoint
3. Batches pod metrics (up to 100 pods)
4. POST /api/v1/pod-metrics/batch → Backend inserts into pod_metrics table
5. Right-sizing aggregates 14 days of metrics for recommendations
```

**Data retention:**
- Raw metrics: 14 days (for analysis window)
- Aggregated daily: 90 days
- Monthly summaries: 2 years

### Hibernation Strategy Pattern

**Three modular strategy classes:**

| Strategy | File | Savings | Wake Time | Risk |
|----------|------|---------|-----------|------|
| Namespace Sleep | `namespace_sleep.py` | 80% | ~2 min | LOW |
| Snapshot & Restore | `snapshot_restore.py` | 90% | ~12 min | LOWEST |
| Nuclear | `nuclear.py` | 99% | ~8 min | MEDIUM |

**Celery Beat task** checks schedules every minute via `backend/workers/app.py`.

**UI:** `HibernationDashboardNew.jsx` — 168-hour grid (24h × 7 days) with click-and-drag scheduling, strategy selector, emergency controls, savings reports, and audit history.

### Cache Strategy (Redis)

**Critical caches (TTLs):**
```python
# Cluster list (5-second TTL)
cache_key = f"clusters:org:{org_id}"
redis.setex(cache_key, 5, json.dumps(clusters))

# Blacklist (sorted set, 12-hour TTL)
redis.zincrby("risky_pools", 1, "m5.large:us-east-1a")
```

**When to clear Redis:**
- After database migrations
- After adding/removing clusters
- After changing hibernation schedules
- After spot interruptions (blacklist updated)
- Command: `docker exec spot-optimizer-redis redis-cli FLUSHALL`

### RBAC Permission System

**Role hierarchy:** `SUPER_ADMIN > ORG_ADMIN > TEAM_LEAD > MEMBER`

**Frontend enforcement:**
```javascript
<PermissionGate featureId="compute:view" sectionName="Right-Sizing">
  <RightSizingDashboard />
</PermissionGate>
```

**Backend enforcement:**
```python
@router.post("/apply-recommendation/{id}")
async def apply_recommendation(
    current_user: User = Depends(RequireAccess("EXECUTION"))
):
    # Only ORG_ADMIN+ can execute
```

---

## API Client Reference (`frontend/src/services/api.js`)

The frontend API client exports these namespaced objects:

| API Namespace | Methods | Purpose |
|---------------|---------|---------|
| `clusterAPI` | getClusters, getCluster, connectCluster, deleteCluster | Cluster CRUD |
| `karpenterAPI` | getRecommendations, applyRecommendation, switchMode, getStatus | Karpenter operations |
| `optimizationAPI` | getEnrichedRightsizing, getRightsizingAnalysis | Right-sizing data |
| `templateAPI` | getTemplates, createTemplate, updateTemplate, deleteTemplate | Node templates |
| `metricsAPI` | getDashboardKPIs, getCostTrends, getInstanceMetrics | Dashboard metrics |
| `adminAPI` | getOrganizations, getUsers, getSystemHealth | Super admin |
| `billingAPI` | getUsage, getInvoices | Billing |
| `hibernationApi` | getSchedules, createSchedule, updateSchedule, deleteSchedule, toggleSchedule | Hibernation (separate file) |

---

## Common Workflows

### Adding a New API Endpoint

1. **Define Pydantic schema** in `backend/schemas/xxx_schemas.py`
2. **Add route handler** in `backend/api/xxx_routes.py`
3. **Implement service logic** in `backend/services/xxx_service.py`
4. **Register router** in `backend/api/__init__.py` (if new file)
5. **Add frontend API method** in `frontend/src/services/api.js`
6. **Rebuild backend:** `docker-compose -f docker/docker-compose.yml build backend && docker-compose -f docker/docker-compose.yml up -d backend celery-worker celery-beat`
7. **Test via Swagger:** http://localhost:8000/docs

### Adding a Celery Background Task

1. **Define task** in `backend/workers/tasks/xxx_task.py`
2. **Register** in `backend/workers/app.py` (include list)
3. **Add to beat schedule** (if periodic) in `app.py`
4. **Restart Celery:** `docker-compose -f docker/docker-compose.yml up -d celery-worker celery-beat`

### Database Migrations

```bash
# Generate migration (always review before applying!)
docker-compose -f docker/docker-compose.yml exec backend alembic revision --autogenerate -m "add_column_x"

# Review migration in backend/migrations/versions/

# Apply migration
docker-compose -f docker/docker-compose.yml exec backend alembic upgrade head

# If multiple heads (merge conflict):
docker-compose -f docker/docker-compose.yml exec backend alembic merge -m "merge_heads" heads
docker-compose -f docker/docker-compose.yml exec backend alembic upgrade head

# Always clear Redis after:
docker exec spot-optimizer-redis redis-cli FLUSHALL
```

### Frontend Component Development

**Design system consistency:**
- Right-Sizing Dashboard uses **inline styles** with design tokens (`C.bg`, `C.text`, `C.indigo`, etc.)
- Hibernation Dashboard uses **Tailwind CSS** classes
- Both should match on: font sizes (`text-xs`=12px, `text-sm`=14px, `text-3xl`=30px for KPIs), colors (gray-900 for headings, gray-500 for labels, green-600 for savings), spacing (`p-5`=20px), border-radius (`rounded-xl`=12px), and border-top accents on KPI cards.

**When creating new components:**
1. Pick style approach based on section (inline tokens or Tailwind)
2. Match font sizes and colors to existing sections for visual consistency
3. Use `PermissionGate` wrapper for protected routes
4. Add route in `App.js` if it's a new page
5. Update `documents/all-components.md` if major feature

---

## Testing & Debugging

### API Testing

```bash
# Login and get token
TOKEN=$(curl -X POST http://localhost:8000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"admin@spotoptimizer.com","password":"admin123"}' \
  | jq -r '.access_token')

# Call protected endpoint
curl http://localhost:8000/api/v1/clusters \
  -H "Authorization: Bearer $TOKEN"

# Swagger UI: http://localhost:8000/docs
```

### Database Debugging

```bash
# Query clusters
docker exec spot-optimizer-postgres psql -U postgres -d spot_optimizer \
  -c "SELECT id, name, karpenter_mode FROM clusters;"

# Check pod metrics count
docker exec spot-optimizer-postgres psql -U postgres -d spot_optimizer \
  -c "SELECT COUNT(*) FROM pod_metrics WHERE timestamp > NOW() - INTERVAL '1 day';"

# View recent audit logs
docker exec spot-optimizer-postgres psql -U postgres -d spot_optimizer \
  -c "SELECT * FROM audit_logs ORDER BY timestamp DESC LIMIT 10;"
```

### Common Issues & Fixes

| Symptom | Cause | Fix |
|---------|-------|-----|
| Old UI after rebuild | Browser cache | Hard refresh Cmd+Shift+R or incognito |
| Celery changes not picked up | Workers don't auto-reload | `docker-compose up -d celery-worker celery-beat` |
| "Multiple head revisions" | Migration merge conflict | `alembic merge -m "merge_heads" heads` |
| "Can't locate revision" | Orphaned migration ref | Delete row from `alembic_version` table |
| No space left on device | Docker disk usage | `docker system prune -a -f` |
| Build cache issues | Stale layer cache | `docker-compose build --no-cache frontend` |
| 404 on API calls | Backend not running | Check `docker logs spot-optimizer-backend` |
| 401 Unauthorized | JWT expired | Re-login to get fresh token |
| FiX icon not defined | Missing react-icons import | Add `import { FiX } from 'react-icons/fi'` |

---

## Production Deployment Notes

### Required Environment Variables

```bash
# Backend (.env file)
DATABASE_URL=postgresql://user:pass@postgres:5432/spot_optimizer
REDIS_URL=redis://redis:6379/0
CELERY_BROKER_URL=redis://redis:6379/1
CELERY_RESULT_BACKEND=redis://redis:6379/2
JWT_SECRET_KEY=<strong-random-secret>
AWS_ACCESS_KEY_ID=<aws-key>
AWS_SECRET_ACCESS_KEY=<aws-secret>
AWS_REGION=us-east-1
ENVIRONMENT=production
CORS_ORIGINS=https://your-domain.com
BACKEND_PUBLIC_URL=https://api.your-domain.com

# Frontend
VITE_API_URL=https://api.your-domain.com
VITE_WS_URL=wss://api.your-domain.com
```

### Security Checklist

- [ ] Change default admin password (`admin123`)
- [ ] Change default demo password (`demo1234`)
- [ ] Rotate JWT_SECRET_KEY to a strong random value
- [ ] Use AWS IAM roles (not access keys) if deploying on EC2/EKS
- [ ] Enable HTTPS (Nginx SSL certificate)
- [ ] Set strong PostgreSQL password
- [ ] Configure Redis password (append to REDIS_URL)
- [ ] Review CORS_ORIGINS (remove `localhost` entries)

### Health Checks

```bash
# All-in-one status
./start.sh status

# Individual checks
curl http://localhost:8000/health         # Backend API
curl http://localhost/                    # Frontend (Nginx)
docker exec spot-optimizer-postgres pg_isready  # Database
docker exec spot-optimizer-redis redis-cli ping # Redis
```

### Scaling Considerations

- **Single PostgreSQL** handles: 500 clusters, 10K nodes, 100K pods, 500K metrics/day
- **Scale DB:** Upgrade RDS instance when CPU >80%; add read replicas for analytics
- **Scale Celery:** Set `deploy.replicas: 3` in docker-compose for celery-worker
- **High write volume:** Migrate pod_metrics to TimescaleDB

---

## Documentation Files

| File | Purpose |
|------|---------|
| `Q&A.md` | 50-page technical deep-dive with trade-offs and alternatives |
| `documents/all-components.md` | Complete UI component inventory with API mappings |
| `documents/MASTER_SUMMARY.md` | Project master summary |
| `documents/Q&A.md` | Comprehensive Q&A (84KB) |
| `documents/schema_info.md` | Database schema documentation |
| `documents/backend-feature.md` | Backend feature catalog |
| `documents/all-files.md` | Full file tree documentation |
| `changes.txt` | Historical change log + latest Right-Sizing Dashboard code |
| `KARPENTER_MODE_INTEGRATION_COMPLETE.md` | Karpenter dual-mode implementation summary |
| `HIBERNATION_COMPLETE_RESTRUCTURE.md` | Hibernation system architecture |

---

## Demo Credentials

| Role | Email | Password |
|------|-------|----------|
| Super Admin | `admin@spotoptimizer.com` | `admin123` |
| Demo Client | `demo@spotoptimizer.com` | `demo1234` |

**⚠️ Change these immediately in production!**
