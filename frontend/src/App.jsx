import React, { useState, useEffect } from 'react';
import { Lock, User, Shield, Mail, Save, AlertCircle } from 'lucide-react';
import { BrowserRouter as Router, Routes, Route, Navigate, Outlet } from 'react-router-dom';
import DashboardLayout from './layouts/DashboardLayout';
import LoginPage from './components/LoginPage';
import LiveOperations from './components/LiveOperations';
import NodeFleet from './components/NodeFleet';
import Controls from './components/Controls';
import ClientSetup from './components/ClientSetup';
import ClientManagement from './components/ClientManagement';
import { AuthProvider, useAuth } from './context/AuthContext';
import ModelExperiments from './components/Lab/ModelExperiments';
import SystemMonitor from './pages/SystemMonitor';
import { ModelProvider } from './context/ModelContext';
import api from './services/api';
import './App.css';

// Protected Route Component
const ProtectedRoute = ({ allowedRoles }) => {
  const { user } = useAuth();

  if (!user) {
    return <Navigate to="/login" replace />;
  }

  if (allowedRoles && !allowedRoles.includes(user.role)) {
    return user.role === 'admin' ? <Navigate to="/" /> : <Navigate to="/client" />;
  }

  return <Outlet />;
};

// Admin Dashboard Component
const AdminDashboard = () => {
  const { user } = useAuth();
  const [currentView, setCurrentView] = useState('live');
  const [selectedClientId, setSelectedClientId] = useState(null);

  const renderView = () => {
    switch (currentView) {
      case 'live':
        return <LiveOperations />;
      case 'fleet':
        return <NodeFleet externalSelectedClientId={selectedClientId} />;
      case 'controls':
        return <Controls />;
      case 'experiments':
        return <ModelExperiments />;
      case 'monitor':
        return <SystemMonitor />;
      case 'onboarding':
        return <ClientSetup />;
      case 'clients':
        return <ClientManagement />;
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
              </div>
            </div>

            {/* Password Reset */}
            <div className="bg-white p-8 rounded-xl border border-slate-200 shadow-sm">
              <h2 className="text-xl font-bold text-slate-900 mb-6 flex items-center">
                <Lock className="w-5 h-5 mr-2 text-purple-600" />
                Security Settings
              </h2>

              <form className="max-w-md space-y-4" onSubmit={(e) => { e.preventDefault(); alert("Password update feature coming soon"); }}>
                <div className="space-y-1">
                  <label className="text-xs font-bold text-slate-500 uppercase tracking-wider">Current Password</label>
                  <input type="password" className="w-full px-4 py-2 border border-slate-200 rounded-lg focus:ring-2 focus:ring-purple-500 outline-none" placeholder="••••••••" />
                </div>
                <div className="space-y-1">
                  <label className="text-xs font-bold text-slate-500 uppercase tracking-wider">New Password</label>
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
      default:
        return <LiveOperations />;
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

// Client Dashboard Component
const ClientDashboard = () => {
  const { user } = useAuth();
  const [currentView, setCurrentView] = useState('live');
  const [clientData, setClientData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  // Fetch client-specific data
  useEffect(() => {
    const fetchClientData = async () => {
      try {
        setLoading(true);
        setError(null);
        const data = await api.getClientDashboard();
        setClientData(data);
      } catch (err) {
        console.error('Error fetching client data:', err);
        setError(err.message || 'Failed to load client data');
      } finally {
        setLoading(false);
      }
    };

    fetchClientData();
    const interval = setInterval(fetchClientData, 60000); // Refresh every minute
    return () => clearInterval(interval);
  }, []);

  const renderView = () => {
    if (loading) {
      return (
        <div className="flex items-center justify-center h-96">
          <div className="text-center">
            <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-600 mx-auto mb-4"></div>
            <p className="text-slate-600">Loading your dashboard...</p>
          </div>
        </div>
      );
    }

    if (error) {
      return (
        <div className="max-w-2xl mx-auto mt-12">
          <div className="bg-red-50 border border-red-200 rounded-xl p-8 text-center">
            <AlertCircle className="w-16 h-16 text-red-500 mx-auto mb-4" />
            <h3 className="text-xl font-bold text-red-900 mb-2">Unable to Load Dashboard</h3>
            <p className="text-red-700 mb-4">{error}</p>
            <button
              onClick={() => window.location.reload()}
              className="px-6 py-2 bg-red-600 text-white rounded-lg hover:bg-red-700 transition-colors"
            >
              Retry
            </button>
          </div>
        </div>
      );
    }

    switch (currentView) {
      case 'live':
        return <LiveOperations clientMode={true} clientData={clientData} />;
      case 'profile':
        return (
          <div className="max-w-4xl mx-auto space-y-6 animate-in fade-in slide-in-from-bottom-2 duration-500">
            {/* Client Details */}
            <div className="bg-white p-8 rounded-xl border border-slate-200 shadow-sm">
              <div className="flex items-center space-x-4 mb-6">
                <div className="w-16 h-16 bg-blue-100 rounded-full flex items-center justify-center text-blue-600">
                  <User className="w-8 h-8" />
                </div>
                <div>
                  <h2 className="text-2xl font-bold text-slate-900">{clientData?.name || 'Client'}</h2>
                  <p className="text-slate-500">Client Account</p>
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
                  <label className="text-xs font-bold text-slate-500 uppercase tracking-wider">Account Type</label>
                  <div className="flex items-center px-4 py-2 bg-slate-50 rounded-lg border border-slate-200 text-slate-700">
                    <Shield className="w-4 h-4 mr-2 text-slate-400" />
                    {user?.role}
                  </div>
                </div>
                <div className="space-y-1">
                  <label className="text-xs font-bold text-slate-500 uppercase tracking-wider">Email Support</label>
                  <div className="flex items-center px-4 py-2 bg-slate-50 rounded-lg border border-slate-200 text-slate-700">
                    <Mail className="w-4 h-4 mr-2 text-slate-400" />
                    support@cloudoptimizer.ai
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

              <form className="max-w-md space-y-4" onSubmit={(e) => { e.preventDefault(); alert("Password update feature coming soon"); }}>
                <div className="space-y-1">
                  <label className="text-xs font-bold text-slate-500 uppercase tracking-wider">Current Password</label>
                  <input type="password" className="w-full px-4 py-2 border border-slate-200 rounded-lg focus:ring-2 focus:ring-blue-500 outline-none" placeholder="••••••••" />
                </div>
                <div className="space-y-1">
                  <label className="text-xs font-bold text-slate-500 uppercase tracking-wider">New Password</label>
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
        return <LiveOperations clientMode={true} clientData={clientData} />;
    }
  };

  return (
    <DashboardLayout
      activeView={currentView}
      setActiveView={setCurrentView}
      onSelectClient={() => {}}
      selectedClientId={null}
      role="client"
      clientName={clientData?.name || 'Client'}
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
            <Route element={<ProtectedRoute allowedRoles={['client']} />}>
              <Route path="/client" element={<ClientDashboard />} />
            </Route>

            <Route path="*" element={<Navigate to="/" />} />
          </Routes>
        </Router>
      </ModelProvider>
    </AuthProvider>
  );
}

export default App;
