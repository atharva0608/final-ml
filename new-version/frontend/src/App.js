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
  const { isAuthenticated } = useAuthStore();

  if (isAuthenticated) {
    return <Navigate to="/dashboard" replace />;
  }

  return children;
};

function App() {
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

            {/* Placeholder routes for other features */}
            <Route path="templates" element={<div className="text-2xl font-bold text-gray-900">Templates - Coming Soon</div>} />
            <Route path="policies" element={<div className="text-2xl font-bold text-gray-900">Policies - Coming Soon</div>} />
            <Route path="hibernation" element={<div className="text-2xl font-bold text-gray-900">Hibernation - Coming Soon</div>} />
            <Route path="metrics" element={<div className="text-2xl font-bold text-gray-900">Metrics - Coming Soon</div>} />
            <Route path="lab" element={<div className="text-2xl font-bold text-gray-900">Lab Experiments - Coming Soon</div>} />
            <Route path="admin" element={<div className="text-2xl font-bold text-gray-900">Admin Portal - Coming Soon</div>} />
            <Route path="settings" element={<div className="text-2xl font-bold text-gray-900">Settings - Coming Soon</div>} />
          </Route>

          {/* Catch All - 404 */}
          <Route path="*" element={<Navigate to="/dashboard" replace />} />
        </Routes>
      </div>
    </BrowserRouter>
  );
}

export default App;
