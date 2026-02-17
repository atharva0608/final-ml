/**
 * Admin Tenant Drilldown Modal
 * Detailed view of organization with tabs for Overview, Members, Clusters, Audit, Billing, Agents
 */
import React, { useState, useEffect } from 'react';
import { FiX, FiUsers, FiServer, FiActivity, FiDollarSign, FiShield, FiInfo } from 'react-icons/fi';
import { adminAPI, clusterAPI, auditAPI } from '../../services/api';
import toast from 'react-hot-toast';
import { formatDistanceToNow } from 'date-fns';

const AdminTenantDrilldown = ({ orgId, onClose }) => {
    const [activeTab, setActiveTab] = useState('overview');
    const [orgData, setOrgData] = useState(null);
    const [loading, setLoading] = useState(true);

    const tabs = [
        { id: 'overview', label: 'Overview', icon: FiInfo },
        { id: 'members', label: 'Members', icon: FiUsers },
        { id: 'clusters', label: 'Clusters', icon: FiServer },
        { id: 'audit', label: 'Audit Log', icon: FiActivity },
        { id: 'billing', label: 'Billing', icon: FiDollarSign },
        { id: 'agents', label: 'Agent Health', icon: FiShield },
    ];

    useEffect(() => {
        if (orgId) {
            fetchOrgDetails();
        }
    }, [orgId]);

    const fetchOrgDetails = async () => {
        setLoading(true);
        try {
            // Fetch organization details
            const res = await adminAPI.getOrganization?.(orgId);
            setOrgData(res.data);
        } catch (err) {
            console.error('Failed to fetch org details:', err);
            toast.error('Failed to load organization details');
        } finally {
            setLoading(false);
        }
    };

    if (!orgId) return null;

    return (
        <div className="fixed inset-0 bg-black bg-opacity-50 z-50 flex items-center justify-center p-4">
            <div className="bg-white rounded-lg shadow-xl max-w-6xl w-full max-h-[90vh] flex flex-col">
                {/* Header */}
                <div className="flex items-center justify-between p-6 border-b border-gray-200">
                    <div>
                        <h2 className="text-2xl font-bold text-gray-900">
                            {orgData?.name || 'Loading...'}
                        </h2>
                        <p className="text-sm text-gray-500 mt-1">
                            {orgData?.slug} • {orgData?.owner_email}
                        </p>
                    </div>
                    <button
                        onClick={onClose}
                        className="p-2 hover:bg-gray-100 rounded-lg transition-colors"
                    >
                        <FiX className="w-6 h-6 text-gray-500" />
                    </button>
                </div>

                {/* Tabs */}
                <div className="border-b border-gray-200 px-6">
                    <nav className="flex space-x-4">
                        {tabs.map((tab) => (
                            <button
                                key={tab.id}
                                onClick={() => setActiveTab(tab.id)}
                                className={`flex items-center gap-2 px-4 py-3 border-b-2 font-medium text-sm transition-colors ${
                                    activeTab === tab.id
                                        ? 'border-blue-500 text-blue-600'
                                        : 'border-transparent text-gray-500 hover:text-gray-700'
                                }`}
                            >
                                <tab.icon className="w-4 h-4" />
                                {tab.label}
                            </button>
                        ))}
                    </nav>
                </div>

                {/* Content */}
                <div className="flex-1 overflow-y-auto p-6">
                    {loading ? (
                        <div className="flex items-center justify-center h-64">
                            <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-600"></div>
                        </div>
                    ) : (
                        <>
                            {activeTab === 'overview' && <OverviewTab data={orgData} />}
                            {activeTab === 'members' && <MembersTab orgId={orgId} />}
                            {activeTab === 'clusters' && <ClustersTab orgId={orgId} />}
                            {activeTab === 'audit' && <AuditTab orgId={orgId} />}
                            {activeTab === 'billing' && <BillingTab orgId={orgId} data={orgData} />}
                            {activeTab === 'agents' && <AgentsTab orgId={orgId} />}
                        </>
                    )}
                </div>
            </div>
        </div>
    );
};

// Overview Tab
const OverviewTab = ({ data }) => (
    <div className="grid grid-cols-2 gap-6">
        <div className="bg-gray-50 p-4 rounded-lg border border-gray-200">
            <h3 className="text-sm font-semibold text-gray-700 mb-3">Organization Info</h3>
            <dl className="space-y-2 text-sm">
                <div className="flex justify-between">
                    <dt className="text-gray-500">ID:</dt>
                    <dd className="font-mono text-gray-900">{data?.id}</dd>
                </div>
                <div className="flex justify-between">
                    <dt className="text-gray-500">Slug:</dt>
                    <dd className="font-medium text-gray-900">{data?.slug}</dd>
                </div>
                <div className="flex justify-between">
                    <dt className="text-gray-500">Status:</dt>
                    <dd>
                        <span className={`px-2 py-0.5 rounded text-xs font-semibold ${
                            data?.is_active ? 'bg-green-100 text-green-700' : 'bg-red-100 text-red-700'
                        }`}>
                            {data?.is_active ? 'Active' : 'Inactive'}
                        </span>
                    </dd>
                </div>
                <div className="flex justify-between">
                    <dt className="text-gray-500">Created:</dt>
                    <dd className="text-gray-900">
                        {data?.created_at ? formatDistanceToNow(new Date(data.created_at), { addSuffix: true }) : 'N/A'}
                    </dd>
                </div>
            </dl>
        </div>

        <div className="bg-gray-50 p-4 rounded-lg border border-gray-200">
            <h3 className="text-sm font-semibold text-gray-700 mb-3">Resource Summary</h3>
            <dl className="space-y-2 text-sm">
                <div className="flex justify-between">
                    <dt className="text-gray-500">Total Users:</dt>
                    <dd className="font-bold text-gray-900">{data?.total_users || 0}</dd>
                </div>
                <div className="flex justify-between">
                    <dt className="text-gray-500">Total Accounts:</dt>
                    <dd className="font-bold text-gray-900">{data?.total_accounts || 0}</dd>
                </div>
                <div className="flex justify-between">
                    <dt className="text-gray-500">Total Clusters:</dt>
                    <dd className="font-bold text-gray-900">{data?.total_clusters || 0}</dd>
                </div>
                <div className="flex justify-between">
                    <dt className="text-gray-500">Total Instances:</dt>
                    <dd className="font-bold text-gray-900">{data?.total_instances || 0}</dd>
                </div>
            </dl>
        </div>
    </div>
);

// Members Tab
const MembersTab = ({ orgId }) => {
    const [members, setMembers] = useState([]);
    const [loading, setLoading] = useState(true);

    useEffect(() => {
        // TODO: Create endpoint to fetch org members
        // For now, show placeholder
        setLoading(false);
    }, [orgId]);

    return (
        <div className="space-y-4">
            <p className="text-sm text-gray-500">Members of this organization</p>
            <div className="text-center py-12 text-gray-400">
                <FiUsers className="w-12 h-12 mx-auto mb-3" />
                <p className="text-sm">Member list coming soon</p>
            </div>
        </div>
    );
};

// Clusters Tab
const ClustersTab = ({ orgId }) => {
    const [clusters, setClusters] = useState([]);
    const [loading, setLoading] = useState(true);

    useEffect(() => {
        const fetchClusters = async () => {
            try {
                const res = await clusterAPI.list({ organization_id: orgId });
                setClusters(res.data.clusters || []);
            } catch (err) {
                console.error('Failed to fetch clusters:', err);
            } finally {
                setLoading(false);
            }
        };
        fetchClusters();
    }, [orgId]);

    if (loading) {
        return <div className="text-center py-12 text-gray-400">Loading clusters...</div>;
    }

    return (
        <div className="space-y-4">
            {clusters.length === 0 ? (
                <div className="text-center py-12 text-gray-400">
                    <FiServer className="w-12 h-12 mx-auto mb-3" />
                    <p className="text-sm">No clusters found</p>
                </div>
            ) : (
                <div className="grid gap-3">
                    {clusters.map((cluster) => (
                        <div key={cluster.id} className="border border-gray-200 rounded-lg p-4 hover:bg-gray-50">
                            <div className="flex items-center justify-between">
                                <div>
                                    <h4 className="font-semibold text-gray-900">{cluster.name}</h4>
                                    <p className="text-xs text-gray-500 mt-1">
                                        {cluster.provider} • {cluster.region} • {cluster.total_nodes || 0} nodes
                                    </p>
                                </div>
                                <span className={`px-2 py-1 rounded text-xs font-semibold ${
                                    cluster.status === 'ACTIVE' ? 'bg-green-100 text-green-700' : 'bg-gray-100 text-gray-700'
                                }`}>
                                    {cluster.status}
                                </span>
                            </div>
                        </div>
                    ))}
                </div>
            )}
        </div>
    );
};

// Audit Tab
const AuditTab = ({ orgId }) => (
    <div className="text-center py-12 text-gray-400">
        <FiActivity className="w-12 h-12 mx-auto mb-3" />
        <p className="text-sm">Audit log filtering by organization coming soon</p>
    </div>
);

// Billing Tab
const BillingTab = ({ orgId, data }) => (
    <div className="space-y-4">
        <div className="bg-gray-50 p-4 rounded-lg border border-gray-200">
            <h3 className="text-sm font-semibold text-gray-700 mb-3">Billing Info</h3>
            <p className="text-sm text-gray-500">Stripe customer ID: {data?.stripe_customer_id || 'Not connected'}</p>
            <p className="text-sm text-gray-500 mt-2">Subscription plan: {data?.subscription_plan || 'Free'}</p>
        </div>
    </div>
);

// Agents Tab
const AgentsTab = ({ orgId }) => (
    <div className="text-center py-12 text-gray-400">
        <FiShield className="w-12 h-12 mx-auto mb-3" />
        <p className="text-sm">Agent health monitoring coming soon</p>
    </div>
);

export default AdminTenantDrilldown;
