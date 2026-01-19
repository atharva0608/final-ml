import React from 'react';
import AdminOverview from './AdminOverview';

/**
 * AdminDashboard
 * 
 * Simplified admin view - just shows the Overview.
 * Other admin sections (Tenants, Health, Config, Audit) are accessible via the sidebar.
 */
const AdminDashboard = () => {
  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">SaaS Command Center</h1>
          <p className="text-gray-600">Platform Administration & Governance</p>
        </div>
      </div>

      {/* Content - Overview Only */}
      <AdminOverview />
    </div>
  );
};

export default AdminDashboard;
