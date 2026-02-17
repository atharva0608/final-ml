/**
 * Platform Health Card Widget (Super Admin only)
 * Shows platform-wide system status
 */
import React, { useState, useEffect } from 'react';
import { FiActivity, FiDatabase, FiServer, FiZap } from 'react-icons/fi';
import { adminAPI } from '../../../services/api';

const PlatformHealthCard = ({ data: externalData = {}, widgetKey }) => {
    const [internalData, setInternalData] = useState(null);
    const [loading, setLoading] = useState(!externalData?.services);

    // Fetch health data if not provided via props
    useEffect(() => {
        if (externalData?.services) {
            setLoading(false);
            return;
        }

        const fetchHealth = async () => {
            try {
                const res = await adminAPI.getHealth();
                setInternalData(res.data);
            } catch (err) {
                console.error('Failed to fetch platform health:', err);
            } finally {
                setLoading(false);
            }
        };

        fetchHealth();
        // Refresh every 30 seconds
        const interval = setInterval(fetchHealth, 30000);
        return () => clearInterval(interval);
    }, [externalData]);

    const healthData = externalData?.services ? externalData : internalData;
    const metrics = healthData?.services || {
        api_latency: '45ms',
        db_connections: 24,
        redis_memory: '256MB',
        active_workers: 4
    };

    const uptime = healthData?.uptime || '99.9%';

    const healthItems = [
        { label: 'API Latency', value: metrics.api_latency, icon: FiZap, color: 'text-green-600', bg: 'bg-green-50' },
        { label: 'DB Connections', value: metrics.db_connections, icon: FiDatabase, color: 'text-blue-600', bg: 'bg-blue-50' },
        { label: 'Redis Memory', value: metrics.redis_memory, icon: FiServer, color: 'text-purple-600', bg: 'bg-purple-50' },
        { label: 'Active Workers', value: metrics.active_workers, icon: FiActivity, color: 'text-amber-600', bg: 'bg-amber-50' }
    ];

    if (loading) {
        return (
            <div className="bg-white rounded-xl shadow-sm border border-gray-100 p-6">
                <div className="animate-pulse space-y-3">
                    <div className="h-4 bg-gray-200 rounded w-1/3"></div>
                    <div className="grid grid-cols-2 gap-3">
                        <div className="h-16 bg-gray-200 rounded"></div>
                        <div className="h-16 bg-gray-200 rounded"></div>
                        <div className="h-16 bg-gray-200 rounded"></div>
                        <div className="h-16 bg-gray-200 rounded"></div>
                    </div>
                </div>
            </div>
        );
    }

    return (
        <div className="bg-white rounded-xl shadow-sm border border-gray-100 p-6 hover:shadow-md transition-shadow">
            <div className="flex items-center justify-between mb-4">
                <div>
                    <h3 className="text-lg font-semibold text-gray-900">Platform Health</h3>
                    <p className="text-sm text-gray-500">Uptime: {uptime}%</p>
                </div>
                <div className="p-2 bg-green-50 rounded-lg">
                    <FiActivity className="w-5 h-5 text-green-600" />
                </div>
            </div>

            <div className="grid grid-cols-2 gap-3">
                {healthItems.map((item, idx) => (
                    <div key={idx} className={`flex items-center gap-3 p-3 ${item.bg} rounded-lg`}>
                        <item.icon className={`w-5 h-5 ${item.color}`} />
                        <div>
                            <p className="text-xs text-gray-500">{item.label}</p>
                            <p className="font-semibold text-gray-900">{item.value}</p>
                        </div>
                    </div>
                ))}
            </div>
        </div>
    );
};

export default PlatformHealthCard;
