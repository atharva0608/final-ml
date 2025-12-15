import React, { useState } from 'react';
import { Lock, User, Shield, Mail, Save } from 'lucide-react';
import { BrowserRouter as Router, Routes, Route, Navigate, Outlet } from 'react-router-dom';
import DashboardLayout from './layouts/DashboardLayout';
import LoginPage from './components/LoginPage';
import LiveOperations from './components/LiveOperations';
import NodeFleet, { ClientDetailView, MOCK_CLIENTS } from './components/NodeFleet';
import { DEMO_CLIENT } from './data/mockData';
import Controls from './components/Controls';
import { AuthProvider, useAuth } from './context/AuthContext';
import ModelExperiments from './components/Lab/ModelExperiments';
import SystemMonitor from './pages/SystemMonitor';
import { ModelProvider } from './context/ModelContext';
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
  const { user } = useAuth();
  const [currentView, setCurrentView] = useState('live');
  const [selectedClientId, setSelectedClientId] = useState(null);

  const renderView = () => {
    switch (currentView) {
      case 'live': return <LiveOperations />;
      case 'fleet': return <NodeFleet externalSelectedClientId={selectedClientId} />;
      case 'controls': return <Controls />;
      case 'experiments': return <ModelExperiments />;
      case 'monitor': return <SystemMonitor />;
      case 'profile':
        return (
          <div className="max-w-4xl mx-auto space-y-6 animate-in fade-in slide-in-from-bottom-2 duration-500">
            {/* Admin Details */}
            <div className="bg-white p-8 rounded-xl border border-slate-200 shadow-sm">
              <div className="flex items-center space-x-4 mb-6">
                <div className="w-16 h-16 bg-purple-100 rounded-full flex items-center justify-center text-purple-600">
                  <User className="w-8 h-8" />
                </div>
                <div>
                  <h2 className="text-2xl font-bold text-slate-900">System Administrator</h2>
                  <p className="text-slate-500">Platform Owner</p>
                </div>
              </div>

              <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                <div className="space-y-1">
                  <label className="text-xs font-bold text-slate-500 uppercase tracking-wider">Username</label>
                  <div className="flex items-center px-4 py-2 bg-slate-50 rounded-lg border border-slate-200 text-slate-700">
                    <User className="w-4 h-4 mr-2 text-slate-400" />
                    {user?.username}
                  </div>
                </div>
                <div className="space-y-1">
                  <label className="text-xs font-bold text-slate-500 uppercase tracking-wider">Role</label>
                  <div className="flex items-center px-4 py-2 bg-slate-50 rounded-lg border border-slate-200 text-slate-700">
                    <Shield className="w-4 h-4 mr-2 text-slate-400" />
                    {user?.role}
                  </div>
                </div>
                <div className="space-y-1">
                  <label className="text-xs font-bold text-slate-500 uppercase tracking-wider">Access Level</label>
                  <div className="flex items-center px-4 py-2 bg-slate-50 rounded-lg border border-slate-200 text-slate-700">
                    <Lock className="w-4 h-4 mr-2 text-slate-400" />
                    Root Access
                  </div>
                </div>
              </div>
            </div>

            {/* Admin Password Reset */}
            <div className="bg-white p-8 rounded-xl border border-slate-200 shadow-sm">
              <h2 className="text-xl font-bold text-slate-900 mb-6 flex items-center">
                <Lock className="w-5 h-5 mr-2 text-purple-600" />
                Security Settings
              </h2>

              <form className="max-w-md space-y-4" onSubmit={(e) => { e.preventDefault(); alert("Admin Password update (simulation) successful."); }}>
                <div className="space-y-1">
                  <label className="text-xs font-bold text-slate-500 uppercase tracking-wider">Current Password</label>
                  <input type="password" className="w-full px-4 py-2 border border-slate-200 rounded-lg focus:ring-2 focus:ring-purple-500 outline-none" placeholder="••••••••" />
                </div>
                <div className="space-y-1">
                  <label className="text-xs font-bold text-slate-500 uppercase tracking-wider">New Password</label>
                  <input type="password" className="w-full px-4 py-2 border border-slate-200 rounded-lg focus:ring-2 focus:ring-purple-500 outline-none" placeholder="••••••••" />
                </div>
                <div className="space-y-1">
                  <label className="text-xs font-bold text-slate-500 uppercase tracking-wider">Confirm New Password</label>
                  <input type="password" className="w-full px-4 py-2 border border-slate-200 rounded-lg focus:ring-2 focus:ring-purple-500 outline-none" placeholder="••••••••" />
                </div>

                <div className="pt-4">
                  <button className="flex items-center px-6 py-2 bg-slate-900 text-white font-bold rounded-lg hover:bg-slate-800 transition-colors shadow-lg shadow-slate-200">
                    <Save className="w-4 h-4 mr-2" />
                    Update Password
                  </button>
                </div>
              </form>
            </div>
          </div>
        );
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
  const [currentView, setCurrentView] = useState('live');

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

  const renderView = () => {
    switch (currentView) {
      case 'live':
        return (
          <ClientDetailView
            client={client}
            onBack={() => { }} // Disable back button action
            onSelectCluster={() => { }} // Clusters are just listed in the dashboard tab logic
            isFallbackActive={false} // Default state
          />
        );
      case 'profile':
        return (
          <div className="max-w-4xl mx-auto space-y-6 animate-in fade-in slide-in-from-bottom-2 duration-500">
            {/* User Details */}
            <div className="bg-white p-8 rounded-xl border border-slate-200 shadow-sm">
              <div className="flex items-center space-x-4 mb-6">
                <div className="w-16 h-16 bg-blue-100 rounded-full flex items-center justify-center text-blue-600">
                  <User className="w-8 h-8" />
                </div>
                <div>
                  <h2 className="text-2xl font-bold text-slate-900">{client.name}</h2>
                  <p className="text-slate-500">Client Administrator</p>
                </div>
              </div>

              <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                <div className="space-y-1">
                  <label className="text-xs font-bold text-slate-500 uppercase tracking-wider">Username</label>
                  <div className="flex items-center px-4 py-2 bg-slate-50 rounded-lg border border-slate-200 text-slate-700">
                    <User className="w-4 h-4 mr-2 text-slate-400" />
                    {user?.username}
                  </div>
                </div>
                <div className="space-y-1">
                  <label className="text-xs font-bold text-slate-500 uppercase tracking-wider">Client ID</label>
                  <div className="flex items-center px-4 py-2 bg-slate-50 rounded-lg border border-slate-200 text-slate-700">
                    <Shield className="w-4 h-4 mr-2 text-slate-400" />
                    {user?.clientId}
                  </div>
                </div>
                <div className="space-y-1">
                  <label className="text-xs font-bold text-slate-500 uppercase tracking-wider">Email Support</label>
                  <div className="flex items-center px-4 py-2 bg-slate-50 rounded-lg border border-slate-200 text-slate-700">
                    <Mail className="w-4 h-4 mr-2 text-slate-400" />
                    support@atharva.ai
                  </div>
                </div>
              </div>
            </div>

            {/* Password Reset */}
            <div className="bg-white p-8 rounded-xl border border-slate-200 shadow-sm">
              <h2 className="text-xl font-bold text-slate-900 mb-6 flex items-center">
                <Lock className="w-5 h-5 mr-2 text-blue-600" />
                Security Settings
              </h2>

              <form className="max-w-md space-y-4" onSubmit={(e) => { e.preventDefault(); alert("Password update simulation successful."); }}>
                <div className="space-y-1">
                  <label className="text-xs font-bold text-slate-500 uppercase tracking-wider">Current Password</label>
                  <input type="password" className="w-full px-4 py-2 border border-slate-200 rounded-lg focus:ring-2 focus:ring-blue-500 outline-none" placeholder="••••••••" />
                </div>
                <div className="space-y-1">
                  <label className="text-xs font-bold text-slate-500 uppercase tracking-wider">New Password</label>
                  <input type="password" className="w-full px-4 py-2 border border-slate-200 rounded-lg focus:ring-2 focus:ring-blue-500 outline-none" placeholder="••••••••" />
                </div>
                <div className="space-y-1">
                  <label className="text-xs font-bold text-slate-500 uppercase tracking-wider">Confirm New Password</label>
                  <input type="password" className="w-full px-4 py-2 border border-slate-200 rounded-lg focus:ring-2 focus:ring-blue-500 outline-none" placeholder="••••••••" />
                </div>

                <div className="pt-4">
                  <button className="flex items-center px-6 py-2 bg-slate-900 text-white font-bold rounded-lg hover:bg-slate-800 transition-colors shadow-lg shadow-slate-200">
                    <Save className="w-4 h-4 mr-2" />
                    Update Password
                  </button>
                </div>
              </form>
            </div>
          </div>
        );
      default:
        return null;
    }
  };

  return (
    <DashboardLayout
      activeView={currentView}
      setActiveView={setCurrentView}
      onSelectClient={() => { }}
      selectedClientId={null}
      role="client"
      clientName={client.name}
    >
      {renderView()}
    </DashboardLayout>
  );
};

function App() {
  return (
    <AuthProvider>
      <ModelProvider>
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

            <Route path="*" element={<Navigate to="/" />} />
          </Routes>
        </Router>
      </ModelProvider>
    </AuthProvider>
  );
}

export default App;
