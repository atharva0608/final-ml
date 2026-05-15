import React, { useEffect, useState } from 'react';
import { Card } from '../../../components/shared';
import { FiActivity, FiCheckCircle, FiAlertTriangle, FiXCircle } from 'react-icons/fi';
import api from '../../../services/api';

const ClusterHealthTimeline = ({ clusterId }) => {
    const [events, setEvents] = useState([]);
    const [loading, setLoading] = useState(true);

    useEffect(() => {
        const fetchData = async () => {
            try {
                if (!clusterId) return;
                const res = await api.get(`/metrics/cluster/${clusterId}/health-timeline`);
                setEvents(res.data);
            } catch (err) {
                console.error("Failed to load health timeline", err);
            } finally {
                setLoading(false);
            }
        };
        fetchData();
    }, [clusterId]);

    const getIcon = (status) => {
        switch (status) {
            case 'healthy': return <FiCheckCircle className="text-green-500" />;
            case 'degraded': return <FiAlertTriangle className="text-yellow-500" />;
            case 'unavailable': return <FiXCircle className="text-red-500" />;
            default: return <FiActivity className="text-gray-400" />;
        }
    };

    if (loading) return <div className="h-48 bg-gray-50 animate-pulse rounded-lg"></div>;

    return (
        <Card title="Health Timeline (24h)" className="h-full">
            <div className="relative border-l-2 border-gray-100 ml-3 space-y-6 py-2">
                {events.map((event, idx) => (
                    <div key={idx} className="relative pl-6">
                        <div className="absolute -left-[9px] top-0 bg-white p-0.5 rounded-full">
                            {getIcon(event.status)}
                        </div>
                        <div>
                            <p className="text-xs text-gray-400 mb-0.5">
                                {new Date(event.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
                            </p>
                            <p className="text-sm font-medium text-gray-800">{event.message}</p>
                            <span className={`text-[10px] uppercase font-bold px-1.5 py-0.5 rounded ${event.status === 'healthy' ? 'bg-green-50 text-green-700' :
                                    event.status === 'degraded' ? 'bg-yellow-50 text-yellow-700' :
                                        'bg-red-50 text-red-700'
                                }`}>
                                {event.status}
                            </span>
                        </div>
                    </div>
                ))}
            </div>
        </Card>
    );
};

export default ClusterHealthTimeline;
