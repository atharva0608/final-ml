/**
 * Main Layout Component
 *
 * Layout with sidebar navigation and header
 */
import React from 'react';
import { Outlet, Link, useNavigate, useLocation } from 'react-router-dom';
import { useAuth } from '../../hooks/useAuth';
import { Button } from '../shared';
import { FiHome, FiServer, FiFileText, FiSettings, FiTarget, FiClock, FiBarChart2, FiUsers, FiActivity, FiLogOut, FiClipboard } from 'react-icons/fi';

const MainLayout = () => {
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();

  const navigation = [
    { name: 'Dashboard', path: '/dashboard', icon: FiHome },
    { name: 'Clusters', path: '/clusters', icon: FiServer },
    { name: 'Policies', path: '/policies', icon: FiTarget },
    { name: 'Templates', path: '/templates', icon: FiFileText },
    { name: 'Right-Sizing', path: '/right-sizing', icon: FiBarChart2 },
    { name: 'Hibernation', path: '/hibernation', icon: FiClock },
    { name: 'Audit Logs', path: '/audit', icon: FiClipboard },
    { name: 'Settings', path: '/settings', icon: FiSettings },
  ];

  const adminNavigation = [
    { name: 'Command Center', path: '/admin', icon: FiActivity },
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

  return (
    <div className="min-h-screen bg-gray-50">
      {/* Sidebar */}
      <div className="fixed inset-y-0 left-0 w-64 bg-white border-r border-gray-200">
        {/* Logo */}
        <div className="h-16 flex items-center px-6 border-b border-gray-200">
          <h1 className="text-xl font-bold text-gray-900">
            {isSuperAdmin ? 'Admin Console' : 'Spot Optimizer'}
          </h1>
        </div>

        {/* Navigation */}
        <nav className="flex-1 px-4 py-4 space-y-1">
          {navItems.map((item) => {
            const Icon = item.icon;
            return (
              <Link
                key={item.path}
                to={item.path}
                className={`flex items-center px-4 py-3 text-sm font-medium rounded-lg transition-colors ${isActive(item.path)
                  ? 'bg-blue-50 text-blue-700'
                  : 'text-gray-700 hover:bg-gray-50'
                  }`}
              >
                <Icon className="w-5 h-5 mr-3" />
                {item.name}
              </Link>
            );
          })}

          {/* Admin Impersonation Notice (Optional Placeholder) */}
          {isSuperAdmin && (
            <div className="mt-8 px-4">
              <div className="p-3 bg-yellow-50 rounded-lg border border-yellow-200">
                <p className="text-xs text-yellow-800 font-medium">Client View Hidden</p>
                <p className="text-xs text-yellow-700 mt-1">Use "Clients" page to impersonate users.</p>
              </div>
            </div>
          )}
        </nav>

        {/* User Profile */}
        <div className="absolute bottom-0 w-64 p-4 border-t border-gray-200 bg-white">
          <div className="flex items-center justify-between">
            <div className="flex items-center">
              <div className="w-8 h-8 bg-blue-600 rounded-full flex items-center justify-center">
                <span className="text-white text-sm font-medium">
                  {user?.email?.[0].toUpperCase()}
                </span>
              </div>
              <div className="ml-3">
                <p className="text-sm font-medium text-gray-900">{user?.email}</p>
                <p className="text-xs text-gray-500">{user?.role}</p>
              </div>
            </div>
            <button
              onClick={logout}
              className="p-2 text-gray-400 hover:text-gray-600 transition-colors"
            >
              <FiLogOut className="w-5 h-5" />
            </button>
          </div>
        </div>
      </div>

      {/* Main Content */}
      <div className="pl-64">
        {/* Header */}
        <header className="h-16 bg-white border-b border-gray-200 flex items-center justify-between px-8">
          <div className="flex items-center">
            <h2 className="text-lg font-semibold text-gray-900">
              {navigation.find(item => isActive(item.path))?.name || 'Dashboard'}
            </h2>
          </div>
          <div className="flex items-center gap-4">
            {/* Settings is now in the sidebar */}
          </div>
        </header>

        {/* Page Content */}
        <main className="p-8">
          <Outlet />
        </main>
      </div>
    </div>
  );
};

export default MainLayout;
