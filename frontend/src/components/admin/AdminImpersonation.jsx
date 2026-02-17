/**
 * Admin Impersonation Tab
 * Allows super admin to impersonate organizations for debugging and support
 */
import React, { useState, useEffect } from 'react';
import { Card, Button, Input } from '../shared';
import { FiSearch, FiUser, FiLogIn, FiAlertTriangle } from 'react-icons/fi';
import { adminAPI } from '../../services/api';
import toast from 'react-hot-toast';

const AdminImpersonation = () => {
    const [organizations, setOrganizations] = useState([]);
    const [filteredOrgs, setFilteredOrgs] = useState([]);
    const [searchQuery, setSearchQuery] = useState('');
    const [loading, setLoading] = useState(true);
    const [impersonating, setImpersonating] = useState(null);
    const [isImpersonated, setIsImpersonated] = useState(false);

    useEffect(() => {
        fetchOrganizations();
        // Check if currently impersonating
        const impersonationData = localStorage.getItem('impersonation');
        if (impersonationData) {
            setIsImpersonated(true);
        }
    }, []);

    useEffect(() => {
        if (searchQuery.trim() === '') {
            setFilteredOrgs(organizations);
        } else {
            const query = searchQuery.toLowerCase();
            const filtered = organizations.filter(org =>
                org.name.toLowerCase().includes(query) ||
                org.slug.toLowerCase().includes(query) ||
                (org.owner_email && org.owner_email.toLowerCase().includes(query))
            );
            setFilteredOrgs(filtered);
        }
    }, [searchQuery, organizations]);

    const fetchOrganizations = async () => {
        try {
            const res = await adminAPI.listOrganizations({ page: 1, page_size: 100 });
            setOrganizations(res.data.organizations || []);
            setFilteredOrgs(res.data.organizations || []);
        } catch (err) {
            console.error('Failed to fetch organizations:', err);
            toast.error('Failed to load organizations');
        } finally {
            setLoading(false);
        }
    };

    const handleImpersonate = async (org) => {
        setImpersonating(org.id);
        try {
            // Call the impersonate API endpoint
            const res = await adminAPI.impersonate(org.id);

            // Store impersonation data
            const impersonationData = {
                orgId: org.id,
                orgName: org.name,
                originalToken: localStorage.getItem('token'),
                impersonatedToken: res.data.token,
                timestamp: new Date().toISOString()
            };

            localStorage.setItem('impersonation', JSON.stringify(impersonationData));
            localStorage.setItem('token', res.data.token);

            toast.success(`Now viewing as ${org.name}`);
            setIsImpersonated(true);

            // Reload the page to apply the new token
            setTimeout(() => {
                window.location.href = '/dashboard';
            }, 1000);
        } catch (err) {
            console.error('Failed to impersonate:', err);
            toast.error(err.response?.data?.message || 'Failed to impersonate organization');
        } finally {
            setImpersonating(null);
        }
    };

    const handleExitImpersonation = () => {
        const impersonationData = JSON.parse(localStorage.getItem('impersonation'));
        if (impersonationData && impersonationData.originalToken) {
            localStorage.setItem('token', impersonationData.originalToken);
            localStorage.removeItem('impersonation');
            toast.success('Exited impersonation mode');
            setTimeout(() => {
                window.location.href = '/admin';
            }, 500);
        }
    };

    if (loading) {
        return (
            <div className="space-y-4">
                <div className="animate-pulse">
                    <div className="h-10 bg-gray-200 rounded mb-4"></div>
                    <div className="h-64 bg-gray-200 rounded"></div>
                </div>
            </div>
        );
    }

    return (
        <div className="space-y-6">
            {/* Impersonation Banner */}
            {isImpersonated && (
                <div className="bg-red-50 border-l-4 border-red-500 p-4 rounded-lg">
                    <div className="flex items-center justify-between">
                        <div className="flex items-center gap-3">
                            <FiAlertTriangle className="w-5 h-5 text-red-600" />
                            <div>
                                <p className="text-sm font-semibold text-red-900">
                                    You are viewing as {JSON.parse(localStorage.getItem('impersonation'))?.orgName}
                                </p>
                                <p className="text-xs text-red-700 mt-0.5">
                                    Actions performed will be attributed to this organization
                                </p>
                            </div>
                        </div>
                        <Button variant="outline" size="sm" onClick={handleExitImpersonation}>
                            Exit Impersonation
                        </Button>
                    </div>
                </div>
            )}

            <Card>
                <div className="mb-6">
                    <h2 className="text-xl font-bold text-gray-900 mb-2">Impersonate Organization</h2>
                    <p className="text-sm text-gray-600">
                        Search and impersonate an organization to debug or support them. Use this feature with caution.
                    </p>
                </div>

                {/* Search Bar */}
                <div className="mb-6">
                    <div className="relative">
                        <FiSearch className="absolute left-3 top-3 text-gray-400 w-5 h-5" />
                        <input
                            type="text"
                            placeholder="Search by organization name, slug, or owner email..."
                            value={searchQuery}
                            onChange={(e) => setSearchQuery(e.target.value)}
                            className="w-full pl-10 pr-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent"
                        />
                    </div>
                    <p className="text-xs text-gray-500 mt-2">
                        Found {filteredOrgs.length} organization{filteredOrgs.length !== 1 ? 's' : ''}
                    </p>
                </div>

                {/* Organizations List */}
                <div className="space-y-2 max-h-96 overflow-y-auto">
                    {filteredOrgs.length === 0 ? (
                        <div className="text-center py-12 text-gray-500">
                            <FiUser className="w-12 h-12 mx-auto mb-3 text-gray-300" />
                            <p className="text-sm">No organizations found</p>
                        </div>
                    ) : (
                        filteredOrgs.map((org) => (
                            <div
                                key={org.id}
                                className="flex items-center justify-between p-4 border border-gray-200 rounded-lg hover:bg-gray-50 transition-colors"
                            >
                                <div className="flex-1">
                                    <div className="flex items-center gap-2">
                                        <h3 className="font-semibold text-gray-900">{org.name}</h3>
                                        <span className="text-xs px-2 py-0.5 bg-gray-100 text-gray-600 rounded">
                                            {org.slug}
                                        </span>
                                    </div>
                                    <div className="flex items-center gap-4 mt-1 text-xs text-gray-500">
                                        {org.owner_email && (
                                            <span className="flex items-center gap-1">
                                                <FiUser className="w-3 h-3" />
                                                {org.owner_email}
                                            </span>
                                        )}
                                        <span>{org.total_clusters || 0} clusters</span>
                                        <span>{org.total_users || 0} users</span>
                                        <span className={`font-medium ${org.is_active ? 'text-green-600' : 'text-red-600'}`}>
                                            {org.is_active ? 'Active' : 'Inactive'}
                                        </span>
                                    </div>
                                </div>
                                <Button
                                    variant="primary"
                                    size="sm"
                                    icon={<FiLogIn />}
                                    onClick={() => handleImpersonate(org)}
                                    disabled={impersonating === org.id || !org.is_active}
                                >
                                    {impersonating === org.id ? 'Impersonating...' : 'Impersonate'}
                                </Button>
                            </div>
                        ))
                    )}
                </div>
            </Card>

            {/* Security Notice */}
            <div className="bg-yellow-50 border border-yellow-200 rounded-lg p-4">
                <div className="flex items-start gap-3">
                    <FiAlertTriangle className="w-5 h-5 text-yellow-600 flex-shrink-0 mt-0.5" />
                    <div className="text-sm text-yellow-800">
                        <p className="font-semibold mb-1">Security Notice</p>
                        <ul className="list-disc list-inside space-y-1 text-xs">
                            <li>All actions performed while impersonating are logged in the global audit log</li>
                            <li>Impersonation sessions expire after 4 hours</li>
                            <li>You cannot impersonate inactive organizations</li>
                            <li>Remember to exit impersonation mode when done</li>
                        </ul>
                    </div>
                </div>
            </div>
        </div>
    );
};

export default AdminImpersonation;
