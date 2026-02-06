/**
 * Main Layout Component
 *
 * Layout with sidebar navigation and header
 */
import React, { useState, useEffect } from 'react';
import { Outlet, Link, useNavigate, useLocation } from 'react-router-dom';
import { useAuth } from '../../hooks/useAuth';
import { clusterAPI } from '../../services/api';
import { Button } from '../shared';
import { FiHome, FiServer, FiFileText, FiSettings, FiTarget, FiClock, FiBarChart2, FiUsers, FiActivity, FiLogOut, FiClipboard, FiBriefcase, FiCheckSquare, FiShield, FiLock, FiTag } from 'react-icons/fi';

import ActiveWindowBanner from '../tickets/ActiveWindowBanner';

// Cluster Notification Badge Component
const ClusterBadge = () => {
  const [clusterStats, setClusterStats] = useState({ discovered: 0, errors: 0, potentialSavings: 0 });

  useEffect(() => {
    const fetchStats = async () => {
      try {
        const res = await clusterAPI.list({});
        const clusters = res.data?.clusters || [];
        const discovered = clusters.filter(c => c.status === 'DISCOVERED').length;
        const errors = clusters.filter(c => c.status === 'ERROR').length;
        const potentialSavings = clusters
          .filter(c => c.status === 'DISCOVERED')
          .reduce((sum, c) => sum + (c.potential_savings_monthly || c.estimated_savings || 0), 0);
        setClusterStats({ discovered, errors, potentialSavings });
      } catch (e) {
        console.error('Failed to fetch cluster stats for badge', e);
      }
    };
    fetchStats();
    const interval = setInterval(fetchStats, 30000); // Refresh every 30s
    return () => clearInterval(interval);
  }, []);

  if (clusterStats.errors > 0) {
    return (
      <span
        className="ml-auto bg-red-500 text-white text-[10px] font-bold px-1.5 py-0.5 rounded-full min-w-[18px] text-center"
        title={`${clusterStats.errors} clusters with errors`}
      >
        {clusterStats.errors}
      </span>
    );
  }

  if (clusterStats.discovered > 0) {
    return (
      <span
        className="ml-auto bg-blue-500 text-white text-[10px] font-bold px-1.5 py-0.5 rounded-full min-w-[18px] text-center animate-pulse"
        title={`${clusterStats.discovered} new clusters detected - Potential Savings: $${clusterStats.potentialSavings.toFixed(0)}/mo`}
      >
        {clusterStats.discovered}
      </span>
    );
  }

  return null;
};

const MainLayout = () => {
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();

  const navigation = [
    { name: 'Dashboard', path: '/dashboard', icon: FiHome },
    { name: 'Approvals', path: '/approvals', icon: FiCheckSquare },
    { name: 'Teams', path: '/teams', icon: FiUsers },
    { name: 'Clusters', path: '/clusters', icon: FiServer },
    { name: 'Policies', path: '/policies', icon: FiTarget },
    { name: 'Tag Management', path: '/tag-management', icon: FiTag },
    { name: 'Templates', path: '/templates', icon: FiFileText },
    { name: 'Right-Sizing', path: '/right-sizing', icon: FiBarChart2 },
    { name: 'Resource Hygiene', path: '/cleanup', icon: FiActivity },
    { name: 'Hibernation', path: '/hibernation', icon: FiClock },
    { name: 'Audit Logs', path: '/audit', icon: FiClipboard },
    { name: 'Settings', path: '/settings', icon: FiSettings },
  ];

  const adminNavigation = [
    { name: 'Command Center', path: '/admin', icon: FiActivity },
    { name: 'Organizations', path: '/admin/organizations', icon: FiBriefcase },
    { name: 'Clients', path: '/admin/clients', icon: FiUsers },
    { name: 'System Health', path: '/admin/health', icon: FiServer },
    { name: 'The Lab', path: '/admin/lab', icon: FiTarget }, // Using Target icon for Lab/Models
    { name: 'Configuration', path: '/admin/config', icon: FiSettings },
    { name: 'Billing', path: '/admin/billing', icon: FiBarChart2 }, // Using BarChart for Billing
  ];

  const isActive = (path) => location.pathname === path;

  // Determine which navigation to show
  const isSuperAdmin = user?.role === 'SUPER_ADMIN' || user?.role === 'super_admin';
  const navItems = isSuperAdmin ? adminNavigation : navigation;

  const [isSidebarOpen, setIsSidebarOpen] = React.useState(true);

  return (
    <div className="min-h-screen bg-gray-50 flex">
      <ActiveWindowBanner />

      {/* Sidebar */}
      <div
        className={`fixed inset-y-0 left-0 bg-white border-r border-gray-200 transition-all duration-300 z-30 ${isSidebarOpen ? 'w-64' : 'w-0 -translate-x-full'}`}
      >
        {/* Logo */}
        <div className="h-16 flex items-center px-6 border-b border-gray-200 justify-between">
          <h1 className="text-xl font-bold text-gray-900 truncate">
            {isSuperAdmin ? 'Admin Console' : 'Spot Optimizer'}
          </h1>
        </div>

        {/* Navigation */}
        <nav className="flex-1 px-4 py-4 space-y-1 overflow-y-auto h-[calc(100vh-8rem)]">
          {navItems.map((item) => {
            const Icon = item.icon;
            // Add notification badge for Clusters
            const showBadge = item.name === 'Clusters';
            return (
              <Link
                key={item.path}
                to={item.path}
                className={`flex items-center px-4 py-3 text-sm font-medium rounded-lg transition-colors relative ${isActive(item.path)
                  ? 'bg-blue-50 text-blue-700'
                  : 'text-gray-700 hover:bg-gray-50'
                  }`}
              >
                <Icon className="w-5 h-5 mr-3 flex-shrink-0" />
                <span className="truncate">{item.name}</span>
                {showBadge && (
                  <ClusterBadge />
                )}
              </Link>
            );
          })}

          {/* Admin Impersonation Notice */}
          {isSuperAdmin && (
            <div className="mt-8 px-4">
              <div className="p-3 bg-yellow-50 rounded-lg border border-yellow-200">
                <p className="text-xs text-yellow-800 font-medium truncate">Client View Hidden</p>
                <p className="text-xs text-yellow-700 mt-1">Use "Clients" page to impersonate users.</p>
              </div>
            </div>
          )}
        </nav>

        {/* User Profile */}
        <div className="absolute bottom-0 w-full p-4 border-t border-gray-200 bg-white">
          <div className="flex items-center justify-between">
            <div className="flex items-center overflow-hidden">
              <div className="w-8 h-8 bg-blue-600 rounded-full flex items-center justify-center flex-shrink-0">
                <span className="text-white text-sm font-medium">
                  {user?.email?.[0].toUpperCase()}
                </span>
              </div>
              <div className="ml-3 truncate">
                <p className="text-sm font-medium text-gray-900 truncate">{user?.email}</p>
                <p className="text-xs text-gray-500 truncate">{user?.role}</p>
              </div>
            </div>
            <button
              onClick={logout}
              className="p-2 text-gray-400 hover:text-gray-600 transition-colors flex-shrink-0"
            >
              <FiLogOut className="w-5 h-5" />
            </button>
          </div>
        </div>
      </div>

      {/* Main Content */}
      <div className={`flex-1 flex flex-col min-w-0 transition-all duration-300 ${isSidebarOpen ? 'pl-64' : 'pl-0'}`}>
        {/* Header */}
        <header className="h-16 bg-white border-b border-gray-200 flex items-center justify-between px-4 sm:px-6 lg:px-8 z-20">
          <div className="flex items-center gap-4">
            <button
              onClick={() => setIsSidebarOpen(!isSidebarOpen)}
              className="p-2 -ml-2 text-gray-500 hover:text-gray-700 rounded-md hover:bg-gray-100 focus:outline-none"
              aria-label="Toggle sidebar"
            >
              <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 6h16M4 12h16M4 18h16" />
              </svg>
            </button>
            <h2 className="text-lg font-semibold text-gray-900">
              {navigation.find(item => isActive(item.path))?.name || 'Dashboard'}
            </h2>
          </div>
          <div className="flex items-center gap-4">
            {/* Settings is now in the sidebar */}
          </div>
        </header>

        {/* Page Content */}
        <main className="flex-1 overflow-y-auto">
          <div className="p-8 h-full">
            <Outlet />
          </div>
        </main>
      </div>
    </div>
  );
};

export default MainLayout;
