import React from 'react';

/**
 * Compact Audit History - Shows recent hibernation executions
 * Designed for dashboard sidebar, not full-page view
 */
const AuditHistory = () => {
  // Mock execution history - replace with real data from API
  const EXECUTION_HISTORY = [
    {
      id: 1,
      action: 'SLEEP',
      cluster: 'prod-cluster-1',
      time: '2h ago',
      detail: 'Scaled down 15 deployments, 3 statefulsets',
      duration: '45s',
      strategy: 'Namespace Sleep',
      status: 'success'
    },
    {
      id: 2,
      action: 'WAKE',
      cluster: 'dev-cluster-2',
      time: '5h ago',
      detail: 'Restored 8 deployments to normal scale',
      duration: '1m 20s',
      strategy: 'Namespace Sleep',
      status: 'success'
    },
    {
      id: 3,
      action: 'PRE-WARM',
      cluster: 'staging-cluster-1',
      time: '8h ago',
      detail: 'Pre-warmed 3 nodes for upcoming wake',
      duration: '2m 15s',
      strategy: 'Nuclear',
      status: 'success'
    },
    {
      id: 4,
      action: 'SLEEP',
      cluster: 'qa-cluster-1',
      time: '12h ago',
      detail: 'Hibernated cluster with snapshot',
      duration: '3m 45s',
      strategy: 'Snapshot & Restore',
      status: 'warning'
    },
    {
      id: 5,
      action: 'WAKE',
      cluster: 'prod-cluster-2',
      time: '1d ago',
      detail: 'Failed to restore deployment nginx',
      duration: '30s',
      strategy: 'Namespace Sleep',
      status: 'error'
    }
  ];

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
              className={`px-4 py-3 flex gap-2 ${
                i < EXECUTION_HISTORY.length - 1 ? 'border-b border-gray-100' : ''
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
