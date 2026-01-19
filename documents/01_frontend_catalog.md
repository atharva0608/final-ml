# 🎨 Frontend Component Catalog

| ID (Unique Tracking Code) | File Path | Type | Function / Feature Description | State / Props Used | Dependencies (Imports) |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **FE-APP::Main::Entry** | `frontend/src/index.js` | App | React application entry point. | `ReactDOM`, `App` | `react-dom` |
| **FE-APP::Main::Root** | `frontend/src/App.js` | App | Main Router and Layout configuration. | `RouterProvider` | `react-router-dom` |
| **FE-CFG::System::Pkg** | `frontend/package.json` | Config | NPM dependencies and scripts. | `N/A` | `N/A` |
| **FE-CFG::System::Tailwind** | `frontend/tailwind.config.js` | Config | Tailwind CSS configuration. | `N/A` | `tailwindcss` |
| **FE-CFG::System::PostCSS** | `frontend/postcss.config.js` | Config | PostCSS configuration. | `N/A` | `postcss` |
| **FE-CFG::System::Env** | `frontend/.env.example` | Config | Frontend environment template. | `N/A` | `N/A` |
| **FE-ASST::Public::HTML** | `frontend/public/index.html` | Asset | Main HTML entry point. | `N/A` | `N/A` |
| **FE-ASST::Public::Manifest** | `frontend/public/manifest.json` | Asset | PWA Manifest file. | `N/A` | `N/A` |
| **FE-CMP::Auth::Login** | `frontend/src/components/auth/Login.jsx` | Page | User Login form. | `email`, `password` | `useAuth`, `Input`, `Button` |
| **FE-CMP::Auth::Signup** | `frontend/src/components/auth/Signup.jsx` | Page | User Signup form. | `email`, `password` | `useAuth`, `Input`, `Button` |
| **FE-CMP::Dash::Main** | `frontend/src/components/dashboard/Dashboard.jsx` | Page | Main KPI Dashboard. **UPDATED (2026-01-16)**: "Connect AWS Account" card now RBAC-enforced (TEAM_LEAD/ORG_ADMIN/CLIENT only when accounts.length === 0). | `kpiStats` | `StatsCard`, `recharts` |
| **FE-CMP::Dash::Widgets** | `frontend/src/components/dashboard/widgets/*` | Widget | **NEW (2026-01-16)**: 9 modular dashboard widgets for role-based customization: CostKPICard, SavingsKPICard, SavingsChart, FleetComposition, ActivityFeed, ClusterHealthCard, PendingApprovalsCard, PlatformHealthCard, TenantListCard. | `data` | `recharts`, `formatters` |
| **FE-CFG::Dash::Registry** | `frontend/src/components/dashboard/widgetRegistry.js` | Config | **NEW (2026-01-16)**: Widget Registry mapping keys to React components. Central registry for dynamic dashboard rendering. | N/A | Widget components |
| **FE-CFG::Dash::Defaults** | `frontend/src/components/dashboard/roleDefaults.js` | Config | **NEW (2026-01-16)**: Role-based default dashboard layouts. Defines which widgets each role sees by default. | N/A | N/A |
| **FE-CMP::Layout::Main** | `frontend/src/components/layout/MainLayout.jsx` | Layout | Sidebar, Header, and Wrapper. | `children` | `Sidebar`, `Header` |
| **FE-CMP::Cluster::List** | `frontend/src/components/clusters/ClusterList.jsx` | Page | List of K8s clusters. | `clusters` | `useClusterStore` |
| **FE-CMP::Cluster::Detail** | `frontend/src/components/clusters/ClusterDetails.jsx` | Page | Cluster details view. | `cluster` | `clusterAPI` |
| **FE-CMP::Cluster::Nodes** | `frontend/src/components/clusters/NodeList.jsx` | Component | Node list within a cluster. | `nodes` | `Table` |
| **FE-CMP::Cluster::Connect** | `frontend/src/components/clusters/ClusterConnectModal.jsx` | Component | Modal to register new clusters. | `step` | `clusterAPI` |
| **FE-CMP::Tpl::List** | `frontend/src/components/templates/TemplateList.jsx` | Page | Node Template management list. | `templates` | `templateAPI` |
| **FE-CMP::Tpl::Builder** | `frontend/src/components/templates/TemplateBuilder.jsx` | Component | Form to create/edit templates. | `formData` | `Input`, `Select` |
| **FE-CMP::Pol::Config** | `frontend/src/components/policies/PolicyConfig.jsx` | Page | Optimization policy settings. | `policy` | `policyAPI` |
| **FE-CMP::Hiber::Sched** | `frontend/src/components/hibernation/HibernationSchedule.jsx` | Page | Hibernation scheduler UI. | `schedule` | `hibernationAPI` |
| **FE-CMP::Lab::Main** | `frontend/src/components/lab/ExperimentLab.jsx` | Page | ML Experimentation dashboard. | `experiments` | `labAPI` |
| **FE-CMP::Right::Main** | `frontend/src/components/right-sizing/RightSizing.jsx` | Page | Rightsizing recommendations. | `recommendations` | `Card` |
| **FE-CMP::Audit::Log** | `frontend/src/components/audit/AuditLog.jsx` | Page | System Audit Log viewer. | `logs` | `auditAPI` |
| **FE-CMP::Admin::Dash** | `frontend/src/components/admin/AdminDashboard.jsx` | Admin | **Super Admin Command Center**. **SIMPLIFIED (2026-01-19)**: No tabs, directly renders `AdminOverview`. All admin sections accessible via sidebar. | `-` | `AdminOverview` |
| **FE-CMP::Admin::Overview** | `frontend/src/components/admin/AdminOverview.jsx` | Admin | **Real**: Platform HUD. Displays Total MRR, Active Users (Real Count), Cluster Stats, and **Live Activity Feed** (Audit Logs). | `stats`, `activity` | `adminAPI`, `StatsCard` |
| **FE-CMP::Admin::Orgs** | `frontend/src/components/admin/AdminOrganizations.jsx` | Admin | Organization management table. **FIXED (2026-01-19)**: Added missing state variables, fetchOrganizations logic, and corrected response parsing (`response.data.organizations` instead of `.items`). | `organizations`, `searchQuery`, `page` | `adminAPI` |
| **FE-CMP::Admin::Clients** | `frontend/src/components/admin/AdminClients.jsx` | Admin | Client management table. | `clients` | `adminAPI` |
| **FE-CMP::Admin::Billing** | `frontend/src/components/admin/AdminBilling.jsx` | Page | Billing overview and Plans (Backend Mocked Data). | `stats`, `plans` | `Card`, `Button`, `Icons` |
| **FE-CMP::Admin::Health** | `frontend/src/components/admin/AdminHealth.jsx` | Admin | System health status. | `health` | `useDashboard` |
| **FE-CMP::Admin::Config** | `frontend/src/components/admin/AdminConfig.jsx` | Admin | **Real**: Platform configuration with Safe Mode toggle (API connected). | `safeMode`, `config` | `adminAPI`, `PlatformSettings` |
| **FE-CMP::Admin::Platform** | `frontend/src/components/admin/PlatformSettings.jsx` | Admin | **Real**: Platform AWS Identity management with STS verification. | `connected`, `formData` | `adminAPI`, `toast` |
| **FE-CMP::Admin::Lab** | `frontend/src/components/admin/AdminLab.jsx` | Admin | Admin view for Lab experiments. | `experiments` | `labAPI` |
| **FE-CMP::Set::Main** | `frontend/src/components/settings/Settings.jsx` | Page | User Settings wrapper. | `tab` | `AccountSettings`, `TeamManagement` |
| **FE-CMP::Set::Account** | `frontend/src/components/settings/AccountSettings.jsx` | Component | User profile settings (Backend Mocked). | `userData` | `authAPI` |
| **FE-CMP::Set::Teams** | `frontend/src/components/settings/TeamManagement.jsx` | Component | **Real**: 4-Tier Role Management (Super Admin, Org Admin, Team Lead, Member). Accordion view for hierarchical team/member management. **Team-Specific Governance** integration via collapsible "Configure Approval Policies" section. | `teams`, `members`, `showGovernanceForTeam` | `teamAPI`, `TeamGovernance` |
| **FE-CMP::Set::Profile** | `frontend/src/components/settings/UserProfile.jsx` | Component | **New**: User Profile settings (Full Name update). | `user` | `userAPI` |
| **FE-CMP::Set::TeamGov** | `frontend/src/components/settings/TeamGovernance.jsx` | Component | **Real**: Team-Specific Approval Policies UI. Toggle switches for 5 actions (CONNECT_ACCOUNT, TERMINATE_INSTANCE, DELETE_VOLUME, DELETE_SNAPSHOT, RELEASE_IP). Fetches/saves to `PUT /teams/{id}/governance`. | `config`, `teamId` | `api`, `toast` |
| **FE-CMP::Set::MemberPerms** | `frontend/src/components/settings/MemberPermissionsModal.jsx` | Component | **NEW (2026-01-19)**: Modal for managing granular team member permission overrides. Displays toggles for predefined permissions (allow_termination, allow_cleanup, view_audit_logs, etc.). Saves via `PUT /teams/{team_id}/members/{member_id}/permissions`. | `member`, `permissions` | `teamAPI`, `Button` |
| **FE-CMP::Set::PermMat** | `frontend/src/components/policies/PermissionMatrix.jsx` | Component | **Real**: Interactive matrix for editing Role permissions. Used in TeamManagement. | `roles` | `rolesAPI` |
| **FE-CMP::Team::Details** | `frontend/src/pages/TeamDetails.jsx` | Page | **Real**: Comprehensive Team Dashboard. **Consolidated View**: Top Spenders Leaderboard, Waste Breakdown (Pie Chart), Cost Trends (Area Chart). **Member Details**: Accordion list of members and connected accounts. **Governance**: Integrated Policy settings. | `teamId` | `metricsAPI`, `teamAPI`, `recharts` |
| **FE-CMP::Account::Analytics** | `frontend/src/pages/AccountAnalytics.jsx` | Page | **Real**: Detailed Account Analytics view. Shows cost breakdown, usage trends, and optimization opportunities for a specific AWS account. | `accountId` | `metricsAPI` |
| **FE-CMP::Approv::Main** | `frontend/src/components/approvals/ApprovalCenter.jsx` | Page | **Real**: Approval Center for Maker-Checker (Four-Eyes) workflows. Lists pending requests and allows Team Leads to Approve/Reject destructive actions. | `requests` | `approvalsAPI`, `Badge` |
| **FE-CMP::Gov::Settings** | `frontend/src/components/settings/GovernanceSettings.jsx` | Page | **Real**: Automated Governance / Policy-as-Code settings. Master toggle, policy cards, required tags configuration. | `config`, `policies` | `governanceAPI`, `toast` |
| **FE-CMP::Ticket::Center** | `frontend/src/pages/TicketCenter.jsx` | Page | **Real (JIT, Audited 2026-01-14)**: Role-based ticket management with real API data. Admin: Stats cards, "Pending Requests" + "Active Grants" tabs. Team Lead: Incoming/Outgoing/Team Access. Member: My Requests. Includes `CLIENT` role support. Real timestamps, expiry countdown. | `tickets`, `activeTab`, `loading` | `ticketsAPI`, `date-fns`, `format` |
| **FE-CMP::Ticket::Modal** | `frontend/src/components/tickets/TicketRequestModal.jsx` | Component | **Real (JIT)**: Role-adaptive access request/grant modal. Admin: Grant Mode (pick recipients). Team Lead: Toggle between Grant/Request. Member: Request Only. Gradient header, duration slider, recipient selection with role badges. | `isGrantMode`, `members` | `organizationAPI`, `ticketsAPI` |
| **FE-CMP::Ticket::Banner** | `frontend/src/components/tickets/ActiveWindowBanner.jsx` | Component | **Real (JIT)**: Active access window countdown banner. Shows remaining time for approved access grants. | `activeWindow` | `ticketsAPI`, `date-fns` |
| **FE-PG::Team::Main** | `frontend/src/pages/Teams.jsx` | Page | **Real (RBAC Fixed 2026-01-14)**: Tabbed view for Team Structure and Roles & Policies. **RBAC Enforced**: Roles tab is HIDDEN from MEMBER and TEAM_LEAD. Only ORG_ADMIN, SUPER_ADMIN, CLIENT can see/access Roles. Uses `useAuthStore` for role check. | `activeTab`, `user` | `TeamManagement`, `Roles`, `useAuthStore` |
| **FE-PG::Roles::Main** | `frontend/src/pages/Roles.jsx` | Page | **Real (RBAC)**: Role management page. Lists all roles as cards. Click to edit permissions via `PermissionMatrix`. System roles (ORG_ADMIN, CLIENT) are read-only to prevent lockout. | `roles`, `editingRole` | `rolesAPI`, `PermissionMatrix` |

### 6. Documentation Components
| **FE-LIB::UI::Card** | `frontend/src/components/shared/Card.jsx` | UI | Reusable Card. | `children` | `N/A` |
| **FE-LIB::UI::Input** | `frontend/src/components/shared/Input.jsx` | UI | Reusable Input. | `onChange` | `N/A` |
| **FE-LIB::UI::Badge** | `frontend/src/components/shared/Badge.jsx` | UI | Status Badge. | `status` | `N/A` |
| **FE-LIB::UI::StatsCard** | `frontend/src/components/shared/StatsCard.jsx` | UI | Dashboard Metric Card. | `title`, `value` | `N/A` |
| **FE-LIB::UI::GaugeChart** | `frontend/src/components/shared/GaugeChart.jsx` | UI | Animated Semi-Circular Gauge for metrics. | `value`, `maxValue` | `useEffect` |
| **FE-LIB::UI::EmptyState** | `frontend/src/components/shared/EmptyState.jsx` | UI | Empty state placeholder for no-data scenarios. | `title`, `message`, `action` | `FiInbox` |
| **FE-LIB::UI::Switch** | `frontend/src/components/shared/Switch.jsx` | UI | Reusable Toggle Switch. | `checked`, `onChange` | `N/A` |
| **FE-HK::Auth::UseAuth** | `frontend/src/hooks/useAuth.js` | Hook | Authentication logic hook. | `user` | `authAPI` |
| **FE-HK::Dash::UseDash** | `frontend/src/hooks/useDashboard.js` | Hook | Dashboard data fetching hook. | `data` | `metricsAPI` |
| **FE-SVC::API::Client** | `frontend/src/services/api.js`| Service | Central Axios instance and API method definitions. Includes `ticketsAPI` for JIT Ticket System (create, grantAccess, approve, revoke, acceptGrant, rejectGrant, list, getActiveWindow). | `axios` | `axios` |
| **FE-STR::Store::Global** | `frontend/src/store/useStore.js` | Store | Global State (Zustand). | `state` | `zustand` |
| **FE-UTL::Fmt::Format** | `frontend/src/utils/formatters.js` | Utility | Currency/Date formatters. | `value` | `Intl` |
| **FE-APP::Style::Global** | `frontend/src/index.css` | Style | Global CSS styles. | `N/A` | `N/A` |
| **FE-LIB::UI::Index** | `frontend/src/components/shared/index.js` | UI | Export barrel for shared components. | `N/A` | `N/A` |
| **FE-CMP::Onboard::Page** | `frontend/src/pages/Onboarding.jsx` | Page | Wrapper page for the onboarding flow. | `step` | `WelcomeStep`, `ConnectStep` |
| **FE-CMP::Onboard::Welcome** | `frontend/src/components/onboarding/WelcomeStep.jsx` | Component | Onboarding Step 1: Welcome. | `onNext` | `Button` |
| **FE-CMP::Onboard::Connect** | `frontend/src/components/onboarding/ConnectStep.jsx` | Component | **REAL (Updated 2026-01-19)**: AWS Account connection step. Added explicit instructions and warning boxes specifying that Role ARN and Account ID belong to the *client's* AWS account. Enhanced UI with a clear "Warning" card to prevent confusion. | `onNext`, `roleArn`, `externalId` | `onboardingAPI`, `Button`, `Icons` |
| **FE-CMP::Onboard::Verify** | `frontend/src/components/onboarding/VerifyStep.jsx` | Component | Onboarding Step 3: Visual loading spinner during verification. | `onNext` | `motion` |
| **FE-CMP::Onboard::Success** | `frontend/src/components/onboarding/SuccessStep.jsx` | Component | Onboarding Step 4: Success. | `onComplete` | `Button` |
| **FE-CMP::Cleanup::Main** | `frontend/src/components/cleanup/CleanupDashboard.jsx` | Page | **REAL (Redesigned 2026-01-19)**: Central hub for AWS cost hygiene. Features a **Static Action Bar** (Authorize, Unauthorize, Cleanup) for bulk operations and an **Integrated Side Navigation** for 9 resource categories. Displays **Live Potential Savings Gauge** tracking selection. | `scanResult`, `selectedAccount`, `selectedItems` | `cleanupAPI`, `SavingsGauge`, `ResourceTable` |
| **FE-CMP::Cleanup::Sidebar** | `frontend/src/components/cleanup/layout/CleanupSidebar.jsx` | Layout | **NEW (2026-01-19)**: Vertical navigation sidebar within the Cleanup dashboard. Grouped categories (Compute, Storage, Network, Identity, RI/Optimization). Collapsible for maximum workspace. | `activeTab`, `onTabChange` | `Icons` |
| **FE-CMP::Cleanup::Filter** | `frontend/src/components/cleanup/layout/FilterPanel.jsx` | Component | **REAL (Updated 2026-01-19)**: Top-bar filtering utility. Includes Account/Region selectors, Refresh trigger, and **Real-Time "Last Scanned" timestamp** display (fixed ReferenceError). | `accounts`, `lastScan` | `Icons` |
| **FE-CMP::Cleanup::Hero** | `frontend/src/components/cleanup/summary/HeroMetricsPanel.jsx` | Component | **NEW (2026-01-19)**: Top-level summary cards showing Total Potential Savings, Untagged Waste, and Health Score. | `summary` | `StatsCard` |
| **FE-CMP::Cleanup::Gauge** | `frontend/src/components/cleanup/summary/SavingsGauge.jsx` | Component | **NEW (2026-01-19)**: **Animated semi-circle meter** with live dollar counter. Features: (1) **Dynamic Normalization**: Scales selected cost against total potential savings. (2) **Smooth Motion**: Uses `framer-motion`'s `animate` function for high-frequency value updates. (3) **SVG Meter**: Custom semi-circle `PieChart` via `recharts`. | `selectedSavings`, `total` | `recharts`, `framer-motion` |
| **FE-CMP::Cleanup::Table** | `frontend/src/components/cleanup/tables/ResourceTable.jsx` | Table | **REAL (Updated 2026-01-19)**: High-performance list view with row-level actions. Added **Inline Action Buttons** (Authorize, Unauthorize, Cleanup) and detailed EBS volume breakdown (State, Attachment Status). | `resources`, `isAuthorized` | `Icons`, `Badge` |
| **FE-CMP::RI::Card** | `frontend/src/components/ri/RIHealthCard.jsx` | Widget | Dashboard widget for RI coverage/waste. | `data` | `api` |
| **FE-CMP::RI::Page** | `frontend/src/components/ri/RIAnalysis.jsx` | Page | Detailed RI Analysis page. | `data` | `api` |
| **FE-CMP::S3::Card** | `frontend/src/components/s3/S3HealthCard.jsx` | Widget | Dashboard widget for S3 optimizations. | `data` | `api` |
| **FE-CMP::S3::Page** | `frontend/src/components/s3/S3Analysis.jsx` | Page | Detailed S3 Analysis page. | `data` | `api` |
| **FE-CMP::RDS::Card** | `frontend/src/components/rds/RDSHealthCard.jsx` | Widget | Dashboard widget for RDS Multi-AZ analysis. | `data` | `api` |
| **FE-CMP::RDS::Page** | `frontend/src/components/rds/RDSAnalysis.jsx` | Page | Detailed RDS Analysis page. | `data` | `api` |
| **FE-CMP::Transfer::Card** | `frontend/src/components/transfer/TransferHealthCard.jsx` | Widget | Dashboard widget for Data Transfer analysis. | `data` | `api` |
| **FE-CMP::Transfer::Page** | `frontend/src/components/transfer/TransferAnalysis.jsx` | Page | Detailed Data Transfer Analysis page. | `data` | `api` |

### 6. Documentation Components

| Component ID | File Path | Category | Description |
| :--- | :--- | :--- | :--- |
| **DOC-INT::FE::Root** | `frontend/INFO.md` | Internal | Frontend architecture overview. |
| **DOC-INT::FE::Src** | `frontend/src/INFO.md` | Internal | Source directory overview. |
| **DOC-INT::FE::Auth** | `frontend/src/components/auth/INFO.md` | Internal | Auth components docs. |
| **DOC-INT::FE::Cluster** | `frontend/src/components/clusters/INFO.md` | Internal | Cluster management docs. |
| **DOC-INT::FE::Dash** | `frontend/src/components/dashboard/INFO.md` | Internal | Dashboard components docs. |
| **DOC-INT::FE::Admin** | `frontend/src/components/admin/INFO.md` | Internal | Admin portal docs. |
| **DOC-INT::FE::Hibernation** | `frontend/src/components/hibernation/INFO.md` | Internal | Hibernation scheduler docs. |
| **DOC-INT::FE::Lab** | `frontend/src/components/lab/INFO.md` | Internal | Lab/Experiment docs. |
| **DOC-INT::FE::Policies** | `frontend/src/components/policies/INFO.md` | Internal | Policy engine docs. |
| **DOC-INT::FE::Settings** | `frontend/src/components/settings/INFO.md` | Internal | Settings components docs. |
| **DOC-INT::FE::Shared** | `frontend/src/components/shared/INFO.md` | Internal | Shared UI library docs. |
| **DOC-INT::FE::Templates** | `frontend/src/components/templates/INFO.md` | Internal | Template builder docs. |
| **DOC-INT::FE::Hooks** | `frontend/src/hooks/INFO.md` | Internal | Custom React hooks docs. |
| **DOC-INT::FE::Services** | `frontend/src/services/INFO.md` | Internal | API service layer docs. |
| **DOC-INT::FE::Audit** | `frontend/src/components/audit/INFO.md` | Internal | Audit log docs. |


### 7. Miscellaneous System Components

| Component ID | File Path | Type | Description |
| :--- | :--- | :--- | :--- |
| **FE-CFG::System::Lock** | `frontend/package-lock.json` | Config | NPM dependency lock file. |
| **FE-CFG::System::GitIgnore** | `frontend/.gitignore` | Config | Git ignore rules for frontend. |
| **FE-ASST::Public::Favicon** | `frontend/public/favicon.ico` | Asset | Browser tab icon. |
| **FE-ASST::Public::Logo** | `frontend/public/logo192.png` | Asset | App logo asset. |

## Orphaned / Zombie Components
These components exist in the codebase but appear to be unused or unreferenced by the main application logic.

| ID | File Path | Status | Reason |
| :--- | :--- | :--- | :--- |
| *None Detected* | - | **Clean** | All source files appear to be in use. |


## Components with Uncertain / Pending Status
These components are fully implemented in Frontend but rely on Backend services that are Mocked, Simplified, or Disconnected.

| ID | File Path | Status | Finding |
| :--- | :--- | :--- | :--- |
| **FE-CMP::Dash::Main** | `frontend/src/components/dashboard/Dashboard.jsx` | **Simplified** | Displays "Savings" based on hardcoded 70% discount assumption (Backend: `MetricsService`). |
| **FE-CMP::Admin::Billing** | `frontend/src/components/admin/AdminBilling.jsx` | **Mocked Data** | Billing plans and history are mocked responses, not real Stripe/AWS data. |
| ~~**FE-CMP::Set::Cloud**~~ | ~~`frontend/src/components/settings/CloudIntegrations.jsx`~~ | ~~**Mocked Logic**~~ | **RESOLVED (2026-01-12)**: Backend `AccountService` now validates AWS STS credentials. Onboarding triggers discovery. |
| **FE-CMP::Set::Account** | `frontend/src/components/settings/AccountSettings.jsx` | **Mocked** | Profile updates (Name, Email) are not permanently persisted to DB (Backend: `SettingsService`). |
| **FE-CMP::RI::Analysis** | `frontend/src/components/ri/RIAnalysis.jsx` | **Partial** | Full visualization of optimization logic requires real Cost Explorer historical data beyond 30 days. |

---

## 🏗️ Core Design Systems (2026-01-19 Update)

### 🎨 Visual Language: "Performance Minimalism"
The frontend has evolved from a generic dashboard to a high-density, performance-oriented UI inspired by CAST AI and modern DevOps tools.
*   **Color Palette**: Shifted to a white-base theme with subtle grays (`bg-gray-50`) to reduce visual fatigue. Use of high-contrast actions (Blue for navigation, Green for savings, Red for critical cleanup).
*   **Typography**: Transitioned to **Inter/System Sans** for maximum readability in data-intensive tables.
*   **Motion**: Strategic use of `framer-motion` for transitions and `recharts` for visualization to make data feel "alive" rather than static.

### 📐 Structural Evolution: Sidebar-First UX
To eliminate horizontal scrolling and improve navigation depth, the platform has moved away from top-level tabs:
1.  **Global Level**: Left-hand sidebar manages primary domains (Clusters, Hygiene, Policies).
2.  **Domain Level**: Nested sidebars (like in `CleanupDashboard`) manage sub-categories and filters, keeping the main content area focused on tables and actions.
3.  **Contextual Actions**: Introduction of **Bulk Action Toolbars** and **Inline Actions** to reduce the number of clicks required for routine cleanup tasks.

### 🔌 API Integration Strategy
*   **Persistence**: Scan results are cached for 1 hour via Redis (Backend) and held in local state (Zustand/React hooks) to ensure zero-latency tab switching.
*   **Real-Time Feedback**: Integration of `react-hot-toast` for immediate execution feedback and animated gauges for live impact analysis.

---

