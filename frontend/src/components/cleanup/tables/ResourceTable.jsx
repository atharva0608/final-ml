import React, { useState } from 'react';
import { FiCheckCircle, FiAlertTriangle, FiAlertOctagon, FiTag, FiServer, FiHardDrive, FiCamera, FiGlobe, FiFolder, FiTrash2, FiXCircle } from 'react-icons/fi';
import { toast } from 'react-hot-toast';
import { useAuthStore } from '../../../store/useStore';
import api from '../../../services/api';

const ResourceTable = ({
    resources,
    loading,
    selectedItems,
    toggleSelection,
    setSelectedItems,
    activeTab,
    showAuthorized,
    onAuthorize,
    onUnauthorize,
    onCleanup,
    requiredTags = [] // Passed from parent or store
}) => {
    const { user } = useAuthStore();
    const isOrgAdmin = user?.role === 'ORG_ADMIN';

    // Helper to get icon
    const getIcon = (type) => {
        switch (type) {
            case 'INSTANCE': return <FiServer />;
            case 'VOLUME': return <FiHardDrive />;
            case 'SNAPSHOT': return <FiCamera />;
            case 'ELASTIC_IP': return <FiGlobe />;
            default: return <FiFolder />;
        }
    };

    // Helper: Get cleanup readiness status
    const getCleanupStatus = (resource) => {
        // ACTIVE/Authorized = In Use (don't delete)
        if (resource.is_authorized || resource.status === 'ACTIVE') {
            return { level: 'IN_USE', label: 'In Use', color: 'blue' };
        }

        // SAFE_TO_DELETE = Ready for cleanup (>30 days, verified safe)
        if (resource.status === 'SAFE_TO_DELETE') {
            return { level: 'READY', label: 'Ready for Cleanup', color: 'green' };
        }

        // ORPHANED = Needs manual review (<30 days or unverified)
        if (resource.status === 'ORPHANED') {
            return { level: 'REVIEW', label: 'Needs Review', color: 'yellow' };
        }

        // Default: Needs review
        return { level: 'REVIEW', label: 'Needs Review', color: 'yellow' };
    };

    // Check tag compliance
    const checkCompliance = (resource) => {
        if (!requiredTags || requiredTags.length === 0) return { compliant: true, missing: [] };

        // Convert resource tags to normalized keys
        const existingKeys = Object.keys(resource.tags || {}).map(k => k.toLowerCase());
        const missing = requiredTags.filter(req => !existingKeys.includes(req.toLowerCase()));

        return {
            compliant: missing.length === 0,
            missing
        };
    };

    const handleAuthorizeClick = async (resource) => {
        const compliance = checkCompliance(resource);

        if (!compliance.compliant) {
            if (!isOrgAdmin) {
                toast.error(`Compliance violation: Missing required tags: ${compliance.missing.join(', ')}`);
                return;
            }
            // Admin override confirmation
            if (!window.confirm(`Warning: This resource is missing required tags (${compliance.missing.join(', ')}). Authorizing it will lower your compliance score. Force authorize?`)) {
                return;
            }
        }

        if (onAuthorize) {
            onAuthorize(resource.id);
        } else {
            // Fallback if prop not provided (for older implementations)
            console.log('Authorize', resource.id);
        }
    };

    if (loading) return <div className="p-12 text-center text-gray-500">Loading resources...</div>;

    if (!resources || resources.length === 0) return (
        <div className="flex flex-col items-center justify-center p-12 text-center">
            <div className="bg-green-50 p-4 rounded-full mb-4">
                <FiCheckCircle className="h-8 w-8 text-green-500" />
            </div>
            <h3 className="text-lg font-medium text-gray-900">No issues found</h3>
            <p className="text-gray-500">Your infrastructure looks clean for this category.</p>
        </div>
    );

    return (
        <div className="bg-white rounded-xl shadow-sm border border-gray-200 overflow-hidden">
            <div className="overflow-x-auto">
                <table className="min-w-full divide-y divide-gray-200">
                    <thead className="bg-gray-50">
                        <tr>
                            <th className="px-6 py-3 w-12">
                                <input
                                    type="checkbox"
                                    className="rounded border-gray-300 text-blue-600 focus:ring-blue-500"
                                    onChange={(e) => {
                                        if (e.target.checked) setSelectedItems(resources.map(r => r.id));
                                        else setSelectedItems([]);
                                    }}
                                    checked={resources.length > 0 && selectedItems.length === resources.length}
                                />
                            </th>
                            <th className="px-6 py-3 text-left text-xs font-semibold text-gray-500 uppercase tracking-wider">Resource</th>
                            <th className="px-6 py-3 text-left text-xs font-semibold text-gray-500 uppercase tracking-wider">Compliance</th>
                            <th className="px-6 py-3 text-left text-xs font-semibold text-gray-500 uppercase tracking-wider">Region</th>
                            <th className="px-6 py-3 text-left text-xs font-semibold text-gray-500 uppercase tracking-wider">Reason</th>
                            <th className="px-6 py-3 text-left text-xs font-semibold text-gray-500 uppercase tracking-wider">Safety</th>
                            <th className="px-6 py-3 text-left text-xs font-semibold text-gray-500 uppercase tracking-wider">Cost/Mo</th>
                            <th className="relative px-6 py-3"><span className="sr-only">Actions</span></th>
                        </tr>
                    </thead>
                    <tbody className="bg-white divide-y divide-gray-200">
                        {resources.map(resource => {
                            const cleanupStatus = getCleanupStatus(resource);
                            const compliance = checkCompliance(resource);

                            return (
                                <tr key={resource.id} className={`hover:bg-gray-50 transition-colors ${selectedItems.includes(resource.id) ? 'bg-blue-50' : ''}`}>
                                    <td className="px-6 py-4">
                                        <input
                                            type="checkbox"
                                            className="rounded border-gray-300 text-blue-600 focus:ring-blue-500"
                                            checked={selectedItems.includes(resource.id)}
                                            onChange={() => toggleSelection(resource.id)}
                                        />
                                    </td>
                                    <td className="px-6 py-4">
                                        <div className="flex items-center">
                                            <div className="flex-shrink-0 h-10 w-10 text-gray-500 bg-gray-100 rounded-lg flex items-center justify-center">
                                                {getIcon(resource.type)}
                                            </div>
                                            <div className="ml-4">
                                                <div className="text-sm font-medium text-gray-900 font-mono">
                                                    {resource.name && resource.name !== "Unknown" ? resource.name : resource.id}
                                                </div>
                                                <div className="text-sm text-gray-500 flex items-center gap-2">
                                                    <span>{resource.type}</span>
                                                    {resource.metadata?.State && (
                                                        <span className={`px-1.5 py-0.5 rounded text-[10px] uppercase font-bold tracking-wide ${resource.metadata.State === 'running' ? 'bg-green-100 text-green-700' :
                                                            resource.metadata.State === 'stopped' ? 'bg-red-100 text-red-700' :
                                                                'bg-gray-100 text-gray-700'
                                                            }`}>
                                                            {resource.metadata.State}
                                                        </span>
                                                    )}
                                                </div>
                                            </div>
                                        </div>
                                    </td>
                                    <td className="px-6 py-4 whitespace-nowrap">
                                        {compliance.compliant ? (
                                            <div className="flex items-center text-green-600" title="All required tags present">
                                                <FiCheckCircle className="w-5 h-5 mr-1" />
                                                <span className="text-xs font-medium">Ready</span>
                                            </div>
                                        ) : (
                                            <div className="group relative flex items-center text-red-500 cursor-help">
                                                <FiXCircle className="w-5 h-5 mr-1" />
                                                <span className="text-xs font-medium">Violation</span>
                                                {/* Tooltip */}
                                                <div className="absolute left-full ml-2 hidden group-hover:block w-48 bg-gray-900 text-white text-xs rounded p-2 z-10 shadow-lg">
                                                    Missing: {compliance.missing.join(', ')}
                                                </div>
                                            </div>
                                        )}
                                    </td>
                                    <td className="px-6 py-4 whitespace-nowrap">
                                        <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-gray-100 text-gray-800">
                                            {resource.region}
                                        </span>
                                    </td>
                                    <td className="px-6 py-4 text-sm text-gray-500">
                                        {resource.reason || resource.status}
                                    </td>
                                    <td className="px-6 py-4 whitespace-nowrap">
                                        {cleanupStatus.level === 'IN_USE' && (
                                            <span className="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-blue-100 text-blue-800" title="Active or authorized resource - do not delete">
                                                <FiCheckCircle className="mr-1.5" /> {cleanupStatus.label}
                                            </span>
                                        )}
                                        {cleanupStatus.level === 'READY' && (
                                            <span className="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-green-100 text-green-800" title=">30 days old, verified safe to delete">
                                                <FiCheckCircle className="mr-1.5" /> {cleanupStatus.label}
                                            </span>
                                        )}
                                        {cleanupStatus.level === 'REVIEW' && (
                                            <span className="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-yellow-100 text-yellow-800" title="Orphaned but needs manual verification before deletion">
                                                <FiAlertTriangle className="mr-1.5" /> {cleanupStatus.label}
                                            </span>
                                        )}
                                    </td>
                                    <td className="px-6 py-4 whitespace-nowrap text-sm font-bold text-gray-900">
                                        ${resource.cost_per_month.toFixed(2)}
                                    </td>
                                    <td className="px-6 py-4 whitespace-nowrap text-right text-sm font-medium">
                                        <div className="flex justify-end gap-2">
                                            {!resource.is_authorized && (
                                                <button
                                                    onClick={() => handleAuthorizeClick(resource)}
                                                    className={`transition-colors p-1 rounded ${!compliance.compliant && !isOrgAdmin
                                                            ? 'text-gray-300 cursor-not-allowed'
                                                            : 'text-gray-400 hover:text-green-600 hover:bg-green-50'
                                                        }`}
                                                    title={!compliance.compliant && !isOrgAdmin ? "Fix tags to authorize" : "Authorize"}
                                                    disabled={!compliance.compliant && !isOrgAdmin}
                                                >
                                                    <FiCheckCircle className="w-5 h-5" />
                                                </button>
                                            )}
                                            {resource.is_authorized && (
                                                <button
                                                    onClick={() => onUnauthorize ? onUnauthorize(resource.id) : console.log('Unauthorize', resource.id)}
                                                    className="text-gray-400 hover:text-red-500 hover:bg-red-50 p-1 rounded"
                                                    title="Unauthorize"
                                                >
                                                    <FiAlertTriangle className="w-5 h-5" />
                                                </button>
                                            )}
                                            <button
                                                onClick={() => onCleanup ? onCleanup(resource.id) : console.log('Cleanup', resource.id)}
                                                className="text-gray-400 hover:text-red-600 hover:bg-red-50 p-1 rounded"
                                                title="Cleanup Resource"
                                            >
                                                <FiTrash2 className="w-5 h-5" />
                                            </button>
                                        </div>
                                    </td>
                                </tr>
                            );
                        })}
                    </tbody>
                </table>
            </div>
        </div>
    );
};

export default ResourceTable;
