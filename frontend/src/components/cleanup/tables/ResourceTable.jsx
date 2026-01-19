import React, { useState } from 'react';
import { FiCheckCircle, FiAlertTriangle, FiAlertOctagon, FiTag, FiServer, FiHardDrive, FiCamera, FiGlobe, FiShare2, FiLink, FiDatabase, FiUsers, FiFolder, FiMoreVertical, FiTrash2 } from 'react-icons/fi';
import Badge from '../../shared/Badge';

const ResourceTable = ({
    resources,
    loading,
    selectedItems,
    toggleSelection,
    setSelectedItems,
    activeTab,
    showAuthorized
}) => {

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

    // Helper safety level (re-used from dashboard logic or consolidated)
    const getSafetyLevel = (resource) => {
        if (resource.is_authorized) return 'HIGH';
        if (resource.status === 'SAFE_TO_DELETE') return 'HIGH';
        if (['VOLUME', 'SNAPSHOT', 'ELASTIC_IP'].includes(resource.type) && resource.status === 'ORPHANED') return 'HIGH';
        return 'LOW';
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
            {/* Table Controls Header (Density, Search etc. - keeping simple for now) */}

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
                            <th className="px-6 py-3 text-left text-xs font-semibold text-gray-500 uppercase tracking-wider">Region</th>
                            <th className="px-6 py-3 text-left text-xs font-semibold text-gray-500 uppercase tracking-wider">Reason</th>
                            <th className="px-6 py-3 text-left text-xs font-semibold text-gray-500 uppercase tracking-wider">Safety</th>
                            <th className="px-6 py-3 text-left text-xs font-semibold text-gray-500 uppercase tracking-wider">Cost/Mo</th>
                            <th className="relative px-6 py-3"><span className="sr-only">Actions</span></th>
                        </tr>
                    </thead>
                    <tbody className="bg-white divide-y divide-gray-200">
                        {resources.map(resource => {
                            const safety = getSafetyLevel(resource);
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
                                                <div className="text-sm font-medium text-gray-900 font-mono">{resource.id}</div>
                                                <div className="text-sm text-gray-500">{resource.name || resource.type}</div>
                                            </div>
                                        </div>
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
                                        {safety === 'HIGH' && (
                                            <span className="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-green-100 text-green-800">
                                                <FiCheckCircle className="mr-1.5" /> Safe
                                            </span>
                                        )}
                                        {safety === 'MEDIUM' && (
                                            <span className="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-yellow-100 text-yellow-800">
                                                <FiAlertTriangle className="mr-1.5" /> Review
                                            </span>
                                        )}
                                        {safety === 'LOW' && (
                                            <span className="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-red-100 text-red-800">
                                                <FiAlertOctagon className="mr-1.5" /> Risky
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
                                                    onClick={() => console.log('Authorize', resource.id)}
                                                    className="text-gray-400 hover:text-green-600"
                                                    title="Authorize"
                                                >
                                                    <FiCheckCircle className="w-5 h-5" />
                                                </button>
                                            )}
                                            {resource.is_authorized && (
                                                <button
                                                    onClick={() => console.log('Unauthorize', resource.id)}
                                                    className="text-gray-400 hover:text-red-500"
                                                    title="Unauthorize"
                                                >
                                                    <FiAlertTriangle className="w-5 h-5" />
                                                </button>
                                            )}
                                            <button
                                                onClick={() => console.log('Cleanup', resource.id)}
                                                className="text-gray-400 hover:text-red-600"
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
