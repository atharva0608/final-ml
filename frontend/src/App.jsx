import React, { useState } from 'react';
import { BrowserRouter as Router, Routes, Route, Navigate, Outlet } from 'react-router-dom';
import DashboardLayout from './layouts/DashboardLayout';
import LoginPage from './components/LoginPage';
import LiveOperations from './components/LiveOperations';
import NodeFleet, { ClientDetailView, MOCK_CLIENTS } from './components/NodeFleet';
import { DEMO_CLIENT } from './data/mockData';
import Controls from './components/Controls';
import SandboxDashboard from './components/Sandbox/SandboxDashboard';
import { AuthProvider, useAuth } from './context/AuthContext';
import './App.css';

// Protected Route Component
const ProtectedRoute = ({ allowedRoles }) => {
  const { user } = useAuth();

  if (!user) {
    return <Navigate to="/login" replace />;
  }

  if (allowedRoles && !allowedRoles.includes(user.role)) {
    // Redirect based on role if they try to access unauthorized route
    return user.role === 'admin' ? <Navigate to="/" /> : <Navigate to="/client" />;
  }

  return <Outlet />;
};

// Admin Dashboard Component (Encapsulates Admin State)
const AdminDashboard = () => {
  const [currentView, setCurrentView] = useState('live');
  const [selectedClientId, setSelectedClientId] = useState(null);

  const renderView = () => {
    switch (currentView) {
      case 'live': return <LiveOperations />;
      case 'fleet': return <NodeFleet externalSelectedClientId={selectedClientId} />;
      case 'controls': return <Controls />;
      default: return <LiveOperations />;
    }
  };

  return (
    <DashboardLayout
      activeView={currentView}
      setActiveView={setCurrentView}
      onSelectClient={setSelectedClientId}
      selectedClientId={selectedClientId}
    >
      {renderView()}
    </DashboardLayout>
  );
};

// Wrapper to inject data for the Client View
const ClientViewWrapper = () => {
  const { user } = useAuth();

  // Combine all known clients
  const allClients = [...MOCK_CLIENTS, DEMO_CLIENT];

  // Find the client assigned to the logged-in user
  const client = allClients.find(c => c.id === user?.clientId);

  if (!client) return (
    <div className="flex items-center justify-center min-h-screen text-slate-500">
      <div className="text-center">
        <h3 className="text-lg font-bold text-slate-900">Client Configuration Not Found</h3>
        <p className="text-sm text-slate-400 mt-2">User: {user?.username} ({user?.clientId})</p>
      </div>
    </div>
  );

  // We pass no-op for onBack to prevent them from going to the master list
  return (
    <div className="min-h-screen w-full bg-slate-50 p-8">
      <div className="max-w-7xl mx-auto">
        <ClientDetailView
          client={client}
          onBack={() => { }} // Disable back button action
          onSelectCluster={() => { }} // Clusters are just listed in the dashboard tab logic
          isFallbackActive={false} // Default state
        />
      </div>
    </div>
  );
};

function App() {
  return (
    <AuthProvider>
      <Router>
        <Routes>
          <Route path="/login" element={<LoginPage />} />

          {/* Admin Routes */}
          <Route element={<ProtectedRoute allowedRoles={['admin']} />}>
            <Route path="/" element={<AdminDashboard />} />
          </Route>

          {/* Client Routes */}
          <Route element={<ProtectedRoute allowedRoles={['client', 'admin']} />}>
            {/* Admin can see client view too for debugging, or restrict to client only */}
            <Route path="/client" element={<ClientViewWrapper />} />
          </Route>

          {/* Sandbox Route - Full Screen, Independent */}
          <Route path="/sandbox" element={<SandboxDashboard />} />

          <Route path="*" element={<Navigate to="/" />} />
        </Routes>
      </Router>
    </AuthProvider>
  );
}

export default App;
