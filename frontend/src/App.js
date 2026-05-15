/**
 * App Component
 *
 * Main application with routing and authentication
 */
import React from 'react';
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { Toaster } from 'react-hot-toast';
import { useAuthStore } from './store/useStore';

// Layouts
import MainLayout from './components/layout/MainLayout';

// Auth Pages
import Login from './components/auth/Login';
import Signup from './components/auth/Signup';

// Main Pages
import Dashboard from './components/dashboard/Dashboard';
import Overview from './pages/overview/Overview';
import Onboarding from './pages/Onboarding';
import ClusterList from './pages/infrastructure/clusters/Clusters';
import PolicyConfig from './components/policies/PolicyConfig';
import { HibernationDashboard } from './pages/infrastructure/hibernation';

import AuditLog from './components/audit/AuditLog';
import Settings from './components/settings/Settings';
import AdminDashboard from './components/admin/AdminDashboard';
import AdminClients from './components/admin/AdminClients';
import AdminHealth from './components/admin/AdminHealth';
import AdminExperiments from './components/admin/AdminExperiments';
import AdminConfig from './components/admin/AdminConfig';
import AdminBilling from './components/admin/AdminBilling';
import AdminOrganizations from './components/admin/AdminOrganizations';
import ScalingActivity from './pages/execution/ScalingActivity';
import NodeActivity from './pages/execution/NodeActivity';
import EventTimeline from './pages/execution/EventTimeline';
import ActiveActions from './pages/execution/ActiveActions';
import NodeSelector from './pages/optimize/nodes/NodeSelector';
import NodeScaling from './pages/optimize/nodes/NodeScaling';
import NodeBinPacking from './pages/optimize/nodes/NodeBinPacking';
import WorkloadProfiling from './pages/optimize/workloads/WorkloadProfiling';
import WorkloadPlacement from './pages/optimize/workloads/WorkloadPlacement';
import WorkloadScaling from './pages/optimize/workloads/WorkloadScaling';
import WorkloadMigration from './pages/optimize/workloads/WorkloadMigration';
import Karpenter from './pages/infrastructure/provisioning/Karpenter';
import NodePool from './pages/infrastructure/provisioning/NodePool';
import KarpenterStatus from './pages/infrastructure/integrations/KarpenterStatus';
import KedaStatus from './pages/infrastructure/integrations/KedaStatus';
import CleanupDashboard from './components/cleanup/CleanupDashboard';
import GovernanceSettings from './components/settings/GovernanceSettings';
import TagPoliciesManager from './components/settings/TagPoliciesManager';

import Teams from './pages/governance/Teams';
import TeamDetails from './pages/governance/TeamDetails';
import Roles from './pages/governance/Roles';
import InviteAcceptance from './components/auth/InviteAcceptance';
import RIAnalysis from './components/ri/RIAnalysis';
import S3Analysis from './components/s3/S3Analysis';
import RDSAnalysis from './components/rds/RDSAnalysis';
import TransferAnalysis from './components/transfer/TransferAnalysis';
import AccountAnalytics from './pages/cost/AccountAnalytics';
import Approvals from './pages/governance/Approvals';
import TicketRequestModal from './components/approvals/TicketRequestModal';
import PermissionGate from './components/governance/PermissionGate';
import NodeTemplates from './pages/infrastructure/provisioning/NodeTemplates';
import VolatilityMonitor from './components/ascpai/VolatilityMonitor';
import ErrorBoundary from './components/shared/ErrorBoundary';
import CostSavings from './pages/cost/CostSavings';
import StorageTransfer from './pages/cost/StorageTransfer';
import Integrations from './pages/infrastructure/Integrations';

// Protected Route Component
const ProtectedRoute = ({ children }) => {
  const { isAuthenticated, user } = useAuthStore();

  console.log("ProtectedRoute Check - User:", user); // DEBUG: Check user status for redirect

  if (!isAuthenticated) {
    return <Navigate to="/login" replace />;
  }

  // NOTE: PENDING_INVITE users will see modal on Dashboard instead of redirect

  return children;
};

// Public Route Component (redirect if authenticated)
const PublicRoute = ({ children }) => {
  const { isAuthenticated, user } = useAuthStore();

  if (isAuthenticated) {
    // Redirect SUPER_ADMIN to admin dashboard
    if (user?.role === 'SUPER_ADMIN' || user?.role === 'super_admin') {
      return <Navigate to="/admin" replace />;
    }
    // Redirect regular users to dashboard
    return <Navigate to="/dashboard" replace />;
  }

  return children;
};

// Admin Route Component (require SUPER_ADMIN role)
const AdminRoute = ({ children }) => {
  const { isAuthenticated, user } = useAuthStore();

  if (!isAuthenticated) {
    return <Navigate to="/login" replace />;
  }

  // Check if user has SUPER_ADMIN role (handles both cases: SUPER_ADMIN and super_admin)
  const isSuperAdmin = user?.role === 'SUPER_ADMIN' || user?.role === 'super_admin';

  if (!isSuperAdmin) {
    // Redirect non-admin users back to overview
    return <Navigate to="/overview" replace />;
  }

  return children;
};

function App() {
  const { accessToken, logout } = useAuthStore();

  // Validate token on app mount - auto logout if token is expired/invalid
  React.useEffect(() => {
    if (accessToken) {
      try {
        // Decode JWT payload
        const payload = JSON.parse(atob(accessToken.split('.')[1]));

        // Debug logging
        console.log('Token validation:', {
          exp: payload.exp,
          expDate: new Date(payload.exp * 1000).toISOString(),
          now: new Date().toISOString(),
          isExpired: payload.exp * 1000 < Date.now()
        });

        // Check if token is expired (with 5 second buffer to prevent edge cases)
        const isExpired = payload.exp * 1000 < (Date.now() - 5000);

        if (isExpired) {
          console.log('Token expired, logging out...');
          logout();
        }
      } catch (error) {
        // Token is malformed or invalid - log but don't auto-logout on parse errors
        console.error('Token validation error:', error);
        // Only logout if token is completely invalid (not just a parse error during login)
        if (!accessToken.includes('.')) {
          console.log('Invalid token format, logging out...');
          logout();
        }
      }
    }
  }, []); // Only run once on mount, not on every accessToken change

  const [governanceModalOpen, setGovernanceModalOpen] = React.useState(false);
  const [governanceData, setGovernanceData] = React.useState(null);

  React.useEffect(() => {
    const handleGovernanceRequired = (event) => {
      setGovernanceData(event.detail);
      setGovernanceModalOpen(true);
    };

    window.addEventListener('governance:required', handleGovernanceRequired);
    return () => window.removeEventListener('governance:required', handleGovernanceRequired);
  }, []);

  return (
    <BrowserRouter>
      {/* VolatilityMonitor runs above the router so its lifecycle is independent
          of layout rendering and route changes (Gap 18 fix). ErrorBoundary ensures
          a crash here never affects the rest of the application. */}
      <ErrorBoundary label="VolatilityMonitor">
        <VolatilityMonitor />
      </ErrorBoundary>
      <div className="App">
        <TicketRequestModal
          isOpen={governanceModalOpen}
          onClose={() => setGovernanceModalOpen(false)}
          initialData={governanceData}
        />
        <Toaster
          position="top-right"
          toastOptions={{
            duration: 4000,
            style: {
              background: '#363636',
              color: '#fff',
            },
            success: {
              duration: 3000,
              iconTheme: {
                primary: '#10b981',
                secondary: '#fff',
              },
            },
            error: {
              duration: 4000,
              iconTheme: {
                primary: '#ef4444',
                secondary: '#fff',
              },
            },
          }}
        />

        <Routes>
          {/* Public Routes */}
          <Route
            path="/login"
            element={
              <PublicRoute>
                <Login />
              </PublicRoute>
            }
          />
          <Route
            path="/signup"
            element={
              <PublicRoute>
                <Signup />
              </PublicRoute>
            }
          />

          {/* Invitation Acceptance Route */}
          <Route
            path="/invite-acceptance"
            element={
              <ProtectedRoute>
                <InviteAcceptance />
              </ProtectedRoute>
            }
          />

          {/* Protected Routes */}
          <Route
            path="/onboarding"
            element={
              <ProtectedRoute>
                <Onboarding />
              </ProtectedRoute>
            }
          />

          <Route
            path="/"
            element={
              <ProtectedRoute>
                <MainLayout />
              </ProtectedRoute>
            }
          >
            <Route index element={<Navigate to="/overview" replace />} />
            {/* Overview */}
            <Route path="overview" element={<Overview />} />

            {/* Optimize -> Nodes */}
            <Route path="optimize/nodes/selection" element={<NodeSelector />} />
            <Route path="optimize/nodes/bin-packing" element={<NodeBinPacking />} />

            {/* Optimize -> Workloads */}
            <Route path="optimize/workloads/profiling" element={<WorkloadProfiling />} />
            <Route path="optimize/workloads/placement" element={<WorkloadPlacement />} />
            <Route path="optimize/workloads/scaling" element={<WorkloadScaling />} />
            <Route path="optimize/workloads/migration" element={<WorkloadMigration />} />

            {/* Execution */}
            <Route path="execution/active-actions" element={<ActiveActions />} />
            <Route path="execution/timeline" element={<EventTimeline />} />

            {/* Cost */}
            <Route path="cost/overview" element={<AccountAnalytics />} />
            <Route path="cost/savings" element={<CostSavings />} />
            <Route path="cost/ri" element={<RIAnalysis />} />
            <Route path="cost/hygiene" element={
              <PermissionGate
                featureId="hygiene:view"
                sectionName="Resource Hygiene"
                sectionDescription="View and clean up wasted cloud resources"
              >
                <CleanupDashboard />
              </PermissionGate>
            } />
            <Route path="cost/storage-transfer" element={<StorageTransfer />} />

            {/* Infrastructure */}
            <Route path="infrastructure/clusters" element={
              <PermissionGate
                featureId="compute:view"
                sectionName="Clusters"
                sectionDescription="View and manage your AWS clusters and compute resources"
              >
                <ClusterList />
              </PermissionGate>
            } />
            <Route path="infrastructure/hibernation" element={
              <PermissionGate
                featureId="hibernation:view"
                sectionName="Hibernation Schedule"
                sectionDescription="Manage cluster hibernation schedules"
              >
                <HibernationDashboard />
              </PermissionGate>
            } />
            <Route path="infrastructure/integrations" element={<Integrations />} />

            {/* Governance */}
            <Route path="governance/policies" element={
              <PermissionGate
                featureId="policy:manage"
                sectionName="Policies"
                sectionDescription="Create and manage optimization policies"
              >
                <PolicyConfig />
              </PermissionGate>
            } />
            <Route path="governance/approvals" element={<Approvals />} />
            <Route path="governance/tag-rules" element={
              <PermissionGate
                featureId="policy:manage"
                sectionName="Tagging Policies"
                sectionDescription="Manage resource tagging policies"
              >
                <TagPoliciesManager />
              </PermissionGate>
            } />
            <Route path="governance/teams" element={
              <PermissionGate
                featureId="team:view"
                sectionName="Teams"
                sectionDescription="View and manage teams and team members"
              >
                <Teams />
              </PermissionGate>
            } />

            {/* Settings */}
            <Route path="settings" element={<Settings />} />

            {/* Hidden / Secondary Routes */}
            <Route path="governance/teams/:teamId" element={
              <PermissionGate
                featureId="team:view"
                sectionName="Team Details"
                sectionDescription="View team details and members"
              >
                <TeamDetails />
              </PermissionGate>
            } />
            <Route path="governance/roles" element={
              <PermissionGate
                featureId="team:manage_roles"
                sectionName="Roles & Permissions"
                sectionDescription="Manage roles and assign permissions"
              >
                <Roles />
              </PermissionGate>
            } />
            <Route path="settings/automation" element={
              <PermissionGate
                featureId="policy:manage"
                sectionName="Automation Settings"
                sectionDescription="Configure system-wide automation and approval controls"
              >
                <GovernanceSettings />
              </PermissionGate>
            } />
            <Route path="settings/audit" element={
              <PermissionGate
                featureId="audit:view"
                sectionName="Audit Logs"
                sectionDescription="View system audit logs and compliance reports"
              >
                <AuditLog />
              </PermissionGate>
            } />
            <Route path="infrastructure/node-templates" element={
              <PermissionGate
                featureId="compute:view"
                sectionName="Node Templates"
                sectionDescription="Define instance type criteria for optimization"
              >
                <NodeTemplates />
              </PermissionGate>
            } />


            {/* Admin Routes (SUPER_ADMIN only) */}
            <Route path="admin" element={<AdminRoute><AdminDashboard /></AdminRoute>} />
            <Route path="admin/clients" element={<AdminRoute><AdminClients /></AdminRoute>} />
            <Route path="admin/health" element={<AdminRoute><AdminHealth /></AdminRoute>} />
            <Route path="admin/experiments" element={<AdminRoute><AdminExperiments /></AdminRoute>} />
            <Route path="admin/config" element={<AdminRoute><AdminConfig /></AdminRoute>} />
            <Route path="admin/organizations" element={<AdminRoute><AdminOrganizations /></AdminRoute>} />
            <Route path="admin/billing" element={<AdminRoute><AdminBilling /></AdminRoute>} />
          </Route>

          {/* Catch All - 404 */}
          <Route path="*" element={<Navigate to="/overview" replace />} />
        </Routes>
      </div>
    </BrowserRouter>
  );
}

export default App;
