/**
 * Activity Feed Widget
 * Shows recent actions and events
 */
import React from 'react';
import { FiClock, FiCheck, FiX, FiAlertCircle } from 'react-icons/fi';
import { formatRelativeTime } from '../../../utils/formatters';

const ActivityFeed = ({ data = {}, widgetKey }) => {
    // Use real activity data from API, no fake fallback
    const activities = data.activities || [];
    const hasData = activities && activities.length > 0;

    const getStatusIcon = (status) => {
        switch (status) {
            case 'success': return <FiCheck className="w-4 h-4 text-green-500" />;
            case 'failed': return <FiX className="w-4 h-4 text-red-500" />;
            case 'error': return <FiX className="w-4 h-4 text-red-500" />;
            case 'pending': return <FiAlertCircle className="w-4 h-4 text-amber-500" />;
            case 'info': return <FiAlertCircle className="w-4 h-4 text-blue-500" />;
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
                {hasData ? (
                    activities.map((activity) => (
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
                    ))
                ) : (
                    <div className="flex flex-col items-center justify-center py-8 text-gray-400">
                        <FiClock className="w-10 h-10 mb-2" />
                        <p className="text-sm font-medium">No recent activity</p>
                        <p className="text-xs mt-1">Actions will appear here once you start managing resources</p>
                    </div>
                )}
            </div>
        </div>
    );
};

export default ActivityFeed;
