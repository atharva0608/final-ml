/**
 * Hibernation Schedule Grid Editor
 * 168-hour schedule matrix (7 days x 24 hours)
 * With triple-strategy selection (Namespace Sleep, Nuclear, Snapshot & Restore)
 */
import React, { useState, useEffect, useRef } from 'react';
import { hibernationAPI, metricAPI } from '../../services/api';
import { useClusterStore } from '../../store/useStore';
import { Card, Button, Input, Badge } from '../shared';
import { FiSave, FiRotateCcw, FiClock, FiSun, FiMoon, FiDollarSign, FiPlay, FiPower, FiZap, FiShield, FiChevronDown, FiChevronUp } from 'react-icons/fi';
import toast from 'react-hot-toast';

const DAYS = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday'];
const HOURS = Array.from({ length: 24 }, (_, i) => i);

const TIMEZONES = [
  'UTC', 'America/New_York', 'America/Chicago', 'America/Denver', 'America/Los_Angeles',
  'Europe/London', 'Europe/Paris', 'Asia/Tokyo', 'Asia/Shanghai', 'Australia/Sydney',
];

const STRATEGIES = [
  {
    value: 'NAMESPACE_SLEEP',
    label: 'Namespace Sleep',
    icon: FiMoon,
    color: 'blue',
    bgColor: 'bg-blue-50',
    borderColor: 'border-blue-500',
    textColor: 'text-blue-700',
    tagline: '~2 min wake | ~80% savings',
    description: 'Scales workloads to 0 replicas. Cluster Autoscaler drains idle nodes.',
    bestFor: 'Best for stateless dev/test',
    savingsMultiplier: 0.80,
  },
  {
    value: 'NUCLEAR',
    label: 'Nuclear',
    icon: FiZap,
    color: 'red',
    bgColor: 'bg-red-50',
    borderColor: 'border-red-500',
    textColor: 'text-red-700',
    tagline: '~8 min wake | ~99% savings',
    description: 'Scales all ASGs to 0. Maximum cost reduction.',
    bestFor: 'Best for non-critical environments',
    savingsMultiplier: 0.99,
  },
  {
    value: 'SNAPSHOT_RESTORE',
    label: 'Snapshot & Restore',
    icon: FiShield,
    color: 'green',
    bgColor: 'bg-green-50',
    borderColor: 'border-green-500',
    textColor: 'text-green-700',
    tagline: '~12 min wake | ~90% savings',
    description: 'Snapshots EBS volumes before shutdown. Preserves data with AZ affinity.',
    bestFor: 'Best for databases',
    savingsMultiplier: 0.90,
  },
];

const HibernationSchedule = ({ clusterId }) => {
  const { clusters } = useClusterStore();
  const [loading, setLoading] = useState(false);
  const [isPainting, setIsPainting] = useState(false);
  const [paintMode, setPaintMode] = useState(null);
  const [hourlyCost, setHourlyCost] = useState(0);
  const [showComparison, setShowComparison] = useState(false);

  const [formData, setFormData] = useState({
    cluster_id: clusterId || '',
    schedule_matrix: Array(168).fill(1),
    timezone: 'UTC',
    pre_warm_minutes: 15,
    is_active: true,
    strategy: 'NAMESPACE_SLEEP',
  });

  const [existingSchedule, setExistingSchedule] = useState(null);
  const [savings, setSavings] = useState(0);
  const gridRef = useRef(null);

  useEffect(() => {
    if (clusterId) {
      fetchScheduleForCluster(clusterId);
      fetchClusterCost(clusterId);
    }
  }, [clusterId]);

  useEffect(() => {
    calculateSavings();
  }, [formData.schedule_matrix, formData.strategy, hourlyCost]);

  const fetchClusterCost = async (clusterIdParam) => {
    try {
      const response = await metricAPI.getClusterMetrics(clusterIdParam);
      if (response.data) {
        const estimatedHourly = (response.data.total_instances || 0) * 0.12;
        setHourlyCost(estimatedHourly);
      }
    } catch (error) {
      console.warn('Failed to fetch hourly cost, using default', error);
      setHourlyCost(2.45);
    }
  };

  const fetchScheduleForCluster = async (clusterIdParam) => {
    setLoading(true);
    try {
      const response = await hibernationAPI.getByCluster(clusterIdParam);
      const schedules = response.data?.schedules || [];
      if (schedules.length > 0) {
        const schedule = schedules[0];
        setExistingSchedule(schedule);
        setFormData({
          cluster_id: schedule.cluster_id,
          schedule_matrix: schedule.schedule_matrix || Array(168).fill(1),
          timezone: schedule.timezone || 'UTC',
          pre_warm_minutes: schedule.pre_warm_minutes || 15,
          is_active: schedule.is_active ?? true,
          strategy: schedule.strategy || 'NAMESPACE_SLEEP',
        });
      }
    } catch (error) {
      if (error.response?.status !== 404) {
        toast.error('Failed to load schedule');
      }
    } finally {
      setLoading(false);
    }
  };

  const calculateSavings = () => {
    const sleepHours = formData.schedule_matrix.filter(h => h === 0).length;
    const strategyConfig = STRATEGIES.find(s => s.value === formData.strategy) || STRATEGIES[0];
    const monthlySavings = (sleepHours / 168) * (hourlyCost * 24 * 30) * strategyConfig.savingsMultiplier;
    setSavings(monthlySavings);
  };

  const handleSave = async (e) => {
    e.preventDefault();

    if (formData.schedule_matrix.length !== 168) {
      toast.error('Schedule matrix must have exactly 168 elements');
      return;
    }

    try {
      const schedulePayload = { ...formData };

      if (existingSchedule) {
        await hibernationAPI.update(existingSchedule.id, schedulePayload);
        toast.success('Schedule updated successfully');
      } else {
        await hibernationAPI.create(schedulePayload);
        toast.success('Schedule created successfully');
      }

      fetchScheduleForCluster(formData.cluster_id);
    } catch (error) {
      toast.error(error.response?.data?.message || 'Failed to save schedule');
    }
  };

  const handleToggleActive = async () => {
    if (!existingSchedule) {
      toast.error('Please save the schedule first');
      return;
    }

    try {
      await hibernationAPI.toggle(existingSchedule.id);
      toast.success(`Schedule ${existingSchedule.is_active ? 'deactivated' : 'activated'}`);
      fetchScheduleForCluster(formData.cluster_id);
    } catch (error) {
      toast.error('Failed to toggle schedule');
    }
  };

  const handleWakeUpNow = async () => {
    if (!existingSchedule) return;
    try {
      await hibernationAPI.override(existingSchedule.id, { action: 'WAKE', duration_minutes: 120 });
      toast.success('Cluster wake-up queued');
    } catch (error) {
      toast.error('Failed to wake cluster');
    }
  };

  const handleSleepNow = async () => {
    if (!existingSchedule) return;
    try {
      await hibernationAPI.override(existingSchedule.id, { action: 'SLEEP' });
      toast.success('Cluster sleep queued');
    } catch (error) {
      toast.error('Failed to sleep cluster');
    }
  };

  // Grid cell interaction handlers
  const handleCellMouseDown = (dayIndex, hourIndex) => {
    const index = dayIndex * 24 + hourIndex;
    const newValue = formData.schedule_matrix[index] === 1 ? 0 : 1;
    setPaintMode(newValue === 1 ? 'awake' : 'sleep');
    setIsPainting(true);
    updateCell(dayIndex, hourIndex, newValue);
  };

  const handleCellMouseEnter = (dayIndex, hourIndex) => {
    if (isPainting && paintMode !== null) {
      const newValue = paintMode === 'awake' ? 1 : 0;
      updateCell(dayIndex, hourIndex, newValue);
    }
  };

  const handleMouseUp = () => {
    setIsPainting(false);
    setPaintMode(null);
  };

  const updateCell = (dayIndex, hourIndex, value) => {
    const index = dayIndex * 24 + hourIndex;
    const newMatrix = [...formData.schedule_matrix];
    newMatrix[index] = value;
    setFormData({ ...formData, schedule_matrix: newMatrix });
  };

  const setAllAwake = () => {
    setFormData({ ...formData, schedule_matrix: Array(168).fill(1) });
    toast.success('All hours set to awake');
  };

  const setAllSleep = () => {
    setFormData({ ...formData, schedule_matrix: Array(168).fill(0) });
    toast.success('All hours set to sleep');
  };

  const setBusinessHours = () => {
    const matrix = Array(168).fill(0);
    for (let day = 0; day < 5; day++) {
      for (let hour = 9; hour < 17; hour++) {
        matrix[day * 24 + hour] = 1;
      }
    }
    setFormData({ ...formData, schedule_matrix: matrix });
    toast.success('Business hours preset applied');
  };

  const set24x7 = () => {
    setFormData({ ...formData, schedule_matrix: Array(168).fill(1) });
    toast.success('24/7 uptime preset applied');
  };

  useEffect(() => {
    document.addEventListener('mouseup', handleMouseUp);
    return () => {
      document.removeEventListener('mouseup', handleMouseUp);
    };
  }, []);

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-600"></div>
      </div>
    );
  }

  const selectedStrategy = STRATEGIES.find(s => s.value === formData.strategy) || STRATEGIES[0];

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex justify-between items-center">
        <div>
          <h1 className="text-3xl font-bold text-gray-900">Hibernation Schedule</h1>
          <p className="text-gray-600 mt-1">Configure when clusters should sleep to save costs</p>
        </div>
        <div className="flex gap-2">
          {existingSchedule && (
            <>
              <Button
                variant="outline"
                icon={<FiMoon />}
                onClick={handleSleepNow}
                title="Put cluster to sleep immediately"
              >
                Sleep Now
              </Button>
              <Button
                variant="outline"
                icon={<FiPlay />}
                onClick={handleWakeUpNow}
                title="Wake up cluster for 2 hours immediately"
              >
                Wake Up Now
              </Button>
              <Button
                variant={existingSchedule.is_active ? 'primary' : 'secondary'}
                icon={<FiPower />}
                onClick={handleToggleActive}
              >
                {existingSchedule.is_active ? 'Active' : 'Inactive'}
              </Button>
            </>
          )}
        </div>
      </div>

      <form onSubmit={handleSave}>
        {/* Configuration Section */}
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6 mb-6">
          <Card className="lg:col-span-2">
            <div className="space-y-4">
              {!clusterId && (
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">Cluster</label>
                  <select
                    value={formData.cluster_id}
                    onChange={(e) => {
                      setFormData({ ...formData, cluster_id: e.target.value });
                      if (e.target.value) fetchScheduleForCluster(e.target.value);
                    }}
                    className="w-full px-4 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500"
                    required
                  >
                    <option value="">Select a cluster</option>
                    {clusters.map((cluster) => (
                      <option key={cluster.id} value={cluster.id}>{cluster.name} - {cluster.region}</option>
                    ))}
                  </select>
                </div>
              )}

              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">Timezone</label>
                  <select
                    value={formData.timezone}
                    onChange={(e) => setFormData({ ...formData, timezone: e.target.value })}
                    className="w-full px-4 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500"
                  >
                    {TIMEZONES.map((tz) => <option key={tz} value={tz}>{tz}</option>)}
                  </select>
                </div>
                <Input
                  label="Pre-warm Minutes"
                  type="number"
                  value={formData.pre_warm_minutes}
                  onChange={(e) => setFormData({ ...formData, pre_warm_minutes: parseInt(e.target.value) })}
                  min="0" max="60" required
                />
              </div>

              <div>
                <label className="block text-sm font-medium text-gray-700 mb-2">Presets</label>
                <div className="flex gap-2 flex-wrap">
                  <Button type="button" variant="outline" size="sm" onClick={set24x7}>24/7 Uptime</Button>
                  <Button type="button" variant="outline" size="sm" onClick={setBusinessHours}>Business Hours</Button>
                  <Button type="button" variant="outline" size="sm" onClick={setAllAwake}>All Awake</Button>
                  <Button type="button" variant="outline" size="sm" onClick={setAllSleep}>All Sleep</Button>
                </div>
              </div>
            </div>
          </Card>

          <Card className="bg-gradient-to-br from-green-50 to-white flex flex-col justify-center">
            <div className="text-center">
              <div className="p-3 bg-green-100 rounded-full w-12 h-12 flex items-center justify-center mx-auto mb-3 text-green-600">
                <FiDollarSign className="w-6 h-6" />
              </div>
              <h3 className="text-lg font-medium text-gray-900">Estimated Monthly Savings</h3>
              <p className="text-3xl font-bold text-green-600 mt-2">
                ${savings.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
              </p>
              <p className="text-sm text-gray-500 mt-1">
                {selectedStrategy.label} strategy ({Math.round(selectedStrategy.savingsMultiplier * 100)}% efficiency)
              </p>
            </div>
          </Card>
        </div>

        {/* Strategy Selection Cards */}
        <div className="mb-6">
          <h3 className="text-lg font-semibold text-gray-900 mb-3">Hibernation Strategy</h3>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            {STRATEGIES.map((strategy) => {
              const Icon = strategy.icon;
              const isSelected = formData.strategy === strategy.value;
              return (
                <div
                  key={strategy.value}
                  onClick={() => setFormData({ ...formData, strategy: strategy.value })}
                  className={`relative cursor-pointer rounded-lg border-2 p-4 transition-all ${
                    isSelected
                      ? `${strategy.borderColor} ${strategy.bgColor} shadow-md`
                      : 'border-gray-200 bg-white hover:border-gray-300 hover:shadow-sm'
                  }`}
                >
                  {isSelected && (
                    <div className={`absolute top-2 right-2 w-5 h-5 rounded-full ${strategy.borderColor.replace('border', 'bg')} flex items-center justify-center`}>
                      <svg className="w-3 h-3 text-white" fill="currentColor" viewBox="0 0 20 20">
                        <path fillRule="evenodd" d="M16.707 5.293a1 1 0 010 1.414l-8 8a1 1 0 01-1.414 0l-4-4a1 1 0 011.414-1.414L8 12.586l7.293-7.293a1 1 0 011.414 0z" clipRule="evenodd" />
                      </svg>
                    </div>
                  )}
                  <div className="flex items-center gap-3 mb-2">
                    <div className={`p-2 rounded-lg ${isSelected ? strategy.bgColor : 'bg-gray-100'}`}>
                      <Icon className={`w-5 h-5 ${isSelected ? strategy.textColor : 'text-gray-500'}`} />
                    </div>
                    <div>
                      <h4 className={`font-semibold ${isSelected ? strategy.textColor : 'text-gray-900'}`}>
                        {strategy.label}
                      </h4>
                      <p className="text-xs text-gray-500">{strategy.tagline}</p>
                    </div>
                  </div>
                  <p className="text-sm text-gray-600">{strategy.description}</p>
                  <p className={`text-xs mt-2 font-medium ${isSelected ? strategy.textColor : 'text-gray-400'}`}>
                    {strategy.bestFor}
                  </p>
                </div>
              );
            })}
          </div>

          {/* Collapsible Comparison Table */}
          <button
            type="button"
            onClick={() => setShowComparison(!showComparison)}
            className="mt-3 flex items-center gap-1 text-sm text-gray-500 hover:text-gray-700 transition-colors"
          >
            {showComparison ? <FiChevronUp /> : <FiChevronDown />}
            {showComparison ? 'Hide' : 'Show'} strategy comparison
          </button>

          {showComparison && (
            <div className="mt-2 overflow-hidden rounded-lg border border-gray-200">
              <table className="min-w-full divide-y divide-gray-200 text-sm">
                <thead className="bg-gray-50">
                  <tr>
                    <th className="px-4 py-2 text-left font-medium text-gray-500">Strategy</th>
                    <th className="px-4 py-2 text-center font-medium text-gray-500">Wake Time</th>
                    <th className="px-4 py-2 text-center font-medium text-gray-500">Savings</th>
                    <th className="px-4 py-2 text-center font-medium text-gray-500">Safety</th>
                    <th className="px-4 py-2 text-left font-medium text-gray-500">Best For</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-100 bg-white">
                  {STRATEGIES.map(s => (
                    <tr key={s.value} className={formData.strategy === s.value ? s.bgColor : ''}>
                      <td className="px-4 py-2 font-medium text-gray-900">{s.label}</td>
                      <td className="px-4 py-2 text-center text-gray-600">{s.tagline.split('|')[0].trim()}</td>
                      <td className="px-4 py-2 text-center text-gray-600">{Math.round(s.savingsMultiplier * 100)}%</td>
                      <td className="px-4 py-2 text-center">
                        <span className={`inline-block px-2 py-0.5 rounded text-xs font-medium ${
                          s.value === 'NUCLEAR' ? 'bg-yellow-100 text-yellow-700' : 'bg-green-100 text-green-700'
                        }`}>
                          {s.value === 'NUCLEAR' ? 'Medium' : 'High'}
                        </span>
                      </td>
                      <td className="px-4 py-2 text-gray-600">{s.bestFor}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>

        {/* Schedule Grid */}
        <Card>
          <div className="mb-4 flex items-center justify-between">
            <div>
              <h3 className="text-lg font-semibold text-gray-900">Weekly Schedule Grid</h3>
              <p className="text-sm text-gray-600 mt-1">
                Click or drag to paint. <FiSun className="inline w-4 h-4 text-green-600" /> Awake |{' '}
                <FiMoon className="inline w-4 h-4 text-gray-400" /> Sleep
              </p>
            </div>
            <div className="flex gap-4 text-sm">
              <div className="flex items-center gap-1"><div className="w-3 h-3 bg-green-500 rounded"></div> Awake</div>
              <div className="flex items-center gap-1"><div className="w-3 h-3 bg-gray-200 rounded"></div> Sleep</div>
            </div>
          </div>

          <div className="overflow-x-auto select-none" ref={gridRef}>
            <div className="inline-block min-w-full">
              <div className="flex">
                <div className="w-24 flex-shrink-0"></div>
                {HOURS.map(hour => (
                  <div key={hour} className="w-8 h-8 flex items-center justify-center text-xs font-medium text-gray-500 border-b">
                    {hour}
                  </div>
                ))}
              </div>

              {DAYS.map((day, dayIndex) => (
                <div key={day} className="flex">
                  <div className="w-24 h-8 flex items-center justify-start pr-2 text-sm font-medium text-gray-700 flex-shrink-0">
                    {day}
                  </div>
                  {HOURS.map(hour => {
                    const index = dayIndex * 24 + hour;
                    const isAwake = formData.schedule_matrix[index] === 1;
                    return (
                      <div
                        key={hour}
                        onMouseDown={() => handleCellMouseDown(dayIndex, hour)}
                        onMouseEnter={() => handleCellMouseEnter(dayIndex, hour)}
                        className={`w-8 h-8 border border-white cursor-pointer transition-colors ${isAwake ? 'bg-green-500 hover:bg-green-600' : 'bg-gray-200 hover:bg-gray-300'
                          }`}
                        title={`${day} ${hour}:00 - ${isAwake ? 'Awake' : 'Sleep'}`}
                      />
                    );
                  })}
                </div>
              ))}
            </div>
          </div>

          <div className="flex justify-end pt-4 border-t mt-6">
            <Button type="submit" variant="primary" icon={<FiSave />}>
              {existingSchedule ? 'Update Schedule' : 'Create Schedule'}
            </Button>
          </div>
        </Card>
      </form>
    </div>
  );
};

export default HibernationSchedule;
