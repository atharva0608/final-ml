# Master Index — Spot Optimizer Platform

> **Platform Mission**: Automated cloud infrastructure optimization using AI to reduce Kubernetes and AWS costs by up to 70% while maintaining 99.99% availability.
> **Last Updated**: 2026-02-10

---

## 1. Document Hub

| Document | Purpose | Key Contents |
|:---------|:--------|:-------------|
| **MASTER_INDEX.md** (this file) | Central directory | Platform overview, feature catalog, file structure, tech stack |
| **SYSTEM_ARCHITECTURE.md** | Core logic & data flow | All 24+ backend services, DB models, worker schedules, dependency diagram |
| **BACKEND_CATALOG.md** | Backend file registry | 169 files across 9 dirs, every model/service/route/worker/module listed |
| **SECURITY_RBAC.md** | Permissions registry | 4-tier RBAC, 73+ JIT features, permission matrices, approval workflows |
| **API_REFERENCE.md** | Endpoint catalog | 100+ endpoints with methods, paths, auth, request/response examples |
| **FRONTEND_CATALOG.md** | UI structure | 90+ components, 38 routes, API service layer, hooks, state management |
| **AUTOMATION_GUIDE.md** | AI/ML control settings | Automation toggles, approval integration, execution flow |
| **CHANGE_LEDGER.md** | History & known issues | Full changelog, enterprise gaps, debugging records |

---

## 2. Feature Catalog

### Status Legend
- **Active**: Fully implemented (backend + frontend + tested)
- **Partial**: Backend exists, frontend incomplete or stubbed
- **Hidden**: Code exists but no route/UI wired
- **Backend Only**: API implemented, no UI

### Feature Matrix

| Category | Feature | Status | SA | OA | TL | M |
|:---------|:--------|:-------|:--:|:--:|:--:|:-:|
| **Auth & Onboarding** | Login / Signup / JWT | Active | x | x | x | x |
| | AWS CloudFormation Onboarding | Active | x | x | — | — |
| | Invitation Acceptance | Active | — | x | x | x |
| **Dashboard** | Role-Based Widget Dashboard | Active | x | x | x | x |
| | Team Dashboard & Analytics | Active | — | x | x | x |
| | Account Analytics | Active | — | x | x | x |
| **Cluster Management** | Cluster Inventory & Details | Active | x | x | x | x |
| | Node Inventory | Active | x | x | x | x |
| | Agent Install (Manual + Auto-Inject) | Active | x | x | — | — |
| | Agent RBAC & HOST_PROC | Active | x | x | — | — |
| | Cluster Disconnect | Active | x | x | — | — |
| | Agent Heartbeat & Status | Active | x | x | x | x |
| | Auto Cluster Cleanup | Active | x | x | x | x |
| **Optimization & Policies** | Right Sizing | Active | x | x | x | x |
| | Spot Optimization | Active | x | x | — | — |
| | Cluster Policies | Active | x | x | — | — |
| | Hibernation Scheduling | Active | x | x | — | — |
| | Template Builder | Active | x | x | — | — |
| | Bin Packing Analysis | Active | x | x | — | — |
| **Resource Hygiene** | Resource Scan & Inventory (11 types) | Active | x | x | x | x |
| | EBS Volume Categorization (4-way) | Active | x | x | x | x |
| | Dependency Checks | Active | x | x | x | x |
| | Authorize / Unauthorize / Actions | Active | x | x | x | x |
| | Resource Discovery for JIT | Active | x | x | x | x |
| | Bulk Tagging Wizard | Active | x | x | x | x |
| | Optimization Wizards (RI/S3/RDS) | Active | x | x | x | x |
| | Hygiene Policies (Automated) | Active | x | x | — | — |
| **Governance & Tagging** | Governance Settings | Active | x | x | — | — |
| | Tag Policies (Enforcement) | Partial | x | x | — | — |
| | Tag Templates | Active | x | x | x | x |
| | Auto-Tag Rules | Hidden | x | x | — | — |
| | Smart Tags (TTL & Schedule) | Hidden | x | x | — | — |
| | Tag Management API | Active | x | x | x | x |
| **Approvals (JIT)** | Approval Center | Active | x | x | x | x |
| | Delegated Access Grants | Active | x | x | x | x |
| | Access Request Modal (auto 403) | Active | x | x | x | x |
| | Active Window Banner | Active | x | x | x | x |
| **Admin & Platform** | Admin Dashboard | Active | x | — | — | — |
| | Admin Organizations | Active | x | — | — | — |
| | Admin Clients | Active | x | — | — | — |
| | Billing (Stripe) | Partial | x | — | — | — |
| | System Health | Active | x | — | — | — |
| | Platform Settings & Identity | Active | x | — | — | — |
| | Experiments (Lab) | Active | x | — | — | — |
| **Advanced Analysis** | RI Analysis | Active | x | x | — | — |
| | Savings Plans Analysis | Backend Only | x | x | — | — |
| | S3 Analysis | Partial | x | x | — | — |
| | RDS Analysis | Partial | x | x | — | — |
| | Transfer Analysis | Partial | x | x | — | — |
| **Kubernetes Agent** | Metrics Collector | Active | x | x | — | — |
| | Action Actuator | Active | x | x | — | — |
| | Spot Interruption Poller | Active | x | x | — | — |
| | WebSocket Client | Active | x | x | — | — |
| **ML & Intelligence** | Spot Optimizer Engine | Active | x | x | — | — |
| | Risk Tracker | Active | x | — | — | — |
| | ML Model Server | Active | x | — | — | — |

**Role Key**: SA = SUPER_ADMIN, OA = ORG_ADMIN, TL = TEAM_LEAD, M = MEMBER

---

## 3. File Structure Index

### Backend (`backend/`)

| Directory | Key Files | Purpose |
|:----------|:----------|:--------|
| `api/` | `auth_routes.py`, `cluster_routes.py`, `approval_routes.py`, `hygiene_routes.py`, `permission_routes.py`, `governance_routes.py`, `admin_routes.py`, `metrics_routes.py`, `onboarding_routes.py`, +15 more | FastAPI route handlers |
| `services/` | `cluster_service.py`, `approval_service.py`, `hygiene_service.py`, `permission_service.py`, `governance_service.py`, `metrics_service.py`, `agent_injector.py`, +12 more | Business logic layer |
| `models/` | `user.py`, `cluster.py`, `approval.py`, `account.py`, `hygiene_policy.py`, +15 more | SQLAlchemy ORM models |
| `schemas/` | `auth_schemas.py`, `cluster_schemas.py`, `approval_schemas.py`, `hygiene_schemas.py`, +8 more | Pydantic validation schemas |
| `workers/tasks/` | `discovery.py`, `pricing_task.py`, `optimization.py`, `hibernation_worker.py`, `agent_tasks.py`, `report_worker.py` | Celery background tasks |
| `core/` | `config.py`, `dependencies.py`, `api_gateway.py`, `feature_registry.py`, `redis_client.py` | Framework core, CORS, JWT |
| `modules/` | `spot_optimizer.py`, `rightsizer.py`, `bin_packer.py`, `risk_tracker.py`, `ml_model_server.py` | ML/optimization engines |
| `scripts/` | `seed_permissions.py`, `seed_rbac.py`, `get_admin_token.py` | Reusable seed/utility scripts |
| `templates/aws/` | `read-only-role.yaml`, `full-access-role.yaml` | CloudFormation IAM templates |

### Frontend (`frontend/src/`)

| Directory | Key Files | Purpose |
|:----------|:----------|:--------|
| `pages/` | `Dashboard.jsx`, `Approvals.jsx`, `Settings.jsx`, `Teams.jsx`, `Login.jsx`, `Signup.jsx` | Top-level page components |
| `components/clusters/` | `ClusterList.jsx`, `ClusterDetails.jsx`, `NodeList.jsx` | Cluster management UI |
| `components/cleanup/` | `CleanupDashboard.jsx`, `CleanupSidebar.jsx`, `SavingsGauge.jsx`, `BulkTagWizard.jsx` | Resource hygiene UI |
| `components/approvals/` | `TicketRequestModal.jsx`, `AccessRequestModal.jsx`, `ActiveWindowBanner.jsx` | Approval/JIT UI |
| `components/governance/` | `ProtectedButton.jsx`, `JITRequestModal.jsx`, `ActiveJITBanner.jsx`, `GovernanceSettings.jsx` | JIT governance UI |
| `components/admin/` | `AdminDashboard.jsx`, `AdminExperiments.jsx`, `AdminHealth.jsx`, `AdminConfig.jsx` | Super admin UI |
| `components/dashboard/` | `CostKPICard.jsx`, `SavingsChart.jsx`, `FleetComposition.jsx`, +6 widgets | Dashboard widgets |
| `components/analysis/` | `RIAnalysis.jsx`, `S3Analysis.jsx`, `RDSAnalysis.jsx`, `TransferAnalysis.jsx` | Cost analysis pages |
| `services/` | `api.js` | Axios API service layer |
| `hooks/` | `usePermission.js`, `useDashboard.js` | Custom React hooks |
| `store/` | `authStore.js` | Zustand state management |

### Agent (`agent/`)

| File | Purpose |
|:-----|:--------|
| `collector.py` | Node metrics from Kubernetes API |
| `actuator.py` | kubectl command execution |
| `poller.py` | IMDS spot termination polling |
| `websocket_client.py` | Real-time backend communication |
| `config.py` | SIGHUP dynamic config reload |

### Infrastructure

| File | Purpose |
|:-----|:--------|
| `docker/docker-compose.yml` | 6 services: postgres, redis, backend, frontend, celery-worker, celery-beat |
| `docker/Dockerfile.backend` | Python 3.11 + FastAPI |
| `docker/Dockerfile.frontend` | Node 18 + React → nginx |
| `helm/` | Kubernetes Helm charts for agent DaemonSet |

---

## 4. Technology Stack

| Layer | Technology | Version |
|:------|:-----------|:--------|
| **Backend** | FastAPI | 0.109.0 |
| **Database** | PostgreSQL + SQLAlchemy | 2.0 ORM |
| **Migrations** | Alembic | 1.13.1 |
| **Task Queue** | Celery + Redis | 5.3.6 |
| **Caching** | Redis | 5.0.1+ |
| **Auth** | JWT (python-jose) + Bcrypt | — |
| **Validation** | Pydantic | 2.5.3 |
| **AWS SDK** | Boto3 | 1.34.34 |
| **Frontend** | React | 18.2.0 |
| **Routing** | React Router DOM | 6 |
| **State** | Zustand | 4.4.7 |
| **HTTP Client** | Axios | — |
| **UI** | Tailwind CSS + Radix UI + Lucide | 3.3.0 |
| **Charts** | Recharts | 2.15.4 |
| **Animations** | Framer Motion | 10.16.4 |
| **Agent** | Python + kubernetes client | 29.0.0 |
| **Orchestration** | Kubernetes + Helm 3 | — |
| **Containers** | Docker + Docker Compose | — |
| **Billing** | Stripe (optional) | — |

---

## 5. Database Models (36+ Models)

| Category | Models |
|:---------|:-------|
| **Auth & Users** | User, Organization, Team, Role, Permission, Invitation, APIKey |
| **AWS Integration** | Account, Cluster, Instance, NodeTemplate |
| **Cost & Optimization** | RIUtilization, SavingsPlanUtilization, S3Analysis, RDSAnalysis, TransferAnalysis, OptimizationJob, SpotPriceHistory, OnDemandPricing |
| **Governance** | Approval, AuditLog, AuthorizedResource, HygienePolicy |
| **Tagging** | AutoTagRule, TagTemplate, TagPolicy |
| **Configuration** | ClusterPolicy, HibernationSchedule, SystemConfig, PlatformSettings |
| **ML/Lab** | LabExperiment, MLModel |
| **Agent** | AgentAction |

---

## 6. Background Workers

| Worker | File | Schedule | Description |
|:-------|:-----|:---------|:------------|
| Discovery | `discovery.py` | Every 5 min | EKS cluster scan + auto-cleanup of deleted clusters |
| Spot Pricing | `pricing_task.py` | Every 5–10 min | `describe_spot_price_history()` |
| On-Demand Pricing | `pricing_task.py` | Daily 1:00 AM UTC | AWS Price List API |
| Optimization | `optimization.py` | Every 15 min | Spot replacement, bin packing, opportunities |
| Hibernation | `hibernation_worker.py` | Every 1 min | Schedule enforcement |
| Reports | `report_worker.py` | Daily/weekly | Usage and savings reports |
| Events | `event_processor.py` | Continuous | K8s event processing |
| Agent Injection | `agent_tasks.py` | On-demand | Async cluster agent installation |

---

## 7. Redis Caching Strategy

| Cache Key Pattern | TTL | Purpose |
|:------------------|:----|:--------|
| `spot_price:*` | 10 min | Real-time spot pricing per region/instance |
| `ondemand_price:*` | 24 hr | On-demand pricing (daily refresh) |
| `cleanup:scan:{account}:{regions}` | 1 hr | Hygiene scan results (force_refresh bypass) |
| `clusters:list:{org_id}:*` | 30 sec | Cluster list API cache |
| Celery task results | 1 day | Background task outcomes |
| Risk tracker data | Variable | Global spot interruption risk intelligence |

---

**Last Updated**: 2026-02-10
