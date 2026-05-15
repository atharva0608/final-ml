/**
 * Tenant List Card Widget (Super Admin only)
 * Shows list of organizations
 */
import React from 'react';
import { FiBriefcase, FiUsers, FiCheckCircle, FiXCircle } from 'react-icons/fi';

const TenantListCard = ({ data = {}, widgetKey }) => {
    const tenants = data.tenants || [
        { id: 1, name: 'Acme Corp', users: 25, status: 'active', mrr: 1500 },
        { id: 2, name: 'TechStart Inc', users: 12, status: 'active', mrr: 750 },
        { id: 3, name: 'CloudScale LLC', users: 8, status: 'suspended', mrr: 0 }
    ];

    const activeTenants = tenants.filter(t => t.status === 'active').length;

    return (
        <div className="bg-white rounded-xl shadow-sm border border-gray-100 p-6 hover:shadow-md transition-shadow">
            <div className="flex items-center justify-between mb-4">
                <div>
                    <h3 className="text-lg font-semibold text-gray-900">Tenants</h3>
                    <p className="text-sm text-gray-500">{activeTenants} active organizations</p>
                </div>
                <div className="p-2 bg-indigo-50 rounded-lg">
                    <FiBriefcase className="w-5 h-5 text-indigo-600" />
                </div>
            </div>

            <div className="space-y-3">
                {tenants.slice(0, 4).map((tenant) => (
                    <div key={tenant.id} className="flex items-center justify-between p-3 bg-gray-50 rounded-lg">
                        <div className="flex items-center gap-3">
                            {tenant.status === 'active' ? (
                                <FiCheckCircle className="w-4 h-4 text-green-500" />
                            ) : (
                                <FiXCircle className="w-4 h-4 text-red-500" />
                            )}
                            <div>
                                <p className="font-medium text-gray-900">{tenant.name}</p>
                                <p className="text-xs text-gray-500 flex items-center gap-1">
                                    <FiUsers className="w-3 h-3" /> {tenant.users} users
                                </p>
                            </div>
                        </div>
                        <span className="text-sm font-medium text-gray-600">
                            ${tenant.mrr}/mo
                        </span>
                    </div>
                ))}
            </div>
        </div>
    );
};

export default TenantListCard;
