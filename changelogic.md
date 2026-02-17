# UI Component Improvement Recommendations
**Generated:** 2026-02-17 | **Based on:** Codebase audit + `all-components.md` analysis

---

## Overview

This document covers three things:
1. **Quick wins** — existing endpoints already wired in the backend that just need to be connected to the frontend
2. **New components** — additions per section that would make the platform easier to navigate and track
3. **Super Admin panel expansion** — a full breakdown of what's missing and how everything can be managed from one place

---

## Part 1: Quick Wins — Wire Up Existing Endpoints (High Priority)

These are the 🔴 red endpoints that have working backend logic but are showing hardcoded/mock data in the UI. These should be fixed first because the infrastructure already exists.

### 1.1 Dashboard — `FleetComposition` Widget
- **File:** `dashboard/widgets/FleetComposition.jsx`
- **Problem:** Currently hardcoded. The endpoint `GET /api/v1/metrics/instances` exists and groups by lifecycle (SPOT/ON_DEMAND).
- **Fix:** Replace hardcoded data with a `useEffect` call to `metricAPI.getInstances()`. The response already contains `instance_type`, `lifecycle`, `cpu_util`, `memory_util`, `state`.
- **Impact:** Admins will finally see a real picture of their fleet composition instead of static placeholder slices.

### 1.2 Dashboard — `PendingApprovalsCard` Widget
- **File:** `dashboard/widgets/PendingApprovalsCard.jsx`
- **Problem:** Hardcoded. The endpoint `GET /api/v1/approvals/` is already wired in the Approvals page — the widget just needs to consume it.
- **Fix:** Call `approvalsAPI.list({ status: 'PENDING', page_size: 5 })` on mount. Filter for PENDING status and display count + top items.
- **Impact:** Dashboard becomes actionable — admins see pending requests without navigating away.

### 1.3 Dashboard — `PlatformHealthCard` Widget (Super Admin)
- **File:** `dashboard/widgets/PlatformHealthCard.jsx`
- **Problem:** Hardcoded uptime % and worker counts. The `AdminHealth` component already calls `GET /api/v1/admin/health` correctly.
- **Fix:** Import `adminAPI.getHealth()` and reuse the same response. Display `status`, `api_latency`, `db_connections`, `worker_status`.
- **Impact:** Super admin dashboard goes from decorative to genuinely useful at a glance.

### 1.4 Settings — Preferences / Save Preferences Button
- **File:** `settings/Settings.jsx`
- **Problem:** "Save Preferences" writes to `localStorage` only. `PATCH /api/v1/users/me/preferences` is defined in `user_routes.py` and in `api.js` — just never called.
- **Fix:** Replace the `localStorage.setItem` call with `userAPI.updatePreferences(prefs)` and keep localStorage as a fallback/cache.
- **Impact:** Preferences actually persist across devices and sessions.

### 1.5 Templates — Instance Families Dropdown
- **File:** `templates/TemplateBuilder.jsx`
- **Problem:** Instance family checkboxes are hardcoded. `GET /api/v1/templates/options` exists but is never called.
- **Fix:** On modal open, call `templateAPI.getOptions()` and populate the families list dynamically.
- **Impact:** As AWS adds new instance families, the UI stays accurate without code changes.

### 1.6 Settings Billing Tab
- **File:** `settings/Settings.jsx` — Billing tab
- **Problem:** Plan name, billing cycle, amount, next date, payment card — all hardcoded. The backend has `billing_routes.py` with `GET /api/v1/billing/status`, `GET /api/v1/billing/cost-summary`, and a Stripe portal session endpoint.
- **Fix:** Wire up `billingAPI` (already in `api.js`) to replace the static values. Add a "Manage Billing" button that calls `POST /api/v1/billing/portal-session` to open the Stripe portal in a new tab.
- **Impact:** Billing tab becomes real instead of a demo placeholder.

---

## Part 2: New UI Components — Section by Section

### Section 1: Dashboard

**Add: `SpendForecastWidget`**
Show projected end-of-month spend based on the current burn rate from `daily_costs`. This is computable from data already flowing through `GET /api/v1/metrics/cost/timeseries`. Display it as a mini card with current spend vs. projected spend and a color-coded variance indicator.

**Add: `SavingsLeaderboardWidget`** (ORG_ADMIN + SUPER_ADMIN)
A ranked list of teams by savings achieved this month. Wire to `GET /api/v1/metrics/teams/{id}/summary` iterated across all teams. Motivates competition and makes cost governance visible.

**Add: `AgentStatusWidget`**
Shows which clusters have an agent installed, their last heartbeat time, and a quick "Reconnect" button for any that are stale. The data comes from `clusters.agent_installed` and `clusters.last_heartbeat` already returned in `GET /api/v1/clusters`.

---

### Section 2: Approvals

**Add: `ApprovalTimelineView`**
Replace (or tab alongside) the flat table with a timeline view grouped by day. Each entry shows the requester, feature, status change, and approver. The data is already in the approvals response — this is purely a presentation improvement.

**Add: `ExpiryCountdownBadge`** on Active Grants rows
The `expires_at` column exists. Add a live countdown (`HH:MM` remaining) displayed inline next to the status badge. Auto-refreshes every minute so admins can see which grants are about to expire without manual calculation.

**Add: Bulk Approve/Reject** controls
When multiple rows are selected (add checkboxes), show a floating action bar with "Approve All" and "Reject All" buttons. Each fires the existing `/approve` or `/reject` endpoint per ID. Saves time when there's a backlog of similar requests.

---

### Section 3: Teams

**Add: `TeamCostHeatmap`** in Team Details page
A 7-day heatmap showing daily spend per team, sourced from `GET /api/v1/metrics/teams/{id}/summary`. This gives team leads an immediate visual of spending patterns — spikes are obvious at a glance.

**Add: `MemberActivityLog`** tab on Team Details page
A filtered view of `GET /api/v1/audit/logs` scoped to `actor_id` values belonging to the team. Shows what each member has been doing recently — useful for onboarding reviews and audits.

**Add: `TeamBudgetProgressBar`**
If `teams.governance_config` contains a budget limit (it's already stored via `TeamGovernance`), display a progress bar on the Team card showing current month spend vs. the budget cap. Color it green → yellow → red as utilization climbs.

---

### Section 4: Clusters

**Add: `ClusterComparisonDrawer`**
Allow users to select 2–3 cluster cards and open a side-by-side comparison: node counts, spot ratio, monthly cost, CPU/memory utilization, savings. Data already exists across `GET /api/v1/clusters` and `GET /api/v1/metrics/cluster/{id}`.

**Add: `HeartbeatStatusIndicator`** on cluster cards
A small pulsing dot (green = heartbeat within 10 min, yellow = 10–30 min, red = stale) next to the cluster name. `clusters.last_heartbeat` is already in the response. Currently there's no visual indicator of agent health on the card itself.

**Add: `NodeDrainModal`**
When selecting a node in the Node List, allow an admin to initiate a cordon+drain via the existing cluster connection. This would call `POST /api/v1/clusters/{id}/optimize` (currently a stub) and would be a natural home for that endpoint once it's implemented.

**Fix: Connect `ClusterHealthTimeline`** to real data
Currently `Mock API`. The `audit_logs` table has cluster events — a filtered query by `resource_type = 'cluster'` and `resource = cluster_id` would populate this without any new schema work.

---

### Section 6: AtharvaAI

**Fix: Replace all `Mock API` with real data**
The entire AtharvaAI section runs on in-memory mock data. The `termination_events` and `rebalancing_actions` tables are defined in the DB schema. A focused sprint to wire `InterruptionHeatmap`, `RebalancingHistoryTimeline`, and `InstanceRankings` to real queries would make this section production-grade.

**Add: `MLModelVersionCard`**
Show the currently active ML model version, its training date, accuracy score, and a "Promote to Production" button (already gated by `feat-model-promote` JIT approval). Wire to `GET /api/v1/atharva/status` with an extended response, or a new `/api/v1/atharva/model-info` endpoint.

---

### Section 9: Right-Sizing

**Fix: Connect `Optimization Score` card**
Currently hardcoded. The score is computable from `instances.cpu_util` and `instances.memory_util` already in the rightsizing response — define a formula (e.g., `100 - avg(over-provisioning %)`) and render it dynamically.

**Add: `ApplyAllRecommendations` button**
Wire the existing `BatchApplyModal` which is currently `Mock API`. The backend endpoint `POST /api/v1/optimization/rightsizing/batch-apply` is defined — it just needs a real service implementation and the modal connected to it.

**Add: `ScheduledApply` toggle per recommendation**
Let users schedule a recommendation to be applied during a maintenance window (e.g., next Sunday 2am). Store the schedule in `hibernation_schedules` or a new `optimization_schedule` table. Display a clock icon on pending scheduled items.

---

### Section 10: Resource Hygiene (Cleanup)

**Add: `ScanScheduler`** component
Let admins configure automatic scans on a cron schedule (daily, weekly) per account. Store in a new `scan_schedules` table or in `organizations.governance_config`. Display the next scheduled scan time in the `FilterPanel`.

**Add: `ResourceDependencyGraph`**
The `Check Dependencies` button exists but just returns a list. Visualize the results as a small force-directed graph showing which resources block others. Libraries like `d3` are already available in the stack.

**Add: `SavedFilters`** in FilterPanel
Let users save combinations of account + region + resource type + status as named filter presets. Store in `localStorage` (or `users.preferences`). A "Saved Views" dropdown on the filter bar would save time for repeated scans.

---

### Section 11: Hibernation

**Wire up unused endpoints:**
- `POST /api/v1/hibernation/schedules/{id}/override` — add a "Wake Now" button to the `HistoryLog` and on the schedule card
- `DELETE /api/v1/hibernation/schedules/{id}` — add a delete button on each schedule in the `Scheduled Jobs List`

**Add: `HibernationCostProjection`**
The `CostAnalytics` sidebar is computed but static. Connect it to `clusters.monthly_cost` and the schedule matrix — calculate projected savings based on the percentage of hours hibernated per week.

---

### Section 13: Audit Logs

**Add: `AuditLogSearchBar`**
A free-text search across `actor_name`, `event`, and `resource` fields. The backend `AuditService.get_audit_logs` already accepts filter params — just add a text input that passes a `search` query param.

**Add: `LiveAuditFeed`** mode
A toggle that enables SSE-based live streaming of new audit events as they happen (similar to the AtharvaAI activity feed). The backend already has SSE infrastructure for approvals — extend it to audit logs.

**Add: `AuditHeatmap`** view
A calendar heatmap (like GitHub's contribution graph) showing event volume per day. Helps identify unusual activity patterns immediately. Computable from the existing `audit_logs.timestamp` data.

---

## Part 3: Super Admin Panel — Full Expansion

The current Admin Panel has the right bones (`AdminDashboard`, `AdminOverview`, `AdminClients`, `AdminHealth`, `AdminBilling`, `AdminExperiments`, `AdminOrganizations`, `AdminConfig`), but several critical tracking and management capabilities are missing or incomplete. Here's a complete picture.

---

### 3.1 What's Missing Today

| Gap | Current State | Impact |
|---|---|---|
| Impersonation ("Login as Tenant") | Endpoint mentioned in `INFO.md` (`POST /admin/impersonate`) but no UI | Cannot debug tenant-specific issues without separate credentials |
| Feature Flag Management | `AdminConfig` exists but feature flags from `feature_registry.py` aren't surfaced | Cannot enable/disable features per org without a code deploy |
| Per-Org Usage Quotas | No UI to set or display node limits, cluster limits, API rate limits | No way to enforce plan limits from the UI |
| Global Audit Log | `roleDefaults.js` has a `global_audit` widget that reuses `ActivityFeed` — but scoped to org-level, not platform-level | Can't see what's happening across all tenants |
| Tenant Health Drilldown | `AdminOrganizations` shows a table but clicking a row doesn't show a detail view | No per-tenant diagnostic capability |
| Revenue Analytics | `AdminBilling` shows MRR but returns hardcoded values — the `billing_routes.py` has real Stripe endpoints | MRR/ARR figures aren't reliable |
| Agent Fleet Overview | No view of all DaemonSet agents across all orgs | Impossible to know how many agents are healthy vs. stale at the platform level |

---

### 3.2 New Components to Add to Admin Panel

#### `AdminImpersonation` — New tab
A searchable org list. Clicking "Impersonate" calls `POST /admin/impersonate` (defined in `INFO.md`), exchanges for a scoped JWT, and opens the app as that org's admin. A persistent banner shows "You are viewing as [Org Name] — Exit Impersonation." This is the single highest-impact feature for support/debugging.

**Files to create:** `admin/AdminImpersonation.jsx`
**API:** `POST /api/v1/admin/impersonate` (implement in `admin_routes.py` + `admin_service.py`)

---

#### `AdminFeatureFlags` — New tab
A grid of all features from `feature_registry.py` with toggles per organization. Columns: Feature Name | Category | Risk Level | Global Default | Per-Org Overrides. Each org row shows a toggle to enable/disable the feature for that specific tenant without affecting others.

**Files to create:** `admin/AdminFeatureFlags.jsx`
**API:** New endpoints `GET /api/v1/admin/feature-flags` and `PATCH /api/v1/admin/feature-flags/{org_id}/{feature_id}`

---

#### `AdminTenantDrilldown` — Modal/Slide-over from `AdminOrganizations`
When clicking any org row, open a full detail view with tabs:
- **Overview** — clusters, accounts, users, monthly cost, savings generated (from `admin_service._get_org_stats`)
- **Members** — all users in that org with roles, last login, MFA status
- **Clusters** — all clusters linked to that org's accounts
- **Audit** — filtered audit log for that org's actors
- **Billing** — their plan, usage vs. limits, Stripe subscription ID
- **Agent Health** — all DaemonSet agents for that org with heartbeat status

**Files to create:** `admin/AdminTenantDrilldown.jsx`
**API:** Extend `GET /api/v1/admin/organizations/{id}` to return the full detail payload

---

#### `AdminAgentFleet` — New tab
A platform-wide table of every registered agent (from the `clusters` table filtered to `agent_installed = True`). Columns: Org Name | Cluster Name | Region | Agent Version | Last Heartbeat | Status. Color-code rows by heartbeat freshness. Add a "Force Reconnect" action.

**Files to create:** `admin/AdminAgentFleet.jsx`
**API:** New endpoint `GET /api/v1/admin/agent-fleet` — queries `clusters` joined to `accounts` and `organizations`

---

#### `AdminUsageQuotas` — Additions to `AdminOrganizations` or new tab
Display and edit per-org quota limits. Each org row shows progress bars for:
- Clusters used / cluster limit
- Nodes managed / node limit
- API calls this month / monthly limit

An "Edit Quotas" button opens a modal to adjust limits. Store limits in `organizations.governance_config` or a new `org_quotas` table.

**Files to create:** `admin/AdminUsageQuotas.jsx`
**API:** `GET /api/v1/admin/organizations/{id}/quotas` + `PATCH /api/v1/admin/organizations/{id}/quotas`

---

#### `AdminRevenueAnalytics` — Expand `AdminBilling`
Connect to real Stripe data via `billing_routes.py`. Add:
- **MRR/ARR trend chart** — 12-month line chart from `GET /api/v1/billing/daily-costs`
- **Churn indicators** — orgs whose status changed to inactive this month
- **Plan distribution** — pie chart of Free/Pro/Enterprise counts
- **Upsell pipeline** — table of orgs near their plan limits (already partially in `AdminBilling.jsx` as `upsell_opportunities`)
- **Failed charges** — list from Stripe webhook events

**Files to modify:** `admin/AdminBilling.jsx`
**API:** Wire `billingAPI` endpoints already defined in `api.js` but never called

---

#### `AdminGlobalAuditLog` — New tab (or enhance `AdminDashboard`)
Platform-wide audit log that spans all organizations. Uses the same `GET /api/v1/audit/logs` endpoint but without org-scoping (super admin bypass). Filters: Org, Actor, Event Type, Date Range, Outcome. This is already planned in `roleDefaults.js` as the `global_audit` widget — expand it into a full tab.

**Files to create:** `admin/AdminGlobalAudit.jsx`
**API:** Add `?global=true` query param to `GET /api/v1/audit/logs` — `require_super_admin` check strips the org filter

---

#### `AdminSystemAlerts` — Add to `AdminHealth`
Proactive alerting panel showing:
- Agents with heartbeat > 30 minutes old (query `clusters.last_heartbeat`)
- Orgs with pending accounts stuck in `PENDING_VALIDATION` > 24h
- Approvals in PENDING status > 48h (potential workflow blockage)
- Any `SAFE_TO_DELETE` resources that have been in that state for > 30 days without action

Implement as a polling component in `AdminHealth.jsx` with color-coded alert cards and direct action links.

---

#### Admin Dashboard Widget Additions (Super Admin role defaults)
The `roleDefaults.js` already defines `['platform_health', 'tenant_list', 'global_audit', 'revenue_chart']` for SUPER_ADMIN. Add two more widgets to the registry:

- **`agent_fleet_health`** — compact card showing total agents, healthy count, stale count, last sync time
- **`top_savings_orgs`** — leaderboard of the top 5 orgs by savings generated this month (good for customer success conversations)

---

### 3.3 How Everything Can Be Managed Through the Platform

Here's the full end-to-end management flow once the above additions are in place:

**Tenant Lifecycle:**
AdminOrganizations → create/invite → org signs up → Onboarding flow → VerifyStep validates AWS → AdminUsageQuotas sets plan limits → AdminFeatureFlags configures which features are available for their plan.

**Tenant Support:**
AdminOrganizations → click org row → AdminTenantDrilldown → switch to Clusters tab to see agent health → use AdminImpersonation to log in as that org and reproduce the issue directly → exit impersonation → log the action (auto-recorded in global audit log).

**Revenue Operations:**
AdminBilling → MRR trend chart → filter upsell_opportunities to orgs near limits → contact them → update their plan in AdminUsageQuotas → Stripe subscription updates automatically.

**Platform Health:**
AdminHealth → AdminSystemAlerts fires if any agents go stale → AdminAgentFleet shows which cluster → click Force Reconnect → alert clears.

**Feature Rollouts:**
AdminFeatureFlags → toggle a new feature on for a single pilot org → monitor via AdminGlobalAuditLog to see usage → roll out to all orgs once confident.

**Security & Compliance:**
AdminGlobalAuditLog → filter by event type `RESOURCE_DELETE` or `ROLE_CHANGE` → export as JSON for compliance reports → cross-reference with AdminImpersonation log to verify no unauthorized access occurred.

---

## Appendix: Priority Matrix

| Item | Effort | Impact | Priority |
|---|---|---|---|
| Wire `FleetComposition` to real API | Low | High | P1 |
| Wire `PendingApprovalsCard` to real API | Low | High | P1 |
| Wire `PlatformHealthCard` to real API | Low | High | P1 |
| Wire Billing tab to real Stripe API | Medium | High | P1 |
| `AdminImpersonation` | Medium | Critical | P1 |
| `AdminTenantDrilldown` modal | Medium | High | P2 |
| `AdminFeatureFlags` tab | Medium | High | P2 |
| Wire unused Hibernation endpoints | Low | Medium | P2 |
| `AdminAgentFleet` tab | Medium | High | P2 |
| `AdminSystemAlerts` panel | Low | High | P2 |
| `AdminRevenueAnalytics` expansion | Medium | High | P2 |
| Wire `AtharvaAI` to real DB tables | High | High | P2 |
| `AdminGlobalAuditLog` | Low | Medium | P3 |
| `ClusterComparisonDrawer` | Medium | Medium | P3 |
| `AuditHeatmap` view | Low | Low | P3 |
| `ResourceDependencyGraph` | High | Medium | P3 |