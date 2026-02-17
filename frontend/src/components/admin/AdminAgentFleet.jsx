/**
 * Admin Agent Fleet Tab
 * Platform-wide view of all agents across all organizations
 */
import React, { useState, useEffect } from 'react';
import { Card } from '../shared';
import { FiActivity, FiCheckCircle, FiAlertTriangle, FiXCircle, FiRefreshCw, FiDownload } from 'react-icons/fi';
import { adminAPI } from '../../services/api';
import toast from 'react-hot-toast';
import { formatDistanceToNow } from 'date-fns';

const AdminAgentFleet = () => {
    const [agents, setAgents] = useState([]);
    const [filteredAgents, setFilteredAgents] = useState([]);
    const [loading, setLoading] = useState(true);
    const [statusFilter, setStatusFilter] = useState('all');
    const [searchQuery, setSearchQuery] = useState('');

    useEffect(() => {
        fetchAgentFleet();
        // Auto-refresh every 30 seconds
        const interval = setInterval(fetchAgentFleet, 30000);
        return () => clearInterval(interval);
    }, []);

    useEffect(() => {
        applyFilters();
    }, [agents, statusFilter, searchQuery]);

    const fetchAgentFleet = async () => {
        try {
            const res = await adminAPI.getAgentFleet();
            setAgents(res.data || []);
        } catch (err) {
            console.error('Failed to fetch agent fleet:', err);
            toast.error('Failed to load agent fleet');
        } finally {
            setLoading(false);
        }
    };

    const applyFilters = () => {
        let filtered = agents;

        // Status filter
        if (statusFilter !== 'all') {
            filtered = filtered.filter(agent => getHeartbeatStatus(agent.last_heartbeat).status === statusFilter);
        }

        // Search filter
        if (searchQuery.trim()) {
            const query = searchQuery.toLowerCase();
            filtered = filtered.filter(agent =>
                agent.organization_name?.toLowerCase().includes(query) ||
                agent.cluster_name?.toLowerCase().includes(query) ||
                agent.region?.toLowerCase().includes(query)
            );
        }

        setFilteredAgents(filtered);
    };

    const getHeartbeatStatus = (lastHeartbeat) => {
        if (!lastHeartbeat) {
            return { status: 'stale', color: 'text-gray-400', bgColor: 'bg-gray-50', dotColor: 'bg-gray-400', label: 'Never Connected' };
        }

        const heartbeatTime = new Date(lastHeartbeat);
        const now = new Date();
        const diffMinutes = (now - heartbeatTime) / 1000 / 60;

        if (diffMinutes < 10) {
            return { status: 'healthy', color: 'text-green-600', bgColor: 'bg-green-50', dotColor: 'bg-green-500', label: 'Healthy' };
        } else if (diffMinutes < 30) {
            return { status: 'warning', color: 'text-yellow-600', bgColor: 'bg-yellow-50', dotColor: 'bg-yellow-500', label: 'Warning' };
        } else {
            return { status: 'stale', color: 'text-red-600', bgColor: 'bg-red-50', dotColor: 'bg-red-500', label: 'Stale' };
        }
    };

    const exportCSV = () => {
        const headers = ['Organization', 'Cluster', 'Region', 'Agent Version', 'Last Heartbeat', 'Status'];
        const rows = filteredAgents.map(agent => [
            agent.organization_name,
            agent.cluster_name,
            agent.region,
            agent.agent_version || 'N/A',
            agent.last_heartbeat || 'Never',
            getHeartbeatStatus(agent.last_heartbeat).label
        ]);

        const csv = [headers, ...rows].map(row => row.join(',')).join('\n');
        const blob = new Blob([csv], { type: 'text/csv' });
        const url = window.URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `agent-fleet-${new Date().toISOString().split('T')[0]}.csv`;
        a.click();
        window.URL.revokeObjectURL(url);
    };

    const healthyCount = agents.filter(a => getHeartbeatStatus(a.last_heartbeat).status === 'healthy').length;
    const warningCount = agents.filter(a => getHeartbeatStatus(a.last_heartbeat).status === 'warning').length;
    const staleCount = agents.filter(a => getHeartbeatStatus(a.last_heartbeat).status === 'stale').length;

    if (loading) {
        return (
            <div className="space-y-4">
                <div className="animate-pulse">
                    <div className="h-32 bg-gray-200 rounded-lg mb-4"></div>
                    <div className="h-96 bg-gray-200 rounded-lg"></div>
                </div>
            </div>
        );
    }

    return (
        <div className="space-y-6">
            {/* Stats Cards */}
            <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
                <Card className="p-4">
                    <div className="flex items-center justify-between">
                        <div>
                            <p className="text-sm text-gray-500">Total Agents</p>
                            <p className="text-2xl font-bold text-gray-900">{agents.length}</p>
                        </div>
                        <FiActivity className="w-8 h-8 text-blue-600" />
                    </div>
                </Card>

                <Card className="p-4">
                    <div className="flex items-center justify-between">
                        <div>
                            <p className="text-sm text-gray-500">Healthy</p>
                            <p className="text-2xl font-bold text-green-600">{healthyCount}</p>
                        </div>
                        <FiCheckCircle className="w-8 h-8 text-green-600" />
                    </div>
                </Card>

                <Card className="p-4">
                    <div className="flex items-center justify-between">
                        <div>
                            <p className="text-sm text-gray-500">Warning</p>
                            <p className="text-2xl font-bold text-yellow-600">{warningCount}</p>
                        </div>
                        <FiAlertTriangle className="w-8 h-8 text-yellow-600" />
                    </div>
                </Card>

                <Card className="p-4">
                    <div className="flex items-center justify-between">
                        <div>
                            <p className="text-sm text-gray-500">Stale</p>
                            <p className="text-2xl font-bold text-red-600">{staleCount}</p>
                        </div>
                        <FiXCircle className="w-8 h-8 text-red-600" />
                    </div>
                </Card>
            </div>

            {/* Filters */}
            <Card className="p-4">
                <div className="flex items-center justify-between gap-4">
                    <div className="flex items-center gap-4 flex-1">
                        {/* Search */}
                        <input
                            type="text"
                            placeholder="Search by org, cluster, or region..."
                            value={searchQuery}
                            onChange={(e) => setSearchQuery(e.target.value)}
                            className="flex-1 px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent"
                        />

                        {/* Status Filter */}
                        <select
                            value={statusFilter}
                            onChange={(e) => setStatusFilter(e.target.value)}
                            className="px-4 py-2 border border-gray-300 rounded-lg bg-white focus:ring-2 focus:ring-blue-500 focus:border-transparent"
                        >
                            <option value="all">All Status</option>
                            <option value="healthy">Healthy Only</option>
                            <option value="warning">Warning Only</option>
                            <option value="stale">Stale Only</option>
                        </select>
                    </div>

                    <div className="flex items-center gap-2">
                        <button
                            onClick={fetchAgentFleet}
                            className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors flex items-center gap-2"
                        >
                            <FiRefreshCw className="w-4 h-4" />
                            Refresh
                        </button>

                        <button
                            onClick={exportCSV}
                            className="px-4 py-2 bg-gray-100 text-gray-700 rounded-lg hover:bg-gray-200 transition-colors flex items-center gap-2"
                        >
                            <FiDownload className="w-4 h-4" />
                            Export CSV
                        </button>
                    </div>
                </div>

                <p className="text-xs text-gray-500 mt-2">
                    Showing {filteredAgents.length} of {agents.length} agents
                </p>
            </Card>

            {/* Agent Table */}
            <Card>
                <div className="overflow-x-auto">
                    <table className="w-full">
                        <thead className="bg-gray-50 border-b border-gray-200">
                            <tr>
                                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                                    Status
                                </th>
                                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                                    Organization
                                </th>
                                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                                    Cluster
                                </th>
                                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                                    Region
                                </th>
                                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                                    Agent Version
                                </th>
                                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                                    Last Heartbeat
                                </th>
                            </tr>
                        </thead>
                        <tbody className="bg-white divide-y divide-gray-200">
                            {filteredAgents.length === 0 ? (
                                <tr>
                                    <td colSpan="6" className="px-6 py-12 text-center text-gray-500">
                                        <FiActivity className="w-12 h-12 mx-auto mb-3 text-gray-300" />
                                        <p className="text-sm">No agents found</p>
                                    </td>
                                </tr>
                            ) : (
                                filteredAgents.map((agent) => {
                                    const heartbeatStatus = getHeartbeatStatus(agent.last_heartbeat);
                                    return (
                                        <tr key={agent.cluster_id} className="hover:bg-gray-50 transition-colors">
                                            <td className="px-6 py-4 whitespace-nowrap">
                                                <div className="flex items-center gap-2">
                                                    <div className={`w-3 h-3 rounded-full ${heartbeatStatus.dotColor}`}></div>
                                                    <span className={`text-sm font-medium ${heartbeatStatus.color}`}>
                                                        {heartbeatStatus.label}
                                                    </span>
                                                </div>
                                            </td>
                                            <td className="px-6 py-4 whitespace-nowrap">
                                                <div className="text-sm font-medium text-gray-900">
                                                    {agent.organization_name}
                                                </div>
                                            </td>
                                            <td className="px-6 py-4 whitespace-nowrap">
                                                <div className="text-sm text-gray-900">{agent.cluster_name}</div>
                                            </td>
                                            <td className="px-6 py-4 whitespace-nowrap">
                                                <span className="px-2 py-1 text-xs font-medium bg-blue-100 text-blue-700 rounded">
                                                    {agent.region}
                                                </span>
                                            </td>
                                            <td className="px-6 py-4 whitespace-nowrap">
                                                <div className="text-sm text-gray-900 font-mono">
                                                    {agent.agent_version || 'N/A'}
                                                </div>
                                            </td>
                                            <td className="px-6 py-4 whitespace-nowrap">
                                                <div className="text-sm text-gray-500">
                                                    {agent.last_heartbeat
                                                        ? formatDistanceToNow(new Date(agent.last_heartbeat), { addSuffix: true })
                                                        : 'Never'}
                                                </div>
                                            </td>
                                        </tr>
                                    );
                                })
                            )}
                        </tbody>
                    </table>
                </div>
            </Card>
        </div>
    );
};

export default AdminAgentFleet;
