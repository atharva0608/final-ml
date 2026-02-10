# Frontend Catalog — UI Component & Route Registry

> **Last Updated**: 2026-02-10
> **Total Components**: ~90 | **Total Routes**: 38
> **Naming**: Reflects Global Naming Synchronization (Approvals, Hygiene, Tagging Policies, Experiments)

---

## 1. Route Map

### Public Routes

| Path | Component | File |
|:-----|:----------|:-----|
| `/login` | Login | `pages/Login.jsx` |
| `/signup` | Signup | `pages/Signup.jsx` |

### Protected Routes (MainLayout)

| Path | Component | File | Description |
|:-----|:----------|:-----|:------------|
| `/` → `/dashboard` | Dashboard | `pages/Dashboard.jsx` | Role-customized widget dashboard |
| `/clusters` | ClusterList | `components/clusters/ClusterList.jsx` | Cluster inventory & cards |
| `/clusters/:id` | ClusterDetails | `components/clusters/ClusterDetails.jsx` | Single cluster detail view |
| `/policies` | PolicyConfig | `components/policies/PolicyConfig.jsx` | Optimization policies |
| `/templates` | TemplateList | `components/templates/TemplateList.jsx` | Node templates |
| `/right-sizing` | RightSizing | `components/optimization/RightSizing.jsx` | Instance rightsizing |
| `/hibernation` | HibernationSchedule | `components/hibernation/HibernationSchedule.jsx` | Cluster hibernation |
| `/audit` | AuditLog | `components/audit/AuditLog.jsx` | Audit trail |
| `/hygiene` | CleanupDashboard | `components/cleanup/CleanupDashboard.jsx` | Resource hygiene |
| `/approvals` | Approvals | `pages/Approvals.jsx` | Approval / ticket center |
| `/settings` | Settings | `pages/Settings.jsx` | Account, integrations, billing |
| `/settings/governance` | GovernanceSettings | `components/governance/GovernanceSettings.jsx` | Governance config |
| `/tagging-policies` | TagPoliciesManager | `components/policies/TagPoliciesManager.jsx` | Tag policies |
| `/tag-templates` | TagTemplateManager | `components/settings/TagTemplateManager.jsx` | Tag templates |
| `/teams` | Teams | `pages/Teams.jsx` | Team management |
| `/teams/:teamId` | TeamDetails | `components/teams/TeamDetails.jsx` | Team details |
| `/roles` | Roles | `pages/Roles.jsx` | Role management |
| `/accounts/:accountId/analytics` | AccountAnalytics | `components/analytics/AccountAnalytics.jsx` | Account analytics |
| `/ri-analysis` | RIAnalysis | `components/analysis/RIAnalysis.jsx` | RI analysis |
| `/s3-analysis` | S3Analysis | `components/analysis/S3Analysis.jsx` | S3 analysis |
| `/rds-analysis` | RDSAnalysis | `components/analysis/RDSAnalysis.jsx` | RDS analysis |
| `/transfer-analysis` | TransferAnalysis | `components/analysis/TransferAnalysis.jsx` | Transfer analysis |
| `/invite-acceptance` | InviteAcceptance | `pages/InviteAcceptance.jsx` | Accept invitations |

### Admin Routes (SUPER_ADMIN Only)

| Path | Component | File |
|:-----|:----------|:-----|
| `/admin` | AdminDashboard | `components/admin/AdminDashboard.jsx` |
| `/admin/clients` | AdminClients | `components/admin/AdminClients.jsx` |
| `/admin/health` | AdminHealth | `components/admin/AdminHealth.jsx` |
| `/admin/experiments` | AdminExperiments | `components/admin/AdminExperiments.jsx` |
| `/admin/config` | AdminConfig | `components/admin/AdminConfig.jsx` |
| `/admin/organizations` | AdminOrganizations | `components/admin/AdminOrganizations.jsx` |
| `/admin/billing` | AdminBilling | `components/admin/AdminBilling.jsx` |

---

## 2. Component Catalog

### Layout & Navigation

| ID | Component | File | Purpose |
|:---|:----------|:-----|:--------|
| FE-CMP::LAYOUT-01 | MainLayout | `components/layout/MainLayout.jsx` | Shell with sidebar, topbar, content area |
| FE-CMP::LAYOUT-02 | Sidebar | (inside MainLayout) | Role-based navigation (client vs admin) |
| FE-CMP::LAYOUT-03 | ClusterBadge | (inside MainLayout) | Pulsing notification badge for discovered/error clusters |

### Dashboard Widgets

| ID | Component | File | Purpose |
|:---|:----------|:-----|:--------|
| FE-CMP::DASH-01 | CostKPICard | `components/dashboard/CostKPICard.jsx` | Monthly spend KPI |
| FE-CMP::DASH-02 | SavingsKPICard | `components/dashboard/SavingsKPICard.jsx` | Realized + potential savings |
| FE-CMP::DASH-03 | SavingsChart | `components/dashboard/SavingsChart.jsx` | Cost over time (Recharts) |
| FE-CMP::DASH-04 | FleetComposition | `components/dashboard/FleetComposition.jsx` | Spot vs On-Demand pie chart |
| FE-CMP::DASH-05 | ActivityFeed | `components/dashboard/ActivityFeed.jsx` | Real-time audit log feed |
| FE-CMP::DASH-06 | ClusterHealthCard | `components/dashboard/ClusterHealthCard.jsx` | Cluster status overview |
| FE-CMP::DASH-07 | PendingApprovalsCard | `components/dashboard/PendingApprovalsCard.jsx` | Pending approval count |
| FE-CMP::DASH-08 | PlatformHealthCard | `components/dashboard/PlatformHealthCard.jsx` | API latency, DB, Redis, workers (SUPER_ADMIN) |
| FE-CMP::DASH-09 | TenantListCard | `components/dashboard/TenantListCard.jsx` | Org list (SUPER_ADMIN) |

### Cluster Components

| ID | Component | File | Purpose |
|:---|:----------|:-----|:--------|
| FE-CMP::CLUST-01 | ClusterList | `components/clusters/ClusterList.jsx` | Cluster inventory with cards & KPIs |
| FE-CMP::CLUST-02 | ClusterDetails | `components/clusters/ClusterDetails.jsx` | Single cluster deep dive |
| FE-CMP::CLUST-03 | ClusterConnectModal | `components/clusters/ClusterConnectModal.jsx` | Helm install command modal |
| FE-CMP::CLUST-04 | ClusterDisconnectModal | `components/clusters/ClusterDisconnectModal.jsx` | Disconnect with options |
| FE-CMP::CLUST-05 | NodeList | `components/clusters/NodeList.jsx` | Node inventory per cluster |

### Resource Hygiene Components

| ID | Component | File | Purpose |
|:---|:----------|:-----|:--------|
| FE-CMP::HYG-01 | CleanupDashboard | `components/cleanup/CleanupDashboard.jsx` | Main hygiene view |
| FE-CMP::HYG-02 | CleanupSidebar | `components/cleanup/CleanupSidebar.jsx` | Vertical resource type navigation |
| FE-CMP::HYG-03 | FilterPanel | `components/cleanup/FilterPanel.jsx` | Region/account/status filters |
| FE-CMP::HYG-04 | HeroMetricsPanel | `components/cleanup/HeroMetricsPanel.jsx` | 4 metric cards (savings, allocation, tag health, safety) |
| FE-CMP::HYG-05 | SavingsGauge | `components/cleanup/SavingsGauge.jsx` | Animated semi-circle savings gauge |
| FE-CMP::HYG-06 | BulkTagWizard | `components/cleanup/BulkTagWizard.jsx` | Template/manual tagging with collision handling |
| FE-CMP::HYG-07 | CleanupPolicies | `components/cleanup/CleanupPolicies.jsx` | Automated cleanup rule builder |
| FE-CMP::HYG-08 | RIWizard | `components/cleanup/RIWizard.jsx` | RI optimization wizard |
| FE-CMP::HYG-09 | S3Wizard | `components/cleanup/S3Wizard.jsx` | S3 optimization wizard |
| FE-CMP::HYG-10 | RDSWizard | `components/cleanup/RDSWizard.jsx` | RDS optimization wizard |

### Approval Components

| ID | Component | File | Purpose |
|:---|:----------|:-----|:--------|
| FE-CMP::APRV-01 | Approvals | `pages/Approvals.jsx` | Main approval center page |
| FE-CMP::APRV-02 | TicketRequestModal | `components/approvals/TicketRequestModal.jsx` | JIT access request modal |
| FE-CMP::APRV-03 | AccessRequestModal | `components/approvals/AccessRequestModal.jsx` | Auto-triggered on 403 |
| FE-CMP::APRV-04 | ActiveWindowBanner | `components/approvals/ActiveWindowBanner.jsx` | Countdown for active access windows |

### Governance & JIT Components

| ID | Component | File | Purpose |
|:---|:----------|:-----|:--------|
| FE-CMP::GOV-01 | GovernanceSettings | `components/governance/GovernanceSettings.jsx` | Org-level governance toggles |
| FE-CMP::GOV-02 | GovernanceManager | `components/governance/GovernanceManager.jsx` | Governance rule engine UI |
| FE-CMP::GOV-03 | ProtectedButton | `components/governance/ProtectedButton.jsx` | Auto-locks buttons requiring JIT approval |
| FE-CMP::GOV-04 | JITRequestModal | `components/governance/JITRequestModal.jsx` | Feature access request modal |
| FE-CMP::GOV-05 | ActiveJITBanner | `components/governance/ActiveJITBanner.jsx` | Active elevated access banner |
| FE-CMP::GOV-06 | RiskBadge | `components/shared/RiskBadge.jsx` | Color-coded risk level badge |

### Settings Components

| ID | Component | File | Purpose |
|:---|:----------|:-----|:--------|
| FE-CMP::SET-01 | Settings | `pages/Settings.jsx` | Settings shell (tabs) |
| FE-CMP::SET-02 | AccountSettings | `components/settings/AccountSettings.jsx` | Password change |
| FE-CMP::SET-03 | CloudIntegrations | `components/settings/CloudIntegrations.jsx` | AWS account management |
| FE-CMP::SET-04 | TagTemplateManager | `components/settings/TagTemplateManager.jsx` | Tag template CRUD |
| FE-CMP::SET-05 | PlatformSettings | `components/settings/PlatformSettings.jsx` | AWS identity, safe mode |

### Onboarding Components

| ID | Component | File | Purpose |
|:---|:----------|:-----|:--------|
| FE-CMP::ONB-01 | Onboarding | `components/onboarding/Onboarding.jsx` | Onboarding wizard shell |
| FE-CMP::ONB-02 | WelcomeStep | `components/onboarding/WelcomeStep.jsx` | Welcome screen |
| FE-CMP::ONB-03 | ConnectStep | `components/onboarding/ConnectStep.jsx` | AWS CloudFormation connect |
| FE-CMP::ONB-04 | DiscoverStep | `components/onboarding/DiscoverStep.jsx` | Cluster discovery |

### Analysis Components

| ID | Component | File | Purpose |
|:---|:----------|:-----|:--------|
| FE-CMP::ANAL-01 | RIAnalysis | `components/analysis/RIAnalysis.jsx` | RI overview & recommendations |
| FE-CMP::ANAL-02 | S3Analysis | `components/analysis/S3Analysis.jsx` | S3 tiering opportunities |
| FE-CMP::ANAL-03 | RDSAnalysis | `components/analysis/RDSAnalysis.jsx` | RDS optimization |
| FE-CMP::ANAL-04 | TransferAnalysis | `components/analysis/TransferAnalysis.jsx` | Data transfer cost analysis |
| FE-CMP::ANAL-05 | RIHealthCard | `components/dashboard/RIHealthCard.jsx` | RI widget |
| FE-CMP::ANAL-06 | S3HealthCard | `components/dashboard/S3HealthCard.jsx` | S3 widget |
| FE-CMP::ANAL-07 | RDSHealthCard | `components/dashboard/RDSHealthCard.jsx` | RDS widget |
| FE-CMP::ANAL-08 | TransferHealthCard | `components/dashboard/TransferHealthCard.jsx` | Transfer widget |

### Hooks

| Hook | File | Purpose |
|:-----|:-----|:--------|
| `usePermission` | `hooks/usePermission.js` | Real-time JIT permission check |
| `useDashboard` | `hooks/useDashboard.js` | Dashboard data fetching |
| `useAuth` (Zustand) | `store/authStore.js` | Auth state management |

---

## 3. API Service Layer (`services/api.js`)

| Object | Prefix | Key Methods |
|:-------|:-------|:------------|
| `authAPI` | `/auth` | login, signup, refresh, me, updatePassword |
| `clusterAPI` | `/clusters` | listClusters, getCluster, autoInstallAgent, disconnect |
| `metricAPI` | `/metrics` | dashboard, cost, instances, timeSeries, teamStats |
| `hygieneAPI` | `/hygiene` | scan, checkDependencies, executeAction, discover |
| `approvalsAPI` | `/approvals` | create, activeWindow, delegate, approve, reject, revoke |
| `accountAPI` | `/accounts` | link, validate, setDefault, disconnect |
| `teamAPI` | `/teams` | list, get, create, invite, removeMembers, governance |
| `adminAPI` | `/admin` | dashboard, clients, health, organizations, platformIdentity |
| `policyAPI` | `/policies` | get, update |
| `templateAPI` | `/templates` | list, create, update, delete, setDefault |
| `auditAPI` | `/audit` | logs, export |
| `governanceAPI` | `/governance` | rules, compliance |
| `experimentsAPI` | `/lab` | experiments, models, liveSwitch, graduate |
| `optimizationAPI` | `/optimization` | rightsizing |
| `healthAPI` | `/health` | system, detailed |
| `riAPI` | `/ri` | overview, list, recommendations, analysis, unifiedCoverage |
| `billingAPI` | `/billing` | portalSession, webhook, status |
| `settingsAPI` | `/settings` | get, update, automation |
| `roleAPI` | `/roles` | list, create, update, delete, permissionMatrix |
| `onboardingAPI` | `/onboarding` | awsLink, verify, template, reset |

---

## 4. State Management

| Store | Library | Purpose |
|:------|:--------|:--------|
| `authStore` | Zustand | User auth, role, token, preferences |

**Widget System**: `widgetRegistry.js` maps widget IDs to components; `roleDefaults.js` defines default layouts per role (SUPER_ADMIN, ORG_ADMIN, TEAM_LEAD, MEMBER).

---

## 5. Zombie & Orphaned Components

| Component | Status | Recommendation |
|:----------|:-------|:---------------|
| Smart Tags (backend only) | Redundant with auto-tag | Delete `smart_tag_routes.py` |
| Legacy TagTemplateManager (`policies/`) | Unused, replaced by settings version | Remove |
| ExperimentLab (user-facing route) | Hidden, admin-only at `/admin/experiments` | Wire up or remove |
| S3 Bucket List endpoint | Missing | Build `/s3/buckets` for pagination |
| RDS Instance List endpoint | Missing | Build `/rds/instances` for pagination |
| Tag Policy Compliance Stats | Stubbed | Implement real scan integration |
| Savings Plans UI | Missing | Build dedicated page |
| Auto-Tag Rules UI | Missing | Build policy builder UI |

---

## 6. Design System

| Layer | Technology |
|:------|:-----------|
| CSS Framework | Tailwind CSS 3.3.0 |
| Primitives | Radix UI |
| Icons | Lucide + react-icons/fi (Feather) |
| Charts | Recharts 2.15.4 |
| Animations | Framer Motion 10.16.4 |
| HTTP | Axios |
| State | Zustand 4.4.7 |
| Routing | React Router DOM 6 |

---

**Last Updated**: 2026-02-10
