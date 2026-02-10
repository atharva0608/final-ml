# Change Ledger — History, Fixes & Known Issues

> **Last Updated**: 2026-02-10
> **Purpose**: Long-term memory preventing re-investigation of solved problems.
> **Naming Note**: Entries before 2026-02-10 use old names (tickets→approvals, cleanup→hygiene). The Global Naming Synchronization was applied on 2026-02-10.

---

## 1. Enterprise-Grade Gaps (Open)

These are architectural gaps between the current implementation and a production-ready enterprise product. They represent real risks that have NOT been addressed yet.

### 1.1 Spot Termination Early-Warning Detection

| Aspect | Current State | Enterprise Target |
|:-------|:-------------|:------------------|
| **Detection** | IMDS poller in agent (`poller.py`) checks for 2-min notice | Need multi-signal detection (IMDS + EventBridge + CloudWatch) |
| **Response** | Agent has `actuator.py` for pod eviction | Need automated drain → reschedule → verify pipeline |
| **Risk** | Single-signal detection may miss events; no PDB awareness | EventBridge catches 100% of events; PDB-aware drain prevents data loss |
| **Impact** | Potential data loss if pods don't gracefully terminate | Zero-downtime spot transitions |

### 1.2 Host-Level Memory Visibility

| Aspect | Current State | Enterprise Target |
|:-------|:-------------|:------------------|
| **Metrics** | Agent reads from Kubernetes Metrics API | Need `/host/proc/meminfo` parsing for true host memory |
| **Issue** | K8s metrics show container-level, not host-level memory | Host-level needed for accurate bin-packing decisions |
| **Status** | HOST_PROC env var + `/proc` volume mount added to DaemonSet | Collector needs to parse `/host/proc/meminfo` directly |

### 1.3 Safe Drain Guardrails (PDB Awareness)

| Aspect | Current State | Enterprise Target |
|:-------|:-------------|:------------------|
| **Eviction** | `actuator.py` uses `create_namespaced_pod_eviction` | Need PDB pre-check before eviction attempt |
| **Risk** | May violate PodDisruptionBudgets silently | Should abort eviction if PDB would be violated |
| **Logic** | No PDB awareness | `minAvailable` / `maxUnavailable` check before each eviction |

### 1.4 Fallback to On-Demand

| Aspect | Current State | Enterprise Target |
|:-------|:-------------|:------------------|
| **Spot Failure** | `spot_optimizer.py` selects instances but no fallback | Need automatic on-demand provisioning when spot unavailable |
| **Detection** | No capacity-available check | Monitor `InsufficientInstanceCapacity` errors |
| **UX** | Silent failure | Alert + automatic fallback + cost impact notification |

### 1.5 Three-State Cluster Lifecycle

| Aspect | Current State | Enterprise Target |
|:-------|:-------------|:------------------|
| **States** | DISCOVERED / ACTIVE (binary) | DISCOVERED → ACTIVE → DISCONNECTED (three-state) |
| **Transitions** | Manual status change | Automatic based on agent heartbeat + AWS API |
| **Status** | Partially implemented (DISCONNECTED exists in enum) | Need full lifecycle state machine with automatic transitions |

### 1.6 Hybrid "Teaser → Control" UX

| Aspect | Current State | Enterprise Target |
|:-------|:-------------|:------------------|
| **DISCOVERED clusters** | Show basic info + "Activate" button | Show estimated savings + animation + one-click activation |
| **Status** | Partially implemented (savings estimates + discovery animation) | Need full "teaser" experience to drive activation |

---

## 2. Chronological Changelog

### 2026-02-10 — Global Naming Synchronization

| Component | Change |
|:----------|:-------|
| Backend | Renamed: `ticket_routes.py` → `approval_routes.py`, `ticket_service.py` → `approval_service.py`, `ticket_schemas.py` → `approval_schemas.py`, `ticket.py` → `approval.py` |
| Backend | Renamed: `cleanup_routes.py` → `hygiene_routes.py`, `cleanup_service.py` → `hygiene_service.py`, `cleanup_schemas.py` → `hygiene_schemas.py`, `cleanup_policy.py` → `hygiene_policy.py` |
| Backend | Updated all imports across 15+ files |
| Backend | API prefix: `/tickets` → `/approvals`, `/cleanup` → `/hygiene` |
| Frontend | Renamed: `TicketCenter.jsx` → `Approvals.jsx`, `AdminLab.jsx` → `AdminExperiments.jsx` |
| Frontend | Route: `/cleanup` → `/hygiene`, `tag-management` → `tagging-policies`, `/admin/lab` → `/admin/experiments` |
| Frontend | API: `ticketAPI` → `approvalsAPI`, `cleanupAPI` → `hygieneAPI`, `labAPI` → `experimentsAPI` |
| Frontend | Sidebar: "Tag Management" → "Tagging Policies", "The Lab" → "Experiments" |
| Scripts | Deleted 9 one-time migration scripts from `backend/scripts/` |
| Bug Fix | Fixed `approvalsAPI.grantAccess()` → `approvalsAPI.delegate()` (method didn't exist) |

### 2026-02-06 — UI Enhancements & Redis Caching

| Component | Change |
|:----------|:-------|
| Frontend | Dual-mode cluster cards: `realizedSavings` (ACTIVE) vs `potentialSavings` (DISCOVERED) |
| Frontend | Cluster notification badge with 30s polling, blue pulse for discovered, red for errors |
| Backend | Redis cache for `list_clusters` (30s TTL, org_id-scoped) |
| Backend | Extended ClusterListItem schema: `estimated_savings`, `cpu_total`, `mem_total` |
| Frontend | Discovery animation banner with radar pulse, progress steps, floating particles |
| Backend | Added missing columns: `potential_savings_monthly`, `on_demand_node_count`, `last_assessed`, `inventory_summary` to clusters; `last_heartbeat`, `status`, `status_message` to instances |

### 2026-02-05 — Agent Injection & Discovery Fixes

| Component | Change |
|:----------|:-------|
| Backend | Fixed `NoRegionError` in agent_injector.py — must create AWS clients with explicit region |
| Backend | Discovery extracts region from Cluster ARN instead of account defaults |
| DevOps | Verified removal of legacy manual manifests; enforced DaemonSet architecture |

### 2026-02-04 — Helm Migration

| Component | Change |
|:----------|:-------|
| Full Stack | Strict Helm Migration: OCI Helm Chart for agent install, removed legacy manifests |
| Frontend | ClusterConnectModal simplified to single Helm command |
| Backend | `generate_install_script` returns Chart URI |

### 2026-01-30 — Dynamic Auto-Tag System

| Component | Change |
|:----------|:-------|
| Backend | Added `ValueSourceType`, `OverrideBehavior`, `ResourceScope` enums; `dynamic_tags`, `resource_scope`, `override_behavior` columns |
| Backend | `AutoTagService.generate_tags()` for dynamic value resolution (user email, creation date, org name, env variables) |
| Backend | Added `/preview` and `/variables` endpoints |
| Frontend | Redesigned TagPoliciesManager as "Policy Builder Wizard" with Live Preview |

### 2026-01-19–20 — Admin Panel Stabilization & Hygiene Policies

| Component | Change |
|:----------|:-------|
| Backend | Fixed system-wide 500/CORS errors (missing `team_member_permissions` column) |
| Backend | Fixed `AdminOrganizations` crash, RBAC seed data (12 permissions, 3 roles) |
| Backend | AWS onboarding: skip ≠ complete, `/reset` endpoint, CloudFormation security |
| Backend | Dynamic cleanup policies: `HygienePolicy` model, rule builder, JSON conditions |
| Frontend | New widgets: RIHealthCard, S3HealthCard, RDSHealthCard, TransferHealthCard |
| Frontend | New pages: RIAnalysis, S3Analysis, RDSAnalysis, TransferAnalysis |

### 2026-01-16 — Role-Based Dashboard & Account Approval

| Component | Change |
|:----------|:-------|
| Backend | `preferences` JSON column on User model for persistent dashboard layouts |
| Backend | PATCH/GET `/users/me/preferences` with role-based widget validation |
| Frontend | 9 modular widget components, `widgetRegistry.js`, `roleDefaults.js` |
| Backend | Account connection approval flow for MEMBER role (Redis-cached encrypted credentials) |
| Backend | `encrypt_data()` / `decrypt_data()` in crypto.py (Fernet symmetric encryption) |

### 2026-01-14 — JIT Privilege Escalation (Complete)

| Component | Change |
|:----------|:-------|
| Backend | Created Approval model with ApprovalType, ApprovalStatus enums |
| Backend | ApprovalService (CRUD, approve, revoke, accept/reject), PermissionService (centralized gatekeeper) |
| Backend | 8 API endpoints at `/api/v1/approvals` + 4 at `/api/v1/permissions` |
| Backend | Feature registry with 73+ protected features |
| Frontend | ProtectedButton, JITRequestModal, ActiveJITBanner, RiskBadge, usePermission hook |
| Frontend | Approvals page with role-based tabs (Admin: Global + Active, Lead: Incoming/Outgoing, Member: My Requests) |
| Backend | TicketCenter rewrite: CLIENT role support, stats cards, real timestamps, expiry countdown |

### 2026-01-13 — Resource Hygiene & Team Governance

| Component | Change |
|:----------|:-------|
| Backend | Advanced hygiene: 11 resource types, parallel scanning, ThreadPoolExecutor |
| Backend | 4-way EBS categorization, dependency checks, tag compliance |
| Backend | Hierarchical RBAC (4-tier), GovernanceService, ApprovalService |
| Backend | Team-specific governance config, AuthorizedResource model |
| Frontend | CleanupDashboard with 9 resource tabs, SavingsGauge, SafetyScore, BulkTagWizard |
| Frontend | Team management rewrite, invitation acceptance flow |

### 2026-01-12 — Core Infrastructure

| Component | Change |
|:----------|:-------|
| Backend | AccountService with STS verification, ClusterService with EKS discovery |
| Backend | Billing routes (Stripe portal, webhook, subscription) |
| Backend | Platform identity management (AdminService) |
| Backend | CloudFormation templates (read-only-role.yaml, full-access-role.yaml) |
| Frontend | CleanupDashboard initial implementation, CloudIntegrations |

### 2026-01-09 — Foundation & Mock Removal

| Component | Change |
|:----------|:-------|
| Backend | All services implemented with real boto3 logic (replacing mocks) |
| Backend | Celery Beat schedule configured (discovery 5m, pricing 10m, optimization 15m) |
| Backend | health_routes.py, optimization_routes.py created |
| Frontend | All components switched from hardcoded data to real API calls |
| Backend | Fixed 20+ import errors, missing schemas, enum mismatches |
| Infra | Repository flattened (removed `new-version/` nesting) |

---

## 3. Docker & Deployment Fixes (Historical)

These issues were encountered and fixed during initial deployment. Documented to prevent re-investigation.

| # | Issue | Severity | Fix |
|:--|:------|:---------|:----|
| 1 | `start.sh` referenced wrong docker-compose path | Critical | Updated to `docker/docker-compose.yml` |
| 5 | PostgreSQL port 5432 conflict | Critical | Changed to port 5433 |
| 6 | `version: '3.8'` obsolete warning | Low | Removed from docker-compose.yml |
| 7 | `COPY public/ ./public/` not found | Critical | Removed (public is inside frontend/) |
| 9 | `npm ci` fails (no package-lock.json) | Critical | Changed to `npm install` |
| 10 | `react-scripts: not found` | Critical | Removed `--production` flag (needs devDeps for build) |
| 11 | `index.html` not found | Critical | Changed `COPY frontend/ ./frontend/` to `COPY frontend/. ./` |
| 12 | `FiFlask` not exported from react-icons | Critical | Replaced with `FiActivity` |
| 13 | `JWT_SECRET_KEY` field required | Critical | Added default for development |
| 14 | `Organization` not defined in report_worker | Critical | Fixed imports `app.` → `backend.` |
| 15 | `ClusterFilter` not exported | Critical | Added 5 missing schema classes |

---

## 4. Pricing System Fixes

| Issue | Root Cause | Fix |
|:------|:-----------|:----|
| Compute cost showing $0.00 | Instance.price was NULL | Set price during discovery using PricingHelper.get_ec2_price() |
| Fallback pricing incomplete | Only a few instance types | Enhanced table with 80+ instance types (T, M, C, R, GPU families) |
| Cluster cost desync | Calculated once, never updated | Celery Beat task recalculates every 15 minutes |
| Price hierarchy | No fallback chain | Cost Explorer → Pricing API → Fallback Table → Ultimate Fallback |

---

## 5. CPU/Memory & Status Fixes

| Issue | Root Cause | Fix |
|:------|:-----------|:----|
| CPU/Memory showing 0.00% | Missing SQLAlchemy columns | Added `cpu_usage_pct`, `mem_usage_pct` to Cluster model |
| Metrics returning zeros | Service methods returning placeholders | Query real data from instances table |
| Status showing "Offline" | Redis cache TTL too long (30s) | Reduced to 5s for real-time status |
| Timezone display errors | Server UTC vs user timezone | Applied timezone-aware formatting |

---

## 6. Tag Management Visibility Issue (Resolved)

**Problem**: Tag Management not visible in sidebar for SUPER_ADMIN users.
**Root Cause**: SUPER_ADMIN uses `adminNavigation` (separate from client navigation). Tag Management was only in client `navigation` list.
**Resolution**: SUPER_ADMIN must impersonate a client user to see Tag Management. This is by design — admin uses Clients page to access client views.

---

## 7. Deleted Files (Reference)

### One-Time Migration Scripts (Deleted 2026-02-10)

| File | Purpose | Reason for Deletion |
|:-----|:--------|:-------------------|
| `backend/scripts/add_ticket_columns.py` | Added columns to old tickets table | Table renamed to approvals |
| `backend/scripts/migrate_delegated_access.py` | One-time migration | Imported deleted models |
| `backend/scripts/migrate_tickets.py` | One-time table creation | Obsolete |
| `backend/scripts/migrate_org_external_id.py` | One-time column addition | Already applied |
| `backend/scripts/migrate_platform_settings.py` | One-time table creation | Already applied |
| `backend/scripts/migrate_rbac.py` | One-time RBAC rebuild | Already applied |
| `backend/scripts/migrate_team_governance.py` | One-time column addition | Already applied |
| `backend/scripts/migrate_user_preferences.py` | One-time column addition | Already applied |
| `backend/scripts/migrate_jit_rbac.py` | One-time JIT migration | Already applied |

### Legacy Approval System (Deleted during naming sync)

| File | Replaced By |
|:-----|:-----------|
| `backend/api/approval_routes.py` (old maker-checker) | New `approval_routes.py` (renamed from ticket_routes.py) |
| `backend/services/approval_service.py` (old) | New `approval_service.py` (renamed from ticket_service.py) |
| `backend/models/approval.py` (old ApprovalRequest) | New `approval.py` (renamed from ticket.py with Approval model) |

### Documentation (Deleted after consolidation)

All files from `docs/` directory consolidated into 7 master files in `documents/`.

---

## 8. Agent Deployment Fixes

| Issue | Fix |
|:------|:----|
| 401 Unauthorized on K8s API | Generate token with backend IAM credentials (not assumed role) |
| ImagePullBackOff | Built and pushed `atharva608/spot-optimizer-agent:latest` to Docker Hub |
| V1Subject AttributeError | K8s client v29 renamed to `RbacV1Subject` |
| ConfigMap URL mismatch | Split into `BACKEND_URL` (HTTP) and `BACKEND_WS_URL` (WSS) |
| Agent image tag not updating | Changed to `:latest` tag with `imagePullPolicy: Always` |
| Missing RBAC permissions | Added pods/eviction, configmaps, deployments, replicasets to ClusterRole |
| No host-level metrics | Added HOST_PROC env var + `/proc` volume mount + hostNetwork |

---

## 9. Auto Cluster Cleanup Logic

**Trigger**: Discovery worker (every 5 min)
**Condition**: Cluster not found in AWS AND agent offline > 10 minutes
**Action**: Delete cluster + associated instances from database
**Safety**: Double verification (AWS state + heartbeat), 10-min grace period, transaction safety
**Re-discovery**: If cluster recreated with same name, discovered fresh (DISCOVERED status)

---

**Last Updated**: 2026-02-10
