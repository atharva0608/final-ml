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
import Onboarding from './pages/Onboarding';
import ClusterList from './components/clusters/ClusterList';
import TemplateList from './components/templates/TemplateList';
import PolicyConfig from './components/policies/PolicyConfig';
import HibernationSchedule from './components/hibernation/HibernationSchedule';
import AuditLog from './components/audit/AuditLog';
import Settings from './components/settings/Settings';
import ExperimentLab from './components/lab/ExperimentLab';
import AdminDashboard from './components/admin/AdminDashboard';
import AdminClients from './components/admin/AdminClients';
import AdminHealth from './components/admin/AdminHealth';
import AdminExperiments from './components/admin/AdminExperiments';
import AdminConfig from './components/admin/AdminConfig';
import AdminBilling from './components/admin/AdminBilling';
import AdminOrganizations from './components/admin/AdminOrganizations';
import RightSizing from './components/right-sizing/RightSizing';
import CleanupDashboard from './components/cleanup/CleanupDashboard';
import GovernanceSettings from './components/settings/GovernanceSettings';
import TagPoliciesManager from './components/settings/TagPoliciesManager';
import TagTemplateManager from './components/settings/TagTemplateManager';

import Teams from './pages/Teams';
import TeamDetails from './pages/TeamDetails';
import Roles from './pages/Roles';
import InviteAcceptance from './components/auth/InviteAcceptance';
import RIAnalysis from './components/ri/RIAnalysis';
import S3Analysis from './components/s3/S3Analysis';
import RDSAnalysis from './components/rds/RDSAnalysis';
import TransferAnalysis from './components/transfer/TransferAnalysis';
import AccountAnalytics from './pages/AccountAnalytics';
import Approvals from './pages/Approvals';
import TicketRequestModal from './components/approvals/TicketRequestModal';

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
    // Redirect non-admin users back to dashboard
    return <Navigate to="/dashboard" replace />;
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
        // Check if token is expired
        const isExpired = payload.exp * 1000 < Date.now();
        if (isExpired) {
          console.log('Token expired, logging out...');
          logout();
        }
      } catch (error) {
        // Token is malformed or invalid
        console.log('Invalid token, logging out...');
        logout();
      }
    }
  }, [accessToken, logout]);

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
            <Route index element={<Navigate to="/dashboard" replace />} />
            <Route path="dashboard" element={<Dashboard />} />
            <Route path="clusters" element={<ClusterList />} />
            <Route path="policies" element={<PolicyConfig />} />
            <Route path="templates" element={<TemplateList />} />
            <Route path="right-sizing" element={<RightSizing />} />
            <Route path="hibernation" element={<HibernationSchedule />} />
            <Route path="audit" element={<AuditLog />} />
            <Route path="hygiene" element={<CleanupDashboard />} />
            <Route path="approvals" element={<Approvals />} />
            <Route path="settings" element={<Settings />} />
            <Route path="settings/governance" element={<GovernanceSettings />} />
            <Route path="tagging-policies" element={<TagPoliciesManager />} />
            <Route path="tag-templates" element={<TagTemplateManager />} />

            <Route path="teams" element={<Teams />} />
            <Route path="teams/:teamId" element={<TeamDetails />} />
            <Route path="roles" element={<Roles />} />
            <Route path="accounts/:accountId/analytics" element={<AccountAnalytics />} />
            <Route path="ri-analysis" element={<RIAnalysis />} />
            <Route path="s3-analysis" element={<S3Analysis />} />
            <Route path="rds-analysis" element={<RDSAnalysis />} />
            <Route path="transfer-analysis" element={<TransferAnalysis />} />

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
          <Route path="*" element={<Navigate to="/dashboard" replace />} />
        </Routes>
      </div>
    </BrowserRouter>
  );
}

export default App;
