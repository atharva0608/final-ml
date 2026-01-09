# 🎨 Frontend Component Catalog

| ID (Unique Tracking Code) | File Path | Type | Function / Feature Description | State / Props Used | Dependencies (Imports) |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **FE-CMP::AdminDashboard::Main** | `src/components/admin/AdminDashboard.jsx` | Page | Main "Command Center" view. Shows global KPIs, Savings Chart, and Live Activity Feed. | `kpiStats`, `activityFeed` | `StatsCard`, `Card`, `recharts` |
| **FE-CMP::AdminClients::Main** | `src/components/admin/AdminClients.jsx` | Page | Client Management Interface. Lists clients with search, filter, and actions. | `clients`, `loading`, `searchQuery`, `statusFilter` | `adminAPI`, `Card`, `Button`, `Table`, `Badge` |
| **FE-CMP::AdminClients::DetailModal** | `src/components/admin/AdminClients.jsx` | Sub-CMP | Modal showing deep profile stats for a client (Resource Usage, Cost). | `selectedClient`, `showDetailModal` | `Card`, `Badge` |
| **FE-CMP::AdminClients::PasswordReset** | `src/components/admin/AdminClients.jsx` | Sub-CMP | Modal to force reset a client's password. | `showResetPasswordModal`, `newPassword` | `adminAPI.resetPassword` |
| **FE-CMP::AdminBilling::Main** | `src/components/admin/AdminBilling.jsx` | Page | Billing overview and Plan configuration. Currently uses mock data. | None (Static) | `Card`, `Button`, `Icons` |
| **FE-CMP::AdminConfig::Main** | `src/components/admin/AdminConfig.jsx` | Page | System Configuration. Controls "Safe Mode" and Global Risk Parameters. | `safeMode`, `agentVersion` | `Card`, `Button`, `ToggleSwitch` |
| **FE-CMP::AdminHealth::Main** | `src/components/admin/AdminHealth.jsx` | Page | Real-time system health monitoring (API, DB, Redis, Queue). Auto-refreshes. | `health`, `autoRefresh`, `loading` | `Card`, `Badge`, `Charts` |
| **FE-CMP::AdminLab::Main** | `src/components/admin/AdminLab.jsx` | Page | AI Model Registry and Risk Map visualization. | None (Static List) | `Card`, `Button` |
| **FE-CMP::AdminOrganizations::Main** | `src/components/admin/AdminOrganizations.jsx` | Page | Organization Management. List, Search, and Filter Organizations. | `organizations`, `loading`, `searchQuery` | `adminAPI`, `FiBriefcase` |
| **FE-CMP::AdminOrganizations::DetailModal** | `src/components/admin/AdminOrganizations.jsx` | Sub-CMP | Modal showing organization statistics, owner info, and clusters. | `selectedOrg` | `Modal Structure` |
| **FE-CMP::Login::Main** | `src/components/auth/Login.jsx` | Page | User Login Form. Handles authentication and error display. | `email`, `password`, `loading`, `errors` | `useAuth`, `Input`, `Button` |
| **FE-CMP::Signup::Main** | `src/components/auth/Signup.jsx` | Page | User Registration Form. Includes Organization Name and password validation. | `email`, `pkgName`, `password` | `useAuth`, `Input`, `Button` |
| **FE-CMP::Onboarding::Welcome** | `src/components/onboarding/WelcomeStep.jsx` | Sub-CMP | Step 0 of Onboarding. Marketing/Intro screen. | None (Stateless) | `Button`, `FramerMotion` |
| **FE-CMP::Onboarding::Connect** | `src/components/onboarding/ConnectStep.jsx` | Sub-CMP | Step 1 of Onboarding. AWS CloudFormation Launch & Verification. | `awsLink`, `roleArn`, `verifying` | `onboardingAPI`, `Button` |
| **FE-CMP::Onboarding::Verify** | `src/components/onboarding/VerifyStep.jsx` | Sub-CMP | Intermediate loading state for verification. Auto-advances. | None | `useEffect`, `setTimeout` |
| **FE-CMP::Onboarding::Success** | `src/components/onboarding/SuccessStep.jsx` | Sub-CMP | Step 2 (Final). Success message and redirect to dashboard. | None | `Confetti`, `Button` |
| **FE-CMP::ClusterList::Main** | `src/components/clusters/ClusterList.jsx` | Page | Displays all K8s clusters. KPI cards for cost/nodes. Connect button. | `clusters`, `kpiData`, `loading` | `useClusterStore`, `Recharts` |
| **FE-CMP::ClusterDetails::Main** | `src/components/clusters/ClusterDetails.jsx` | Sub-CMP | Detailed view of a single cluster. Metrics, Policy, Schedule. | `cluster`, `metrics`, `policy` | `clusterAPI`, `metricsAPI` |
| **FE-CMP::ClusterConnect::Modal** | `src/components/clusters/ClusterConnectModal.jsx` | Sub-CMP | Wizard to connect a new cluster (Agent script or AWS IAM). | `step`, `provider`, `roleArn` | `clusterAPI`, `Toast` |
| **FE-CMP::Settings::Main** | `src/components/settings/Settings.jsx` | Page | Settings Hub. Tab navigation for Account, Team, Cloud, Billing. | `activeTab`, `canManageTeam` | `AccountSettings`, `CloudIntegrations`, `TeamManagement` |
| **FE-CMP::Settings::Account** | `src/components/settings/AccountSettings.jsx` | Sub-CMP | Profile management, Password change, Preferences (Timezone, Alerts). | `passwordData`, `preferences` | `useAuthStore`, `authAPI` |
| **FE-CMP::Settings::Cloud** | `src/components/settings/CloudIntegrations.jsx` | Sub-CMP | AWS Account Linkage. List, Add, Validate, Delete AWS Accounts. | `accounts`, `formData` | `accountAPI` |
| **FE-CMP::Settings::Team** | `src/components/settings/TeamManagement.jsx` | Sub-CMP | User Management. List members, Invite users, Manage roles. | `members`, `inviteEmail` | `organizationAPI` |
| **FE-CMP::TemplateList::Main** | `src/components/templates/TemplateList.jsx` | Page | Node Template Management. List, Create, Set Default, Delete. | `templates`, `showCreateModal` | `useTemplateStore`, `templateAPI` |
| **FE-CMP::TemplateBuilder::Main** | `src/components/templates/TemplateBuilder.jsx` | Sub-CMP | Complex form builder for Node Templates (Compute, Storage, Network, K8s). | `formData`, `activeTab` | `Input`, `Select` |
| **FE-LOGIC::Store::Main** | `src/store/useStore.js` | Store | Global State (Zustand). Auth, Clusters, Templates, Policies, Metrics, UI. | `useAuthStore`, `useClusterStore`, etc. | `zustand`, `persist` |
| **FE-LOGIC::Hooks::useAuth** | `src/hooks/useAuth.js` | Hook | Auth Wrapper. Login, Signup, Logout, Token Management. | `user`, `isAuthenticated` | `useAuthStore`, `authAPI` |
| **FE-LOGIC::Services::API** | `src/services/api.js`| Service | Central Axios instance and API method definitions. | `authAPI`, `clusterAPI`, etc. | `axios` |
