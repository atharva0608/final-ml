import React, { useState } from 'react';
import {
  FiUsers,
  FiActivity,
  FiSettings,
  FiCpu,
  FiShield,
  FiGrid
} from 'react-icons/fi';

import AdminOrganizations from './AdminOrganizations';
import AdminHealth from './AdminHealth';
import AdminLab from './AdminLab';
import AdminConfig from './AdminConfig';
import AuditLog from '../audit/AuditLog';
import AdminOverview from './AdminOverview';

const AdminDashboard = () => {
  const [activeTab, setActiveTab] = useState('overview');

  const renderContent = () => {
    switch (activeTab) {
      case 'overview':
        return <AdminOverview />;
      case 'tenants':
        return <AdminOrganizations />;
      case 'health':
        return <AdminHealth />;
      case 'models':
        return <AdminLab />;
      case 'config':
        return <AdminConfig />;
      case 'audit':
        // Reuse AuditLog but maybe with specific admin props if needed
        return <AuditLog title="Global Audit Log" isAdminView={true} />;
      default:
        return <AdminOverview />;
    }
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">SaaS Command Center</h1>
          <p className="text-gray-600">Platform Administration & Governance</p>
        </div>
      </div>

      {/* Tabs */}
      <div className="bg-white rounded-lg shadow p-1">
        <nav className="flex space-x-2 overflow-x-auto" aria-label="Tabs">
          <button
            onClick={() => setActiveTab('overview')}
            className={`${activeTab === 'overview'
              ? 'bg-blue-100 text-blue-700'
              : 'text-gray-500 hover:text-gray-700 hover:bg-gray-50'
              } px-4 py-2 font-medium text-sm rounded-md transition-colors flex items-center gap-2 whitespace-nowrap`}
          >
            <FiGrid className="w-4 h-4" />
            Overview
          </button>

          <button
            onClick={() => setActiveTab('tenants')}
            className={`${activeTab === 'tenants'
              ? 'bg-blue-100 text-blue-700'
              : 'text-gray-500 hover:text-gray-700 hover:bg-gray-50'
              } px-4 py-2 font-medium text-sm rounded-md transition-colors flex items-center gap-2 whitespace-nowrap`}
          >
            <FiUsers className="w-4 h-4" />
            Tenants
          </button>

          <button
            onClick={() => setActiveTab('health')}
            className={`${activeTab === 'health'
              ? 'bg-blue-100 text-blue-700'
              : 'text-gray-500 hover:text-gray-700 hover:bg-gray-50'
              } px-4 py-2 font-medium text-sm rounded-md transition-colors flex items-center gap-2 whitespace-nowrap`}
          >
            <FiActivity className="w-4 h-4" />
            Platform Health
          </button>

          <button
            onClick={() => setActiveTab('models')}
            className={`${activeTab === 'models'
              ? 'bg-blue-100 text-blue-700'
              : 'text-gray-500 hover:text-gray-700 hover:bg-gray-50'
              } px-4 py-2 font-medium text-sm rounded-md transition-colors flex items-center gap-2 whitespace-nowrap`}
          >
            <FiCpu className="w-4 h-4" />
            ML Model Registry
          </button>

          <button
            onClick={() => setActiveTab('config')}
            className={`${activeTab === 'config'
              ? 'bg-blue-100 text-blue-700'
              : 'text-gray-500 hover:text-gray-700 hover:bg-gray-50'
              } px-4 py-2 font-medium text-sm rounded-md transition-colors flex items-center gap-2 whitespace-nowrap`}
          >
            <FiSettings className="w-4 h-4" />
            Global Config
          </button>

          <button
            onClick={() => setActiveTab('audit')}
            className={`${activeTab === 'audit'
              ? 'bg-blue-100 text-blue-700'
              : 'text-gray-500 hover:text-gray-700 hover:bg-gray-50'
              } px-4 py-2 font-medium text-sm rounded-md transition-colors flex items-center gap-2 whitespace-nowrap`}
          >
            <FiShield className="w-4 h-4" />
            Global Audit
          </button>
        </nav>
      </div>

      {/* Content Area */}
      <div className="mt-6">
        {renderContent()}
      </div>
    </div>
  );
};

export default AdminDashboard;
