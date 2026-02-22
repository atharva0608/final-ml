import React, { useEffect, useState } from 'react';
import { Card } from '../shared';
import { FiActivity, FiArrowRight, FiCheckCircle, FiAlertTriangle, FiClock, FiServer } from 'react-icons/fi';
import api from '../../services/api';

const RebalancingTimeline = () => {
    const [events, setEvents] = useState([]);
    const [loading, setLoading] = useState(true);

    useEffect(() => {
        fetchHistory();
    }, []);

    const fetchHistory = async () => {
        try {
            // Fetch rebalancing status from the new endpoint
            const response = await api.get('/api/v1/atharvaai/rebalancing/status?limit=20');
            setEvents(response.data || []);
        } catch (error) {
            console.error("Failed to fetch rebalancing history:", error);
            setEvents([]);
        } finally {
            setLoading(false);
        }
    };

    const getStatusIcon = (status) => {
        switch (status) {
            case 'completed': return <FiCheckCircle className="text-green-500 w-5 h-5" />;
            case 'failed': return <FiAlertTriangle className="text-red-500 w-5 h-5" />;
            case 'in_progress': return <FiActivity className="text-blue-500 w-5 h-5 animate-pulse" />;
            default: return <FiClock className="text-gray-400 w-5 h-5" />;
        }
    };

    const formatTime = (isoString) => {
        if (!isoString) return '';
        const date = new Date(isoString);
        return date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
    };

    const formatDuration = (seconds) => {
        if (!seconds) return '';
        if (seconds < 60) return `${seconds}s`;
        return `${Math.floor(seconds / 60)}m ${seconds % 60}s`;
    };

    if (loading) return <div className="p-4 text-center text-gray-400">Loading timeline...</div>;

    return (
        <Card className="h-full flex flex-col">
            <div className="flex items-center justify-between mb-4">
                <h3 className="font-semibold text-gray-800 flex items-center gap-2">
                    <FiActivity className="text-blue-600" />
                    Rebalancing Timeline
                </h3>
                <span className="text-xs text-gray-500">Last 24 Hours</span>
            </div>

            <div className="flex-1 overflow-y-auto pr-2 space-y-4 max-h-[400px] scrollbar-thin scrollbar-thumb-gray-200">
                {events.length === 0 ? (
                    <div className="text-center py-8 text-gray-400 text-sm">No rebalancing events recorded</div>
                ) : (
                    events.map((event, idx) => (
                        <div key={idx} className="relative pl-6 pb-4 border-l-2 border-gray-100 last:border-0 last:pb-0">
                            {/* Dot */}
                            <div className={`absolute -left-[9px] top-0 w-4 h-4 rounded-full border-2 border-white shadow-sm flex items-center justify-center ${event.trigger === 'emergency' ? 'bg-red-100' : 'bg-blue-100'
                                }`}>
                                <div className={`w-2 h-2 rounded-full ${event.trigger === 'emergency' ? 'bg-red-500' : 'bg-blue-500'
                                    }`} />
                            </div>

                            <div className="flex items-start justify-between">
                                <div>
                                    <div className="flex items-center gap-2 mb-1">
                                        <span className={`text-xs font-bold uppercase px-1.5 py-0.5 rounded ${event.trigger === 'emergency' ? 'bg-red-100 text-red-700' : 'bg-blue-100 text-blue-700'
                                            }`}>
                                            {event.trigger}
                                        </span>
                                        <span className="text-xs text-gray-400">{formatTime(event.started_at)}</span>
                                    </div>

                                    <div className="flex items-center gap-2 text-sm font-medium text-gray-700">
                                        <span>{event.source_pool}</span>
                                        <FiArrowRight className="text-gray-400 w-3 h-3" />
                                        <span>{event.target_pool}</span>
                                    </div>

                                    <div className="flex items-center gap-3 mt-1 text-xs text-gray-500">
                                        {(event.nodes_affected || event.pods_migrated) && (
                                            <span className="flex items-center gap-1">
                                                <FiServer className="w-3 h-3" />
                                                {event.nodes_affected > 0 ? `${event.nodes_affected} nodes` : ''}
                                                {event.nodes_affected && event.pods_migrated ? ', ' : ''}
                                                {event.pods_migrated > 0 ? `${event.pods_migrated} pods` : ''}
                                            </span>
                                        )}
                                        {event.duration_seconds && (
                                            <span className="flex items-center gap-1">
                                                <FiClock className="w-3 h-3" />
                                                {formatDuration(event.duration_seconds)}
                                            </span>
                                        )}
                                    </div>

                                    {event.error_message && (
                                        <div className="mt-1 text-xs text-red-600 bg-red-50 px-2 py-1 rounded border border-red-100">
                                            Error: {event.error_message}
                                        </div>
                                    )}
                                </div>

                                <div className="ml-2 pt-1" title={event.status}>
                                    {getStatusIcon(event.status)}
                                </div>
                            </div>
                        </div>
                    ))
                )}
            </div>
        </Card>
    );
};

export default RebalancingTimeline;
