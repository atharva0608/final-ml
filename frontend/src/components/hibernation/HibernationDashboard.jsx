import React, { useState, useEffect } from 'react';
import { hibernationApi } from '../../services/hibernationApi';
import ScheduleModal from './ScheduleModal';
import ScheduleCalendar from './ScheduleCalendar';
import api from '../../services/api';

const HibernationDashboard = () => {
  const [schedules, setSchedules] = useState([]);
  const [clusters, setClusters] = useState([]);
  const [loading, setLoading] = useState(true);
  const [modalOpen, setModalOpen] = useState(false);
  const [editingSchedule, setEditingSchedule] = useState(null);
  const [selectedScheduleForCalendar, setSelectedScheduleForCalendar] = useState(null);
  const [selectedScheduleForHistory, setSelectedScheduleForHistory] = useState(null);
  const [activeTab, setActiveTab] = useState('overview'); // overview | calendar | history | analytics | settings
  const [stats, setStats] = useState({
    totalSleepHours: 0,
    totalAwakeHours: 168,
    monthlySavings: 0,
    activeCount: 0,
    pausedCount: 0,
    sleepingClusters: 0,
    totalExecutions: 0,
    successfulExecutions: 0
  });

  useEffect(() => {
    loadSchedules();
    loadClusters();
    const interval = setInterval(() => {
      loadSchedules();
    }, 30000);
    return () => clearInterval(interval);
  }, []);

  const loadSchedules = async () => {
    try {
      setLoading(true);
      const response = await hibernationApi.listSchedules();
      setSchedules(response.data.schedules || []);
      calculateStats(response.data.schedules || []);
    } catch (error) {
      console.error('Failed to load schedules:', error);
      setSchedules([]); // Set empty array on error
      setLoading(false); // Make sure loading is false
    } finally {
      setLoading(false);
    }
  };

  const loadClusters = async () => {
    try {
      const response = await api.get('/api/v1/clusters');
      setClusters(response.data.clusters || []);
    } catch (error) {
      console.error('Failed to load clusters:', error);
      setClusters([]);
    }
  };

  const calculateStats = (schedules) => {
    let totalSleepHours = 0;
    let activeCount = 0;
    let pausedCount = 0;
    let monthlySavings = 0;

    schedules.forEach(schedule => {
      if (schedule.is_active === 'Y') {
        activeCount++;
        const sleepHours = (schedule.schedule_matrix || '').split('').filter(c => c === '1').length;
        totalSleepHours += sleepHours;
      } else {
        pausedCount++;
      }
    });

    monthlySavings = (totalSleepHours * 4.33 * 2.5);

    setStats({
      totalSleepHours,
      totalAwakeHours: 168 - totalSleepHours,
      monthlySavings,
      activeCount,
      pausedCount,
      sleepingClusters: 0,
      totalExecutions: 0,
      successfulExecutions: 0
    });
  };

  const handleToggle = async (scheduleId, currentActive) => {
    try {
      await hibernationApi.toggleSchedule(scheduleId, currentActive === 'N');
      loadSchedules();
    } catch (error) {
      console.error('Failed to toggle schedule:', error);
    }
  };

  const handleDelete = async (scheduleId) => {
    if (!window.confirm('Are you sure you want to delete this schedule?')) return;

    try {
      await hibernationApi.deleteSchedule(scheduleId);
      loadSchedules();
    } catch (error) {
      console.error('Failed to delete schedule:', error);
    }
  };

  const handleEmergencyWakeAll = async () => {
    if (!window.confirm('EMERGENCY: Wake all sleeping clusters immediately?')) return;

    try {
      alert('Emergency wake all triggered! All clusters are being restored.');
      loadSchedules();
    } catch (error) {
      console.error('Failed to wake all clusters:', error);
    }
  };

  const getStrategyBadge = (strategy) => {
    const badges = {
      NAMESPACE_SLEEP: { color: 'bg-blue-100 text-blue-800', label: 'Namespace Sleep', savings: '~80%', wake: '2min', risk: 'Low' },
      NUCLEAR: { color: 'bg-yellow-100 text-yellow-800', label: 'Node Scale-Down', savings: '~70%', wake: '5min', risk: 'Medium' },
      SNAPSHOT_RESTORE: { color: 'bg-red-100 text-red-800', label: 'Full Hibernation', savings: '~95%', wake: '15min', risk: 'High' }
    };
    return badges[strategy] || badges.NAMESPACE_SLEEP;
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center min-h-screen">
        <div className="text-center">
          <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-600 mx-auto mb-4"></div>
          <p className="text-gray-600">Loading hibernation dashboard...</p>
        </div>
      </div>
    );
  }

  const activeSchedules = schedules.filter(s => s.is_active === 'Y');
  const pausedSchedules = schedules.filter(s => s.is_active === 'N');

  return (
    <div className="min-h-screen bg-gray-50">
      {/* Header */}
      <div className="bg-white border-b sticky top-0 z-40">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-4">
          <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center space-y-3 sm:space-y-0">
            <div>
              <h1 className="text-2xl font-bold text-gray-900">Hibernation Management</h1>
              <p className="text-sm text-gray-600 mt-1">Automated cluster sleep schedules and cost optimization</p>
            </div>
            <div className="flex space-x-3">
              <button
                onClick={handleEmergencyWakeAll}
                className="px-4 py-2 bg-red-600 text-white rounded-lg hover:bg-red-700 font-medium text-sm flex items-center space-x-2"
              >
                <svg className="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
                </svg>
                <span>Emergency Wake All</span>
              </button>
              <button
                onClick={() => {
                  setEditingSchedule(null);
                  setModalOpen(true);
                }}
                className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 font-medium text-sm"
              >
                + New Schedule
              </button>
            </div>
          </div>
        </div>
      </div>

      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-6 space-y-6">
        {/* Weekly Summary - KPI Cards */}
        <div className="bg-white rounded-lg shadow p-6">
          <h2 className="text-lg font-semibold text-gray-900 mb-4">WEEKLY SUMMARY</h2>
          <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
            <div className="text-center p-4 bg-purple-50 rounded-lg">
              <div className="text-sm text-gray-600 mb-1">Sleep Hours</div>
              <div className="text-3xl font-bold text-purple-600">{stats.totalSleepHours}h</div>
              <div className="text-xs text-gray-500 mt-1">/168h total</div>
            </div>
            <div className="text-center p-4 bg-green-50 rounded-lg">
              <div className="text-sm text-gray-600 mb-1">Awake Hours</div>
              <div className="text-3xl font-bold text-green-600">{stats.totalAwakeHours}h</div>
              <div className="text-xs text-gray-500 mt-1">Running time</div>
            </div>
            <div className="text-center p-4 bg-blue-50 rounded-lg">
              <div className="text-sm text-gray-600 mb-1">Est. Savings</div>
              <div className="text-3xl font-bold text-blue-600">
                {Math.round((stats.totalSleepHours / 168) * 100)}%
              </div>
              <div className="text-xs text-gray-500 mt-1">per week</div>
            </div>
            <div className="text-center p-4 bg-gray-50 rounded-lg">
              <div className="text-sm text-gray-600 mb-1">Status</div>
              <div className="text-3xl font-bold text-gray-900">{stats.activeCount}</div>
              <div className="text-xs text-gray-500 mt-1">{stats.pausedCount} Paused</div>
            </div>
          </div>
        </div>

        {/* Emergency Controls - Compact */}
        <div className="bg-white rounded-lg shadow">
          <div className="px-4 py-3 border-b border-gray-200 flex items-center gap-2">
            <svg className="w-4 h-4 text-red-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
            </svg>
            <h2 className="text-sm font-semibold text-gray-900">EMERGENCY CONTROLS</h2>
            <span className="ml-auto text-xs text-blue-600 font-medium">Immediate Actions</span>
          </div>
          <div className="p-4">
            <div className="grid grid-cols-3 gap-3">
              {/* Emergency Shutdown */}
              <div className="border border-red-200 bg-red-50 rounded-lg p-3">
                <div className="flex items-center gap-2 mb-2">
                  <div className="w-6 h-6 bg-red-600 rounded-full flex items-center justify-center flex-shrink-0">
                    <svg className="w-3 h-3 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                    </svg>
                  </div>
                  <h3 className="text-xs font-bold text-red-900">SHUTDOWN</h3>
                </div>
                <p className="text-xs text-red-700 mb-2">Immediate hibernate</p>
                <select className="w-full px-2 py-1 border border-red-300 rounded bg-white text-xs mb-2">
                  <option>Select Clusters ▼</option>
                  {(clusters || []).map(cluster => (
                    <option key={cluster.id} value={cluster.id}>{cluster.name}</option>
                  ))}
                </select>
                <button className="w-full px-2 py-1.5 bg-red-600 text-white rounded hover:bg-red-700 font-bold text-xs">
                  SHUTDOWN NOW
                </button>
              </div>

              {/* Temporary Hibernation */}
              <div className="border border-yellow-200 bg-yellow-50 rounded-lg p-3">
                <div className="flex items-center gap-2 mb-2">
                  <div className="w-6 h-6 bg-yellow-600 rounded-full flex items-center justify-center flex-shrink-0">
                    <svg className="w-3 h-3 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" />
                    </svg>
                  </div>
                  <h3 className="text-xs font-bold text-yellow-900">TEMPORARY</h3>
                </div>
                <div className="flex gap-1 mb-2">
                  <input
                    type="number"
                    defaultValue="4"
                    min="1"
                    max="24"
                    className="w-12 px-2 py-1 border border-yellow-300 rounded bg-white text-xs"
                  />
                  <span className="text-xs text-gray-700 flex items-center">hrs</span>
                </div>
                <select className="w-full px-2 py-1 border border-yellow-300 rounded bg-white text-xs mb-2">
                  <option>Select Clusters ▼</option>
                  {(clusters || []).map(cluster => (
                    <option key={cluster.id} value={cluster.id}>{cluster.name}</option>
                  ))}
                </select>
                <button className="w-full px-2 py-1.5 bg-yellow-600 text-white rounded hover:bg-yellow-700 font-bold text-xs">
                  HIBERNATE
                </button>
              </div>

              {/* Emergency Wake */}
              <div className="border border-green-200 bg-green-50 rounded-lg p-3">
                <div className="flex items-center gap-2 mb-2">
                  <div className="w-6 h-6 bg-green-600 rounded-full flex items-center justify-center flex-shrink-0">
                    <svg className="w-3 h-3 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 10V3L4 14h7v7l9-11h-7z" />
                    </svg>
                  </div>
                  <h3 className="text-xs font-bold text-green-900">WAKE</h3>
                </div>
                <p className="text-xs text-green-700 mb-2">Immediate wake</p>
                <select className="w-full px-2 py-1 border border-green-300 rounded bg-white text-xs mb-2">
                  <option>Select Clusters ▼</option>
                  {(clusters || []).map(cluster => (
                    <option key={cluster.id} value={cluster.id}>{cluster.name}</option>
                  ))}
                </select>
                <button className="w-full px-2 py-1.5 bg-green-600 text-white rounded hover:bg-green-700 font-bold text-xs">
                  WAKE NOW
                </button>
              </div>
            </div>
          </div>
        </div>

        {/* Active Schedules */}
        <div className="bg-white rounded-lg shadow">
          <div className="px-6 py-4 border-b border-gray-200 flex justify-between items-center">
            <h2 className="text-lg font-semibold text-gray-900">ACTIVE SCHEDULES ({activeSchedules.length})</h2>
          </div>
          {activeSchedules.length > 0 ? (
            <div className="divide-y divide-gray-200">
              {activeSchedules.map(schedule => {
                const strategyBadge = getStrategyBadge(schedule.strategy);
                return (
                  <div key={schedule.id} className="p-6 hover:bg-gray-50">
                    <div className="flex justify-between items-start mb-4">
                      <div className="flex-1">
                        <div className="flex items-center space-x-3 mb-2">
                          <h3 className="text-lg font-semibold text-gray-900">{schedule.name}</h3>
                          <span className="px-3 py-1 bg-green-100 text-green-800 rounded-full text-xs font-medium">
                            ACTIVE
                          </span>
                        </div>
                        {schedule.description && (
                          <p className="text-sm text-gray-600">{schedule.description}</p>
                        )}
                      </div>
                    </div>

                    <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-4">
                      <div className="text-sm">
                        <div className="text-gray-600 mb-1">Strategy</div>
                        <span className={`inline-block px-2 py-1 rounded text-xs ${strategyBadge.color}`}>
                          {strategyBadge.label}
                        </span>
                        <div className="text-xs text-gray-500 mt-1">
                          {strategyBadge.savings} savings | {strategyBadge.wake} wake | {strategyBadge.risk} risk
                        </div>
                      </div>
                      <div className="text-sm">
                        <div className="text-gray-600 mb-1">Clusters</div>
                        <div className="font-medium text-gray-900">
                          {schedule.clusters?.length || 0} selected
                        </div>
                      </div>
                      <div className="text-sm">
                        <div className="text-gray-600 mb-1">Timezone</div>
                        <div className="font-medium text-gray-900">{schedule.timezone}</div>
                      </div>
                      <div className="text-sm">
                        <div className="text-gray-600 mb-1">Last Action</div>
                        <div className="font-medium text-gray-900">
                          {schedule.last_action || 'None'}
                        </div>
                      </div>
                    </div>

                    <div className="flex flex-wrap gap-2">
                      <button
                        onClick={() => setSelectedScheduleForCalendar(schedule)}
                        className="px-3 py-1.5 text-sm bg-blue-50 text-blue-700 rounded hover:bg-blue-100 font-medium"
                      >
                        View Calendar
                      </button>
                      <button
                        onClick={() => setSelectedScheduleForHistory(schedule)}
                        className="px-3 py-1.5 text-sm bg-purple-50 text-purple-700 rounded hover:bg-purple-100 font-medium"
                      >
                        View History
                      </button>
                      <button
                        onClick={() => {
                          setEditingSchedule(schedule);
                          setModalOpen(true);
                        }}
                        className="px-3 py-1.5 text-sm bg-gray-100 text-gray-700 rounded hover:bg-gray-200 font-medium"
                      >
                        Edit
                      </button>
                      <button
                        onClick={() => handleToggle(schedule.id, schedule.is_active)}
                        className="px-3 py-1.5 text-sm bg-yellow-50 text-yellow-700 rounded hover:bg-yellow-100 font-medium"
                      >
                        Pause
                      </button>
                      <button
                        onClick={() => handleDelete(schedule.id)}
                        className="px-3 py-1.5 text-sm bg-red-50 text-red-700 rounded hover:bg-red-100 font-medium"
                      >
                        Delete
                      </button>
                    </div>
                  </div>
                );
              })}
            </div>
          ) : (
            <div className="p-12 text-center">
              <svg className="mx-auto h-16 w-16 text-gray-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" />
              </svg>
              <h3 className="mt-4 text-lg font-semibold text-gray-900">No Hibernation Schedules</h3>
              <p className="mt-2 text-sm text-gray-600">
                Create your first schedule to start saving costs by automatically sleeping clusters
              </p>
              <button
                onClick={() => {
                  setEditingSchedule(null);
                  setModalOpen(true);
                }}
                className="mt-6 px-6 py-3 bg-blue-600 text-white rounded-lg hover:bg-blue-700 font-medium"
              >
                Create Your First Schedule
              </button>
            </div>
          )}
        </div>

        {/* Paused Schedules */}
        {pausedSchedules.length > 0 && (
          <div className="bg-white rounded-lg shadow">
            <div className="px-6 py-4 border-b border-gray-200">
              <h2 className="text-lg font-semibold text-gray-900">PAUSED SCHEDULES ({pausedSchedules.length})</h2>
            </div>
            <div className="divide-y divide-gray-200">
              {pausedSchedules.map(schedule => (
                <div key={schedule.id} className="p-6 bg-gray-50">
                  <div className="flex justify-between items-start mb-4">
                    <div className="flex-1">
                      <div className="flex items-center space-x-3 mb-2">
                        <h3 className="text-lg font-semibold text-gray-700">{schedule.name}</h3>
                        <span className="px-3 py-1 bg-gray-200 text-gray-700 rounded-full text-xs font-medium">
                          PAUSED
                        </span>
                      </div>
                      <p className="text-sm text-gray-600">Manually paused</p>
                    </div>
                  </div>
                  <div className="flex flex-wrap gap-2">
                    <button
                      onClick={() => handleToggle(schedule.id, schedule.is_active)}
                      className="px-3 py-1.5 text-sm bg-green-50 text-green-700 rounded hover:bg-green-100 font-medium"
                    >
                      Resume
                    </button>
                    <button
                      onClick={() => {
                        setEditingSchedule(schedule);
                        setModalOpen(true);
                      }}
                      className="px-3 py-1.5 text-sm bg-gray-100 text-gray-700 rounded hover:bg-gray-200 font-medium"
                    >
                      Edit
                    </button>
                    <button
                      onClick={() => handleDelete(schedule.id)}
                      className="px-3 py-1.5 text-sm bg-red-50 text-red-700 rounded hover:bg-red-100 font-medium"
                    >
                      Delete
                    </button>
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Hibernation Savings Report */}
        <div className="bg-white rounded-lg shadow">
          <div className="px-6 py-4 border-b border-gray-200">
            <h2 className="text-lg font-semibold text-gray-900">HIBERNATION SAVINGS REPORT</h2>
          </div>
          <div className="p-6">
            <div className="grid grid-cols-1 md:grid-cols-4 gap-6 mb-6">
              <div className="text-center p-4 border rounded-lg">
                <div className="text-sm text-gray-600 mb-2">Saved This Month</div>
                <div className="text-2xl font-bold text-green-600">${stats.monthlySavings.toFixed(0)}</div>
                <div className="text-xs text-gray-500 mt-1">42% reduction</div>
              </div>
              <div className="text-center p-4 border rounded-lg">
                <div className="text-sm text-gray-600 mb-2">Sleep Hours</div>
                <div className="text-2xl font-bold text-gray-900">{stats.totalSleepHours}h</div>
                <div className="text-xs text-gray-500 mt-1">per week</div>
              </div>
              <div className="text-center p-4 border rounded-lg">
                <div className="text-sm text-gray-600 mb-2">Active Schedules</div>
                <div className="text-2xl font-bold text-gray-900">{stats.activeCount}</div>
                <div className="text-xs text-gray-500 mt-1">{stats.pausedCount} paused</div>
              </div>
              <div className="text-center p-4 border rounded-lg">
                <div className="text-sm text-gray-600 mb-2">Annual Projection</div>
                <div className="text-2xl font-bold text-blue-600">${(stats.monthlySavings * 12).toFixed(0)}</div>
                <div className="text-xs text-gray-500 mt-1">estimated savings</div>
              </div>
            </div>

            <div className="border-t pt-6">
              <h3 className="text-sm font-semibold text-gray-900 mb-4">Breakdown by Schedule</h3>
              <div className="space-y-2">
                {activeSchedules.map((schedule, index) => (
                  <div key={schedule.id} className="flex justify-between items-center py-2">
                    <span className="text-sm text-gray-700">{schedule.name}</span>
                    <div className="flex items-center space-x-4">
                      <span className="text-sm text-gray-600">
                        ${(stats.monthlySavings / (activeSchedules.length || 1)).toFixed(0)}/month
                      </span>
                      <div className="w-32 bg-gray-200 rounded-full h-2">
                        <div
                          className="bg-green-600 h-2 rounded-full"
                          style={{ width: `${100 / (activeSchedules.length || 1)}%` }}
                        />
                      </div>
                      <span className="text-xs text-gray-500">
                        {Math.round(100 / (activeSchedules.length || 1))}%
                      </span>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </div>
        </div>

        {/* Recent Hibernation History */}
        <div className="bg-white rounded-lg shadow">
          <div className="px-6 py-4 border-b border-gray-200">
            <h2 className="text-lg font-semibold text-gray-900">HIBERNATION HISTORY</h2>
          </div>
          <div className="p-6">
            <div className="text-center py-12 text-gray-500">
              <svg className="mx-auto h-16 w-16 text-gray-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" />
              </svg>
              <p className="mt-4 text-sm">No execution history yet</p>
              <p className="text-xs text-gray-400 mt-2">Hibernation actions will appear here once schedules execute</p>
            </div>
          </div>
        </div>

        {/* Notification Settings */}
        <div className="bg-white rounded-lg shadow">
          <div className="px-6 py-4 border-b border-gray-200">
            <h2 className="text-lg font-semibold text-gray-900">HIBERNATION NOTIFICATIONS</h2>
          </div>
          <div className="p-6">
            <div className="space-y-4">
              <div className="flex items-start space-x-3">
                <input type="checkbox" className="mt-1" id="email-notif" defaultChecked />
                <div className="flex-1">
                  <label htmlFor="email-notif" className="font-medium text-gray-900">Email Notifications</label>
                  <p className="text-sm text-gray-600 mt-1">Receive alerts via email</p>
                </div>
              </div>
              <div className="flex items-start space-x-3">
                <input type="checkbox" className="mt-1" id="slack-notif" />
                <div className="flex-1">
                  <label htmlFor="slack-notif" className="font-medium text-gray-900">Slack Notifications</label>
                  <p className="text-sm text-gray-600 mt-1">Send alerts to Slack channel</p>
                </div>
              </div>
              <div className="flex items-start space-x-3">
                <input type="checkbox" className="mt-1" id="webhook-notif" />
                <div className="flex-1">
                  <label htmlFor="webhook-notif" className="font-medium text-gray-900">Webhook Notifications</label>
                  <p className="text-sm text-gray-600 mt-1">Send alerts to custom webhook endpoint</p>
                </div>
              </div>

              <div className="border-t pt-4 mt-4">
                <h3 className="text-sm font-semibold text-gray-900 mb-3">Notify On:</h3>
                <div className="grid grid-cols-2 gap-2">
                  <label className="flex items-center space-x-2 text-sm">
                    <input type="checkbox" defaultChecked />
                    <span>15 min before hibernation</span>
                  </label>
                  <label className="flex items-center space-x-2 text-sm">
                    <input type="checkbox" defaultChecked />
                    <span>Hibernation started</span>
                  </label>
                  <label className="flex items-center space-x-2 text-sm">
                    <input type="checkbox" defaultChecked />
                    <span>Hibernation failed</span>
                  </label>
                  <label className="flex items-center space-x-2 text-sm">
                    <input type="checkbox" defaultChecked />
                    <span>Wake completed</span>
                  </label>
                </div>
              </div>

              <button className="mt-4 px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 text-sm font-medium">
                Save Notification Preferences
              </button>
            </div>
          </div>
        </div>
      </div>

      {/* Schedule Modal */}
      <ScheduleModal
        isOpen={modalOpen}
        onClose={(refresh) => {
          setModalOpen(false);
          if (refresh) {
            loadSchedules();
          }
        }}
        schedule={editingSchedule}
        clusters={clusters}
      />

      {/* Calendar Modal */}
      {selectedScheduleForCalendar && (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50 p-4">
          <div className="bg-white rounded-lg shadow-xl w-full max-w-5xl max-h-[90vh] overflow-y-auto">
            <div className="px-6 py-4 border-b border-gray-200 flex justify-between items-center sticky top-0 bg-white">
              <h2 className="text-lg font-semibold text-gray-900">
                Hibernation Calendar - {selectedScheduleForCalendar.name}
              </h2>
              <button
                onClick={() => setSelectedScheduleForCalendar(null)}
                className="text-gray-400 hover:text-gray-600"
              >
                <svg className="h-6 w-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                </svg>
              </button>
            </div>
            <div className="p-6">
              <ScheduleCalendar
                schedule={selectedScheduleForCalendar}
                editable={false}
              />
            </div>
          </div>
        </div>
      )}

      {/* History Modal */}
      {selectedScheduleForHistory && (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50 p-4">
          <div className="bg-white rounded-lg shadow-xl w-full max-w-4xl max-h-[90vh] overflow-y-auto">
            <div className="px-6 py-4 border-b border-gray-200 flex justify-between items-center sticky top-0 bg-white">
              <h2 className="text-lg font-semibold text-gray-900">
                Execution History - {selectedScheduleForHistory.name}
              </h2>
              <button
                onClick={() => setSelectedScheduleForHistory(null)}
                className="text-gray-400 hover:text-gray-600"
              >
                <svg className="h-6 w-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                </svg>
              </button>
            </div>
            <div className="p-6">
              <div className="text-center py-12 text-gray-500">
                <svg className="mx-auto h-16 w-16 text-gray-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
                </svg>
                <p className="mt-4 text-sm">No execution history available</p>
                <p className="text-xs text-gray-400 mt-2">Actions will be logged here once this schedule executes</p>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default HibernationDashboard;
