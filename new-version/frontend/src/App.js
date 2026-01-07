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
import ClusterList from './components/clusters/ClusterList';
import TemplateList from './components/templates/TemplateList';
import PolicyConfig from './components/policies/PolicyConfig';
import HibernationSchedule from './components/hibernation/HibernationSchedule';
import AuditLog from './components/audit/AuditLog';
import AccountSettings from './components/settings/AccountSettings';
import CloudIntegrations from './components/settings/CloudIntegrations';
import ExperimentLab from './components/lab/ExperimentLab';
import AdminDashboard from './components/admin/AdminDashboard';
import AdminClients from './components/admin/AdminClients';
import AdminHealth from './components/admin/AdminHealth';

// Protected Route Component
const ProtectedRoute = ({ children }) => {
  const { isAuthenticated } = useAuthStore();

  if (!isAuthenticated) {
    return <Navigate to="/login" replace />;
  }

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

  return (
    <BrowserRouter>
      <div className="App">
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

          {/* Protected Routes */}
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
            <Route path="templates" element={<TemplateList />} />
            <Route path="policies" element={<PolicyConfig />} />
            <Route path="hibernation" element={<HibernationSchedule />} />
            <Route path="audit" element={<AuditLog />} />
            <Route path="lab" element={<ExperimentLab />} />
            <Route path="settings/account" element={<AccountSettings />} />
            <Route path="settings/integrations" element={<CloudIntegrations />} />

            {/* Admin Routes (SUPER_ADMIN only) */}
            <Route path="admin" element={<AdminRoute><AdminDashboard /></AdminRoute>} />
            <Route path="admin/clients" element={<AdminRoute><AdminClients /></AdminRoute>} />
            <Route path="admin/health" element={<AdminRoute><AdminHealth /></AdminRoute>} />
          </Route>

          {/* Catch All - 404 */}
          <Route path="*" element={<Navigate to="/dashboard" replace />} />
        </Routes>
      </div>
    </BrowserRouter>
  );
}

export default App;
