import React, { useEffect, useState } from 'react';
import { Card, Badge, Button } from '../shared';
import { auditAPI } from '../../services/api';
import { FiRefreshCw, FiClock, FiUser, FiActivity } from 'react-icons/fi';
import { useHibernationStore } from '../../store/useHibernationStore';

const HistoryLog = ({ clusterId: propClusterId }) => {
    const { clusterId: storeClusterId } = useHibernationStore && useHibernationStore() || {};
    const clusterId = propClusterId || storeClusterId;
    const [logs, setLogs] = useState([]);
    const [loading, setLoading] = useState(false);

    const fetchLogs = async () => {
        setLoading(true);
        try {
            // Filter by HIBERNATION resource type
            const params = {
                resource_type: 'HIBERNATION',
                limit: 10
            };
            if (clusterId) {
                params.resource_id = clusterId; // Assuming backend filters by resource_id if provided, need to check auditAPI
            }

            const res = await auditAPI.list(params);
            setLogs(res.data.logs || []);
        } catch (err) {
            console.error(err);
        } finally {
            setLoading(false);
        }
    };

    useEffect(() => {
        fetchLogs();
    }, [clusterId]);

    return (
        <Card className="overflow-hidden">
            <div className="flex items-center justify-between mb-4">
                <h3 className="text-lg font-semibold text-gray-900">Hibernation History</h3>
                <Button
                    variant="ghost"
                    size="sm"
                    icon={<FiRefreshCw className={loading ? "animate-spin" : ""} />}
                    onClick={fetchLogs}
                >
                    Refresh
                </Button>
            </div>

            <div className="overflow-x-auto">
                <table className="min-w-full text-sm text-left">
                    <thead className="text-xs text-gray-500 uppercase bg-gray-50">
                        <tr>
                            <th className="px-4 py-3">Time</th>
                            <th className="px-4 py-3">Event</th>
                            <th className="px-4 py-3">Actor</th>
                            <th className="px-4 py-3">Outcome</th>
                            <th className="px-4 py-3">Details</th>
                        </tr>
                    </thead>
                    <tbody className="divide-y divide-gray-100">
                        {logs.length === 0 ? (
                            <tr>
                                <td colSpan="5" className="px-4 py-8 text-center text-gray-500">
                                    No history found for current filters
                                </td>
                            </tr>
                        ) : (
                            logs.map((log) => (
                                <tr key={log.id} className="hover:bg-gray-50/50 transition-colors">
                                    <td className="px-4 py-3 whitespace-nowrap text-gray-600">
                                        {new Date(log.timestamp).toLocaleString()}
                                    </td>
                                    <td className="px-4 py-3 font-medium text-gray-900">
                                        {log.event}
                                    </td>
                                    <td className="px-4 py-3">
                                        <div className="flex items-center gap-2">
                                            <FiUser className="w-3 h-3 text-gray-400" />
                                            <span className="text-gray-700">{log.actor_name}</span>
                                        </div>
                                    </td>
                                    <td className="px-4 py-3">
                                        <Badge variant={log.outcome === 'success' ? 'success' : 'error'}>
                                            {log.outcome}
                                        </Badge>
                                    </td>
                                    <td className="px-4 py-3 text-gray-500 truncate max-w-xs" title={JSON.stringify(log.diff_after)}>
                                        {log.resource}
                                    </td>
                                </tr>
                            ))
                        )}
                    </tbody>
                </table>
            </div>
        </Card>
    );
};

export default HistoryLog;
