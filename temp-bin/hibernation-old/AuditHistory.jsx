import React, { useState, useEffect } from 'react';
import { auditAPI } from '../../services/api';

/**
 * Compact Audit History - Shows recent hibernation executions
 * Designed for dashboard sidebar, not full-page view
 */
const AuditHistory = () => {
  const [executionHistory, setExecutionHistory] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    loadHistory();
    // Refresh every 30 seconds
    const interval = setInterval(loadHistory, 30000);
    return () => clearInterval(interval);
  }, []);

  const loadHistory = async () => {
    try {
      const response = await auditAPI.list({
        resource_type: 'HIBERNATION',
        limit: 5
      });

      const logs = response.data?.logs || response.data || [];
      const transformed = (Array.isArray(logs) ? logs : []).map(log => ({
        id: log.id,
        action: log.event.includes('sleep') ? 'SLEEP' : log.event.includes('wake') ? 'WAKE' : 'PRE-WARM',
        cluster: log.metadata?.cluster_name || 'Unknown',
        time: formatTimestamp(log.timestamp),
        detail: log.metadata?.detail || log.event,
        duration: formatDuration(log.metadata?.duration_seconds || 0),
        strategy: log.metadata?.strategy?.replace('_', ' ') || 'Unknown',
        status: log.outcome === 'success' ? 'success' : log.outcome === 'failure' ? 'error' : 'warning'
      }));

      setExecutionHistory(transformed);
    } catch (error) {
      console.error('Failed to load audit history:', error);
    } finally {
      setLoading(false);
    }
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
    return `${diffDays}d ago`;
  };

  const formatDuration = (seconds) => {
    if (seconds < 60) return `${seconds}s`;
    const mins = Math.floor(seconds / 60);
    const secs = seconds % 60;
    return `${mins}m ${secs}s`;
  };

  const EXECUTION_HISTORY = executionHistory;

  const actionColors = {
    SLEEP: { text: '#6366f1', bg: '#eef2ff' },
    WAKE: { text: '#22c55e', bg: '#f0fdf4' },
    'PRE-WARM': { text: '#f59e0b', bg: '#fffbeb' }
  };

  const statusDots = {
    success: '#22c55e',
    warning: '#f59e0b',
    error: '#ef4444'
  };

  if (loading) {
    return (
      <div className="bg-white border border-gray-200 rounded-xl">
        <div className="px-5 py-4 border-b border-gray-200">
          <span className="text-sm font-bold text-gray-900">Execution History</span>
        </div>
        <div className="p-6 text-center text-gray-500">Loading...</div>
      </div>
    );
  }

  return (
    <div className="bg-white border border-gray-200 rounded-xl">
      {/* Header */}
      <div className="px-5 py-4 border-b border-gray-200 flex justify-between items-center">
        <span className="text-sm font-bold text-gray-900">Execution History</span>
        <button className="text-xs font-semibold text-indigo-600 hover:text-indigo-700 transition-colors px-2 py-1">
          View All
        </button>
      </div>

      {/* History Items */}
      <div>
        {EXECUTION_HISTORY.map((h, i) => {
          const actionColor = actionColors[h.action] || { text: '#64748b', bg: '#f1f5f9' };
          return (
            <div
              key={h.id}
              className={`px-4 py-3 flex gap-2 ${i < EXECUTION_HISTORY.length - 1 ? 'border-b border-gray-100' : ''
                }`}
            >
              {/* Status Dot */}
              <div
                className="w-2 h-2 rounded-full mt-1.5 flex-shrink-0"
                style={{
                  backgroundColor: statusDots[h.status],
                  boxShadow: `0 0 0 3px ${statusDots[h.status]}22`
                }}
              />

              {/* Content */}
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2 mb-0.5">
                  <span
                    className="text-xs font-bold px-2 py-0.5 rounded"
                    style={{
                      color: actionColor.text,
                      backgroundColor: actionColor.bg
                    }}
                  >
                    {h.action}
                  </span>
                  <span className="text-xs font-semibold text-gray-900 truncate">
                    {h.cluster}
                  </span>
                  <span className="text-xs text-gray-400 ml-auto flex-shrink-0">
                    {h.time}
                  </span>
                </div>
                <div className="text-xs text-gray-600">{h.detail}</div>
                <div className="text-xs text-gray-400 mt-0.5">
                  {h.duration} · {h.strategy}
                </div>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
};

export default AuditHistory;
