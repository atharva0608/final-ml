/**
 * Activity Feed Widget
 * Shows recent actions and events
 */
import React from 'react';
import { FiClock, FiCheck, FiX, FiAlertCircle } from 'react-icons/fi';
import { formatRelativeTime } from '../../../utils/formatters';

const ActivityFeed = ({ data = {}, widgetKey }) => {
    const activities = data.activities || [
        { id: 1, action: 'Instance terminated', resource: 'i-1234567890', status: 'success', time: new Date(Date.now() - 300000) },
        { id: 2, action: 'Cluster scaled down', resource: 'prod-cluster', status: 'success', time: new Date(Date.now() - 900000) },
        { id: 3, action: 'Cleanup scheduled', resource: 'staging-vpc', status: 'pending', time: new Date(Date.now() - 1800000) },
        { id: 4, action: 'Action rejected', resource: 'dev-instance', status: 'failed', time: new Date(Date.now() - 3600000) }
    ];

    const getStatusIcon = (status) => {
        switch (status) {
            case 'success': return <FiCheck className="w-4 h-4 text-green-500" />;
            case 'failed': return <FiX className="w-4 h-4 text-red-500" />;
            case 'pending': return <FiAlertCircle className="w-4 h-4 text-amber-500" />;
            default: return <FiClock className="w-4 h-4 text-gray-400" />;
        }
    };

    return (
        <div className="bg-white rounded-xl shadow-sm border border-gray-100 p-6 hover:shadow-md transition-shadow">
            <div className="flex items-center justify-between mb-4">
                <div>
                    <h3 className="text-lg font-semibold text-gray-900">Activity Feed</h3>
                    <p className="text-sm text-gray-500">Recent actions</p>
                </div>
                <div className="p-2 bg-gray-50 rounded-lg">
                    <FiClock className="w-5 h-5 text-gray-600" />
                </div>
            </div>

            <div className="space-y-3 max-h-64 overflow-y-auto">
                {activities.map((activity) => (
                    <div key={activity.id} className="flex items-start gap-3 p-3 bg-gray-50 rounded-lg">
                        <div className="mt-0.5">{getStatusIcon(activity.status)}</div>
                        <div className="flex-1 min-w-0">
                            <p className="text-sm font-medium text-gray-900 truncate">{activity.action}</p>
                            <p className="text-xs text-gray-500 truncate">{activity.resource}</p>
                        </div>
                        <span className="text-xs text-gray-400 whitespace-nowrap">
                            {formatRelativeTime(activity.time)}
                        </span>
                    </div>
                ))}
            </div>
        </div>
    );
};

export default ActivityFeed;
