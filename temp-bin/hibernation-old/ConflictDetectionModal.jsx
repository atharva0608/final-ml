import React from 'react';

/**
 * Conflict Detection Modal - Shows schedule conflicts before creation
 * Helps prevent multiple schedules controlling same cluster at same time
 */
const ConflictDetectionModal = ({ isOpen, onClose, conflicts, onConfirm }) => {
  if (!isOpen || !conflicts || conflicts.length === 0) return null;

  const getSeverityBadge = (severity) => {
    const badges = {
      CRITICAL: {
        color: 'bg-red-100 text-red-800 border-red-300',
        icon: '',
        label: 'Critical'
      },
      WARNING: {
        color: 'bg-yellow-100 text-yellow-800 border-yellow-300',
        icon: '',
        label: 'Warning'
      },
      INFO: {
        color: 'bg-blue-100 text-blue-800 border-blue-300',
        icon: '',
        label: 'Info'
      }
    };
    return badges[severity] || badges.WARNING;
  };

  const getConflictTypeName = (type) => {
    const types = {
      OVERLAPPING_SLEEP: 'Overlapping Sleep Schedules',
      OVERLAPPING_WAKE: 'Overlapping Wake Schedules',
      RAPID_TRANSITIONS: 'Too Frequent Sleep/Wake Cycles',
      CLUSTER_OVERLOAD: 'Too Many Schedules on Same Cluster'
    };
    return types[type] || type;
  };

  const hasCriticalConflicts = conflicts.some(c => c.severity === 'CRITICAL');

  return (
    <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
      <div className="bg-white rounded-lg shadow-xl w-full max-w-3xl max-h-[90vh] overflow-y-auto">
        {/* Header */}
        <div className={`p-6 border-b ${hasCriticalConflicts ? 'bg-red-50' : 'bg-yellow-50'}`}>
          <div className="flex justify-between items-start">
            <div>
              <h2 className="text-2xl font-bold flex items-center space-x-2">
                {hasCriticalConflicts ? (
                  <>
                    <span></span>
                    <span className="text-red-700">Schedule Conflicts Detected</span>
                  </>
                ) : (
                  <>
                    <span></span>
                    <span className="text-yellow-700">Potential Schedule Conflicts</span>
                  </>
                )}
              </h2>
              <p className="text-gray-700 mt-2">
                {hasCriticalConflicts
                  ? 'Critical conflicts must be resolved before proceeding'
                  : 'Review these potential conflicts before creating the schedule'}
              </p>
            </div>
            <button
              onClick={() => onClose()}
              className="text-gray-500 hover:text-gray-700 text-2xl"
            >
              ✕
            </button>
          </div>
        </div>

        {/* Conflicts List */}
        <div className="p-6 space-y-4">
          {conflicts.map((conflict, index) => {
            const badge = getSeverityBadge(conflict.severity);

            return (
              <div
                key={index}
                className={`border-2 rounded-lg p-4 ${badge.color}`}
              >
                {/* Conflict Header */}
                <div className="flex items-start justify-between mb-3">
                  <div className="flex items-center space-x-3">
                    <span className="text-3xl">{badge.icon}</span>
                    <div>
                      <h3 className="font-bold text-lg">
                        {getConflictTypeName(conflict.type)}
                      </h3>
                      <span className={`text-xs px-2 py-1 rounded ${badge.color} font-medium`}>
                        {badge.label}
                      </span>
                    </div>
                  </div>
                </div>

                {/* Conflict Details */}
                <div className="space-y-2 text-sm">
                  {conflict.description && (
                    <p className="font-medium">{conflict.description}</p>
                  )}

                  {/* Affected Clusters */}
                  {conflict.clusters && conflict.clusters.length > 0 && (
                    <div>
                      <strong>Affected Clusters:</strong>
                      <ul className="list-disc list-inside ml-4">
                        {conflict.clusters.map((cluster, i) => (
                          <li key={i}>{cluster}</li>
                        ))}
                      </ul>
                    </div>
                  )}

                  {/* Conflicting Schedules */}
                  {conflict.existing_schedules && conflict.existing_schedules.length > 0 && (
                    <div>
                      <strong>Conflicting With:</strong>
                      <ul className="list-disc list-inside ml-4">
                        {conflict.existing_schedules.map((schedule, i) => (
                          <li key={i}>
                            <span className="font-mono">{schedule.name}</span>
                            {schedule.timezone && (
                              <span className="text-xs ml-2">({schedule.timezone})</span>
                            )}
                          </li>
                        ))}
                      </ul>
                    </div>
                  )}

                  {/* Time Windows */}
                  {conflict.time_windows && conflict.time_windows.length > 0 && (
                    <div>
                      <strong>Overlapping Time Windows:</strong>
                      <ul className="list-disc list-inside ml-4">
                        {conflict.time_windows.map((window, i) => (
                          <li key={i} className="font-mono text-xs">
                            {window.day} {window.start_hour}:00 - {window.end_hour}:00
                          </li>
                        ))}
                      </ul>
                    </div>
                  )}

                  {/* Recommendation */}
                  {conflict.recommendation && (
                    <div className="mt-3 p-3 bg-white bg-opacity-60 rounded">
                      <strong> Recommendation:</strong>
                      <p className="mt-1">{conflict.recommendation}</p>
                    </div>
                  )}
                </div>
              </div>
            );
          })}
        </div>

        {/* Summary Stats */}
        <div className="px-6 pb-4">
          <div className="bg-gray-100 rounded-lg p-4 grid grid-cols-3 gap-4 text-center">
            <div>
              <div className="text-2xl font-bold text-red-600">
                {conflicts.filter(c => c.severity === 'CRITICAL').length}
              </div>
              <div className="text-sm text-gray-600">Critical</div>
            </div>
            <div>
              <div className="text-2xl font-bold text-yellow-600">
                {conflicts.filter(c => c.severity === 'WARNING').length}
              </div>
              <div className="text-sm text-gray-600">Warnings</div>
            </div>
            <div>
              <div className="text-2xl font-bold text-blue-600">
                {conflicts.filter(c => c.severity === 'INFO').length}
              </div>
              <div className="text-sm text-gray-600">Info</div>
            </div>
          </div>
        </div>

        {/* Footer Actions */}
        <div className="p-6 border-t bg-gray-50 flex justify-between">
          <button
            onClick={() => onClose()}
            className="px-6 py-2 border border-gray-300 rounded-lg hover:bg-gray-100"
          >
            Cancel
          </button>

          <div className="space-x-2">
            <button
              onClick={() => onClose()}
              className="px-6 py-2 bg-blue-100 text-blue-800 rounded-lg hover:bg-blue-200"
            >
              Edit Schedule
            </button>

            {!hasCriticalConflicts && (
              <button
                onClick={() => {
                  onConfirm();
                  onClose();
                }}
                className="px-6 py-2 bg-yellow-600 text-white rounded-lg hover:bg-yellow-700"
              >
                 Proceed Anyway
              </button>
            )}

            {hasCriticalConflicts && (
              <div className="inline-block px-6 py-2 bg-gray-300 text-gray-600 rounded-lg cursor-not-allowed">
                Cannot Proceed (Critical Conflicts)
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
};

/**
 * Example conflicts structure:
 *
 * [
 *   {
 *     type: 'OVERLAPPING_SLEEP',
 *     severity: 'CRITICAL',
 *     description: 'Two schedules are trying to sleep the same cluster at overlapping times',
 *     clusters: ['prod-cluster-1', 'prod-cluster-2'],
 *     existing_schedules: [
 *       { name: 'Weekend Shutdown', timezone: 'UTC' }
 *     ],
 *     time_windows: [
 *       { day: 'Saturday', start_hour: 0, end_hour: 24 }
 *     ],
 *     recommendation: 'Combine these schedules or adjust time windows to avoid overlap'
 *   }
 * ]
 */

export default ConflictDetectionModal;
