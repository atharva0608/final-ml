/**
 * Agent Status Widget
 * Shows clusters with agents, their last heartbeat, and reconnect options
 */
import React, { useState, useEffect } from 'react';
import { FiActivity, FiCheckCircle, FiAlertCircle, FiXCircle, FiRefreshCw } from 'react-icons/fi';
import { clusterAPI } from '../../../services/api';
import { formatDistanceToNow } from 'date-fns';

const AgentStatusWidget = ({ data: externalData, widgetKey }) => {
    const [internalData, setInternalData] = useState([]);
    const [loading, setLoading] = useState(!externalData);
    const [reconnecting, setReconnecting] = useState(null);

    useEffect(() => {
        if (externalData) {
            setLoading(false);
            return;
        }

        fetchAgents();
        // Refresh every 30 seconds
        const interval = setInterval(fetchAgents, 30000);
        return () => clearInterval(interval);
    }, [externalData]);

    const fetchAgents = async () => {
        try {
            const res = await clusterAPI.list();
            const clusters = res.data.clusters || res.data || [];

            // Filter only clusters with agents installed
            const clustersWithAgents = clusters.filter(c => c.agent_installed);

            setInternalData(clustersWithAgents);
        } catch (err) {
            console.error('Failed to fetch agent status:', err);
        } finally {
            setLoading(false);
        }
    };

    const handleReconnect = async (clusterId) => {
        setReconnecting(clusterId);
        try {
            // Call cluster reconnect endpoint (could be implement as POST /clusters/{id}/reconnect)
            await clusterAPI.reconnectAgent?.(clusterId);
            // Refresh data after reconnect attempt
            await fetchAgents();
        } catch (err) {
            console.error('Failed to reconnect agent:', err);
        } finally {
            setReconnecting(null);
        }
    };

    const getHeartbeatStatus = (lastHeartbeat) => {
        if (!lastHeartbeat) return { status: 'stale', color: 'text-gray-400', bg: 'bg-gray-50', icon: FiXCircle };

        const heartbeatTime = new Date(lastHeartbeat);
        const now = new Date();
        const diffMinutes = (now - heartbeatTime) / 1000 / 60;

        if (diffMinutes < 10) {
            return { status: 'healthy', color: 'text-green-600', bg: 'bg-green-50', icon: FiCheckCircle };
        } else if (diffMinutes < 30) {
            return { status: 'warning', color: 'text-yellow-600', bg: 'bg-yellow-50', icon: FiAlertCircle };
        } else {
            return { status: 'stale', color: 'text-red-600', bg: 'bg-red-50', icon: FiXCircle };
        }
    };

    if (loading) {
        return (
            <div className="bg-white rounded-xl shadow-sm border border-gray-100 p-6">
                <div className="animate-pulse space-y-3">
                    <div className="h-4 bg-gray-200 rounded w-1/2"></div>
                    <div className="h-12 bg-gray-200 rounded"></div>
                    <div className="h-12 bg-gray-200 rounded"></div>
                </div>
            </div>
        );
    }

    const agents = externalData || internalData;
    const healthyCount = agents.filter(a => getHeartbeatStatus(a.last_heartbeat).status === 'healthy').length;
    const warningCount = agents.filter(a => getHeartbeatStatus(a.last_heartbeat).status === 'warning').length;
    const staleCount = agents.filter(a => getHeartbeatStatus(a.last_heartbeat).status === 'stale').length;

    return (
        <div className="bg-white rounded-xl shadow-sm border border-gray-100 p-6 hover:shadow-md transition-shadow">
            <div className="flex items-center justify-between mb-4">
                <div>
                    <h3 className="text-lg font-semibold text-gray-900">Agent Status</h3>
                    <p className="text-sm text-gray-500">
                        {agents.length} agents ({healthyCount} healthy, {warningCount} warning, {staleCount} stale)
                    </p>
                </div>
                <div className="p-2 bg-blue-50 rounded-lg">
                    <FiActivity className="w-5 h-5 text-blue-600" />
                </div>
            </div>

            {agents.length === 0 ? (
                <div className="text-center py-8 text-gray-500">
                    <FiActivity className="w-8 h-8 mx-auto mb-2 text-gray-300" />
                    <p className="text-sm">No agents installed</p>
                    <p className="text-xs mt-1">Install agents on your clusters to monitor health</p>
                </div>
            ) : (
                <div className="space-y-2 max-h-64 overflow-y-auto">
                    {agents.slice(0, 5).map((agent) => {
                        const heartbeatStatus = getHeartbeatStatus(agent.last_heartbeat);
                        const Icon = heartbeatStatus.icon;

                        return (
                            <div
                                key={agent.id}
                                className={`flex items-center justify-between p-3 rounded-lg border ${heartbeatStatus.bg} border-gray-200`}
                            >
                                <div className="flex items-center gap-3 flex-1 min-w-0">
                                    <Icon className={`w-4 h-4 flex-shrink-0 ${heartbeatStatus.color}`} />
                                    <div className="min-w-0 flex-1">
                                        <p className="text-sm font-medium text-gray-900 truncate">
                                            {agent.name}
                                        </p>
                                        <p className="text-xs text-gray-500">
                                            {agent.last_heartbeat
                                                ? `Last seen ${formatDistanceToNow(new Date(agent.last_heartbeat), { addSuffix: true })}`
                                                : 'Never connected'}
                                        </p>
                                    </div>
                                </div>

                                {heartbeatStatus.status !== 'healthy' && (
                                    <button
                                        onClick={() => handleReconnect(agent.id)}
                                        disabled={reconnecting === agent.id}
                                        className="ml-2 p-1.5 text-blue-600 hover:bg-blue-100 rounded transition-colors disabled:opacity-50"
                                        title="Reconnect agent"
                                    >
                                        <FiRefreshCw
                                            className={`w-4 h-4 ${reconnecting === agent.id ? 'animate-spin' : ''}`}
                                        />
                                    </button>
                                )}
                            </div>
                        );
                    })}

                    {agents.length > 5 && (
                        <p className="text-xs text-center text-gray-500 pt-2">
                            +{agents.length - 5} more agents
                        </p>
                    )}
                </div>
            )}
        </div>
    );
};

export default AgentStatusWidget;
