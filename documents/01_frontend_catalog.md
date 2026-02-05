# 🎨 Frontend Component Catalog

| ID (Unique Tracking Code) | File Path | Type | Function / Feature Description | State / Props Used | Dependencies (Imports) |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **FE-APP::Main::Entry** | `frontend/src/index.js` | App | React application entry point. | `ReactDOM`, `App` | `react-dom` |
| **FE-APP::Main::Root** | `frontend/src/App.js` | App | Main router and layout configuration. | `BrowserRouter`, `Routes` | `react-router-dom` |
| **FE-CFG::System::Pkg** | `frontend/package.json` | Config | NPM dependencies and scripts. | `N/A` | `N/A` |
| **FE-CFG::System::Tailwind** | `frontend/tailwind.config.js` | Config | Tailwind CSS configuration. | `N/A` | `tailwindcss` |
| **FE-CFG::System::PostCSS** | `frontend/postcss.config.js` | Config | PostCSS configuration. | `N/A` | `postcss` |
| **FE-CFG::System::Env** | `frontend/.env.example` | Config | Frontend environment template. | `N/A` | `N/A` |
| **FE-ASST::Public::HTML** | `frontend/public/index.html` | Asset | Main HTML entry point. | `N/A` | `N/A` |
| **FE-ASST::Public::Manifest** | `frontend/public/manifest.json` | Asset | PWA Manifest file. | `N/A` | `N/A` |
| **FE-CMP::Auth::Login** | `frontend/src/components/auth/Login.jsx` | Page | User Login form. | `email`, `password` | `useAuth`, `Input`, `Button` |
| **FE-CMP::Auth::Signup** | `frontend/src/components/auth/Signup.jsx` | Page | User Signup form. | `email`, `password` | `useAuth`, `Input`, `Button` |
| **FE-CMP::Auth::Invite** | `frontend/src/components/auth/InviteAcceptance.jsx` | Page | Invitation acceptance/decline flow for pending invites. | `loading`, `user` | `authAPI`, `useAuthStore`, `framer-motion` |
| **FE-CMP::Dash::Main** | `frontend/src/components/dashboard/Dashboard.jsx` | Page | Main KPI dashboard with role-based widgets, customization drawer, and JIT access request modal. Shows Connect AWS notice when no accounts and user is not SUPER_ADMIN. | `dashboardKPIs`, `costTimeSeries`, `activeLayout` | `useDashboard`, `widgetRegistry`, `roleDefaults`, `AccessRequestModal` |
| **FE-CMP::Dash::Widget::CostKPI** | `frontend/src/components/dashboard/widgets/CostKPICard.jsx` | Widget | Cost KPI summary card. | `data` | `formatters`, `react-icons` |
| **FE-CMP::Dash::Widget::SavingsKPI** | `frontend/src/components/dashboard/widgets/SavingsKPICard.jsx` | Widget | Savings KPI summary card. | `data` | `formatters`, `react-icons` |
| **FE-CMP::Dash::Widget::SavingsChart** | `frontend/src/components/dashboard/widgets/SavingsChart.jsx` | Widget | Savings trend bar chart. | `data` | `recharts`, `react-icons` |
| **FE-CMP::Dash::Widget::FleetComposition** | `frontend/src/components/dashboard/widgets/FleetComposition.jsx` | Widget | Fleet composition pie chart. | `data` | `recharts`, `react-icons` |
| **FE-CMP::Dash::Widget::ActivityFeed** | `frontend/src/components/dashboard/widgets/ActivityFeed.jsx` | Widget | Recent activity feed list. | `data` | `formatters`, `react-icons` |
| **FE-CMP::Dash::Widget::ClusterHealth** | `frontend/src/components/dashboard/widgets/ClusterHealthCard.jsx` | Widget | Cluster health status summary. | `data` | `react-icons` |
| **FE-CMP::Dash::Widget::PendingApprovals** | `frontend/src/components/dashboard/widgets/PendingApprovalsCard.jsx` | Widget | Pending approvals summary. | `data` | `react-icons` |
| **FE-CMP::Dash::Widget::PlatformHealth** | `frontend/src/components/dashboard/widgets/PlatformHealthCard.jsx` | Widget | Platform health rollup. | `data` | `react-icons` |
| **FE-CMP::Dash::Widget::TenantList** | `frontend/src/components/dashboard/widgets/TenantListCard.jsx` | Widget | Tenant list summary (super admin). | `data` | `react-icons` |
| **FE-CFG::Dash::Registry** | `frontend/src/components/dashboard/widgetRegistry.js` | Config | **NEW (2026-01-16)**: Widget Registry mapping keys to React components. Central registry for dynamic dashboard rendering. | N/A | Widget components |
| **FE-CFG::Dash::Defaults** | `frontend/src/components/dashboard/roleDefaults.js` | Config | **NEW (2026-01-16)**: Role-based default dashboard layouts. Defines which widgets each role sees by default. | N/A | N/A |
| **FE-CMP::Layout::Main** | `frontend/src/components/layout/MainLayout.jsx` | Layout | Sidebar, Header, and Wrapper. | `children` | `Sidebar`, `Header` |
| **FE-CMP::Cluster::List** | `frontend/src/components/clusters/ClusterList.jsx` | Page | List of K8s clusters. | `clusters` | `useClusterStore` |
| **FE-CMP::Cluster::Detail** | `frontend/src/components/clusters/ClusterDetails.jsx` | Page | Cluster details view. | `cluster` | `clusterAPI` |
| **FE-CMP::Cluster::Nodes** | `frontend/src/components/clusters/NodeList.jsx` | Component | Node list within a cluster (table + status badges). | `nodes` | `clusterAPI`, `Card`, `Badge` |
| **FE-CMP::Cluster::Disconnect** | `frontend/src/components/clusters/ClusterDisconnectModal.jsx` | Component | Confirmation modal for disconnecting clusters (name confirmation + optional node deletion). | `isOpen`, `cluster`, `deleteNodes` | `react-icons` |
| **FE-CMP::Tpl::List** | `frontend/src/components/templates/TemplateList.jsx` | Page | Node Template management list. | `templates` | `templateAPI` |
| **FE-CMP::Tpl::Builder** | `frontend/src/components/templates/TemplateBuilder.jsx` | Component | Form to create/edit templates. | `formData` | `Input`, `Select` |
| **FE-CMP::Pol::Config** | `frontend/src/components/policies/PolicyConfig.jsx` | Page | Optimization policy settings. | `policy` | `policyAPI` |
| **FE-CMP::Pol::TagTemplates** | `frontend/src/components/policies/TagTemplateManager.jsx` | Component | Legacy tag template manager (CRUD for tag presets; unused). | `templates`, `formData` | `tagTemplateAPI`, `Card`, `Input`, `Button` |
| **FE-CMP::Pol::Cleanup** | `frontend/src/components/policies/CleanupPolicies.jsx` | Page | **NEW (2026-01-20)**: Dynamic Cleanup Policy Manager. Rule Builder UI for creating JSON-based cleanup conditions (Age, Tags). Integrated via `CleanupDashboard`. | `policies` | `cleanupAPI` |
| **FE-CMP::Hiber::Sched** | `frontend/src/components/hibernation/HibernationSchedule.jsx` | Page | Hibernation scheduler UI. | `schedule` | `hibernationAPI` |
| **FE-CMP::Lab::Main** | `frontend/src/components/lab/ExperimentLab.jsx` | Page | ML Experimentation dashboard. | `experiments` | `labAPI` |
| **FE-CMP::Right::Main** | `frontend/src/components/right-sizing/RightSizing.jsx` | Page | Rightsizing recommendations. | `recommendations` | `Card` |
| **FE-CMP::Audit::Log** | `frontend/src/components/audit/AuditLog.jsx` | Page | System Audit Log viewer. | `logs` | `auditAPI` |
| **FE-CMP::Admin::Dash** | `frontend/src/components/admin/AdminDashboard.jsx` | Admin | **Super Admin Command Center**. **SIMPLIFIED (2026-01-19)**: No tabs, directly renders `AdminOverview`. All admin sections accessible via sidebar. | `-` | `AdminOverview` |
| **FE-CMP::Admin::Overview** | `frontend/src/components/admin/AdminOverview.jsx` | Admin | **Real**: Platform HUD. Displays Total MRR, Active Users (Real Count), Cluster Stats, and **Live Activity Feed** (Audit Logs). | `stats`, `activity` | `adminAPI`, `StatsCard` |
| **FE-CMP::Admin::Orgs** | `frontend/src/components/admin/AdminOrganizations.jsx` | Admin | Organization management table. **FIXED (2026-01-19)**: Added missing state variables, fetchOrganizations logic, and corrected response parsing (`response.data.organizations` instead of `.items`). | `organizations`, `searchQuery`, `page` | `adminAPI` |
| **FE-CMP::Admin::Clients** | `frontend/src/components/admin/AdminClients.jsx` | Admin | Client management table. | `clients` | `adminAPI` |
| **FE-CMP::Admin::Billing** | `frontend/src/components/admin/AdminBilling.jsx` | Page | Billing overview and plans (API-backed; falls back to placeholder values when data is missing). | `billingData` | `adminAPI`, `Card`, `Button` |
| **FE-CMP::Admin::Health** | `frontend/src/components/admin/AdminHealth.jsx` | Admin | System health status and diagnostics. | `health`, `loading` | `api`, `Card`, `Badge`, `formatters` |
| **FE-CMP::Admin::Config** | `frontend/src/components/admin/AdminConfig.jsx` | Admin | **Real**: Platform configuration with Safe Mode toggle (API connected). | `safeMode`, `config` | `adminAPI`, `PlatformSettings` |
| **FE-CMP::Admin::Platform** | `frontend/src/components/admin/PlatformSettings.jsx` | Admin | **Real**: Platform AWS Identity management with STS verification. | `connected`, `formData` | `adminAPI`, `toast` |
| **FE-CMP::Admin::Lab** | `frontend/src/components/admin/AdminLab.jsx` | Admin | Admin view for Lab experiments. | `experiments` | `labAPI` |
| **FE-CMP::Set::Main** | `frontend/src/components/settings/Settings.jsx` | Page | Tabbed settings for Account, Cloud Integrations, and Billing (Billing tab is local UI stub). | `activeTab` | `AccountSettings`, `CloudIntegrations`, `Card`, `Button` |
| **FE-CMP::Set::Account** | `frontend/src/components/settings/AccountSettings.jsx` | Component | Account profile, password change, and local preference controls. | `passwordData`, `preferences` | `authAPI`, `Card`, `Input`, `Button` |
| **FE-CMP::Set::Cloud** | `frontend/src/components/settings/CloudIntegrations.jsx` | Component | AWS account linking/validation and external ID management. | `accounts`, `formData`, `connectionInfo` | `accountAPI`, `authService`, `Card`, `Button`, `Input`, `Badge` |
| **FE-CMP::Set::Teams** | `frontend/src/components/settings/TeamManagement.jsx` | Component | **Real**: 4-Tier Role Management (Super Admin, Org Admin, Team Lead, Member). Accordion view for hierarchical team/member management. **Team-Specific Governance** integration via collapsible "Configure Approval Policies" section. | `teams`, `members`, `showGovernanceForTeam` | `teamAPI`, `TeamGovernance` |
| **FE-CMP::Set::TeamForm** | `frontend/src/components/settings/TeamFormModal.jsx` | Component | Team create/rename modal (currently unused). | `name` | `Button` |
| **FE-CMP::Set::Profile** | `frontend/src/components/settings/UserProfile.jsx` | Component | **New**: User Profile settings (Full Name update). | `user` | `userAPI` |
| **FE-CMP::Set::TeamGov** | `frontend/src/components/settings/TeamGovernance.jsx` | Component | **Real**: Team-Specific Approval Policies UI. Toggle switches for 5 actions (CONNECT_ACCOUNT, TERMINATE_INSTANCE, DELETE_VOLUME, DELETE_SNAPSHOT, RELEASE_IP). Fetches/saves to `PUT /teams/{id}/governance`. | `config`, `teamId` | `teamAPI`, `toast` |
| **FE-CMP::Set::MemberPerms** | `frontend/src/components/settings/MemberPermissionsModal.jsx` | Component | **NEW (2026-01-19)**: Modal for managing granular team member permission overrides. Displays toggles for predefined permissions (allow_termination, allow_cleanup, view_audit_logs, etc.). Saves via `PUT /teams/{team_id}/members/{member_id}/permissions`. | `member`, `permissions` | `teamAPI`, `Button` |
| **FE-CMP::Set::PermMat** | `frontend/src/components/policies/PermissionMatrix.jsx` | Component | **Real**: Interactive matrix for editing Role permissions. Used in TeamManagement. | `roles` | `rolesAPI` |
| **FE-CMP::Team::Details** | `frontend/src/pages/TeamDetails.jsx` | Page | **Real**: Comprehensive Team Dashboard. **Consolidated View**: Top Spenders Leaderboard, Waste Breakdown (Pie Chart), Cost Trends (Area Chart). **Member Details**: Accordion list of members and connected accounts. **Governance**: Integrated Policy settings. | `teamId` | `metricsAPI`, `teamAPI`, `recharts` |
| **FE-CMP::Account::Analytics** | `frontend/src/pages/AccountAnalytics.jsx` | Page | **Real**: Detailed Account Analytics view. Shows cost breakdown, usage trends, and optimization opportunities for a specific AWS account. | `accountId` | `metricsAPI` |
| **FE-CMP::Gov::Settings** | `frontend/src/components/settings/GovernanceSettings.jsx` | Page | **Real**: Automated Governance / Policy-as-Code settings. Master toggle, policy cards, required tags configuration. | `config`, `policies` | `governanceAPI`, `toast` |
| **FE-CMP::Ticket::Center** | `frontend/src/pages/TicketCenter.jsx` | Page | **Real (JIT, Audited 2026-01-14)**: Role-based ticket management with real API data. Admin: Stats cards, "Pending Requests" + "Active Grants" tabs. Team Lead: Incoming/Outgoing/Team Access. Member: My Requests. Includes `CLIENT` role support. Real timestamps, expiry countdown. | `tickets`, `activeTab`, `loading` | `ticketsAPI`, `date-fns`, `format` |
| **FE-CMP::Ticket::Modal** | `frontend/src/components/tickets/TicketRequestModal.jsx` | Component | **Real (JIT)**: Role-adaptive access request/grant modal. Admin: Grant Mode (pick recipients). Team Lead: Toggle between Grant/Request. Member: Request Only. Gradient header, duration slider, recipient selection with role badges. | `isGrantMode`, `members` | `organizationAPI`, `ticketsAPI` |
| **FE-CMP::Ticket::AccessModal** | `frontend/src/components/tickets/AccessRequestModal.jsx` | Component | JIT access request modal for restricted actions. | `reason`, `duration`, `loading` | `api`, `Button`, `toast` |
| **FE-CMP::Ticket::Banner** | `frontend/src/components/tickets/ActiveWindowBanner.jsx` | Component | **Real (JIT)**: Active access window countdown banner. Shows remaining time for approved access grants. | `activeWindow` | `ticketsAPI`, `date-fns` |
| **FE-PG::Team::Main** | `frontend/src/pages/Teams.jsx` | Page | **Real (RBAC Fixed 2026-01-14)**: Tabbed view for Team Structure and Roles & Policies. **RBAC Enforced**: Roles tab is HIDDEN from MEMBER and TEAM_LEAD. Only ORG_ADMIN, SUPER_ADMIN, CLIENT can see/access Roles. Uses `useAuthStore` for role check. | `activeTab`, `user` | `TeamManagement`, `Roles`, `useAuthStore` |
| **FE-PG::Roles::Main** | `frontend/src/pages/Roles.jsx` | Page | **Real (RBAC)**: Role management page. Lists all roles as cards. Click to edit permissions via `PermissionMatrix`. System roles (ORG_ADMIN, CLIENT) are read-only to prevent lockout. | `roles`, `editingRole` | `rolesAPI`, `PermissionMatrix` |
| **FE-CMP::Tag::PoliciesMgr** | `frontend/src/components/settings/TagPoliciesManager.jsx` | Component | Unified tabbed view for governance tag policies and tag templates. | `activeTab` | `TagPoliciesList`, `TagTemplateManager` |
| **FE-CMP::Tag::PoliciesList** | `frontend/src/components/settings/TagPoliciesList.jsx` | Component | CRUD UI for tag enforcement policies (required/advisory, allowed values, regex, scope). | `policies`, `formData`, `editingPolicy` | `api`, `toast` |
| **FE-CMP::Tag::Templates** | `frontend/src/components/settings/TagTemplateManager.jsx` | Component | CRUD UI for tag templates with dynamic variables and resource scope. | `templates`, `formData` | `api`, `toast` |
| **FE-CMP::Gov::Manager** | `frontend/src/components/settings/GovernanceManager.jsx` | Component | Unified governance hub for cleanup rules, tag policies, and tag templates (used in Cleanup). | `activeTab` | `CleanupPolicies`, `TagPoliciesList`, `TagTemplateManager` |
| **FE-LIB::UI::Card** | `frontend/src/components/shared/Card.jsx` | UI | Reusable Card. | `children` | `N/A` |
| **FE-LIB::UI::Input** | `frontend/src/components/shared/Input.jsx` | UI | Reusable Input. | `onChange` | `N/A` |
| **FE-LIB::UI::Button** | `frontend/src/components/shared/Button.jsx` | UI | Reusable button with variants, sizes, and loading state. | `variant`, `size`, `loading` | `framer-motion` |
| **FE-LIB::UI::Dropdown** | `frontend/src/components/shared/Dropdown.jsx` | UI | Click/ellipsis dropdown menu with outside-click close. | `items`, `align` | `react-icons` |
| **FE-LIB::UI::Badge** | `frontend/src/components/shared/Badge.jsx` | UI | Status Badge. | `status` | `N/A` |
| **FE-LIB::UI::StatsCard** | `frontend/src/components/shared/StatsCard.jsx` | UI | Dashboard Metric Card. | `title`, `value` | `N/A` |
| **FE-LIB::UI::GaugeChart** | `frontend/src/components/shared/GaugeChart.jsx` | UI | Animated Semi-Circular Gauge for metrics. | `value`, `maxValue` | `useEffect` |
| **FE-LIB::UI::EmptyState** | `frontend/src/components/shared/EmptyState.jsx` | UI | Empty state placeholder for no-data scenarios. | `title`, `message`, `action` | `FiInbox` |
| **FE-LIB::UI::Switch** | `frontend/src/components/shared/Switch.jsx` | UI | Reusable Toggle Switch. | `checked`, `onChange` | `N/A` |
| **FE-HK::Auth::UseAuth** | `frontend/src/hooks/useAuth.js` | Hook | Authentication logic hook. | `user` | `authAPI` |
| **FE-HK::Dash::UseDash** | `frontend/src/hooks/useDashboard.js` | Hook | Dashboard data fetching hook. | `data` | `metricsAPI` |
| **FE-SVC::API::Client** | `frontend/src/services/api.js` | Service | Central Axios instance and API method definitions. Includes `ticketsAPI` for JIT Ticket System (create, grantAccess, approve, revoke, acceptGrant, rejectGrant, list, getActiveWindow). | `axios` | `axios` |
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
| **FE-CMP::Cleanup::BulkTagWizard** | `frontend/src/components/cleanup/BulkTagWizard.jsx` | Modal | Multi-step bulk tagging wizard (template/manual, variable inputs, collision handling). | `step`, `selectedResources`, `mode` | `api`, `toast`, `react-icons` |
| **FE-CMP::Cleanup::InlineTagEditor** | `frontend/src/components/cleanup/InlineTagEditor.jsx` | Component | Inline tag editor for a single resource (unused). | `resource`, `tags` | `api`, `toast` |
| **FE-CMP::Cleanup::BulkTagEditor** | `frontend/src/components/cleanup/BulkTagEditor.jsx` | Component | Legacy bulk tag editor modal (unused). | `resources`, `mode` | `api`, `toast` |
| **FE-CMP::Cleanup::Wizard::RI** | `frontend/src/components/cleanup/wizards/RIWizard.jsx` | Modal | Multi-step Reserved Instance optimization wizard. | `step`, `selectedResources` | `Button`, `react-icons` |
| **FE-CMP::Cleanup::Wizard::S3** | `frontend/src/components/cleanup/wizards/S3Wizard.jsx` | Modal | Multi-step S3 lifecycle optimization wizard. | `step`, `selectedResources` | `Button`, `react-icons` |
| **FE-CMP::Cleanup::Wizard::RDS** | `frontend/src/components/cleanup/wizards/RDSWizard.jsx` | Modal | Multi-step RDS Multi-AZ optimization wizard. | `step`, `selectedResources` | `Button`, `react-icons` |
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
| **DOC-INT::FE::Components** | `frontend/src/components/INFO.md` | Internal | Components directory overview. |
| **DOC-INT::FE::Auth** | `frontend/src/components/auth/INFO.md` | Internal | Auth components docs. |
| **DOC-INT::FE::Cluster** | `frontend/src/components/clusters/INFO.md` | Internal | Cluster management docs. |
| **DOC-INT::FE::Dash** | `frontend/src/components/dashboard/INFO.md` | Internal | Dashboard components docs. |
| **DOC-INT::FE::Admin** | `frontend/src/components/admin/INFO.md` | Internal | Admin portal docs. |
| **DOC-INT::FE::Hibernation** | `frontend/src/components/hibernation/INFO.md` | Internal | Hibernation scheduler docs. |
| **DOC-INT::FE::Policies** | `frontend/src/components/policies/INFO.md` | Internal | Policy engine docs. |
| **DOC-INT::FE::Settings** | `frontend/src/components/settings/INFO.md` | Internal | Settings components docs. |
| **DOC-INT::FE::Templates** | `frontend/src/components/templates/INFO.md` | Internal | Template builder docs. |
| **DOC-INT::FE::Hooks** | `frontend/src/hooks/INFO.md` | Internal | Custom React hooks docs. |
| **DOC-INT::FE::Services** | `frontend/src/services/INFO.md` | Internal | API service layer docs. |
| **DOC-INT::FE::Audit** | `frontend/src/components/audit/INFO.md` | Internal | Audit log docs. |
| **DOC-INT::FE::Utils** | `frontend/src/utils/INFO.md` | Internal | Utilities docs. |


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
| **FE-CMP::Cleanup::InlineTagEditor** | `frontend/src/components/cleanup/InlineTagEditor.jsx` | **Unused** | No imports/references found in frontend/src. |
| **FE-CMP::Cleanup::BulkTagEditor** | `frontend/src/components/cleanup/BulkTagEditor.jsx` | **Unused** | Legacy bulk tag editor superseded by `BulkTagWizard`. |
| **FE-CMP::Pol::TagTemplates** | `frontend/src/components/policies/TagTemplateManager.jsx` | **Unused** | Legacy tag template manager; no imports found. |
| **FE-CMP::Set::TeamForm** | `frontend/src/components/settings/TeamFormModal.jsx` | **Unused** | No imports/references found in frontend/src. |


## Components with Uncertain / Pending Status
These components are fully implemented in Frontend but rely on Backend services that are Mocked, Simplified, or Disconnected.

| ID | File Path | Status | Finding |
| :--- | :--- | :--- | :--- |
| **FE-CMP::Admin::Billing** | `frontend/src/components/admin/AdminBilling.jsx` | **Partial** | Uses `adminAPI.getBilling`; UI falls back to placeholder stats/plans when backend returns empty. |
| **FE-CMP::Set::Account** | `frontend/src/components/settings/AccountSettings.jsx` | **Partial** | Password change is real, but preference changes are stored in localStorage (no backend persistence). |
| **FE-CMP::RI::Analysis** | `frontend/src/components/ri/RIAnalysis.jsx` | **Partial** | Full visualization of optimization logic requires real Cost Explorer historical data beyond 30 days. |

---

## 🏗️ Core Design Systems (2026-01-19 Update)

### 🎨 Visual Language: "Performance Minimalism"
The frontend has evolved from a generic dashboard to a high-density, performance-oriented UI inspired by CAST AI and modern DevOps tools.
*   **Color Palette**: Shifted to a white-base theme with subtle grays (`bg-gray-50`) to reduce visual fatigue. Use of high-contrast actions (Blue for navigation, Green for savings, Red for critical cleanup).
*   **Typography**: Uses the system UI font stack (`-apple-system`, `Segoe UI`, `Roboto`, etc.) for readable, neutral data tables.
*   **Motion**: Strategic use of `framer-motion` for transitions and `recharts` for visualization to make data feel "alive" rather than static.

### 📐 Structural Evolution: Sidebar-First UX
To eliminate horizontal scrolling and improve navigation depth, the platform has moved away from top-level tabs:
1.  **Global Level**: Left-hand sidebar manages primary domains (Clusters, Hygiene, Policies).
2.  **Domain Level**: Nested sidebars (like in `CleanupDashboard`) manage sub-categories and filters, keeping the main content area focused on tables and actions.
3.  **Contextual Actions**: Introduction of **Bulk Action Toolbars** and **Inline Actions** to reduce the number of clicks required for routine cleanup tasks.

### 🔌 API Integration Strategy
*   **Persistence**: Scan results are held in component state for fast tab switching and UI responsiveness.
*   **Real-Time Feedback**: Integration of `react-hot-toast` for immediate execution feedback and animated gauges for live impact analysis.

---
