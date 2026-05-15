import React, { useState, useEffect } from 'react';
import { auditAPI } from '../../../services/api';

/**
 * Execution History & Logs - Shows timeline of hibernation actions
 */
const ExecutionHistory = ({ scheduleId = null, limit = 50 }) => {
  const [history, setHistory] = useState([]);
  const [loading, setLoading] = useState(true);
  const [filter, setFilter] = useState('all'); // all | sleep | wake | error
  const [timeRange, setTimeRange] = useState('7d'); // 24h | 7d | 30d | all

  useEffect(() => {
    loadHistory();
    // Refresh every 30 seconds
    const interval = setInterval(loadHistory, 30000);
    return () => clearInterval(interval);
  }, [scheduleId, timeRange]);

  const loadHistory = async () => {
    try {
      setLoading(true);

      // Fetch real audit logs for hibernation events
      const response = await auditAPI.list({
        resource_type: 'HIBERNATION',
        limit: limit,
        event: scheduleId ? undefined : undefined // Can filter by specific events if needed
      });

      // Transform audit logs to history format
      const logs = response.data || [];
      const transformedHistory = logs.map(log => ({
        id: log.id,
        schedule_id: log.resource || 'manual',
        schedule_name: log.metadata?.schedule_name || log.resource || 'Manual Action',
        cluster_name: log.metadata?.cluster_name || 'Unknown',
        action: log.event.includes('sleep') ? 'SLEEP' : log.event.includes('wake') ? 'WAKE' : 'PREWARM',
        status: log.outcome === 'success' ? 'SUCCESS' : log.outcome === 'failure' ? 'ERROR' : 'IN_PROGRESS',
        started_at: log.timestamp,
        completed_at: log.metadata?.completed_at || log.timestamp,
        duration_seconds: log.metadata?.duration_seconds || 0,
        resources_affected: log.metadata?.resources_affected || { deployments: 0, statefulsets: 0, nodes: 0 },
        cost_saved: log.metadata?.cost_saved || 0,
        error_message: log.metadata?.error_message || null
      }));

      setHistory(transformedHistory);
    } catch (error) {
      console.error('Failed to load execution history:', error);
      // Fallback to empty array on error
      setHistory([]);
    } finally {
      setLoading(false);
    }
  };

  const getActionBadge = (action) => {
    const badges = {
      SLEEP: { icon: '💤', color: 'bg-purple-100 text-purple-800', label: 'Sleep' },
      WAKE: { icon: '🟢', color: 'bg-green-100 text-green-800', label: 'Wake' },
      PREWARM: { icon: '', color: 'bg-orange-100 text-orange-800', label: 'Pre-warm' },
      ERROR: { icon: '', color: 'bg-red-100 text-red-800', label: 'Error' }
    };
    return badges[action] || badges.SLEEP;
  };

  const getStatusBadge = (status) => {
    const badges = {
      SUCCESS: { icon: '✓', color: 'bg-green-100 text-green-800', label: 'Success' },
      ERROR: { icon: '✗', color: 'bg-red-100 text-red-800', label: 'Error' },
      IN_PROGRESS: { icon: '⏳', color: 'bg-blue-100 text-blue-800', label: 'In Progress' },
      PARTIAL: { icon: '⚠', color: 'bg-yellow-100 text-yellow-800', label: 'Partial' }
    };
    return badges[status] || badges.SUCCESS;
  };

  const formatDuration = (seconds) => {
    if (seconds < 60) return `${seconds}s`;
    const minutes = Math.floor(seconds / 60);
    const secs = seconds % 60;
    return `${minutes}m ${secs}s`;
  };

  const formatTimestamp = (timestamp) => {
    const date = new Date(timestamp);
    const now = new Date();
    const diffMs = now - date;
    const diffMins = Math.floor(diffMs / 60000);
    const diffHours = Math.floor(diffMs / 3600000);
    const diffDays = Math.floor(diffMs / 86400000);

    if (diffMins < 1) return 'Just now';
    if (diffMins < 60) return `${diffMins}m ago`;
    if (diffHours < 24) return `${diffHours}h ago`;
    if (diffDays < 7) return `${diffDays}d ago`;

    return date.toLocaleDateString() + ' ' + date.toLocaleTimeString();
  };

  const filteredHistory = history.filter(entry => {
    if (filter === 'all') return true;
    if (filter === 'error') return entry.status === 'ERROR';
    return entry.action === filter.toUpperCase();
  });

  const totalCostSaved = history
    .filter(h => h.status === 'SUCCESS')
    .reduce((sum, h) => sum + (h.cost_saved || 0), 0);

  if (loading) {
    return (
      <div className="bg-white rounded-lg shadow p-6">
        <div className="text-center py-8 text-gray-500">Loading execution history...</div>
      </div>
    );
  }

  return (
    <div className="bg-white rounded-lg shadow">
      {/* Header */}
      <div className="p-6 border-b">
        <div className="flex justify-between items-center">
          <div>
            <h2 className="text-2xl font-bold"> Execution History</h2>
            <p className="text-gray-600 mt-1">Timeline of all hibernation actions</p>
          </div>

          {/* Stats */}
          <div className="flex space-x-6">
            <div className="text-center">
              <div className="text-2xl font-bold text-purple-600">{history.length}</div>
              <div className="text-sm text-gray-600">Total Actions</div>
            </div>
            <div className="text-center">
              <div className="text-2xl font-bold text-green-600">
                ${totalCostSaved.toFixed(2)}
              </div>
              <div className="text-sm text-gray-600">Saved</div>
            </div>
            <div className="text-center">
              <div className="text-2xl font-bold text-red-600">
                {history.filter(h => h.status === 'ERROR').length}
              </div>
              <div className="text-sm text-gray-600">Errors</div>
            </div>
          </div>
        </div>

        {/* Filters */}
        <div className="mt-4 flex space-x-4">
          <div className="flex space-x-2">
            <button
              onClick={() => setFilter('all')}
              className={`px-3 py-1 rounded text-sm ${
                filter === 'all'
                  ? 'bg-blue-600 text-white'
                  : 'bg-gray-200 text-gray-700 hover:bg-gray-300'
              }`}
            >
              All
            </button>
            <button
              onClick={() => setFilter('sleep')}
              className={`px-3 py-1 rounded text-sm ${
                filter === 'sleep'
                  ? 'bg-blue-600 text-white'
                  : 'bg-gray-200 text-gray-700 hover:bg-gray-300'
              }`}
            >
              💤 Sleep
            </button>
            <button
              onClick={() => setFilter('wake')}
              className={`px-3 py-1 rounded text-sm ${
                filter === 'wake'
                  ? 'bg-blue-600 text-white'
                  : 'bg-gray-200 text-gray-700 hover:bg-gray-300'
              }`}
            >
              🟢 Wake
            </button>
            <button
              onClick={() => setFilter('error')}
              className={`px-3 py-1 rounded text-sm ${
                filter === 'error'
                  ? 'bg-blue-600 text-white'
                  : 'bg-gray-200 text-gray-700 hover:bg-gray-300'
              }`}
            >
               Errors
            </button>
          </div>

          <div className="flex space-x-2 ml-auto">
            {['24h', '7d', '30d', 'all'].map(range => (
              <button
                key={range}
                onClick={() => setTimeRange(range)}
                className={`px-3 py-1 rounded text-sm ${
                  timeRange === range
                    ? 'bg-gray-700 text-white'
                    : 'bg-gray-200 text-gray-700 hover:bg-gray-300'
                }`}
              >
                {range === 'all' ? 'All Time' : `Last ${range}`}
              </button>
            ))}
          </div>
        </div>
      </div>

      {/* History Timeline */}
      <div className="p-6">
        {filteredHistory.length === 0 ? (
          <div className="text-center py-12 text-gray-500">
            <div className="text-5xl mb-4">📭</div>
            <p className="text-lg font-medium">No execution history</p>
            <p className="text-sm">Actions will appear here once schedules execute</p>
          </div>
        ) : (
          <div className="space-y-4">
            {filteredHistory.map((entry, index) => {
              const actionBadge = getActionBadge(entry.action);
              const statusBadge = getStatusBadge(entry.status);

              return (
                <div
                  key={entry.id}
                  className={`border-l-4 rounded-lg p-4 ${
                    entry.status === 'ERROR'
                      ? 'border-red-500 bg-red-50'
                      : entry.status === 'SUCCESS'
                      ? 'border-green-500 bg-white'
                      : 'border-blue-500 bg-blue-50'
                  } hover:shadow-md transition-shadow`}
                >
                  <div className="flex justify-between items-start">
                    {/* Left: Action & Details */}
                    <div className="flex-1">
                      <div className="flex items-center space-x-3 mb-2">
                        <span className={`px-3 py-1 rounded font-medium ${actionBadge.color}`}>
                          {actionBadge.icon} {actionBadge.label}
                        </span>
                        <span className={`px-3 py-1 rounded text-sm ${statusBadge.color}`}>
                          {statusBadge.icon} {statusBadge.label}
                        </span>
                        <span className="text-sm text-gray-600">
                          {formatTimestamp(entry.started_at)}
                        </span>
                      </div>

                      <div className="text-sm space-y-1">
                        <div className="font-medium">{entry.schedule_name}</div>
                        <div className="text-gray-700">
                          Cluster: <span className="font-mono">{entry.cluster_name}</span>
                        </div>

                        {entry.resources_affected && (
                          <div className="text-gray-600">
                            Affected:
                            {entry.resources_affected.deployments > 0 && (
                              <span className="ml-2">{entry.resources_affected.deployments} deployments</span>
                            )}
                            {entry.resources_affected.statefulsets > 0 && (
                              <span className="ml-2">{entry.resources_affected.statefulsets} statefulsets</span>
                            )}
                            {entry.resources_affected.nodes > 0 && (
                              <span className="ml-2">{entry.resources_affected.nodes} nodes</span>
                            )}
                          </div>
                        )}

                        {entry.error_message && (
                          <div className="text-red-700 bg-red-100 p-2 rounded mt-2">
                            <strong>Error:</strong> {entry.error_message}
                          </div>
                        )}
                      </div>
                    </div>

                    {/* Right: Metrics */}
                    <div className="text-right space-y-1">
                      <div className="text-xs text-gray-600">Duration</div>
                      <div className="text-lg font-bold text-gray-800">
                        {formatDuration(entry.duration_seconds)}
                      </div>

                      {entry.cost_saved > 0 && (
                        <>
                          <div className="text-xs text-gray-600 mt-2">Saved</div>
                          <div className="text-lg font-bold text-green-600">
                            ${entry.cost_saved.toFixed(2)}
                          </div>
                        </>
                      )}
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>

      {/* Footer */}
      <div className="p-4 bg-gray-50 border-t text-center text-sm text-gray-600">
        Showing {filteredHistory.length} of {history.length} actions
      </div>
    </div>
  );
};

export default ExecutionHistory;
