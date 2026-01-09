# 🎨 Frontend Component Catalog

| ID (Unique Tracking Code) | File Path | Type | Function / Feature Description | State / Props Used | Dependencies (Imports) |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **FE-APP::Main::Entry** | `frontend/src/index.js` | App | React application entry point. | `ReactDOM`, `App` | `react-dom` |
| **FE-APP::Main::Root** | `frontend/src/App.js` | App | Main Router and Layout configuration. | `RouterProvider` | `react-router-dom` |
| **FE-CFG::System::Pkg** | `frontend/package.json` | Config | NPM dependencies and scripts. | `N/A` | `N/A` |
| **FE-CFG::System::Tailwind** | `frontend/tailwind.config.js` | Config | Tailwind CSS configuration. | `N/A` | `tailwindcss` |
| **FE-CFG::System::PostCSS** | `frontend/postcss.config.js` | Config | PostCSS configuration. | `N/A` | `postcss` |
| **FE-CFG::System::Env** | `frontend/.env.example` | Config | Frontend environment template. | `N/A` | `N/A` |
| **FE-CMP::Auth::Login** | `frontend/src/components/auth/Login.jsx` | Page | User Login form. | `email`, `password` | `useAuth`, `Input`, `Button` |
| **FE-CMP::Auth::Signup** | `frontend/src/components/auth/Signup.jsx` | Page | User Signup form. | `email`, `password` | `useAuth`, `Input`, `Button` |
| **FE-CMP::Dash::Main** | `frontend/src/components/dashboard/Dashboard.jsx` | Page | Main KPI Dashboard (Backend Simplified: 70% savings assumption). | `kpiStats` | `StatsCard`, `recharts` |
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
| **FE-CMP::Admin::Dash** | `frontend/src/components/admin/AdminDashboard.jsx` | Admin | Super Admin Overview. Fetches real stats/charts from adminAPI. | `stats`, `activityFeed` | `StatsCard`, `recharts` |
| **FE-CMP::Admin::Orgs** | `frontend/src/components/admin/AdminOrganizations.jsx` | Admin | Organization management table. | `orgs` | `adminAPI` |
| **FE-CMP::Admin::Clients** | `frontend/src/components/admin/AdminClients.jsx` | Admin | Client management table. | `clients` | `adminAPI` |
| **FE-CMP::Admin::Billing** | `src/components/admin/AdminBilling.jsx` | Page | Billing overview and Plans (Backend Mocked Data). | `stats`, `plans` | `Card`, `Button`, `Icons` |
| **FE-CMP::Admin::Health** | `frontend/src/components/admin/AdminHealth.jsx` | Admin | System health status. | `health` | `useDashboard` |
| **FE-CMP::Admin::Config** | `frontend/src/components/admin/AdminConfig.jsx` | Admin | Platform configuration. | `config` | `adminAPI` |
| **FE-CMP::Admin::Lab** | `frontend/src/components/admin/AdminLab.jsx` | Admin | Admin view for Lab experiments. | `experiments` | `labAPI` |
| **FE-CMP::Set::Main** | `frontend/src/components/settings/Settings.jsx` | Page | User Settings wrapper. | `tab` | `AccountSettings`, `TeamManagement` |
| **FE-CMP::Set::Account** | `frontend/src/components/settings/AccountSettings.jsx` | Component | User profile settings (Backend Mocked). | `userData` | `authAPI` |
| **FE-CMP::Set::Teams** | `frontend/src/components/settings/TeamManagement.jsx` | Component | Team member management. | `members` | `organizationAPI` |
| **FE-CMP::Set::Cloud** | `frontend/src/components/settings/CloudIntegrations.jsx` | Component | Cloud credentials management (Backend Mocked Logic). | `accounts` | `accountAPI` |
| **FE-LIB::UI::Button** | `frontend/src/components/shared/Button.jsx` | UI | Reusable Button. | `onClick` | `N/A` |
| **FE-LIB::UI::Card** | `frontend/src/components/shared/Card.jsx` | UI | Reusable Card. | `children` | `N/A` |
| **FE-LIB::UI::Input** | `frontend/src/components/shared/Input.jsx` | UI | Reusable Input. | `onChange` | `N/A` |
| **FE-LIB::UI::Badge** | `frontend/src/components/shared/Badge.jsx` | UI | Status Badge. | `status` | `N/A` |
| **FE-LIB::UI::StatsCard** | `frontend/src/components/shared/StatsCard.jsx` | UI | Dashboard Metric Card. | `title`, `value` | `N/A` |
| **FE-LIB::UI::EmptyState** | `frontend/src/components/shared/EmptyState.jsx` | UI | Empty state placeholder for no-data scenarios. | `title`, `message`, `action` | `FiInbox` |
| **FE-HK::Auth::UseAuth** | `frontend/src/hooks/useAuth.js` | Hook | Authentication logic hook. | `user` | `authAPI` |
| **FE-HK::Dash::UseDash** | `frontend/src/hooks/useDashboard.js` | Hook | Dashboard data fetching hook. | `data` | `metricsAPI` |
| **FE-SVC::API::Client** | `frontend/src/services/api.js`| Service | Central Axios instance and API method definitions. | `axios` | `axios` |
| **FE-STR::Store::Global** | `frontend/src/store/useStore.js` | Store | Global State (Zustand). | `state` | `zustand` |
| **FE-UTL::Fmt::Format** | `frontend/src/utils/formatters.js` | Utility | Currency/Date formatters. | `value` | `Intl` |
| **FE-APP::Style::Global** | `frontend/src/index.css` | Style | Global CSS styles. | `N/A` | `N/A` |
| **FE-LIB::UI::Index** | `frontend/src/components/shared/index.js` | UI | Export barrel for shared components. | `N/A` | `N/A` |
| **FE-CMP::Onboard::Page** | `frontend/src/pages/Onboarding.jsx` | Page | Wrapper page for the onboarding flow. | `step` | `WelcomeStep`, `ConnectStep` |
| **FE-CMP::Onboard::Welcome** | `frontend/src/components/onboarding/WelcomeStep.jsx` | Component | Onboarding Step 1: Welcome. | `onNext` | `Button` |
| **FE-CMP::Onboard::Connect** | `frontend/src/components/onboarding/ConnectStep.jsx` | Component | Onboarding Step 2: AWS Connect. | `onNext`, `onBack` | `Input`, `Button` |
| **FE-CMP::Onboard::Verify** | `frontend/src/components/onboarding/VerifyStep.jsx` | Component | Onboarding Step 3: Verify Role. | `roleArn` | `onboardingAPI` |
| **FE-CMP::Onboard::Success** | `frontend/src/components/onboarding/SuccessStep.jsx` | Component | Onboarding Step 4: Success. | `onComplete` | `Button` |
