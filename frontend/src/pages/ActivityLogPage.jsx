import React, { useState, useEffect } from 'react';
import { History, RefreshCw, Server, AlertCircle } from 'lucide-react';
import LoadingSpinner from '../components/common/LoadingSpinner';
import EmptyState from '../components/common/EmptyState';
import api from '../services/api';

const ActivityLogPage = () => {
  const [activity, setActivity] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const loadActivity = async () => {
      setLoading(true);
      try {
        const data = await api.getRecentActivity();
        setActivity(data);
      } catch (error) {
        console.error('Failed to load activity:', error);
      } finally {
        setLoading(false);
      }
    };
    loadActivity();
  }, []);

  const icons = {
    switch: <RefreshCw size={20} className="text-blue-500" />,
    agent: <Server size={20} className="text-green-500" />,
    event: <AlertCircle size={20} className="text-yellow-500" />,
  };

  return (
    <div className="bg-white p-4 md:p-6 rounded-xl shadow-sm border border-gray-200">
      <h3 className="text-lg font-bold text-gray-900 mb-6">System Activity Log</h3>
      {loading ? (
        <div className="flex justify-center items-center h-64"><LoadingSpinner /></div>
      ) : activity.length === 0 ? (
        <EmptyState
          icon={<History size={48} />}
          title="No Activity"
          description="No recent system activity"
        />
      ) : (
        <div className="space-y-3">
          {activity.map(item => (
            <div key={item.id} className="flex items-start space-x-4 p-4 bg-gray-50 rounded-lg hover:bg-gray-100 transition-colors">
              <span className="flex-shrink-0 w-12 h-12 flex items-center justify-center bg-white rounded-lg shadow-sm border border-gray-200">
                {icons[item.type] || <AlertCircle size={20} className="text-gray-500" />}
              </span>
              <div className="flex-1 min-w-0">
                <p className="text-sm font-medium text-gray-900 break-words">{item.text}</p>
                <p className="text-xs text-gray-500 mt-1">{item.time}</p>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
};

export default ActivityLogPage;
