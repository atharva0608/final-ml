
import React, { useState, useEffect } from 'react';
import {
    FiSearch,
    FiFilter,
    FiBriefcase,
    FiUsers
} from 'react-icons/fi';
import { adminAPI } from '../../services/api';
import { format } from 'date-fns';

const AdminOrganizations = () => {
    const [organizations, setOrganizations] = useState([]);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState(null);
    const [searchQuery, setSearchQuery] = useState('');
    const [page, setPage] = useState(1);
    const [totalPages, setTotalPages] = useState(1);
    const [selectedOrg, setSelectedOrg] = useState(null);

    const fetchOrganizations = async () => {
        try {
            setLoading(true);
            const response = await adminAPI.listOrganizations({
                page,
                page_size: 10,
                search: searchQuery || undefined
            });
            setOrganizations(response.data.organizations);
            setTotalPages(Math.ceil(response.data.total / 10));
            setError(null);
        } catch (err) {
            console.error('Failed to fetch organizations:', err);
            setError('Failed to load organizations');
        } finally {
            setLoading(false);
        }
    };

    useEffect(() => {
        fetchOrganizations();
    }, [page, searchQuery]);

    // Debounce search
    useEffect(() => {
        const timer = setTimeout(() => {
            if (searchQuery) setPage(1);
            fetchOrganizations();
        }, 500);
        return () => clearTimeout(timer);
    }, [searchQuery]);

    return (
        <div className="space-y-6">
            <div className="flex justify-between items-center">
                <div>
                    <h1 className="text-2xl font-bold text-gray-900">Organization Management</h1>
                    <p className="text-gray-600 mt-1">Manage all organizations on the platform</p>
                </div>
            </div>

            {/* Filters */}
            <div className="bg-white rounded-lg shadow p-4 flex gap-4">
                <div className="flex-1 relative">
                    <FiSearch className="h-5 w-5 text-gray-400 absolute left-3 top-1/2 transform -translate-y-1/2" />
                    <input
                        type="text"
                        placeholder="Search organizations..."
                        value={searchQuery}
                        onChange={(e) => setSearchQuery(e.target.value)}
                        className="w-full bg-gray-50 text-gray-900 pl-10 pr-4 py-2 rounded-lg border border-gray-200 focus:outline-none focus:ring-2 focus:ring-blue-500"
                    />
                </div>
                <button className="flex items-center space-x-2 px-4 py-2 bg-white border border-gray-200 text-gray-600 rounded-lg hover:bg-gray-50 transition-colors">
                    <FiFilter className="h-5 w-5" />
                    <span>Filters</span>
                </button>
            </div>

            {/* Table */}
            <div className="bg-white rounded-lg shadow overflow-hidden border border-gray-200">
                <div className="overflow-x-auto">
                    <table className="w-full text-left">
                        <thead className="bg-gray-50">
                            <tr>
                                <th className="px-6 py-4 text-xs font-medium text-gray-500 uppercase tracking-wider">Organization</th>
                                <th className="px-6 py-4 text-xs font-medium text-gray-500 uppercase tracking-wider">Slug</th>
                                <th className="px-6 py-4 text-xs font-medium text-gray-500 uppercase tracking-wider">Owner</th>
                                <th className="px-6 py-4 text-xs font-medium text-gray-500 uppercase tracking-wider">Stats</th>
                                <th className="px-6 py-4 text-xs font-medium text-gray-500 uppercase tracking-wider">Created</th>
                                <th className="px-6 py-4 text-xs font-medium text-gray-500 uppercase tracking-wider">Status</th>
                                <th className="px-6 py-4 text-xs font-medium text-gray-500 uppercase tracking-wider">Actions</th>
                            </tr>
                        </thead>
                        <tbody className="divide-y divide-gray-200 bg-white">
                            {loading ? (
                                <tr>
                                    <td colSpan="7" className="px-6 py-8 text-center text-gray-500">Loading organizations...</td>
                                </tr>
                            ) : organizations.length === 0 ? (
                                <tr>
                                    <td colSpan="7" className="px-6 py-8 text-center text-gray-500">No organizations found</td>
                                </tr>
                            ) : (
                                organizations.map((org) => (
                                    <tr key={org.id} className="hover:bg-gray-50 transition-colors">
                                        <td className="px-6 py-4">
                                            <div className="flex items-center space-x-3">
                                                <div className="p-2 bg-blue-50 rounded-lg">
                                                    <FiBriefcase className="h-5 w-5 text-blue-600" />
                                                </div>
                                                <div>
                                                    <div className="font-medium text-gray-900">{org.name}</div>
                                                    <div className="text-sm text-gray-500 text-xs">ID: {org.id.substring(0, 8)}...</div>
                                                </div>
                                            </div>
                                        </td>
                                        <td className="px-6 py-4">
                                            <code className="text-gray-600 bg-gray-100 px-2 py-1 rounded text-sm">{org.slug}</code>
                                        </td>
                                        <td className="px-6 py-4 text-gray-600">
                                            {org.owner_email || 'N/A'}
                                        </td>
                                        <td className="px-6 py-4">
                                            <div className="space-y-1">
                                                <div className="text-xs text-gray-500 flex items-center gap-1">
                                                    <FiUsers className="h-3 w-3" /> {org.total_users} Users
                                                </div>
                                                <div className="text-xs text-gray-500">
                                                    {org.total_clusters} Clusters • {org.total_instances} Instances
                                                </div>
                                            </div>
                                        </td>
                                        <td className="px-6 py-4 text-gray-600">
                                            {format(new Date(org.created_at), 'MMM d, yyyy')}
                                        </td>
                                        <td className="px-6 py-4">
                                            <span className={`px-2 py-1 rounded-full text-xs font-medium ${org.is_active
                                                ? 'bg-green-100 text-green-800'
                                                : 'bg-red-100 text-red-800'
                                                }`}>
                                                {org.is_active ? 'Active' : 'Inactive'}
                                            </span>
                                        </td>
                                        <td className="px-6 py-4">
                                            <button
                                                onClick={() => setSelectedOrg(org)}
                                                className="text-blue-600 hover:text-blue-800 text-sm font-medium"
                                            >
                                                Details
                                            </button>
                                        </td>
                                    </tr>
                                ))
                            )}
                        </tbody>
                    </table>
                </div>

                {/* Pagination */}
                <div className="px-6 py-4 border-t border-gray-200 flex justify-between items-center bg-gray-50">
                    <div className="text-sm text-gray-700">
                        Page {page} of {totalPages}
                    </div>
                    <div className="flex gap-2">
                        <button
                            disabled={page === 1}
                            onClick={() => setPage(p => Math.max(1, p - 1))}
                            className="px-3 py-1 bg-white border border-gray-300 text-gray-700 rounded text-sm hover:bg-gray-50 disabled:opacity-50 disabled:bg-gray-100"
                        >
                            Previous
                        </button>
                        <button
                            disabled={page === totalPages}
                            onClick={() => setPage(p => Math.min(totalPages, p + 1))}
                            className="px-3 py-1 bg-white border border-gray-300 text-gray-700 rounded text-sm hover:bg-gray-50 disabled:opacity-50 disabled:bg-gray-100"
                        >
                            Next
                        </button>
                    </div>
                </div>
            </div>

            {/* Details Modal */}
            {selectedOrg && (
                <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center p-4 z-50">
                    <div className="bg-white rounded-lg shadow-xl max-w-2xl w-full max-h-[90vh] overflow-y-auto">
                        <div className="flex justify-between items-center p-6 border-b border-gray-200">
                            <h2 className="text-xl font-bold text-gray-900">Organization Details</h2>
                            <button
                                onClick={() => setSelectedOrg(null)}
                                className="text-gray-400 hover:text-gray-500"
                            >
                                <svg className="h-6 w-6" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                                </svg>
                            </button>
                        </div>
                        <div className="p-6 space-y-6">
                            {/* Header Info */}
                            <div className="flex items-start gap-4">
                                <div className="p-3 bg-blue-100 rounded-lg">
                                    <FiBriefcase className="h-8 w-8 text-blue-600" />
                                </div>
                                <div>
                                    <h3 className="text-xl font-bold text-gray-900">{selectedOrg.name}</h3>
                                    <p className="text-sm text-gray-500">ID: {selectedOrg.id}</p>
                                    <div className="flex gap-2 mt-2">
                                        <span className="px-2 py-1 bg-gray-100 text-gray-600 rounded text-xs font-mono">
                                            {selectedOrg.slug}
                                        </span>
                                        <span className={`px-2 py-1 rounded-full text-xs font-medium ${selectedOrg.is_active ? 'bg-green-100 text-green-800' : 'bg-red-100 text-red-800'
                                            }`}>
                                            {selectedOrg.is_active ? 'Active' : 'Inactive'}
                                        </span>
                                    </div>
                                </div>
                            </div>

                            {/* Stats Grid */}
                            <div className="grid grid-cols-3 gap-4">
                                <div className="p-4 bg-gray-50 rounded-lg text-center">
                                    <div className="text-2xl font-bold text-gray-900">{selectedOrg.total_users}</div>
                                    <div className="text-sm text-gray-500">Total Users</div>
                                </div>
                                <div className="p-4 bg-gray-50 rounded-lg text-center">
                                    <div className="text-2xl font-bold text-gray-900">{selectedOrg.total_clusters}</div>
                                    <div className="text-sm text-gray-500">Clusters</div>
                                </div>
                                <div className="p-4 bg-gray-50 rounded-lg text-center">
                                    <div className="text-2xl font-bold text-gray-900">{selectedOrg.total_instances}</div>
                                    <div className="text-sm text-gray-500">Instances</div>
                                </div>
                            </div>

                            {/* Additional Info */}
                            <div className="space-y-4">
                                <div>
                                    <h4 className="text-sm font-medium text-gray-700 uppercase tracking-wider mb-2">Owner Information</h4>
                                    <div className="bg-gray-50 p-4 rounded-lg">
                                        <div className="flex items-center gap-3">
                                            <div className="h-10 w-10 rounded-full bg-indigo-100 flex items-center justify-center text-indigo-600 font-bold">
                                                {selectedOrg.owner_email ? selectedOrg.owner_email[0].toUpperCase() : '?'}
                                            </div>
                                            <div>
                                                <div className="font-medium text-gray-900">{selectedOrg.owner_email || 'No Owner Assigned'}</div>
                                                <div className="text-sm text-gray-500">Organization Owner</div>
                                            </div>
                                        </div>
                                    </div>
                                </div>

                                <div>
                                    <h4 className="text-sm font-medium text-gray-700 uppercase tracking-wider mb-2">Metadata</h4>
                                    <div className="grid grid-cols-2 gap-4 text-sm">
                                        <div>
                                            <span className="text-gray-500">Created At:</span>
                                            <span className="ml-2 text-gray-900">{format(new Date(selectedOrg.created_at), 'PPP pp')}</span>
                                        </div>
                                    </div>
                                </div>
                            </div>
                        </div>
                        <div className="p-6 border-t border-gray-200 flex justify-end">
                            <button
                                onClick={() => setSelectedOrg(null)}
                                className="px-4 py-2 bg-gray-100 text-gray-700 rounded-lg hover:bg-gray-200 transition-colors"
                            >
                                Close
                            </button>
                        </div>
                    </div>
                </div>
            )}
        </div>
    );
};

export default AdminOrganizations;
