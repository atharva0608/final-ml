import React, { useState, useEffect, useCallback } from 'react';
import AdminSidebar from './components/layout/AdminSidebar';
import AdminHeader from './components/layout/AdminHeader';
import AdminOverview from './pages/AdminOverview';
import AllClientsPage from './pages/AllClientsPage';
import AllAgentsPage from './pages/AllAgentsPage';
import AllInstancesPage from './pages/AllInstancesPage';
import GlobalSavingsPage from './pages/GlobalSavingsPage';
import ActivityLogPage from './pages/ActivityLogPage';
import SystemHealthPage from './pages/SystemHealthPage';
import ClientDetailView from './components/details/ClientDetailView';
import api from './services/api';

const App = () => {
  const [activePage, setActivePage] = useState('overview');
  const [selectedClientId, setSelectedClientId] = useState(null);
  const [clients, setClients] = useState([]);
  const [stats, setStats] = useState(null);
  const [systemHealth, setSystemHealth] = useState(null);
  const [lastRefresh, setLastRefresh] = useState(null);
  const [sidebarOpen, setSidebarOpen] = useState(false);

  const loadData = useCallback(async () => {
    try {
      const [clientsData, statsData, healthData] = await Promise.all([
        api.getAllClients(),
        api.getGlobalStats(),
        api.getSystemHealth()
      ]);
      setClients(clientsData);
      setStats(statsData);
      setSystemHealth(healthData);
      setLastRefresh(new Date().toISOString());
    } catch (error) {
      console.error('Failed to load data:', error);
    }
  }, []);

  useEffect(() => {
    loadData();
    const interval = setInterval(loadData, 60000);
    return () => clearInterval(interval);
  }, [loadData]);

  const handleSelectClient = (clientId) => {
    setSelectedClientId(clientId);
    setActivePage('client-detail');
    setSidebarOpen(false);
  };

  const handleBackToOverview = () => {
    setSelectedClientId(null);
    setActivePage('overview');
  };

  const handlePageChange = (page) => {
    setActivePage(page);
    setSelectedClientId(null);
  };

  return (
    <div className="min-h-screen bg-gray-50">
      {/* Sidebar */}
      <AdminSidebar
        clients={clients}
        onSelectClient={handleSelectClient}
        activeClientId={selectedClientId}
        onSelectPage={handlePageChange}
        activePage={activePage}
        isOpen={sidebarOpen}
        onClose={() => setSidebarOpen(false)}
        systemHealth={systemHealth}
      />

      {/* Main Content Area */}
      <div className="lg:ml-72 min-h-screen">
        {/* Header */}
        <AdminHeader
          stats={stats}
          onRefresh={loadData}
          lastRefresh={lastRefresh}
          onMenuToggle={() => setSidebarOpen(true)}
        />

        {/* Page Content */}
        <main className="p-4 md:p-6">
          {activePage === 'overview' && <AdminOverview />}
          {activePage === 'clients' && <AllClientsPage onSelectClient={handleSelectClient} />}
          {activePage === 'agents' && <AllAgentsPage />}
          {activePage === 'instances' && <AllInstancesPage />}
          {activePage === 'savings' && <GlobalSavingsPage />}
          {activePage === 'activity' && <ActivityLogPage />}
          {activePage === 'health' && <SystemHealthPage />}
          {activePage === 'client-detail' && selectedClientId && (
            <ClientDetailView
              clientId={selectedClientId}
              onBack={handleBackToOverview}
            />
          )}
        </main>
      </div>
    </div>
  );
};

export default App;
