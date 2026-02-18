import React, { useState, useEffect } from 'react';
import { hibernationApi } from '../../services/hibernationApi';

/**
 * Emergency Controls - Panic button and manual overrides for hibernation
 * Allows immediate wake-up of all clusters or specific clusters
 */
const EmergencyControls = () => {
  const [schedules, setSchedules] = useState([]);
  const [clusters, setClusters] = useState([]);
  const [loading, setLoading] = useState(true);
  const [actionInProgress, setActionInProgress] = useState(null);
  const [panicMode, setPanicMode] = useState(false);
  const [confirmDialog, setConfirmDialog] = useState(null);

  useEffect(() => {
    loadData();
  }, []);

  const loadData = async () => {
    try {
      setLoading(true);
      // const [schedulesRes, clustersRes] = await Promise.all([
      //   hibernationApi.listSchedules(),
      //   clusterApi.listClusters()
      // ]);
      // setSchedules(schedulesRes.data.schedules || []);
      // setClusters(clustersRes.data || []);

      // Mock data
      setSchedules([
        {
          id: 1,
          name: 'Production Weekend Shutdown',
          is_active: 'Y',
          clusters: [
            { id: 1, name: 'prod-cluster-1', status: 'SLEEPING' },
            { id: 2, name: 'prod-cluster-2', status: 'AWAKE' }
          ]
        },
        {
          id: 2,
          name: 'Dev Nightly Shutdown',
          is_active: 'Y',
          clusters: [{ id: 3, name: 'dev-cluster-1', status: 'SLEEPING' }]
        }
      ]);

      setClusters([
        { id: 1, name: 'prod-cluster-1', region: 'us-east-1', status: 'SLEEPING' },
        { id: 2, name: 'prod-cluster-2', region: 'us-west-2', status: 'AWAKE' },
        { id: 3, name: 'dev-cluster-1', region: 'eu-west-1', status: 'SLEEPING' },
        { id: 4, name: 'staging-cluster-1', region: 'ap-south-1', status: 'AWAKE' }
      ]);
    } catch (error) {
      console.error('Failed to load data:', error);
    } finally {
      setLoading(false);
    }
  };

  const handlePanicButton = () => {
    setConfirmDialog({
      title: ' EMERGENCY WAKE ALL CLUSTERS',
      message: 'This will immediately wake ALL sleeping clusters and pause all active hibernation schedules. This action should only be used in emergencies.',
      confirmText: 'WAKE ALL CLUSTERS NOW',
      confirmStyle: 'bg-red-600 hover:bg-red-700',
      onConfirm: async () => {
        try {
          setActionInProgress('panic');
          setPanicMode(true);

          // await hibernationApi.emergencyWakeAll();
          console.log('PANIC: Waking all clusters...');

          setTimeout(() => {
            setActionInProgress(null);
            loadData();
            alert('All clusters have been woken up and all schedules paused!');
          }, 3000);
        } catch (error) {
          console.error('Panic wake failed:', error);
          setActionInProgress(null);
        }
      }
    });
  };

  const handleWakeCluster = (clusterId, clusterName) => {
    setConfirmDialog({
      title: `Wake ${clusterName}`,
      message: `This will immediately wake up ${clusterName} and restore all workloads. Any active hibernation schedules will be temporarily overridden.`,
      confirmText: 'Wake Cluster',
      confirmStyle: 'bg-green-600 hover:bg-green-700',
      onConfirm: async () => {
        try {
          setActionInProgress(`wake-${clusterId}`);

          // await hibernationApi.manualWake(clusterId);
          console.log(`Waking cluster ${clusterName}...`);

          setTimeout(() => {
            setActionInProgress(null);
            loadData();
            alert(`${clusterName} is now awake!`);
          }, 2000);
        } catch (error) {
          console.error('Wake failed:', error);
          setActionInProgress(null);
        }
      }
    });
  };

  const handleSleepCluster = (clusterId, clusterName) => {
    setConfirmDialog({
      title: `Sleep ${clusterName}`,
      message: `This will manually put ${clusterName} to sleep immediately, scaling down workloads. You can wake it up at any time.`,
      confirmText: 'Sleep Cluster',
      confirmStyle: 'bg-purple-600 hover:bg-purple-700',
      onConfirm: async () => {
        try {
          setActionInProgress(`sleep-${clusterId}`);

          // await hibernationApi.manualSleep(clusterId);
          console.log(`Sleeping cluster ${clusterName}...`);

          setTimeout(() => {
            setActionInProgress(null);
            loadData();
            alert(`${clusterName} is now sleeping!`);
          }, 2000);
        } catch (error) {
          console.error('Sleep failed:', error);
          setActionInProgress(null);
        }
      }
    });
  };

  const handlePauseSchedule = (scheduleId, scheduleName) => {
    setConfirmDialog({
      title: `Pause ${scheduleName}`,
      message: `This will temporarily pause ${scheduleName}. No hibernation actions will occur until you resume it.`,
      confirmText: 'Pause Schedule',
      confirmStyle: 'bg-yellow-600 hover:bg-yellow-700',
      onConfirm: async () => {
        try {
          // await hibernationApi.toggleSchedule(scheduleId, false);
          console.log(`Pausing schedule ${scheduleName}...`);
          loadData();
          alert(`${scheduleName} has been paused!`);
        } catch (error) {
          console.error('Pause failed:', error);
        }
      }
    });
  };

  const handleResumeSchedule = (scheduleId, scheduleName) => {
    setConfirmDialog({
      title: `Resume ${scheduleName}`,
      message: `This will resume ${scheduleName}. Hibernation actions will resume according to the schedule.`,
      confirmText: 'Resume Schedule',
      confirmStyle: 'bg-green-600 hover:bg-green-700',
      onConfirm: async () => {
        try {
          // await hibernationApi.toggleSchedule(scheduleId, true);
          console.log(`Resuming schedule ${scheduleName}...`);
          loadData();
          alert(`${scheduleName} has been resumed!`);
        } catch (error) {
          console.error('Resume failed:', error);
        }
      }
    });
  };

  const sleepingClusters = clusters.filter(c => c.status === 'SLEEPING');
  const activeSchedules = schedules.filter(s => s.is_active === 'Y');

  if (loading) {
    return (
      <div className="p-6">
        <div className="text-center py-12 text-gray-500">Loading emergency controls...</div>
      </div>
    );
  }

  return (
    <div className="p-6 space-y-6">
      {/* Header */}
      <div>
        <h1 className="text-3xl font-bold"> Emergency Controls</h1>
        <p className="text-gray-600 mt-1">Manual overrides and panic button for critical situations</p>
      </div>

      {/* Panic Mode Banner */}
      {panicMode && (
        <div className="bg-red-600 text-white rounded-lg shadow-lg p-6 animate-pulse">
          <div className="flex items-center space-x-4">
            <div className="text-5xl"></div>
            <div>
              <h2 className="text-2xl font-bold">PANIC MODE ACTIVE</h2>
              <p className="mt-1">All hibernation schedules are paused. All clusters are being woken up.</p>
            </div>
          </div>
        </div>
      )}

      {/* Panic Button */}
      <div className="bg-gradient-to-r from-red-500 to-red-600 text-white rounded-lg shadow-xl p-8">
        <div className="flex items-center justify-between">
          <div className="flex items-center space-x-6">
            <div className="text-7xl"></div>
            <div>
              <h2 className="text-3xl font-bold">EMERGENCY WAKE ALL</h2>
              <p className="text-lg mt-2 opacity-90">
                Immediately wake all sleeping clusters and pause all schedules
              </p>
              <div className="mt-3 flex items-center space-x-4 text-sm opacity-90">
                <span>• {sleepingClusters.length} clusters currently sleeping</span>
                <span>• {activeSchedules.length} active schedules</span>
              </div>
            </div>
          </div>

          <button
            onClick={handlePanicButton}
            disabled={actionInProgress === 'panic'}
            className={`px-8 py-6 bg-white text-red-600 rounded-lg font-bold text-xl shadow-lg hover:shadow-xl transition-all ${
              actionInProgress === 'panic' ? 'opacity-50 cursor-not-allowed' : 'hover:scale-105'
            }`}
          >
            {actionInProgress === 'panic' ? (
              <div className="flex items-center space-x-3">
                <div className="animate-spin rounded-full h-6 w-6 border-4 border-red-600 border-t-transparent"></div>
                <span>WAKING ALL...</span>
              </div>
            ) : (
              'WAKE ALL NOW'
            )}
          </button>
        </div>
      </div>

      {/* Manual Cluster Controls */}
      <div className="bg-white rounded-lg shadow">
        <div className="p-6 border-b">
          <h2 className="text-xl font-bold">🖥️ Manual Cluster Controls</h2>
          <p className="text-gray-600 mt-1">Wake or sleep individual clusters manually</p>
        </div>

        <div className="p-6 space-y-3">
          {clusters.map(cluster => (
            <div
              key={cluster.id}
              className="flex items-center justify-between p-4 border rounded-lg hover:bg-gray-50"
            >
              <div className="flex items-center space-x-4">
                <div
                  className={`w-3 h-3 rounded-full ${
                    cluster.status === 'SLEEPING' ? 'bg-purple-500' : 'bg-green-500'
                  } animate-pulse`}
                />
                <div>
                  <h3 className="font-bold">{cluster.name}</h3>
                  <p className="text-sm text-gray-600">{cluster.region}</p>
                </div>
                <span
                  className={`px-3 py-1 rounded-full text-sm font-medium ${
                    cluster.status === 'SLEEPING'
                      ? 'bg-purple-100 text-purple-800'
                      : 'bg-green-100 text-green-800'
                  }`}
                >
                  {cluster.status}
                </span>
              </div>

              <div className="flex space-x-2">
                {cluster.status === 'SLEEPING' ? (
                  <button
                    onClick={() => handleWakeCluster(cluster.id, cluster.name)}
                    disabled={actionInProgress === `wake-${cluster.id}`}
                    className="px-4 py-2 bg-green-600 text-white rounded hover:bg-green-700 disabled:opacity-50"
                  >
                    {actionInProgress === `wake-${cluster.id}` ? (
                      <span className="flex items-center space-x-2">
                        <div className="animate-spin rounded-full h-4 w-4 border-2 border-white border-t-transparent"></div>
                        <span>Waking...</span>
                      </span>
                    ) : (
                      '🟢 Wake Up'
                    )}
                  </button>
                ) : (
                  <button
                    onClick={() => handleSleepCluster(cluster.id, cluster.name)}
                    disabled={actionInProgress === `sleep-${cluster.id}`}
                    className="px-4 py-2 bg-purple-600 text-white rounded hover:bg-purple-700 disabled:opacity-50"
                  >
                    {actionInProgress === `sleep-${cluster.id}` ? (
                      <span className="flex items-center space-x-2">
                        <div className="animate-spin rounded-full h-4 w-4 border-2 border-white border-t-transparent"></div>
                        <span>Sleeping...</span>
                      </span>
                    ) : (
                      '💤 Sleep Now'
                    )}
                  </button>
                )}
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* Schedule Overrides */}
      <div className="bg-white rounded-lg shadow">
        <div className="p-6 border-b">
          <h2 className="text-xl font-bold"> Schedule Controls</h2>
          <p className="text-gray-600 mt-1">Pause or resume hibernation schedules</p>
        </div>

        <div className="p-6 space-y-3">
          {schedules.map(schedule => (
            <div
              key={schedule.id}
              className="flex items-center justify-between p-4 border rounded-lg hover:bg-gray-50"
            >
              <div>
                <h3 className="font-bold">{schedule.name}</h3>
                <p className="text-sm text-gray-600">
                  {schedule.clusters.length} clusters •{' '}
                  {schedule.is_active === 'Y' ? 'Active' : 'Paused'}
                </p>
              </div>

              {schedule.is_active === 'Y' ? (
                <button
                  onClick={() => handlePauseSchedule(schedule.id, schedule.name)}
                  className="px-4 py-2 bg-yellow-600 text-white rounded hover:bg-yellow-700"
                >
                  ⏸️ Pause Schedule
                </button>
              ) : (
                <button
                  onClick={() => handleResumeSchedule(schedule.id, schedule.name)}
                  className="px-4 py-2 bg-green-600 text-white rounded hover:bg-green-700"
                >
                  ▶️ Resume Schedule
                </button>
              )}
            </div>
          ))}
        </div>
      </div>

      {/* Safety Guidelines */}
      <div className="bg-blue-50 border border-blue-200 rounded-lg p-6">
        <h3 className="font-bold text-blue-900 mb-3"> Safety Guidelines</h3>
        <ul className="space-y-2 text-sm text-blue-800">
          <li className="flex items-start space-x-2">
            <span>•</span>
            <span>
              <strong>Panic Button:</strong> Use only in true emergencies (production down, critical issue).
              Waking all clusters can result in significant cost spikes.
            </span>
          </li>
          <li className="flex items-start space-x-2">
            <span>•</span>
            <span>
              <strong>Manual Wake:</strong> Waking a cluster bypasses schedules until next scheduled sleep.
              The cluster will resume normal hibernation cycle after that.
            </span>
          </li>
          <li className="flex items-start space-x-2">
            <span>•</span>
            <span>
              <strong>Manual Sleep:</strong> Immediately scales down workloads. Use during maintenance windows
              or off-hours to save costs.
            </span>
          </li>
          <li className="flex items-start space-x-2">
            <span>•</span>
            <span>
              <strong>Schedule Pause:</strong> Temporarily disables automated hibernation. Remember to resume
              when issue is resolved to maintain savings.
            </span>
          </li>
        </ul>
      </div>

      {/* Confirmation Dialog */}
      {confirmDialog && (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
          <div className="bg-white rounded-lg shadow-xl max-w-md w-full p-6">
            <h3 className="text-xl font-bold mb-3">{confirmDialog.title}</h3>
            <p className="text-gray-700 mb-6">{confirmDialog.message}</p>

            <div className="flex justify-end space-x-3">
              <button
                onClick={() => setConfirmDialog(null)}
                className="px-4 py-2 border border-gray-300 rounded hover:bg-gray-50"
              >
                Cancel
              </button>
              <button
                onClick={() => {
                  confirmDialog.onConfirm();
                  setConfirmDialog(null);
                }}
                className={`px-4 py-2 text-white rounded ${confirmDialog.confirmStyle}`}
              >
                {confirmDialog.confirmText}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default EmergencyControls;
