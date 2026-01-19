# Frontend-Backend Gap Analysis
**Date:** 2026-01-19 (Last Updated)
**Scope:** `frontend/src/services/api.js` vs `backend/api/*.py`

This document outlines the discrepancies found between the Frontend's expected API calls and the Backend's actual routes.

## Summary
| Category | Count | Description |
| :--- | :--- | :--- |
| **Real APIs** | 60+ | Endpoints that exist and are correctly linked (includes JIT Ticket System, Cost Optimization). |
| **Missing / Fake APIs** | 0 | Endpoints called by Frontend but **NOT** implemented in Backend. |
| **Zombie APIs** | 1 | Backend endpoints that exist but appear unused. |

## 1. Missing / Fake APIs (Frontend calls -> 404/Function Missing)
*None detected.* All core frontend API calls now have corresponding backend routes (validated 2026-01-13).

## 2. Real APIs (Verified Matches)

### Core APIs
*   **Auth**: Login, Signup, Me, Refresh, Change Password.
*   **Clusters**: List, Get, Update, Delete, Connect AWS, Discovery.
*   **Admin**: List Clients, Toggle Client, Stats, Reset Password.
*   **Metrics**: Global, Cluster-specific.
*   **Lab**: Experiments CRUD.
*   **Policies**: CRUD + Toggle.
*   **Hibernation**: Schedule Management.
*   **Audit**: Activity logs.

### Newly Implemented APIs (Cost Optimization - 2026-01-19)
*   **Feature 1: RI Waste Detection**:
    *   `GET /api/v1/ri/overview` - Summary stats.
    *   `GET /api/v1/ri/list` - List RIs.
    *   `POST /api/v1/ri/analyze` - Trigger analysis.
    *   `GET /api/v1/ri/{id}/recommendations` - Detailed actions.
*   **Feature 2: S3 Intelligent-Tiering**:
    *   `GET /api/v1/s3/overview` - Storage breakdown.
    *   `GET /api/v1/s3/buckets` - Bucket list.
    *   `POST /api/v1/s3/analyze` - Trigger scan.
*   **Feature 3: RDS Multi-AZ Analysis**:
    *   `GET /api/v1/rds/overview` - Multi-AZ savings.
    *   `GET /api/v1/rds/instances` - Instance list.
    *   `POST /api/v1/rds/analyze` - Trigger scan.
*   **Feature 4: Data Transfer Optimization**:
    *   `GET /api/v1/transfer/overview` - Transfer costs.
    *   `GET /api/v1/transfer/analyze` - Trigger analysis.

### Newly Implemented APIs (2026-01-14)
*   **JIT Tickets**: Full CRUD + workflow endpoints at `/api/v1/tickets` (NEW - JIT System).
    *   `POST /` - Create access request
    *   `POST /grant` - Admin grants access to recipients
    *   `GET /` - List tickets (role-filtered)
    *   `POST /{id}/approve` - Approve pending ticket
    *   `POST /{id}/revoke` - Revoke active access
    *   `POST /{id}/accept` - Accept delegated grant (PENDING_CONSENT → APPROVED_ACTIVE)
    *   `POST /{id}/reject` - Decline delegated grant
    *   `GET /active-window` - Get user's current active access window

### Newly Implemented APIs (Admin Dashboard Reset)
*   **Super Admin Command Center**:
    *   `GET /admin/dashboard` - Real-time Platform Stats and Live Activity Feed (sourced from Audit Logs).
    *   `POST /admin/organizations/{id}/toggle` - Suspend/Activate tenants (Kill Switch).

### Previously Implemented APIs (2026-01-13)
*   **Governance**: Get Policies, Update Policies, Run Autopilot (Feature 4).
*   **Cleanup / Dependencies**: `check-dependencies` pre-flight verification (Feature 1).
*   **Cleanup / Tag Compliance**: `is_compliant`, `missing_tags`, `untagged_waste_cost` in scan results (Feature 2).
*   **Approvals**: Pending request management (List, Approve, Reject) - Feature 3.
*   **Team-Specific Governance**: `GET/PUT /teams/{id}/governance` for Team Lead approval policy configuration.
*   **Cleanup / Authorization**: `AUTHORIZE` and `UNAUTHORIZE` actions in `cleanupAPI.execute` (Persistence).

### Previously Implemented APIs (2026-01-12)
*   **Accounts**: Link, Validate, Set Default, Disconnect, List.
*   **Billing**: Create Portal Session, Webhook, Status.
*   **Onboarding**: Get State, AWS Link, Verify (+ triggers discovery), Skip.
*   **Cleanup**: Resource Hygiene scanning and action execution (Multi-Region).
*   **Templates**: CloudFormation template listing and download.

### Status Notes
| Feature | Backend Status | Notes |
| :--- | :--- | :--- |
| **Cost Optimization (4 Features)** | **Real + UI** | Complete implementation of RI, S3, RDS, Transfer analysis with Cost Explorer/CloudWatch integration. |
| **Governance (Autopilot)** | **Real** | Policy-as-Code auto-cleanup with "System Autopilot" actor. |
| **Dependency Check (Feature 1)** | **Real + UI** | Pre-flight verification with Warning Modal in CleanupDashboard. |
| **Tag Compliance (Feature 2)** | **Real + UI** | Shameback card + Compliance column with missing tags tooltip. |
| **Cleanup** | **Real** | Full implementation with parallel scanning, caching, tag compliance, dependency checks. |
| **Hierarchical Governance (Feature 6)** | **Real** | 4-Tier RBAC (Super Admin, Org Admin, Team Lead, Member), Governance toggles, Four-Eyes approval workflow. |
| **Team-Specific Governance** | **Real + UI** | Team.governance_config JSON, GET/PUT /teams/{id}/governance API, TeamGovernance.jsx with 5 action toggles. |
| **Approvals (Feature 3)** | **Real** | Four-Eyes approval workflow for Members and Strict Mode. |
| **Authorization** | **Real + UI** | `AuthorizedResource` model, persistence, and dashboard filtering. |
| **JIT Ticket System** | **Real + UI (Audited 2026-01-14)** | Full role-based ticket workflow. Backend: Ticket model, TicketService, PermissionService. Authorization fixed to include `CLIENT` role. Frontend: TicketCenter with stats cards, real timestamps, expiry countdown. No mock data - uses `ticketsAPI` for all operations. |

## 3. Resolved Gaps (2026-01-13)

| Component | Previous Status | New Status |
| :--- | :--- | :--- |
| **Governance** | Not Implemented | **Real**: GovernanceService + API routes for policy management |
| **Dependency Check** | Not Implemented | **Real**: CleanupService.check_dependencies() + API endpoint |
| **Tag Compliance** | Not Implemented | **Real**: is_compliant, missing_tags enrichment during scan |
| **Team-Specific Governance** | Not Implemented | **Real**: Team.governance_config + TeamGovernance.jsx UI |
| **Approval Workflow** | Already Implemented | ✅ Verified working |
| **Resource Authorization** | Not Implemented | **Real**: AuthorizedResource model + Actions |
| **JIT Ticket System** | Not Implemented | **Real**: Ticket model, TicketService, PermissionService, role-based UI |

## 4. Remaining Zombie APIs
| Component | Status | Reason |
| :--- | :--- | :--- |
| **ML Model Server** | **Standalone** | Implemented but not integrated into prediction flow. |

## 5. Recommendations
1. ~~Implement Dependency Check~~ ✅ Done (2026-01-13)
2. ~~Implement Tag Compliance~~ ✅ Done (2026-01-13)
3. ~~Implement Governance Service~~ ✅ Done (2026-01-13)
4. **Configure Stripe Keys**: Add `STRIPE_SECRET_KEY` to `.env` for billing.
5. **Connect ML Model Server**: Wire predictions into Lab experiments.
6. **Schedule Autopilot Worker**: Add Celery beat task for periodic governance runs.
