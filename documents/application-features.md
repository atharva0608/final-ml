# Application Feature Catalog

This document provides a current inventory of the Spot Optimizer platform's features across frontend + backend, including active capabilities, partial implementations, and hidden/zombie code.

## 1. Feature Catalog

### Legend
*   **Status**:
    *   🟢 **Active**: Fully implemented and exposed in UI.
    *   🟡 **Partial**: Backend exists but UI is incomplete/mocked or missing critical endpoints.
    *   🔴 **Hidden**: Fully implemented backend but no UI exposure.
    *   🧟 **Zombie**: Deprecated, redundant, or unused code.
*   **Roles**: **SA** (Super Admin), **OA** (Org Admin), **TL** (Team Lead), **MB** (Member).

| Category | Feature | Status | Description & Logic | SA | OA | TL | MB |
| :--- | :--- | :--- | :--- | :---: | :---: | :---: | :---: |
| **Authentication & Access** | **Login / Token Refresh / Password Change** | 🟢 | Email/password auth with JWT. Defaults: access 60m, refresh 30d (configurable in `config.py`). | ✅ | ✅ | ✅ | ✅ |
| | **Pending Invite Acceptance** | 🟢 | Users created in `PENDING_INVITE` accept/decline via `/auth/invitation-response`; decline hard-deletes account. | ✅ | ✅ | ✅ | ✅ |
| | **RBAC Enforcement (Roles + Access Levels)** | 🟢 | `RequireRole`, `RequireAccess`, `RequirePermission` middleware; CLIENT treated as ORG_ADMIN. | ✅ | ✅ | ✅ | ✅ |
| | **Role & Permission Matrix** | 🟢 | Custom roles + permission matrix editor (`/roles`). System roles read-only. | ✅ | ✅ | ❌ | ❌ |
| **Organization & Teams** | **Organization Members** | 🟢 | Org admins add/remove/update members; direct user creation with default password `demo1234` and `must_reset_password`. | ✅ | ✅ | ❌ | ❌ |
| | **Team Management & Invites** | 🟢 | Create/rename teams, assign/remove members; Team Leads can invite to own team. | ✅ | ✅ | ✅ | ❌ |
| | **Team Governance Policies** | 🟢 | Per-team approval toggles for destructive actions (CONNECT_ACCOUNT, TERMINATE_INSTANCE, etc.). | ✅ | ✅ | ✅ | ❌ |
| | **Member Permission Overrides** | 🟢 | Granular per-member overrides stored on team member record. | ✅ | ✅ | ✅ | ❌ |
| **Onboarding & Cloud Accounts** | **Onboarding Flow** | 🟢 | Welcome → connect AWS role → verify; generates External ID and CloudFormation template. | ✅ | ✅ | ✅ | ❌ |
| | **AWS Account Linking** | 🟢 | Link/validate accounts with Role ARN + External ID; requires EXECUTION/FULL access level. | ✅ | ✅ | ✅ | ❌ |
| | **Connection Info / External ID** | 🟢 | `/organization/connection-info` provides External ID + platform account ID. | ✅ | ✅ | ✅ | ✅ |
| **Dashboard & Analytics** | **KPI Dashboard & Widgets** | 🟢 | Role-based widget layouts, personalization, refresh and activity feed. | ✅ | ✅ | ✅ | ✅ |
| | **Audit Log Viewer** | 🟢 | Query audit logs with filters; alias `/audit/logs` for UI. | ✅ | ✅ | ✅ | ✅ |
| | **Team Analytics** | 🟢 | Team-level spend, waste, cost trends, member/account details. | ✅ | ✅ | ✅ | ✅ |
| | **Account Analytics** | 🟢 | Per-account cost breakdown and optimization insights. | ✅ | ✅ | ✅ | ✅ |
| **Cluster Management** | **Cluster Inventory & Details** | 🟢 | List, filter, and view cluster details. | ✅ | ✅ | ✅ | ✅ |
| | **Node Inventory** | 🟢 | Node list per cluster with utilization stats. | ✅ | ✅ | ✅ | ✅ |
| | **Agent Install (Manual + Auto)** | 🟢 | Install script + auto-inject via cross-account role assumption. | ✅ | ✅ | ❌ | ❌ |
| | **Connection Verification & Cost Updates** | 🟢 | Verify install, update resource cost metrics. | ✅ | ✅ | ❌ | ❌ |
| **Optimization & Policies** | **Right Sizing** | 🟢 | Over-provisioned instance recommendations via `optimization` API. | ✅ | ✅ | ✅ | ✅ |
| | **Cluster Policies** | 🟢 | PolicyConfig UI + `policy_routes` for optimization constraints. | ✅ | ✅ | ❌ | ❌ |
| | **Hibernation Scheduling** | 🟢 | Cron-based schedules per cluster. | ✅ | ✅ | ❌ | ❌ |
| | **Template Builder** | 🟢 | Node template creation & defaults. | ✅ | ✅ | ❌ | ❌ |
| **Resource Hygiene (Cleanup)** | **Resource Scan & Inventory** | 🟢 | `/cleanup/scan` for orphaned resources across regions. | ✅ | ✅ | ✅ | ✅ |
| | **Dependency Checks** | 🟢 | Pre-delete dependency mapping (`/cleanup/check-dependencies`). | ✅ | ✅ | ✅ | ✅ |
| | **Authorize / Unauthorize / Cleanup Actions** | 🟢 | Executes actions; members may require approval (JIT). | ✅ | ✅ | ✅ | ✅ |
| | **Bulk Tagging Wizard** | 🟢 | Template/manual tagging with collision handling. | ✅ | ✅ | ✅ | ✅ |
| | **Optimization Wizards (RI/S3/RDS)** | 🟢 | Guided UI flows for optimization review. | ✅ | ✅ | ✅ | ✅ |
| **Governance & Tagging** | **Governance Settings (Policy-as-Code)** | 🟢 | Org-level governance toggles and critical action rules. | ✅ | ✅ | ❌ | ❌ |
| | **Tag Policies (Enforcement)** | 🟡 | CRUD for required/advisory/regex policies; compliance stats currently stubbed. | ✅ | ✅ | ❌ | ❌ |
| | **Tag Templates** | 🟢 | Reusable tag presets with dynamic variables. | ✅ | ✅ | ✅ | ✅ |
| | **Auto-Tag Rules** | 🔴 | Backend routes exist (`/tags/rules`) but no UI wired. | ✅ | ✅ | ❌ | ❌ |
| | **Tag Management API** | 🟢 | Get/update/bulk-tag resources; suggestions included. | ✅ | ✅ | ✅ | ✅ |
| **Tickets & Approvals (JIT)** | **Ticket Center** | 🟢 | Request/grant/approve/revoke access windows and action tickets. | ✅ | ✅ | ✅ | ✅ |
| | **Access Request Modal** | 🟢 | Auto-triggered on 403 with `required_ticket`. | ✅ | ✅ | ✅ | ✅ |
| | **Active Window Banner** | 🟢 | Countdown for approved access windows. | ✅ | ✅ | ✅ | ✅ |
| **Admin & Platform** | **Admin Dashboard** | 🟢 | Platform overview, organizations, clients. | ✅ | ❌ | ❌ | ❌ |
| | **Billing Overview** | 🟡 | API-backed, UI falls back to placeholder values when data missing. | ✅ | ❌ | ❌ | ❌ |
| | **System Health** | 🟢 | Health checks + diagnostics. | ✅ | ❌ | ❌ | ❌ |
| | **Platform Settings** | 🟢 | Safe Mode and config toggles. | ✅ | ❌ | ❌ | ❌ |
| | **Platform AWS Identity** | 🟢 | Connect platform AWS credentials for STS operations. | ✅ | ❌ | ❌ | ❌ |
| | **Admin Lab** | 🟢 | Model registry and risk map UI. | ✅ | ❌ | ❌ | ❌ |
| **Advanced Analysis** | **RI Analysis** | 🟢 | RI overview, list, recommendations, analysis runs. | ✅ | ✅ | ❌ | ❌ |
| | **Savings Plans Analysis** | 🔴 | Backend endpoints exist, no UI wired. | ✅ | ✅ | ❌ | ❌ |
| | **S3 Analysis** | 🟡 | Overview + top opportunities; missing bucket list endpoint. | ✅ | ✅ | ❌ | ❌ |
| | **RDS Analysis** | 🟡 | Overview + top opportunities; missing instance list endpoint. | ✅ | ✅ | ❌ | ❌ |
| | **Transfer Analysis** | 🟡 | Overview + top opportunities; list granularity limited. | ✅ | ✅ | ❌ | ❌ |

---

## 2. Zombie & Redundant Code Analysis

These features exist in the codebase but are flagged for cleanup or repair.

| Component | Diagnosis | File Path | Recommendation | Reason |
| :--- | :--- | :--- | :--- | :--- |
| **Smart Tags** | 🧟 **Redundant** | `backend/api/smart_tag_routes.py` | **Delete** | Overlaps with `auto_tag_routes.py` and tag policy system. Appears legacy. |
| **Legacy Tag Template Manager** | 🧟 **Unused** | `frontend/src/components/policies/TagTemplateManager.jsx` | **Remove** | Replaced by settings `TagTemplateManager`; no imports. |
| **BulkTagEditor / InlineTagEditor** | 🧟 **Unused** | `frontend/src/components/cleanup/BulkTagEditor.jsx`, `frontend/src/components/cleanup/InlineTagEditor.jsx` | **Remove** | Superseded by `BulkTagWizard`; no imports. |
| **Experiment Lab (User-facing)** | 🔴 **Hidden** | `frontend/src/components/lab/ExperimentLab.jsx` | **Wire Up or Remove** | Component exists but no route is registered in `App.js`. |
| **S3 Bucket List** | 🟡 **Missing** | `backend/api/s3_routes.py` | **Fix** | Only `/overview` and `/analyze` exist; UI needs a list endpoint. |
| **RDS Instance List** | 🟡 **Missing** | `backend/api/rds_routes.py` | **Fix** | UI uses `top_opportunities`; no list endpoint for pagination. |
| **Transfer Details List** | 🟡 **Partial** | `backend/api/transfer_routes.py` | **Enhance** | Overview exists, but list granularity is limited to top opportunities. |
| **Tag Policy Compliance Stats** | 🟡 **Stubbed** | `backend/api/tag_policy_routes.py` | **Implement** | `compliance/stats` currently returns empty stats. |

---

## 3. Detailed Logic Specifications

### A. AWS Onboarding & Account Linking
1.  **Start:** User enters onboarding flow or Cloud Integrations.
2.  **Template:** Backend generates External ID and CloudFormation template (`/onboarding/aws-link` or `/onboarding/template`).
3.  **Verify:** `/onboarding/verify` validates STS assume-role; account record is created.
4.  **Discovery:** Background discovery worker is triggered; onboarding marked complete.

### B. JIT Access Enforcement & Ticketing
1.  **Enforcement:** `PermissionService.enforce()` blocks high-risk actions for non-admins.
2.  **Signal:** Backend raises `GovernanceError` with `required_ticket: true` (HTTP 403).
3.  **UI Intercept:** Frontend intercepts 403 and opens `AccessRequestModal`.
4.  **Approval:** Ticket Center handles approval/revoke/accept; active window grants temporary access.

### C. Cleanup Scan & Action Execution
1.  **Scan:** `/cleanup/scan/{account_id}` returns resources + summary across regions.
2.  **Review:** UI filters by type/authorization state; dependency check available.
3.  **Execute:** `/cleanup/action` performs cleanup; returns 202 when approval is required.

### D. Tag Governance Stack
| Tool | Purpose | UI |
| :--- | :--- | :--- |
| **Tag Policies** | Enforcement rules (required/advisory/regex) | TagPoliciesList (Settings) |
| **Tag Templates** | Preset tags with dynamic variables | TagTemplateManager (Settings + Cleanup) |
| **Auto-Tag Rules** | Dynamic rule engine + preview | Backend only (no UI) |

---

## 4. Middleware & Infrastructure
*   **CORS:** Dynamic origin allowlist in `api_gateway.py` + fallback headers for errors.
*   **Request Logging:** Logs Method, Path, Status, Duration, UserID + adds `X-Process-Time` header.
*   **Exception Handling:** Global handlers for `SpotOptimizerException`, validation errors, and 500s.
*   **Rate Limiting:** **Missing**. Config exists (`API_RATE_LIMIT`) but no middleware is wired.
*   **Health Checks:** `/health` (basic) and `/health/detailed` (DB + Redis).
*   **JWT Defaults:** Access token 60 minutes; refresh token 30 days (configurable).
